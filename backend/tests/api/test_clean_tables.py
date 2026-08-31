"""The truncation fixture, checked against the one shape it can silently miss.

`clean_tables` is test infrastructure, so when it is wrong nothing reports it
here. It surfaces as an assertion inside whichever test happens to run second,
reading as a bug in that test.
"""

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from conftest import all_tables

pytestmark = pytest.mark.asyncio


def isolated_tables():
    """Modeled tables that no `TRUNCATE ... CASCADE` can reach.

    CASCADE propagates from a truncated table to tables holding a foreign key
    INTO it, so a table with no outbound foreign key is emptied only if it is
    named. That is the only shape a hand-written list can silently miss:
    `stored_secrets` was missing from the list for months and truncated anyway
    through `user_id -> users`, so a check built around it would pass with the
    defect present and prove nothing.
    """
    from app.db.models import Base

    return [t for t in Base.metadata.sorted_tables if not any(t.foreign_keys)]


def sample(column):
    """A value that satisfies the column, not a meaningful one."""
    if enums := getattr(column.type, "enums", None):
        return enums[0]
    try:
        python_type = column.type.python_type
    except NotImplementedError:  # CITEXT and friends do not declare one
        python_type = str
    if python_type is uuid.UUID:
        return uuid.uuid4()
    if python_type is datetime:
        return datetime.now(UTC)
    if python_type is bool:
        return False
    if python_type is int:
        return 1
    if python_type is float:
        return 1.0
    return f"clean-tables-{uuid.uuid4().hex}"


def a_row(table) -> dict:
    return {
        c.name: sample(c)
        for c in table.columns
        if not c.nullable and c.default is None and c.server_default is None
    }


async def test_every_isolated_table_is_emptied_between_tests(db_session):
    """Plant a row in each unreachable table, run the real truncate, expect zero.

    Deliberately empirical. Comparing the truncate's table list against
    `Base.metadata` would be a list diffed against a list, which is how the
    hand-written list looked correct while `area_fills` leaked.
    """
    tables = isolated_tables()
    assert tables, "no isolated tables found; this check would pass vacuously"

    for table in tables:
        await db_session.execute(sa.insert(table).values(a_row(table)))
    await db_session.commit()

    planted = {
        t.name: await db_session.scalar(sa.select(sa.func.count()).select_from(t))
        for t in tables
    }
    assert all(n == 1 for n in planted.values()), planted

    # Those counts opened a read transaction on this session. TRUNCATE takes
    # ACCESS EXCLUSIVE and runs on a different connection, so it would block
    # behind it forever rather than fail. Release it before truncating.
    await db_session.rollback()

    import app.db.engine as db

    async with db.engine.begin() as conn:
        await conn.execute(sa.text(f"truncate {all_tables()} cascade"))

    leaked = {}
    async with db.engine.connect() as conn:
        for table in tables:
            count = await conn.scalar(sa.select(sa.func.count()).select_from(table))
            if count:
                leaked[table.name] = count
    assert not leaked, f"rows survived the truncate and will leak into the next test: {leaked}"

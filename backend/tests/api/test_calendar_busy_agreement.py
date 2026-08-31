"""The read-side busy predicate has three spellings. They must agree.

`is_busy(row)` for callers holding rows, `busy_clause()` for the ORM, and
`BUSY_SQL` for textual SQL - three because the three consumers read in three
different ways, not because the rule is three rules. This file is what stops
them drifting, which matters more than usual here: the calendar research closes
by saying the busy rule eventually becomes a *user preference*.

The last test ties the two halves together, `classify` at write time and
`is_busy` at read time, so a change to one that contradicts the other fails.
"""

import pytest
import sqlalchemy as sa

from app.db.models import CalendarEvent
from app.services.calendar.busy import BUSY_SQL, busy_clause, classify, is_busy

pytestmark = pytest.mark.asyncio


async def _source(session, user):
    return (
        await session.execute(
            sa.text(
                "insert into connected_sources (user_id, kind) "
                "values (:u, 'google_calendar') returning source_id"
            ),
            {"u": user.user_id},
        )
    ).scalar_one()


async def _event(session, user, source_id, external_id, busy):
    await session.execute(
        sa.text(
            "insert into calendar_events "
            "(user_id, source_id, external_id, title, starts_at, ends_at, "
            " content_hash, busy) values "
            "(:u, :s, :e, :e, now(), now(), :e, :b)"
        ),
        {"u": user.user_id, "s": source_id, "e": external_id, "b": busy},
    )


async def _all_three(session):
    """The busy set as each spelling sees it."""
    via_orm = set(
        (await session.execute(sa.select(CalendarEvent.external_id).where(busy_clause())))
        .scalars()
        .all()
    )
    via_text = set(
        (
            await session.execute(
                sa.text(f"select external_id from calendar_events where {BUSY_SQL}")
            )
        )
        .scalars()
        .all()
    )
    rows = (await session.execute(sa.select(CalendarEvent))).scalars().all()
    via_python = {row.external_id for row in rows if is_busy(row)}
    return via_orm, via_text, via_python


async def test_all_three_spellings_agree(db_session, user):
    source_id = await _source(db_session, user)
    for external_id, busy in (("blocks", True), ("free", False), ("unknown", None)):
        await _event(db_session, user, source_id, external_id, busy)

    via_orm, via_text, via_python = await _all_three(db_session)
    assert via_orm == via_text == via_python


async def test_an_unclassified_event_still_blocks_time(db_session, user):
    """The whole reason the column is nullable: NULL is not 'free'."""
    source_id = await _source(db_session, user)
    for external_id, busy in (("blocks", True), ("free", False), ("unknown", None)):
        await _event(db_session, user, source_id, external_id, busy)

    via_orm, via_text, via_python = await _all_three(db_session)
    assert via_orm == via_text == via_python == {"blocks", "unknown"}


async def test_reading_is_not_filtering(db_session, user):
    """One query, two consumers. A declined meeting stays on the timeline and
    still must not carve a window, so the caller splits a list it already has
    rather than running a second filtered query."""
    source_id = await _source(db_session, user)
    await _event(db_session, user, source_id, "standup", True)
    await _event(db_session, user, source_id, "declined-lunch", False)

    rows = (await db_session.execute(sa.select(CalendarEvent))).scalars().all()
    commitments = {row.external_id for row in rows}
    blocking = {row.external_id for row in rows if is_busy(row)}
    assert commitments == {"standup", "declined-lunch"}
    assert blocking == {"standup"}


@pytest.mark.parametrize(
    ("payload", "external_id"),
    [
        ({"start": {"dateTime": "2026-09-01T10:00:00Z"}}, "ordinary"),
        ({"start": {"dateTime": "2026-09-01T10:00:00Z"}, "status": "cancelled"}, "cancelled"),
        ({"start": {"dateTime": "2026-09-01T10:00:00Z"}, "transparency": "transparent"}, "free"),
        ({"start": {"date": "2026-09-01"}}, "all-day"),
    ],
)
async def test_what_classify_writes_is_what_is_busy_reads(
    db_session, user, payload, external_id
):
    source_id = await _source(db_session, user)
    await _event(db_session, user, source_id, external_id, classify(payload))

    row = (await db_session.execute(sa.select(CalendarEvent))).scalar_one()
    assert is_busy(row) == classify(payload)

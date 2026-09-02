"""The read-side "still happening" predicate has two spellings. They must agree.

`live_clause()` is what `overlap.py` puts in the one query both readers share;
`is_live(row)` is for callers already holding rows. Same shape as the busy
agreement file, and for the same reason: a rule with two spellings is one rule
only while something checks.
"""

import pytest
import sqlalchemy as sa

from app.db.models import CalendarEvent
from app.services.calendar.status import is_live, live_clause

pytestmark = pytest.mark.asyncio


async def _source(session, user):
    return (
        await session.execute(
            sa.text(
                "insert into connected_sources (user_id, kind, status) "
                "values (:u, 'google_calendar', 'revoked') returning source_id"
            ),
            {"u": user.user_id},
        )
    ).scalar_one()


async def _event(session, user, source_id, external_id, status):
    await session.execute(
        sa.text(
            "insert into calendar_events "
            "(user_id, source_id, external_id, title, starts_at, ends_at, "
            " content_hash, status) values "
            "(:u, :s, :e, :e, now(), now(), :e, :st)"
        ),
        {"u": user.user_id, "s": source_id, "e": external_id, "st": status},
    )


async def test_both_spellings_agree(db_session, user):
    source_id = await _source(db_session, user)
    for external_id, status in (
        ("kept", "confirmed"),
        ("maybe", "tentative"),
        ("gone", "cancelled"),
    ):
        await _event(db_session, user, source_id, external_id, status)

    via_orm = set(
        (await db_session.execute(sa.select(CalendarEvent.external_id).where(live_clause())))
        .scalars()
        .all()
    )
    rows = (await db_session.execute(sa.select(CalendarEvent))).scalars().all()
    via_python = {row.external_id for row in rows if is_live(row)}
    assert via_orm == via_python == {"kept", "maybe"}

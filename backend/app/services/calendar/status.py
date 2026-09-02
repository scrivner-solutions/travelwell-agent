"""Is this event still happening? A different question from "does it block time".

They were briefly going to be answered by the same predicate, which would have
been wrong in both directions. A free-marked or declined event is **not busy**
and still belongs on the traveler's timeline. A cancelled event **is not on the
timeline at all**, whatever it was marked.

Two dialects, like `busy.py` minus the text one: an ORM clause for
`overlap.py`, which builds the one query both the trip timeline and the agent's
context gather read through, and Python for callers already holding rows. The
text spelling went with the timeline's private SQL; nothing reads this table
through `text()` any more.

Latent until sync landed. The demo seed only ever wrote real events, so nothing
in the database could be cancelled; the first real sync writes them, because
the client asks Google for them on purpose - see `google.py` on `showDeleted`.
"""

from __future__ import annotations

import sqlalchemy as sa

from app.db.models import CalendarEvent

CANCELLED = "cancelled"


def is_live(event: CalendarEvent) -> bool:
    """Did this event survive? Cancelled rows are kept as tombstones, so that
    a removed commitment is distinguishable from one that never synced."""
    return event.status != CANCELLED


def live_clause() -> sa.ColumnElement[bool]:
    """The same predicate as an ORM expression. Not `busy.isnot(False)` -
    that is the other question."""
    return CalendarEvent.status != CANCELLED

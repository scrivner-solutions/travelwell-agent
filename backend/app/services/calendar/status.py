"""Is this event still happening? A different question from "does it block time".

They were briefly going to be answered by the same predicate, which would have
been wrong in both directions. A free-marked or declined event is **not busy**
and still belongs on the traveler's timeline. A cancelled event **is not on the
timeline at all**, whatever it was marked.

Two dialects rather than three, because two consumers exist: the trip timeline
reads SQL text, and the agent's context builder holds rows in Python. An ORM
clause is a third spelling nothing has asked for yet.

Latent until sync landed. The demo seed only ever wrote real events, so nothing
in the database could be cancelled; the first real sync writes them, because
the client asks Google for them on purpose - see `google.py` on `showDeleted`.
"""

from __future__ import annotations

from app.db.models import CalendarEvent

CANCELLED = "cancelled"

# For raw SQL. Not `busy is not false` - that is the other question.
LIVE_SQL = f"status <> '{CANCELLED}'"


def is_live(event: CalendarEvent) -> bool:
    """Did this event survive? Cancelled rows are kept as tombstones, so that
    a removed commitment is distinguishable from one that never synced."""
    return event.status != CANCELLED

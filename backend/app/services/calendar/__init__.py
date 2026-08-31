"""Google Calendar: the busy predicate, the read seam, and the sync that writes.

Swapping providers is meant to be two edits: write a class implementing
`CalendarClient` in this package, and return it from `calendar_client` below.
Nothing outside this module names an implementation.

There is no environment switch, for the reason `token_store` gives and one
more: which provider serves a connection is already recorded per row, as
`connected_sources.kind`. An env var would be a second, quieter answer to a
question the database already answers.

`FakeCalendarClient` is deliberately not exported. It returns an empty
schedule, and an empty schedule is indistinguishable from a free one.
"""

from app.services.calendar.busy import BUSY_SQL, busy_clause, classify, is_busy
from app.services.calendar.google import GoogleCalendarClient
from app.services.calendar.ports import (
    CalendarClient,
    CalendarUnavailable,
    CredentialRejected,
    RemoteEvent,
)
from app.services.calendar.status import CANCELLED, LIVE_SQL, is_live
from app.services.calendar.sync import SyncResult, content_hash, sync_source

__all__ = [
    "BUSY_SQL",
    "CANCELLED",
    "LIVE_SQL",
    "CalendarClient",
    "CalendarUnavailable",
    "CredentialRejected",
    "RemoteEvent",
    "SyncResult",
    "busy_clause",
    "calendar_client",
    "classify",
    "content_hash",
    "is_busy",
    "is_live",
    "sync_source",
]


def calendar_client(refresh_token: str) -> CalendarClient:
    """The client this deployment uses, holding one user's grant."""
    return GoogleCalendarClient(refresh_token)

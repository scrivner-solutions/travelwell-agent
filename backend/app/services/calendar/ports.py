"""The calendar seam: exactly one operation, because exactly one step is remote.

Everything else about calendar sync is deterministic - classifying an event,
hashing it, deciding whether the stored row changed - and deterministic code
belongs in tests that run in CI without credentials. So the network is confined
to `list_events` and nothing else crosses this line.

What crosses it is a `RemoteEvent`, not the provider's JSON. That is the whole
point of the seam: `busy` is already decided here, because deciding it needs
Google's own vocabulary (`transparency`, `attendees[].responseStatus`, an
all-day `start.date`), and passing raw payloads through would make every
consumer downstream learn a provider. An Apple or CalDAV implementation answers
the same question from a different vocabulary and the callers never notice.

The two errors are separate because the responses are opposite. A
`CalendarUnavailable` is worth retrying and the grant is still good. A
`CredentialRejected` will fail identically forever until the user reconnects,
so retrying it is how a source stays quietly broken.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


class CalendarUnavailable(RuntimeError):
    """The provider could not be reached, or refused for a transient reason."""


class CredentialRejected(CalendarUnavailable):
    """The stored grant is no longer accepted.

    Its own subclass because the caller's response differs: reconnecting is the
    only fix, so the source is marked `error` rather than retried.
    """


@dataclass(frozen=True, slots=True)
class RemoteEvent:
    """One occurrence, normalized. Recurrence is already expanded upstream.

    `starts_at` and `ends_at` are timezone-aware, always: the column is
    `timestamptz`, and an all-day event read as naive UTC lands on the wrong
    day for anyone east or west of London, which is a planning bug rather than
    a display one.
    """

    external_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    status: str
    busy: bool
    location: str | None = None


@runtime_checkable
class CalendarClient(Protocol):
    """Read a window of a user's calendar. One method, deliberately."""

    async def list_events(
        self, start: datetime, end: datetime
    ) -> Sequence[RemoteEvent]:
        """Every occurrence overlapping [start, end), cancellations included.

        Cancellations are included rather than filtered because a row that
        vanishes and a row that was cancelled are indistinguishable to a caller
        that only sees what is left, and only one of them means the user
        removed the commitment. Callers filter on `status`.
        """
        ...

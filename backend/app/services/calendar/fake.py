"""An in-process CalendarClient, for tests and nothing else.

Deliberately not exported from the package, for the same reason
`InMemoryTokenStore` is not: a fake calendar returns an empty schedule, and an
empty schedule is indistinguishable from a free one. Nothing a deployment can
reach should be able to select it.

It filters by window like the real client does. A fake that returns everything
regardless of the range asked for would let a sync that computes its window
wrongly pass every test.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from app.services.calendar.ports import CalendarUnavailable, RemoteEvent


class FakeCalendarClient:
    def __init__(
        self,
        events: Iterable[RemoteEvent] = (),
        *,
        raises: CalendarUnavailable | None = None,
    ) -> None:
        self._events = list(events)
        self._raises = raises
        self.calls: list[tuple[datetime, datetime]] = []

    async def list_events(
        self, start: datetime, end: datetime
    ) -> Sequence[RemoteEvent]:
        self.calls.append((start, end))
        if self._raises is not None:
            raise self._raises
        # Overlap, not containment: a meeting that started before the window
        # opened is still occupying the traveler inside it.
        return [e for e in self._events if e.starts_at < end and e.ends_at > start]

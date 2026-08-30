"""The `external_link` provider: record the intent, hand the booking over.

This is a complete product path, not a degraded one (RESERVATIONS.md section
3). Most places have no reservation API at all, and for those the honest
answer is the whole answer: here is where to book, you book it. Pretending
otherwise would mean showing "Waiting to book" next to a booking nobody is
making.

So it books nothing and claims nothing. The reservation it produces rests at
`pending` - not yet booked, which is true - and is marked handed off, which is
what stops the executor waiting on a table that will never be held.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.db.models import ReservationProvider, ReservationStatus
from app.services.reservations.links import booking_search_url
from app.services.reservations.ports import (
    BookingHandle,
    BookingRequest,
    BookingUpdate,
)

Clock = Callable[[], datetime]


class ExternalLinkProvider:
    """Implements ReservationPort."""

    provider = ReservationProvider.external_link

    def __init__(self, clock: Clock | None = None) -> None:
        self._now = clock or (lambda: datetime.now(UTC))

    async def place(self, request: BookingRequest) -> BookingHandle:
        return BookingHandle(
            provider=self.provider,
            reference=f"ext_{uuid.uuid4().hex[:20]}",
            placed_at=self._now(),
            details={
                "place_name": request.place_name,
                "slot_at": request.slot_at.isoformat(),
                "party_size": request.party_size,
                "url": request.booking_url or booking_search_url(request.place_name),
            },
        )

    async def poll(self, handle: BookingHandle) -> BookingUpdate:
        """Always the same answer. There is no remote booking to read, and
        saying so on every poll is more honest than inventing progress."""
        return self._update(ReservationStatus.pending, handle, handed_off=True)

    async def cancel(self, handle: BookingHandle) -> BookingUpdate:
        """Drop the intent. Nothing is released because nothing was held, but
        the user deciding against it is still worth recording as canceled."""
        return self._update(ReservationStatus.canceled, handle)

    def _update(
        self, status: ReservationStatus, handle: BookingHandle, *, handed_off: bool = False
    ) -> BookingUpdate:
        return BookingUpdate(
            status=status,
            external_url=handle.details.get("url"),
            handed_off=handed_off,
            raw={
                "provider": self.provider.value,
                "reference": handle.reference,
                "status": status.value,
                "read_at": self._now().isoformat(),
                "note": "no booking was attempted; this provider hands off to the user",
            },
        )

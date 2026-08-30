"""The booking seam: what any reservation provider must be able to do.

Written against the shape a real booking API has, not against what is
convenient to simulate. Every one of them - OpenTable, Resy, SevenRooms -
works the same way: you submit a request and get a reference back, the table
is not yours yet, and you read that reference until it settles. So the port is
`place` -> `poll` until terminal, plus `cancel`.

That shape is the whole point. `poll` against a real provider asks their API
what the booking is now, and it changed on their clock; `poll` against the
simulator computes what it would be by now from the same elapsed time. The
executor cannot tell the two apart, which is what makes swapping one for the
other a registry entry rather than a rewrite.

Nothing here may mention simulation, scenarios, or fast-forwarding. A concept
that only makes sense for the fake does not belong in the interface the real
one has to implement.

Implementations live beside this file and are chosen by `provider_for`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.db.models import ReservationProvider, ReservationStatus

# The states no further poll can move. Kept here rather than in the executor:
# it is a fact about the reservation lifecycle, and both sides read it.
TERMINAL_STATUSES = frozenset({
    ReservationStatus.confirmed,
    ReservationStatus.failed,
    ReservationStatus.canceled,
})


class ProviderError(RuntimeError):
    """The provider could not be reached or answered unusably.

    Deliberately not the same thing as a decline. "No table at 7pm" is a
    successful call with a negative answer and arrives as a BookingUpdate;
    this is a timeout, a 500, or a body we cannot parse. The executor treats
    them differently because only one of them is worth retrying, and
    integrations that conflate the two report outages as refusals.
    """


@dataclass(frozen=True)
class BookingRequest:
    """What the user wants held. Provider-neutral by construction."""

    place_name: str
    slot_at: datetime
    party_size: int
    place_id: uuid.UUID | None = None
    # Where this place takes bookings, when we know. A property of the place,
    # not of any one provider, which is why it rides along on the request.
    booking_url: str | None = None
    # Per-attempt token. Real providers accept one so a retried submit cannot
    # double-book; ours is the action's own key, so the guarantee is the same
    # one end to end rather than two schemes that have to agree.
    idempotency_key: str | None = None


@dataclass(frozen=True)
class BookingHandle:
    """The provider's identifier for one attempt, and whatever it needs back.

    Persisted verbatim into pending_actions.execution_result, so it must be
    JSON. That persistence is not an implementation detail: it is what lets
    the executor restart mid-booking and keep polling something it did not
    itself submit, exactly as it would have to against a real provider.
    """

    provider: ReservationProvider
    reference: str
    placed_at: datetime
    # Opaque to the executor. A real client puts the provider's own booking
    # payload here; nothing outside the implementation may read into it.
    details: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "provider": self.provider.value,
            "reference": self.reference,
            "placed_at": self.placed_at.isoformat(),
            "details": self.details,
        }

    @classmethod
    def from_json(cls, raw: dict) -> BookingHandle:
        return cls(
            provider=ReservationProvider(raw["provider"]),
            reference=raw["reference"],
            placed_at=datetime.fromisoformat(raw["placed_at"]),
            details=raw.get("details") or {},
        )


@dataclass(frozen=True)
class BookingUpdate:
    """The provider's current view of one attempt.

    `raw` is what it actually said, stored as the verification record. We keep
    it because "we believe it is confirmed" and "here is what they told us"
    are different claims, and only the second one is evidence.
    """

    status: ReservationStatus
    confirmation_code: str | None = None
    failure_reason: str | None = None
    external_url: str | None = None
    raw: dict = field(default_factory=dict)
    # The provider has done everything it is going to; whatever remains is the
    # user's to do. Set by providers that hand a booking off rather than making
    # it, which is a real category and not a fallback: plenty of venues have no
    # API at all, and the honest answer there is a link, not a pending booking
    # we are secretly not working on.
    handed_off: bool = False

    @property
    def terminal(self) -> bool:
        """No further poll will change this.

        Not the same as a terminal *status*: a handed-off booking rests at
        `pending` forever and is still finished, because nothing on our side
        will ever move it.
        """
        return self.handed_off or self.status in TERMINAL_STATUSES


@runtime_checkable
class ReservationPort(Protocol):
    """One booking provider.

    Implementations are stateless with respect to a booking: everything needed
    to read an attempt back is in the handle. That is not a preference, it is
    what remote providers force -- we hold a reference, they hold the booking -
    and holding ourselves to it is what keeps the simulator honest.
    """

    provider: ReservationProvider

    async def place(self, request: BookingRequest) -> BookingHandle:
        """Submit the request. Returns once the provider has accepted it,
        which is not the same as the table being held. Raises ProviderError if
        the submission itself could not be made."""
        ...

    async def poll(self, handle: BookingHandle) -> BookingUpdate:
        """Read the attempt back. Called until the update is terminal."""
        ...

    async def cancel(self, handle: BookingHandle) -> BookingUpdate:
        """Release a hold or a confirmed booking."""
        ...

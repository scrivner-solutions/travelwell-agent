"""The `travelwell` provider: a booking simulator that behaves like a remote one.

What it is for is exercising the states nothing else can reach. Every seeded
reservation is born in its final state, so `pending` and `canceled` have never
rendered and `holding` never becomes anything (RESERVATIONS.md section 1). The
four seeded rows cover four outcomes and zero transitions, and transitions are
where the bugs are.

So the rules it holds itself to, from RESERVATIONS.md section 4:

- **It walks the machine.** A booking passes through `pending` and, if it is
  going to succeed, `holding`, on a clock. Jumping to `confirmed` would repeat
  in code the exact limitation the seed already has.
- **It is steerable, not random.** A demo that fails on a coin flip cannot be
  rehearsed. Outcomes come from rules over the request, so the same booking
  behaves the same way every time, and a refusal can be shown on request.
- **It is idempotent.** Submitting the same idempotency key twice yields the
  same reference, which is the guarantee a real provider gives and the one the
  executor is written against.

The clock lives in here, behind the port, and that placement is the design.
`poll` against a real provider asks what the booking is now; `poll` here works
out what it would be by now. Same call, same answer shape, no caller changes
when one replaces the other.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.db.models import ReservationProvider, ReservationStatus
from app.services.reservations.links import booking_search_url
from app.services.reservations.ports import (
    BookingHandle,
    BookingRequest,
    BookingUpdate,
)

Clock = Callable[[], datetime]

# Unambiguous in print: no O/0, no I/1. Confirmation codes get read aloud.
_CODE_ALPHABET = "ACDEFGHJKLMNPQRTUVWXY2346789"
_CODE_LENGTH = 5

# Above this, a restaurant wants a phone call. A real constraint rather than an
# invented one, which is what makes it a demo you can explain.
DEFAULT_MAX_PARTY = 8


@dataclass(frozen=True)
class Timings:
    """How long the walk takes. Configurable because the right answer differs:
    a demo needs it slow enough to watch, a test needs it to cost nothing."""

    hold_after: timedelta = timedelta(seconds=2)
    settle_after: timedelta = timedelta(seconds=6)

    @classmethod
    def from_env(cls) -> Timings:
        return cls(
            hold_after=timedelta(seconds=float(os.getenv("RESERVATION_SIM_HOLD_S", "2"))),
            settle_after=timedelta(
                seconds=float(os.getenv("RESERVATION_SIM_SETTLE_S", "6"))
            ),
        )


@dataclass(frozen=True)
class Rules:
    """What the simulator refuses, and why.

    Both rules are things a real venue actually does, so a declined booking in
    a demo can be explained rather than apologised for. `declining_places` is
    how the seed's "Mildreds declined the 7:00 hold" becomes reproducible
    instead of typed in by hand.
    """

    max_party: int = DEFAULT_MAX_PARTY
    declining_places: frozenset[str] = frozenset()

    @classmethod
    def from_env(cls) -> Rules:
        raw = os.getenv("RESERVATION_SIM_DECLINES", "")
        return cls(
            max_party=int(os.getenv("RESERVATION_SIM_MAX_PARTY", DEFAULT_MAX_PARTY)),
            declining_places=frozenset(
                name.strip().casefold() for name in raw.split(",") if name.strip()
            ),
        )

    def decline_reason(self, request: BookingRequest) -> str | None:
        """The reason this request will be refused, or None to accept it."""
        if request.place_name.casefold() in self.declining_places:
            return f"{request.place_name} declined the hold for that time."
        if request.party_size > self.max_party:
            return (
                f"{request.place_name} does not take online reservations for "
                f"parties over {self.max_party}."
            )
        return None


def _reference(request: BookingRequest) -> str:
    """Opaque per-attempt token, stable for a given idempotency key.

    Same key in, same reference out, so a resubmitted request lands on the
    booking that already exists rather than a second one. That is what a real
    provider promises and what stops a retry from double-booking a table.
    """
    if request.idempotency_key:
        digest = hashlib.sha256(request.idempotency_key.encode()).hexdigest()
        return f"twl_{digest[:20]}"
    return f"twl_{uuid.uuid4().hex[:20]}"


def _confirmation_code(reference: str) -> str:
    """Derived from the reference, so every poll returns the same code.

    A code that changed between reads would be a code that means nothing, and
    the UI prints it next to the booking.
    """
    digest = hashlib.sha256(f"code:{reference}".encode()).digest()
    return "".join(_CODE_ALPHABET[b % len(_CODE_ALPHABET)] for b in digest[:_CODE_LENGTH])


class SimulatedProvider:
    """Implements ReservationPort. Stateless: the handle carries the booking.

    Holding to statelessness is not tidiness, it is fidelity. A remote provider
    keeps the booking and hands us a reference; if the simulator kept a dict in
    memory it would quietly gain properties no real client has, and code
    written against those would break on the day a real one arrives.
    """

    provider = ReservationProvider.travelwell

    def __init__(
        self,
        clock: Clock | None = None,
        timings: Timings | None = None,
        rules: Rules | None = None,
    ) -> None:
        self._now = clock or (lambda: datetime.now(UTC))
        self._timings = timings or Timings.from_env()
        self._rules = rules or Rules.from_env()

    async def place(self, request: BookingRequest) -> BookingHandle:
        """Accept the request and decide, once, how it will go.

        Resolving the outcome here rather than on each poll is what a remote
        provider does too: the booking record exists on their side from the
        moment they accept it, and reading it cannot change it.
        """
        decline_reason = self._rules.decline_reason(request)
        return BookingHandle(
            provider=self.provider,
            reference=_reference(request),
            placed_at=self._now(),
            details={
                "place_name": request.place_name,
                "slot_at": request.slot_at.isoformat(),
                "party_size": request.party_size,
                "decline_reason": decline_reason,
                "hold_after_s": self._timings.hold_after.total_seconds(),
                "settle_after_s": self._timings.settle_after.total_seconds(),
            },
        )

    async def poll(self, handle: BookingHandle) -> BookingUpdate:
        elapsed = self._now() - handle.placed_at
        details = handle.details
        hold_after = timedelta(seconds=details["hold_after_s"])
        settle_after = timedelta(seconds=details["settle_after_s"])
        place_name = details["place_name"]
        decline_reason = details.get("decline_reason")

        # A refusal arrives before anything is held: a venue that will not take
        # the booking says so, it does not hold a table first. This is the
        # pending -> failed edge; the accepted path is the one that holds.
        if decline_reason is not None:
            if elapsed < hold_after:
                return self._update(ReservationStatus.pending, handle)
            return self._update(
                ReservationStatus.failed,
                handle,
                failure_reason=decline_reason,
                external_url=booking_search_url(place_name),
            )

        if elapsed < hold_after:
            return self._update(ReservationStatus.pending, handle)
        if elapsed < hold_after + settle_after:
            return self._update(ReservationStatus.holding, handle)
        return self._update(
            ReservationStatus.confirmed,
            handle,
            confirmation_code=_confirmation_code(handle.reference),
        )

    async def cancel(self, handle: BookingHandle) -> BookingUpdate:
        """Release the booking.

        Nothing records the cancellation on this side, because nothing needs
        to: the fact lives in our reservations row, an action that reaches a
        terminal state is never driven again, and so this handle is never
        polled after. A real provider would remember; the difference is not
        reachable from any call the executor makes.
        """
        current = await self.poll(handle)
        if current.status is ReservationStatus.failed:
            # There is nothing to release, and reporting `canceled` would claim
            # we undid a booking that never existed.
            return current
        return self._update(ReservationStatus.canceled, handle)

    def _update(
        self,
        status: ReservationStatus,
        handle: BookingHandle,
        *,
        confirmation_code: str | None = None,
        failure_reason: str | None = None,
        external_url: str | None = None,
    ) -> BookingUpdate:
        return BookingUpdate(
            status=status,
            confirmation_code=confirmation_code,
            failure_reason=failure_reason,
            external_url=external_url,
            # Shaped like a provider's response body, because that is what it
            # stands in for: this lands in pending_actions.verification and is
            # the only record of what we were told rather than what we decided.
            raw={
                "provider": self.provider.value,
                "reference": handle.reference,
                "status": status.value,
                "read_at": self._now().isoformat(),
                "place_name": handle.details.get("place_name"),
                "party_size": handle.details.get("party_size"),
            },
        )

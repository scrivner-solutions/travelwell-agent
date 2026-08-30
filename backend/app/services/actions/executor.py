"""The pending_actions executor: claim, execute, verify, record.

Every external side effect the app performs goes through here. A caller
proposes an action, a user approves it, and this is the only thing that
carries it out - which is what makes "the agent cannot book" a property of the
system rather than a promise in a prompt (AGENT_DESIGN.md section 14).

Shape, per ROADMAP.md:

    proposed -> approved -> executing -> completed / failed

`approved` means the user said yes and nobody has picked it up. The first
claim submits the effect and moves the row to `executing`; later claims read
the provider back until it settles. Two steps rather than one because a real
booking is not synchronous: submitting is fast, being told whether you got the
table is not, and an executor that pretends otherwise only works against a
fake.

Why a background claim rather than advancing state inside the read endpoints:
a booking the user approved has to reach its conclusion whether or not anyone
is still watching the screen. Progress that only happens while someone polls
is not execution, it is animation.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    ActionStatus,
    ActionType,
    ItemStatus,
    PendingAction,
    PlanItem,
    Reservation,
    ReservationProvider,
    ReservationStatus,
)
from app.services.reservations import (
    BookingHandle,
    BookingRequest,
    BookingUpdate,
    ProviderError,
    UnsupportedProvider,
    provider_for,
)

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]

# Claimable states. `approved` still has to be submitted; `executing` has been
# submitted and is waiting on the provider.
_CLAIMABLE = (ActionStatus.approved, ActionStatus.executing)

# Only these two are built. The calendar writes share the machinery but not the
# slice, and refusing them by name beats a handler that quietly does nothing.
IMPLEMENTED_TYPES = frozenset({
    ActionType.make_reservation,
    ActionType.cancel_reservation,
})

# The slice of the item lifecycle the executor owns. `working` and `confirmed`
# exist for booking and nothing else writes them: the demo seed pairs them with
# a `holding` and a `confirmed` reservation, and itemBadge renders them as
# "Booking…" and "Booked". Moving an item through these is not planning - it is
# recording what the provider did, which is why a refusal returns it to
# `planned` rather than skipping it.
_BOOKING_TRACK_ENTRY = frozenset({ItemStatus.planned, ItemStatus.changed})

# How long an action may sit unsettled before we stop waiting. Denver's seeded
# reservation says "Holding a table" forever; nothing in the app should be able
# to do that for real.
EXECUTION_DEADLINE = timedelta(minutes=10)


class ActionFailure(Exception):
    """A reason this action cannot complete, in the shape the client reads."""

    def __init__(self, code: str, message: str, external_url: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.external_url = external_url

    def as_json(self) -> dict:
        body = {"code": self.code, "message": self.message}
        if self.external_url:
            body["external_url"] = self.external_url
        return body


def _now() -> datetime:
    return datetime.now(UTC)


async def drive_once(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    clock: Clock | None = None,
    batch: int = 8,
) -> int:
    """Advance up to `batch` claimable actions by one step each.

    Returns how many were touched, so a caller can tell a quiet tick from a
    busy one. One action per transaction: a provider that violates a database
    constraint should fail its own action, not poison the batch.
    """
    touched = 0
    for _ in range(batch):
        async with session_factory() as session:
            action = await _claim(session)
            if action is None:
                break
            try:
                await _advance(session, action, clock or _now)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("action %s failed to advance", action.action_id)
                await _mark_failed_out_of_band(
                    session_factory,
                    action.action_id,
                    ActionFailure("internal_error", "This action could not be completed."),
                )
            touched += 1
    return touched


async def _claim(session: AsyncSession) -> PendingAction | None:
    """One claimable action, locked for the life of this transaction.

    FOR UPDATE SKIP LOCKED is what makes more than one instance safe: a row
    another worker holds is passed over rather than waited on.

    The lock is held across the provider call. That is the simple thing and it
    is fine at one action per transaction and a handful in flight; it stops
    being fine when provider calls are slow enough that open transactions pile
    up, and the answer then is a lease column plus a heartbeat, not a longer
    statement timeout.
    """
    stmt = (
        select(PendingAction)
        .where(PendingAction.status.in_(_CLAIMABLE))
        .order_by(PendingAction.approved_at.asc().nullsfirst())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return (await session.execute(stmt)).scalars().first()


async def _advance(session: AsyncSession, action: PendingAction, clock: Clock) -> None:
    now = clock()
    if action.action_type not in IMPLEMENTED_TYPES:
        await _abandon(
            session,
            action,
            ActionFailure(
                "action_unsupported",
                f"{action.action_type.value} is not implemented yet.",
            ),
            now,
        )
        return

    if action.executed_at is not None and now - action.executed_at > EXECUTION_DEADLINE:
        # Submitted, never settled. Better to say the booking is unresolved
        # than to leave a row claiming it is still being worked on.
        await _abandon(
            session,
            action,
            ActionFailure(
                "provider_timeout",
                "The provider did not answer in time. Nothing was confirmed.",
            ),
            now,
        )
        return

    try:
        if action.action_type is ActionType.make_reservation:
            await _make_reservation(session, action, clock)
        else:
            await _cancel_reservation(session, action, clock)
    except ActionFailure as failure:
        await _abandon(session, action, failure, now)
    except UnsupportedProvider as exc:
        await _abandon(
            session, action, ActionFailure("provider_unsupported", str(exc)), now
        )
    except ProviderError as exc:
        # Reaching the provider failed, which is not the provider saying no.
        # Leave the action claimable and try again next tick; the deadline
        # above is what stops that being forever.
        logger.warning("provider unreachable for action %s: %s", action.action_id, exc)


async def _make_reservation(
    session: AsyncSession, action: PendingAction, clock: Clock
) -> None:
    payload = action.proposed_payload or {}
    provider_name = payload.get("provider") or ReservationProvider.travelwell.value
    provider = provider_for(ReservationProvider(provider_name), clock=clock)
    result = dict(action.execution_result or {})

    if "handle" not in result:
        handle = await provider.place(_booking_request(action, payload))
        reservation = Reservation(
            trip_id=action.trip_id,
            item_id=action.subject_item_id,
            place_id=uuid.UUID(payload["place_id"]) if payload.get("place_id") else None,
            provider=ReservationProvider(provider_name),
            status=ReservationStatus.pending,
            slot_at=datetime.fromisoformat(payload["slot_at"]),
            party_size=int(payload.get("party_size") or 1),
        )
        session.add(reservation)
        await session.flush()
        await _set_item_status(
            session, action, ItemStatus.working, only_from=_BOOKING_TRACK_ENTRY
        )
        action.status = ActionStatus.executing
        action.executed_at = clock()
        # Both halves are needed to resume: the handle to read the provider
        # back, the id to know which row this action is responsible for.
        action.execution_result = {
            "handle": handle.to_json(),
            "reservation_id": str(reservation.reservation_id),
        }
        return

    handle = BookingHandle.from_json(result["handle"])
    reservation = await session.get(Reservation, uuid.UUID(result["reservation_id"]))
    if reservation is None:
        raise ActionFailure("reservation_missing", "The reservation record is gone.")

    update = await provider.poll(handle)
    _apply(reservation, update, clock())
    if not update.terminal:
        return

    # The verification step: read it back once more and keep what we were
    # told. Against a real provider that is a second confirmation the booking
    # exists; against the simulator it proves the answer is stable rather than
    # a one-time guess. Either way `verification` holds evidence, not a belief.
    verified = await provider.poll(handle)
    _apply(reservation, verified, clock())
    action.verification = verified.raw

    if verified.status is ReservationStatus.failed:
        # _abandon hands the item back to `planned`: the window still stands and
        # the table is still unbooked, which is exactly the state a retry is
        # for. itemBadge reads "Couldn't book" off the reservation from there.
        raise ActionFailure(
            "provider_declined",
            verified.failure_reason or "The provider declined this booking.",
            external_url=verified.external_url,
        )
    # Only a real confirmation earns `confirmed`. A handed-off booking finished
    # without a table being held, so the item goes back to waiting for one.
    await _set_item_status(
        session,
        action,
        ItemStatus.confirmed
        if verified.status is ReservationStatus.confirmed
        else ItemStatus.planned,
        only_from={ItemStatus.working},
    )
    action.status = ActionStatus.completed


async def _cancel_reservation(
    session: AsyncSession, action: PendingAction, clock: Clock
) -> None:
    payload = action.proposed_payload or {}
    reservation = await session.get(
        Reservation, uuid.UUID(payload["reservation_id"])
    )
    if reservation is None or reservation.trip_id != action.trip_id:
        raise ActionFailure("reservation_missing", "That reservation does not exist.")

    result = dict(action.execution_result or {})
    handle = (
        BookingHandle.from_json(result["handle"])
        if "handle" in result
        else _handle_for_existing(reservation)
    )
    provider = provider_for(reservation.provider, clock=clock)
    update = await provider.cancel(handle)
    _apply(reservation, update, clock())
    # A cancelled booking leaves the plan item standing and unbooked.
    await _set_item_status(
        session,
        action,
        ItemStatus.planned,
        only_from={ItemStatus.working, ItemStatus.confirmed},
    )
    action.status = ActionStatus.completed
    action.executed_at = clock()
    action.execution_result = {
        "handle": handle.to_json(),
        "reservation_id": str(reservation.reservation_id),
    }
    action.verification = update.raw


async def _set_item_status(
    session: AsyncSession,
    action: PendingAction,
    target: ItemStatus,
    *,
    only_from: frozenset[ItemStatus] | set[ItemStatus],
) -> None:
    """Move the item this action is for, but only out of a state we own.

    `only_from` is the guard that keeps execution out of the user's way: if
    someone skipped or removed the item while the provider was thinking, that
    answer stands and the booking result is recorded on the reservation alone.
    """
    if action.subject_item_id is None:
        return
    item = await session.get(PlanItem, action.subject_item_id)
    if item is None or item.status not in only_from:
        return
    item.status = target
    item.updated_at = _now()


def _handle_for_existing(reservation: Reservation) -> BookingHandle:
    """A handle for a reservation this executor did not place.

    Seeded rows have no provider reference, because nothing ever called a
    provider for them. Reconstructing one from the row is the honest stand-in:
    a real integration would store the provider's reference at booking time and
    this branch would simply not exist.
    """
    return BookingHandle(
        provider=reservation.provider,
        reference=f"seed_{reservation.reservation_id.hex[:16]}",
        placed_at=reservation.created_at,
        details={
            "place_name": "",
            "slot_at": reservation.slot_at.isoformat(),
            "party_size": reservation.party_size,
            "decline_reason": None,
            "hold_after_s": 0.0,
            "settle_after_s": 0.0,
            "url": reservation.external_url,
        },
    )


def _booking_request(action: PendingAction, payload: dict) -> BookingRequest:
    return BookingRequest(
        place_name=payload.get("place_name") or "",
        slot_at=datetime.fromisoformat(payload["slot_at"]),
        party_size=int(payload.get("party_size") or 1),
        place_id=uuid.UUID(payload["place_id"]) if payload.get("place_id") else None,
        booking_url=payload.get("booking_url"),
        # The action's own key, so one guarantee runs end to end instead of two
        # schemes that have to agree: a resubmitted action cannot double-book.
        idempotency_key=action.idempotency_key,
    )


def _apply(reservation: Reservation, update: BookingUpdate, now: datetime) -> None:
    """Write a provider's answer onto the row.

    Fields are only ever filled in, never cleared: a confirmation code or a
    refusal reason is a fact about an attempt, and a later read that omits it
    has not withdrawn it.
    """
    reservation.status = update.status
    if update.confirmation_code is not None:
        reservation.confirmation_code = update.confirmation_code
    if update.failure_reason is not None:
        reservation.failure_reason = update.failure_reason
    if update.external_url is not None:
        reservation.external_url = update.external_url
    reservation.updated_at = now


async def _abandon(
    session: AsyncSession,
    action: PendingAction,
    failure: ActionFailure,
    now: datetime,
) -> None:
    """Fail the action and hand the item back.

    Every failure path goes through here, because the alternative is an item
    stranded at `working` — a row that says "Booking…" about a booking that
    stopped. Back to `planned`, never skipped: the window still stands and the
    table is still unbooked, which is what a retry is for.
    """
    _fail(action, failure, now)
    await _set_item_status(
        session, action, ItemStatus.planned, only_from={ItemStatus.working}
    )


def _fail(action: PendingAction, failure: ActionFailure, now: datetime) -> None:
    action.status = ActionStatus.failed
    action.execution_result = {
        **(action.execution_result or {}),
        "failure": failure.as_json(),
    }
    action.executed_at = action.executed_at or now


async def _mark_failed_out_of_band(
    session_factory: async_sessionmaker[AsyncSession],
    action_id: uuid.UUID,
    failure: ActionFailure,
) -> None:
    """Record a failure whose own transaction was rolled back.

    Without this an action that trips a database constraint stays `executing`
    and is claimed again every tick, failing the same way forever.
    """
    try:
        async with session_factory() as session:
            action = await session.get(PendingAction, action_id)
            if action is not None and action.status in _CLAIMABLE:
                await _abandon(session, action, failure, _now())
                await session.commit()
    except SQLAlchemyError:
        logger.exception("could not record failure for action %s", action_id)

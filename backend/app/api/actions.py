"""Actions: propose an effect, approve it, watch it happen.

The confirmation boundary of the whole product. Nothing books, cancels or
writes anything except through a pending_actions row that a user approved, so
"the agent cannot book" is enforced by the fact that there is no other path
rather than by asking it not to (AGENT_DESIGN.md section 14).

Three of these four routes are ordinary reads and writes. The fourth exists
because execution is not synchronous: approving hands the row to the executor
and returns, and the stream is how the screen finds out what happened.

Idempotency is real here, unlike on POST /trips: pending_actions has the
unique key column, so a resubmitted proposal lands on the action that already
exists instead of proposing a second booking of the same table.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import ApiRoute, CurrentUser, SessionDep
from app.api.plan import reject_if_past
from app.api.problems import Problem
from app.api.schemas import (
    ActionCreateIn,
    PendingActionOut,
    action_updated_at,
    item_title,
    pending_action_to_out,
)
from app.api.trips import owned_trip
from app.db.models import (
    ActionStatus,
    ActionType,
    ItemStatus,
    OptionState,
    PendingAction,
    PlanItem,
    Reservation,
    Trip,
)
from app.services.actions import IMPLEMENTED_TYPES
from app.services.reservations import default_provider

router = APIRouter(tags=["actions"], route_class=ApiRoute)

# Booking is the third gate and the gates are ordered: an item has to be kept
# before a table is asked for. "Accepting is not agreeing to book"
# (accept_all_plan_items) is the same rule read from the other side. Mirrors
# `_BOOKING_TRACK_ENTRY` in the executor and `KEPT` in the frontend's useBooking;
# all three must agree or the button proposes work nothing will finish.
_BOOKABLE_ITEM_STATES = frozenset({ItemStatus.planned, ItemStatus.changed})

# Past these the action is out of the user's hands: it has been handed to the
# executor or it is over.
_APPROVABLE = frozenset({ActionStatus.proposed})

# Nothing more will happen to an action in one of these.
_TERMINAL = frozenset({
    ActionStatus.completed,
    ActionStatus.failed,
    ActionStatus.canceled,
})

# How long a stream stays open with nothing to say. The client reconnects, and
# a socket held open forever is a socket leaked forever.
_STREAM_MAX_SECONDS = 300
_STREAM_POLL_SECONDS = 1.0


class ApproveIn(BaseModel):
    updated_at: datetime


async def _owned_action(session, user, action_id: uuid.UUID) -> PendingAction:
    """404 whether it is missing or someone else's; the two are the same answer
    to anyone not entitled to know the difference."""
    action = await session.get(PendingAction, action_id)
    if action is None or action.user_id != user.user_id:
        raise Problem(404, "Action not found", "action_not_found")
    return action


async def _reservation_for(session, action: PendingAction) -> Reservation | None:
    """The booking this action produced, if it got that far.

    There is no foreign key: pending_actions predates any of them being
    written, and the id is recorded in execution_result when the effect is
    submitted. See executor._make_reservation.
    """
    raw = (action.execution_result or {}).get("reservation_id")
    if raw is None:
        return None
    return await session.get(Reservation, uuid.UUID(raw))


async def _owned_item(session, user, item_id: uuid.UUID) -> tuple[PlanItem, Trip]:
    stmt = (
        select(PlanItem, Trip)
        .join(Trip, Trip.trip_id == PlanItem.trip_id)
        .where(PlanItem.item_id == item_id, Trip.user_id == user.user_id)
        .options(
            selectinload(PlanItem.options), selectinload(PlanItem.reservations)
        )
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        raise Problem(404, "Plan item not found", "item_not_found")
    return row[0], row[1]


def _reservation_payload(item: PlanItem, body: ActionCreateIn) -> dict:
    """What will be booked, assembled from the item rather than the request.

    The client chooses the party size and may move the time; the place comes
    from the option it already selected. That asymmetry is the point: an
    endpoint that took a place name would be a way to book anything, and the
    approval sheet would be describing a request the plan never made.
    """
    selected = next((o for o in item.options if o.state == OptionState.selected), None)
    place_name = selected.display_name if selected else item_title(item)
    party_size = int(body.payload.get("party_size") or 1)
    if party_size < 1:
        raise Problem(
            422,
            "Party size must be at least 1",
            "validation_error",
            "A reservation needs at least one seat.",
        )
    slot_at = item.scheduled_start
    if raw_slot := body.payload.get("slot_at"):
        try:
            slot_at = datetime.fromisoformat(raw_slot)
        except ValueError:
            raise Problem(
                422, "Invalid slot time", "validation_error", f"{raw_slot!r} is not a timestamp."
            ) from None
    provider = default_provider()
    return {
        "provider": provider.value,
        "place_name": place_name,
        "place_id": str(selected.place_id) if selected and selected.place_id else None,
        "slot_at": slot_at.isoformat(),
        "party_size": party_size,
        # Values, not sentences. The trip's timezone lives on the client and
        # formats every other time there; a second formatter here would drift.
        "summary": {
            "what": item_title(item),
            "where": place_name,
            "when": slot_at.isoformat(),
            "party_size": party_size,
            "provider": provider.value,
        },
    }


def _cancel_payload(item: PlanItem, body: ActionCreateIn) -> dict:
    raw = body.payload.get("reservation_id")
    if raw is None:
        # The newest attempt, which is the one the UI is showing; PlanItem
        # orders reservations newest first for exactly this reason.
        if not item.reservations:
            raise Problem(
                422,
                "Nothing to cancel",
                "no_reservation",
                "This item has no reservation.",
            )
        raw = str(item.reservations[0].reservation_id)
    return {
        "reservation_id": str(raw),
        "summary": {
            "what": f"Cancel {item_title(item)}",
            "where": item_title(item),
        },
    }


@router.post("/actions", status_code=201)
async def create_action(
    body: ActionCreateIn,
    idempotency_key: Annotated[uuid.UUID, Header(alias="Idempotency-Key")],
    user: CurrentUser,
    session: SessionDep,
) -> PendingActionOut:
    """Propose an action. Nothing happens until it is approved."""
    trip = await owned_trip(session, user, body.trip_id)
    reject_if_past(trip)

    # Namespaced per user: the column is unique across the whole table, so a
    # bare client UUID would let one account's key collide with another's, and
    # a collision here returns someone else's action. Mirrors the demo seed.
    key = f"{user.user_id}:{idempotency_key}"
    existing = (
        await session.execute(
            select(PendingAction).where(PendingAction.idempotency_key == key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Postcondition first, as everywhere else on this surface: a retry
        # whose response was lost deserves the action, not a conflict.
        return pending_action_to_out(existing, await _reservation_for(session, existing))

    if body.action_type not in IMPLEMENTED_TYPES:
        raise Problem(
            422,
            "Action type not available",
            "action_unsupported",
            f"{body.action_type.value} is not implemented yet.",
        )
    if body.plan_item_id is None:
        raise Problem(
            422,
            "Plan item required",
            "validation_error",
            "A reservation action names the item it is for.",
        )

    item, item_trip = await _owned_item(session, user, body.plan_item_id)
    if item_trip.trip_id != trip.trip_id:
        raise Problem(
            422,
            "Item is not on this trip",
            "validation_error",
            "The plan item belongs to a different trip.",
        )

    if (
        body.action_type is ActionType.make_reservation
        and item.status not in _BOOKABLE_ITEM_STATES
    ):
        raise Problem(
            409,
            "Item is not ready to book",
            "invalid_state",
            f"A {item.status.value} item has not been kept yet. "
            "Answer the suggestion first, then book it.",
        )

    payload = (
        _reservation_payload(item, body)
        if body.action_type is ActionType.make_reservation
        else _cancel_payload(item, body)
    )
    action = PendingAction(
        trip_id=trip.trip_id,
        user_id=user.user_id,
        action_type=body.action_type,
        status=ActionStatus.proposed,
        approval_required=True,
        subject_item_id=item.item_id,
        proposed_payload=payload,
        idempotency_key=key,
        proposed_at=datetime.now(UTC),
    )
    session.add(action)
    await session.commit()
    return pending_action_to_out(action)


@router.get("/actions/{action_id}")
async def get_action(
    action_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PendingActionOut:
    """Polling fallback for the stream, and what the sheet reads on open."""
    action = await _owned_action(session, user, action_id)
    return pending_action_to_out(action, await _reservation_for(session, action))


@router.post("/actions/{action_id}/approve")
async def approve_action(
    action_id: uuid.UUID, body: ApproveIn, user: CurrentUser, session: SessionDep
) -> PendingActionOut:
    """Say yes. The executor picks it up from here; this returns immediately.

    It does not wait for the booking, because the booking takes as long as the
    provider takes. The stream is how the screen follows it.
    """
    action = await _owned_action(session, user, action_id)
    reject_if_past(await owned_trip(session, user, action.trip_id))

    if action.status is ActionStatus.canceled:
        raise Problem(
            409,
            "Action cannot be approved",
            "invalid_state",
            "A canceled action cannot be approved.",
        )
    if action.status not in _APPROVABLE:
        # Already approved, executing, or finished. Approving twice is the same
        # request arriving twice, and the answer is the action it produced --
        # postcondition first, as everywhere else on this surface.
        return pending_action_to_out(action, await _reservation_for(session, action))

    if body.updated_at != action_updated_at(action):
        raise Problem(
            409,
            "Action was modified",
            "conflict",
            "The action changed since you loaded it. Refetch and retry.",
        )

    action.status = ActionStatus.approved
    action.approved_at = datetime.now(UTC)
    # The item is being booked from the moment the user says yes, not from
    # whenever the executor next ticks. Saying so here rather than at submit
    # time is what lets the timeline row show `Booking…` immediately, and what
    # lets the plan query start following it without having to guess.
    if action.action_type is ActionType.make_reservation:
        item = await session.get(PlanItem, action.subject_item_id)
        if item is not None and item.status in _BOOKABLE_ITEM_STATES:
            item.status = ItemStatus.working
            item.updated_at = datetime.now(UTC)
    await session.commit()
    return pending_action_to_out(action, await _reservation_for(session, action))


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def _trace(action: PendingAction, reservation: Reservation | None) -> str:
    """One line of honest progress copy.

    Never in the first person: the product does not speak as "I" (the same
    rule the rest of the UI copy follows), and a booking is something the
    system is doing, not someone talking.
    """
    if action.status is ActionStatus.proposed:
        return "Waiting for your approval."
    if action.status is ActionStatus.approved:
        return "Sending the request."
    if action.status is ActionStatus.executing:
        if reservation is None:
            return "Sending the request."
        return {
            "pending": f"Asking {_place(action)} for the table.",
            "holding": f"{_place(action)} is holding the table.",
        }.get(reservation.status.value, "Working on it.")
    if action.status is ActionStatus.completed:
        if reservation is not None and reservation.confirmation_code:
            return f"Booked. Confirmation {reservation.confirmation_code}."
        return "Done."
    failure = (action.execution_result or {}).get("failure") or {}
    return failure.get("message") or "This did not go through."


def _place(action: PendingAction) -> str:
    return (action.proposed_payload or {}).get("place_name") or "the venue"


@router.get("/actions/{action_id}/events")
async def stream_action_events(
    action_id: uuid.UUID, request: Request, user: CurrentUser, session: SessionDep
) -> StreamingResponse:
    """Server-sent events for one action, until it settles.

    Polls the row rather than listening, per AGENT_DESIGN.md section 14: the
    upgrade to LISTEN/NOTIFY is worth making when the polling cost is real
    rather than imagined. Ownership is checked once, here, before the stream
    opens - a generator that raised would already have sent 200.
    """
    await _owned_action(session, user, action_id)

    async def events():
        from app.db.engine import SessionFactory

        last: tuple[str, str | None] | None = None
        deadline = asyncio.get_running_loop().time() + _STREAM_MAX_SECONDS
        while asyncio.get_running_loop().time() < deadline:
            if await request.is_disconnected():
                return
            # A short session per tick: holding one open for the life of a
            # stream would pin a connection per watching client.
            async with SessionFactory() as poll_session:
                action = await poll_session.get(PendingAction, action_id)
                if action is None:
                    yield _sse("error", {"code": "action_not_found"})
                    return
                reservation = await _reservation_for(poll_session, action)
                signature = (
                    action.status.value,
                    reservation.status.value if reservation else None,
                )
                if signature != last:
                    last = signature
                    yield _sse("status", {"status": action.status.value})
                    yield _sse("trace", {"message": _trace(action, reservation)})
                if action.status in _TERMINAL:
                    yield _sse(
                        "result",
                        pending_action_to_out(action, reservation).model_dump(
                            mode="json", exclude_none=True
                        ),
                    )
                    return
            await asyncio.sleep(_STREAM_POLL_SECONDS)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # Nginx buffers proxied responses by default, which turns a live stream
        # into one delivery at the end. The frontend is served through it.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

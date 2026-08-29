"""Plan reads and the three item gates: accept, choose an option, skip.

Every mutation here follows the pattern confirm_trip established: check the
postcondition first so a retry whose response was lost gets success rather than
409, then require a strict updated_at match, then apply. Nothing is deleted;
declining an item and swapping an option are both state flips.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import ApiRoute, CurrentUser, SessionDep
from app.api.problems import Problem
from app.api.schemas import (
    PlanItemOut,
    PlanOut,
    ProvenanceOut,
    option_to_out,
    plan_item_to_out,
    plan_to_out,
    window_to_out,
)
from app.api.trips import current_plan, owned_trip
from app.db.models import (
    ItemStatus,
    OptionState,
    Plan,
    PlanItem,
    PlanStatus,
    Trip,
    TripState,
)

router = APIRouter(tags=["plan"], route_class=ApiRoute)

# The gates a suggestion can still be answered at. Past them the item has left
# the user's hands: confirmed and working are held by a reservation, and the
# two tombstones are answers already given.
_OPEN_TO_DECISION = frozenset({
    ItemStatus.suggested,
    ItemStatus.awaiting_user,
    ItemStatus.planned,
    ItemStatus.changed,
})
# Accepting means answering the suggestion gate, so only the two undecided
# states reach it; `planned` is handled as an already-satisfied postcondition.
_ACCEPTABLE = frozenset({ItemStatus.suggested, ItemStatus.awaiting_user})
# The plan rollup only moves between these; draft and superseded belong to the
# agent that wrote the version, and nothing a user does should produce them.
_USER_MAINTAINED = frozenset({
    PlanStatus.proposed,
    PlanStatus.partially_accepted,
    PlanStatus.accepted,
})


# A trip that is over. Its plan is a record of what happened, and a record does
# not take edits -- `removed` in particular is filtered out of the retrospective,
# so allowing it here would let a user delete their own history. Mirrors
# `pastStates` in frontend/src/lib/trips.ts; the two must agree.
# `dismissed` is deliberately not here: that trip is not over, it is not
# happening, which is a different question and has no plan to edit anyway.
_PAST_TRIP_STATES = frozenset({TripState.completed, TripState.archived})


def _reject_if_past(trip: Trip) -> None:
    if trip.state in _PAST_TRIP_STATES:
        raise Problem(
            409,
            "Trip is over",
            "trip_past",
            "This trip has ended. Its plan is a record and cannot be changed.",
        )


class ItemTokenIn(BaseModel):
    updated_at: datetime


class SelectOptionIn(ItemTokenIn):
    option_id: uuid.UUID


class SkipIn(ItemTokenIn):
    remove: bool = False


async def _owned_item(session, user, item_id: uuid.UUID) -> tuple[PlanItem, Trip]:
    """The item and its trip, or 404 whether it is missing or someone else's.

    The trip rides along because a mutation has to know the tense: item status
    alone cannot tell a live plan from a finished one.
    """
    stmt = (
        select(PlanItem, Trip)
        .join(Trip, Trip.trip_id == PlanItem.trip_id)
        .where(PlanItem.item_id == item_id, Trip.user_id == user.user_id)
        .options(
            selectinload(PlanItem.options),
            selectinload(PlanItem.window),
            selectinload(PlanItem.reservations),
            # Siblings, so the plan rollup can be recomputed from the items.
            selectinload(PlanItem.plan).selectinload(Plan.items),
        )
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        raise Problem(404, "Plan item not found", "item_not_found")
    return row[0], row[1]


def _raise_conflict() -> None:
    """Staleness is strict token mismatch, as in confirm_trip: `<` would wave
    through a future timestamp, which only clock skew or a bug produces."""
    raise Problem(
        409,
        "Item was modified",
        "conflict",
        "The item changed since you loaded it. Refetch and retry.",
    )


def _require_open(item: PlanItem, verb: str) -> None:
    if item.status not in _OPEN_TO_DECISION:
        raise Problem(
            409,
            f"Item cannot be {verb}",
            "invalid_state",
            f"A {item.status.value} item cannot be {verb}.",
        )


def _recompute_plan_status(plan: Plan) -> None:
    """Keep plans.status honest. It is persisted and queried, never rendered.

    list_trips filters versions on it, so a plan left at `proposed` forever
    would be a lie the trip list reads.
    """
    if plan.status not in _USER_MAINTAINED:
        return
    live = [i for i in plan.items if i.status != ItemStatus.removed]
    undecided = [
        i for i in live if i.status in (ItemStatus.suggested, ItemStatus.awaiting_user)
    ]
    decided = [i for i in live if i.status not in
               (ItemStatus.suggested, ItemStatus.awaiting_user)]
    if not undecided and live:
        plan.status = PlanStatus.accepted
    elif decided:
        plan.status = PlanStatus.partially_accepted
    else:
        plan.status = PlanStatus.proposed


@router.get("/trips/{trip_id}/plan")
async def get_trip_plan(
    trip_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PlanOut:
    await owned_trip(session, user, trip_id)
    plan = await current_plan(session, trip_id)
    if plan is None:
        # A trip with no plan yet is not an error the client can retry into a
        # plan, but it is also not this resource. 404 keeps the two apart.
        raise Problem(
            404,
            "No plan yet",
            "plan_not_found",
            "This trip has no plan. It gets one when the agent activates.",
        )
    return plan_to_out(plan)


@router.post("/trips/{trip_id}/plan/accept-all")
async def accept_all_plan_items(
    trip_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> PlanOut:
    """Answer every open item at once, the way `Accept all` reads.

    Items needing a reservation still land on `planned`, not `awaiting_user`:
    booking is its own gate later, and the review summary is what tells the
    user a reservation is still coming. Accepting is not agreeing to book.
    """
    _reject_if_past(await owned_trip(session, user, trip_id))
    plan = await current_plan(session, trip_id)
    if plan is None:
        raise Problem(
            404,
            "No plan yet",
            "plan_not_found",
            "This trip has no plan. It gets one when the agent activates.",
        )

    now = datetime.now(UTC)
    # Already-decided items are left alone, which is also what makes a retry
    # safe: there is no token here, so the operation has to be idempotent.
    for item in plan.items:
        if item.status in _ACCEPTABLE:
            item.status = ItemStatus.planned
            item.updated_at = now
    _recompute_plan_status(plan)

    await session.commit()
    return plan_to_out(plan)


@router.post("/plan-items/{item_id}/accept")
async def accept_plan_item(
    item_id: uuid.UUID, body: ItemTokenIn, user: CurrentUser, session: SessionDep
) -> PlanItemOut:
    """Take a suggestion into the plan."""
    item, trip = await _owned_item(session, user, item_id)
    _reject_if_past(trip)

    if item.status == ItemStatus.planned:
        # Postcondition first: a lost response leaves the client holding a
        # stale token, and the retry deserves success. No updated_at bump.
        pass
    elif body.updated_at != item.updated_at:
        _raise_conflict()
    elif item.status in _ACCEPTABLE:
        item.status = ItemStatus.planned
        item.updated_at = datetime.now(UTC)
        _recompute_plan_status(item.plan)
    else:
        raise Problem(
            409,
            "Item cannot be accepted",
            "invalid_state",
            f"A {item.status.value} item cannot be accepted.",
        )

    await session.commit()
    return plan_item_to_out(item)


@router.post("/plan-items/{item_id}/select-option")
async def select_plan_item_option(
    item_id: uuid.UUID, body: SelectOptionIn, user: CurrentUser, session: SessionDep
) -> PlanItemOut:
    """Choose which option the item uses. Status is untouched: picking a place
    is not the same act as accepting the suggestion, and the review card lets
    someone swap and only then keep."""
    item, trip = await _owned_item(session, user, item_id)
    _reject_if_past(trip)
    option = next((o for o in item.options if o.option_id == body.option_id), None)
    if option is None:
        raise Problem(
            404,
            "Option not found",
            "option_not_found",
            "That option does not belong to this item.",
        )

    if option.state == OptionState.selected:
        # Postcondition first, as in accept. Nothing was written, so no commit.
        return plan_item_to_out(item)

    if option.state == OptionState.rejected:
        # Ahead of the staleness check because refetching cannot make this
        # request valid: promoting a rejected option would have to clear the
        # rejection_reason a CHECK ties to the state, erasing the text
        # "Also considered" renders.
        raise Problem(
            422,
            "Option was ruled out",
            "option_rejected",
            f"{option.display_name} was rejected: {option.rejection_reason}",
        )

    if body.updated_at != item.updated_at:
        _raise_conflict()
    _require_open(item, "changed")

    current = next(
        (o for o in item.options if o.state == OptionState.selected), None
    )
    if current is not None:
        # plan_item_options_selected_uq is a partial unique index checked per
        # statement, so the demotion has to reach the database before the
        # promotion does.
        current.state = OptionState.alternative
        await session.flush()
    option.state = OptionState.selected
    item.updated_at = datetime.now(UTC)

    await session.commit()
    return plan_item_to_out(item)


@router.post("/plan-items/{item_id}/skip")
async def skip_plan_item(
    item_id: uuid.UUID, body: SkipIn, user: CurrentUser, session: SessionDep
) -> PlanItemOut:
    """Decline an item. `remove` is the stronger form: skipped means not this
    time, removed is a tombstone the agent should not re-offer."""
    item, trip = await _owned_item(session, user, item_id)
    _reject_if_past(trip)
    target = ItemStatus.removed if body.remove else ItemStatus.skipped

    if item.status == target:
        pass  # Postcondition first, as in accept.
    elif body.updated_at != item.updated_at:
        _raise_conflict()
    # Escalation only: skipped may harden into removed, but downgrading a
    # tombstone would re-open a decision the user has now made twice.
    elif item.status in _OPEN_TO_DECISION or (
        item.status == ItemStatus.skipped and target == ItemStatus.removed
    ):
        item.status = target
        item.updated_at = datetime.now(UTC)
        _recompute_plan_status(item.plan)
    else:
        raise Problem(
            409,
            "Item cannot be skipped",
            "invalid_state",
            f"A {item.status.value} item cannot be skipped.",
        )

    await session.commit()
    return plan_item_to_out(item)


@router.get("/plan-items/{item_id}/provenance")
async def get_plan_item_provenance(
    item_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> ProvenanceOut:
    """"How I got here", served from stored rows and never regenerated.

    Unlike PlanItem.options this includes the rejected candidates: they are
    read-only here, which is exactly why they are safe to show.
    """
    # No past-trip gate: reading why a window was there stays legitimate after
    # the fact, and is the whole point of a retrospective.
    item, _ = await _owned_item(session, user, item_id)
    return ProvenanceOut(
        item_id=item.item_id,
        window=window_to_out(item.window) if item.window else None,
        considered=[option_to_out(o) for o in item.options],
    )

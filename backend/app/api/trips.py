"""Trips endpoints: the walking-skeleton read path plus manual create.

needs_you_count, needs_you_kind and plan_progress are computed here with
textual SQL over plan_items and pending_actions (ADR-001 point 3: shaped reads
may skip the ORM), in one pass per user.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.api.deps import ApiRoute, CurrentUser, SessionDep
from app.api.problems import Problem
from app.api.schemas import (
    EMPTY_PROGRESS,
    CalendarEventSummaryOut,
    NeedsYouKind,
    PlanProgress,
    TimelineEntryOut,
    TimelineOut,
    TodayViewOut,
    TripCreateIn,
    TripListOut,
    TripOut,
    TripProgress,
    plan_item_to_out,
    trip_to_out,
    window_to_out,
)
from app.db.models import (
    ItemStatus,
    Plan,
    PlanItem,
    PlanStatus,
    Trip,
    TripOrigin,
    TripState,
    WellnessWindow,
    WindowStatus,
)
from app.services.calendar import LIVE_SQL

router = APIRouter(tags=["trips"], route_class=ApiRoute)

# Everything a trip row renders that cannot be read off the trip itself, in one
# pass: the open-work terms (one per gate -- confirm the trip, decide a
# suggestion, approve an action) and the plan rollup behind the badge. Contract:
# "derived ... never computed client-side".
#
# The plan_items joins go through plans so a superseded version's leftovers
# cannot count; the old query filtered on item status alone.
TRIP_PROGRESS_SQL = text(
    """
    select t.trip_id,
           t.state,
           case when t.state = 'detected' then 1 else 0 end as detection_n,
           coalesce(pi.awaiting_n, 0) as awaiting_n,
           coalesce(pi.working_n, 0) as working_n,
           coalesce(pi.undecided_n, 0) as undecided_n,
           coalesce(pi.live_n, 0) as live_n,
           coalesce(pa.n, 0) as approval_n
    from trips t
    left join (
        select pi.trip_id,
               count(*) filter (where pi.status = 'awaiting_user') as awaiting_n,
               count(*) filter (where pi.status = 'working') as working_n,
               count(*) filter (
                   where pi.status in ('suggested', 'awaiting_user')
               ) as undecided_n,
               count(*) as live_n
        from plan_items pi
        join plans p on p.plan_id = pi.plan_id
        where p.status not in ('draft', 'superseded')
          and pi.status not in ('skipped', 'removed')
        group by pi.trip_id
    ) pi on pi.trip_id = t.trip_id
    left join (
        select trip_id, count(*) as n
        from pending_actions
        where status = 'proposed' and approval_required
        group by trip_id
    ) pa on pa.trip_id = t.trip_id
    where t.user_id = :user_id
    """
)


def _plan_progress(row) -> PlanProgress:
    """The single badge a trip row carries, in precedence order.

    A working state outranks the settled one it will revert to: `Preparing...`
    stands where nothing stood, `Booking...` where `Planned` will stand again.
    That is what keeps a row to one badge instead of one per combination.
    """
    if row.state == TripState.preparing.value:
        return PlanProgress.preparing
    if row.working_n:
        return PlanProgress.booking
    # An empty plan is not an accepted plan, so live_n has to be positive.
    if row.live_n and not row.undecided_n:
        return PlanProgress.planned
    return PlanProgress.none


def _needs_you_kind(row) -> NeedsYouKind | None:
    """Which gate the open work belongs to, so the row can name the ask.

    A detection is its own section rather than a row in the list, so it only
    ever adds to the count here; it never names the kind.
    """
    plan = bool(row.awaiting_n)
    approval = bool(row.approval_n)
    if plan and approval:
        return NeedsYouKind.mixed
    if plan:
        return NeedsYouKind.plan
    if approval:
        return NeedsYouKind.approval
    return None


async def _trip_progress(session, user_id: uuid.UUID) -> dict[uuid.UUID, TripProgress]:
    rows = await session.execute(TRIP_PROGRESS_SQL, {"user_id": user_id})
    return {
        row.trip_id: TripProgress(
            needs_you_count=row.detection_n + row.awaiting_n + row.approval_n,
            needs_you_kind=_needs_you_kind(row),
            plan_progress=_plan_progress(row),
        )
        for row in rows
    }


@router.get("/trips")
async def list_trips(
    user: CurrentUser, session: SessionDep, state: TripState | None = None
) -> TripListOut:
    stmt = (
        select(Trip)
        .where(Trip.user_id == user.user_id)
        .options(selectinload(Trip.evidence))
        .order_by(Trip.start_date)
    )
    if state is not None:
        stmt = stmt.where(Trip.state == state)
    else:
        # Tombstones are invisible unless asked for by name. Filtering here and
        # not per screen is what stops a rejected detection reappearing in the
        # next list someone builds.
        stmt = stmt.where(Trip.state != TripState.dismissed)
    trips = (await session.execute(stmt)).scalars().all()
    progress = await _trip_progress(session, user.user_id)
    return TripListOut(
        trips=[trip_to_out(t, progress.get(t.trip_id, EMPTY_PROGRESS)) for t in trips]
    )


# The Today screen's state line, keyed by trip state (design: dot + word +
# detail, one hue per meaning; the word must match the prototype's stateMap).
_STATE_WORDS: dict[TripState, tuple[str, str | None]] = {
    TripState.detected: ("Detected", "Waiting for your confirmation"),
    TripState.confirmed: ("Upcoming", None),  # detail derived from activation_at
    TripState.upcoming: ("Upcoming", None),
    TripState.preparing: ("Preparing", "Building your plan"),
    TripState.active: ("Active", "Watching for schedule changes"),
    TripState.completed: ("Complete", "Archived"),
    TripState.archived: ("Archived", None),
    TripState.dismissed: ("Dismissed", None),
}

# Timeline and Today never render these; skipped stays visible nowhere per the
# prototype (removed is a backend tombstone).
_HIDDEN_ITEM_STATUSES = (ItemStatus.skipped, ItemStatus.removed)

CALENDAR_EVENTS_SQL = text(
    f"""
    select cal_event_id, title, location, starts_at, ends_at
    from calendar_events
    where trip_id = :trip_id
      and {LIVE_SQL}
      and (cast(:day as date) is null
           or (starts_at at time zone :tz)::date = cast(:day as date))
    order by starts_at
    """
)


async def owned_trip(
    session, user, trip_id: uuid.UUID, *, with_evidence: bool = False
) -> Trip:
    stmt = select(Trip).where(Trip.trip_id == trip_id, Trip.user_id == user.user_id)
    if with_evidence:
        stmt = stmt.options(selectinload(Trip.evidence))
    trip = (await session.execute(stmt)).scalar_one_or_none()
    if trip is None:
        # Same problem for wrong owner and missing row: existence is private.
        raise Problem(404, "Trip not found", "trip_not_found")
    return trip


async def current_plan(session, trip_id: uuid.UUID) -> Plan | None:
    stmt = (
        select(Plan)
        .where(
            Plan.trip_id == trip_id,
            Plan.status != PlanStatus.superseded,
            Plan.status != PlanStatus.draft,
        )
        .order_by(Plan.version.desc())
        .limit(1)
        .options(
            selectinload(Plan.items).selectinload(PlanItem.options),
            # plan_item_to_out embeds the window, and a lazy load under asyncio
            # raises rather than querying, so it has to be loaded here.
            selectinload(Plan.items).selectinload(PlanItem.window),
            selectinload(Plan.items).selectinload(PlanItem.reservations),
        )
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _local_today(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()


def _day_label(trip: Trip, today: date) -> str:
    total = (trip.end_date - trip.start_date).days + 1
    if trip.start_date <= today <= trip.end_date:
        day_n = (today - trip.start_date).days + 1
        return f"{trip.destination_city} · Day {day_n} of {total}"
    if today < trip.start_date:
        until = (trip.start_date - today).days
        return f"{trip.destination_city} in {until} {'day' if until == 1 else 'days'}"
    return f"{trip.destination_city} · trip complete"


@router.get("/trips/{trip_id}")
async def get_trip(
    trip_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> TripOut:
    trip = await owned_trip(session, user, trip_id, with_evidence=True)
    progress = await _trip_progress(session, user.user_id)
    return trip_to_out(trip, progress.get(trip.trip_id, EMPTY_PROGRESS))


@router.get("/trips/{trip_id}/today")
async def get_trip_today(
    trip_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> TodayViewOut:
    trip = await owned_trip(session, user, trip_id)
    today = _local_today(trip.timezone)
    word, detail = _STATE_WORDS[trip.state]
    if detail is None and trip.activation_at is not None and trip.state in (
        TripState.confirmed,
        TripState.upcoming,
    ):
        detail = f"Preparing from {trip.activation_at.astimezone(ZoneInfo(trip.timezone)):%b %d}"

    # Entity-shaped read: ORM with eager loads (ADR-001 point 3 reserves
    # textual SQL for aggregate shapes like needs_you_count).
    window_stmt = (
        select(WellnessWindow)
        .where(
            WellnessWindow.trip_id == trip_id,
            WellnessWindow.local_date == today,
            WellnessWindow.status == WindowStatus.open,
        )
        .order_by(WellnessWindow.starts_at)
        .limit(1)
    )
    window = (await session.execute(window_stmt)).scalar_one_or_none()

    plan = await current_plan(session, trip_id)
    tz = ZoneInfo(trip.timezone)
    next_up = [
        plan_item_to_out(item)
        for item in (plan.items if plan else [])
        if item.status not in _HIDDEN_ITEM_STATUSES
        and item.scheduled_start.astimezone(tz).date() == today
    ]

    return TodayViewOut(
        trip_id=trip.trip_id,
        day_label=_day_label(trip, today),
        state_word=word,
        state_detail=detail,
        timezone=trip.timezone,
        window=window_to_out(window) if window else None,
        next_up=next_up,
    )


@router.get("/trips/{trip_id}/timeline")
async def get_trip_timeline(
    trip_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    day: date | None = None,
) -> TimelineOut:
    trip = await owned_trip(session, user, trip_id)
    tz = ZoneInfo(trip.timezone)

    rows = await session.execute(
        CALENDAR_EVENTS_SQL,
        {"trip_id": trip_id, "tz": trip.timezone, "day": day},
    )
    entries = [
        TimelineEntryOut(
            entry_type="calendar_event",
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            calendar_event=CalendarEventSummaryOut(
                id=row.cal_event_id, title=row.title, location_name=row.location
            ),
        )
        for row in rows
    ]

    plan = await current_plan(session, trip_id)
    entries.extend(
        TimelineEntryOut(
            entry_type="plan_item",
            starts_at=item.scheduled_start,
            ends_at=item.scheduled_end,
            plan_item=plan_item_to_out(item),
        )
        for item in (plan.items if plan else [])
        if item.status not in _HIDDEN_ITEM_STATUSES
        and (day is None or item.scheduled_start.astimezone(tz).date() == day)
    )

    entries.sort(key=lambda e: e.starts_at)
    return TimelineOut(entries=entries)


class TripConfirmIn(BaseModel):
    updated_at: datetime


@router.post("/trips/{trip_id}/confirm")
async def confirm_trip(
    trip_id: uuid.UUID,
    body: TripConfirmIn,
    user: CurrentUser,
    session: SessionDep,
) -> TripOut:
    trip = await owned_trip(session, user, trip_id, with_evidence=True)

    if trip.state == TripState.confirmed:
        # Postcondition first: a retry whose earlier response was lost holds a
        # stale token, and must get success, not 409. No updated_at bump.
        pass
    # Staleness is strict token mismatch, not ordering: `<` would wave through
    # a future timestamp, which only clock skew or a bug produces.
    elif body.updated_at != trip.updated_at:
        raise Problem(
            409,
            "Trip was modified",
            "conflict",
            "The trip changed since you loaded it. Refetch and retry.",
        )
    elif trip.state == TripState.detected:
        trip.state = TripState.confirmed
        # T-7d activation, midnight trip-local; a past activation_at is due
        # immediately, so short-notice trips need no special case.
        local_midnight = datetime.combine(
            trip.start_date - timedelta(days=7), time.min, ZoneInfo(trip.timezone)
        )
        trip.activation_at = local_midnight
        trip.updated_at = datetime.now(UTC)
    else:
        # Every other state has left the confirmable part of the lifecycle;
        # 409 because the conflict is with current state, not request shape.
        raise Problem(
            409,
            "Trip is not confirmable",
            "invalid_state",
            f"A {trip.state.value} trip cannot be confirmed.",
        )

    await session.commit()
    progress = await _trip_progress(session, user.user_id)
    return trip_to_out(trip, progress.get(trip.trip_id, EMPTY_PROGRESS))


@router.post("/trips/{trip_id}/dismiss")
async def dismiss_trip(
    trip_id: uuid.UUID,
    body: TripConfirmIn,
    user: CurrentUser,
    session: SessionDep,
) -> TripOut:
    """"Not a trip". Detection is noisy, so the gate has to open both ways."""
    trip = await owned_trip(session, user, trip_id, with_evidence=True)

    if trip.state == TripState.dismissed:
        # Postcondition first, as in confirm: a retry holding a stale token
        # must get success, not 409.
        pass
    elif body.updated_at != trip.updated_at:
        raise Problem(
            409,
            "Trip was modified",
            "conflict",
            "The trip changed since you loaded it. Refetch and retry.",
        )
    elif trip.state == TripState.detected:
        # A tombstone, not a delete: the row has to outlive the detection so
        # the next calendar sync cannot re-offer what the user rejected.
        trip.state = TripState.dismissed
        trip.updated_at = datetime.now(UTC)
    else:
        # Dismiss only answers the detection gate. Discarding a trip the user
        # already confirmed is a different act and needs its own affordance.
        raise Problem(
            409,
            "Trip is not dismissable",
            "invalid_state",
            f"A {trip.state.value} trip cannot be dismissed.",
        )

    await session.commit()
    progress = await _trip_progress(session, user.user_id)
    return trip_to_out(trip, progress.get(trip.trip_id, EMPTY_PROGRESS))


@router.post("/trips", status_code=status.HTTP_201_CREATED)
async def create_trip(
    body: TripCreateIn,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: Annotated[uuid.UUID, Header(alias="Idempotency-Key")],
) -> TripOut:
    # Idempotency-Key is required by the contract but not yet deduplicated:
    # trips has no idempotency column; the durable mechanism arrives with the
    # pending_actions executor slice.
    city, _, region = body.destination_name.partition(",")
    trip = Trip(
        user_id=user.user_id,
        destination_city=city.strip(),
        destination_region=region.strip() or None,
        # Destination timezone resolution (geocode + tz lookup) is a later
        # slice; the user's home zone is the honest placeholder.
        timezone=user.home_timezone,
        start_date=body.starts_on,
        end_date=body.ends_on,
        hotel_name=body.lodging_name,
        label=body.label,
        state=TripState.confirmed,
        origin=TripOrigin.manual,
    )
    session.add(trip)
    await session.commit()
    await session.refresh(trip, attribute_names=["evidence"])
    return trip_to_out(trip, EMPTY_PROGRESS)

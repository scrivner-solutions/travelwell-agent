"""Trips endpoints: the walking-skeleton read path plus manual create.

needs_you_count is computed here with textual SQL over plan_items and
pending_actions (ADR-001 point 3: shaped reads may skip the ORM). Those
tables exist via the initial migration even though they have no models yet.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, status
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.api.schemas import TripCreateIn, TripListOut, TripOut, trip_to_out
from app.db.models import Trip, TripOrigin, TripState

router = APIRouter(tags=["trips"])

# Open work per trip: plan items waiting on the user + proposed actions that
# need approval. Contract: "derived ... never computed client-side".
NEEDS_YOU_SQL = text(
    """
    select t.trip_id, coalesce(pi.n, 0) + coalesce(pa.n, 0) as needs_you
    from trips t
    left join (
        select trip_id, count(*) as n
        from plan_items
        where status = 'awaiting_user'
        group by trip_id
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


async def _needs_you_counts(session, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
    rows = await session.execute(NEEDS_YOU_SQL, {"user_id": user_id})
    return {row.trip_id: row.needs_you for row in rows}


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
    trips = (await session.execute(stmt)).scalars().all()
    counts = await _needs_you_counts(session, user.user_id)
    return TripListOut(
        trips=[trip_to_out(t, counts.get(t.trip_id, 0)) for t in trips]
    )


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
        state=TripState.confirmed,
        origin=TripOrigin.manual,
    )
    session.add(trip)
    await session.commit()
    await session.refresh(trip, attribute_names=["evidence"])
    return trip_to_out(trip, 0)

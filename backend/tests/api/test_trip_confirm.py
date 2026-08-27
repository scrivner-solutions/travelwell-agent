"""POST /trips/{id}/confirm: the optimistic-concurrency 409 template.

This endpoint is the template every future mutation follows (strict token
mismatch -> conflict; idempotent no-op repeat without a token bump; token
rotates only on a real transition), so the tests spell out each branch.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.asyncio

STALE = "2020-01-01T00:00:00Z"


async def _get_token(client, trip_id) -> str:
    r = await client.get(f"/api/v1/trips/{trip_id}")
    assert r.status_code == 200, r.text
    return r.json()["updated_at"]


async def test_stale_token_conflicts(authed_client, user, make_trip):
    trip = await make_trip(user)
    r = await authed_client.post(
        f"/api/v1/trips/{trip.trip_id}/confirm", json={"updated_at": STALE}
    )
    assert r.status_code == 409
    assert r.json()["code"] == "conflict"


async def test_confirm_transitions_and_rotates_token(
    authed_client, user, make_trip, db_session
):
    from app.db.models import Trip

    trip = await make_trip(user, start_in=30)
    token = await _get_token(authed_client, trip.trip_id)

    r = await authed_client.post(
        f"/api/v1/trips/{trip.trip_id}/confirm", json={"updated_at": token}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "confirmed"
    assert body["updated_at"] != token, "token must rotate on a real transition"

    # Confirming schedules the agent: activation_at lands at midnight
    # trip-local, seven days before the trip starts.
    stored = await db_session.get(Trip, trip.trip_id)
    expected = datetime.combine(
        trip.start_date - timedelta(days=7), time.min, ZoneInfo(trip.timezone)
    )
    assert stored.activation_at == expected


async def test_repeat_confirm_is_idempotent(authed_client, user, make_trip):
    trip = await make_trip(user)
    token = await _get_token(authed_client, trip.trip_id)

    first = await authed_client.post(
        f"/api/v1/trips/{trip.trip_id}/confirm", json={"updated_at": token}
    )
    token2 = first.json()["updated_at"]

    repeat = await authed_client.post(
        f"/api/v1/trips/{trip.trip_id}/confirm", json={"updated_at": token2}
    )
    assert repeat.status_code == 200
    assert repeat.json()["state"] == "confirmed"
    # A no-op must not invalidate tokens other clients hold.
    assert repeat.json()["updated_at"] == token2


async def test_stale_token_conflicts_even_when_already_confirmed(
    authed_client, user, make_trip
):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.confirmed)
    # Token check comes before the idempotent branch: a stale client gets
    # told to refetch even though the postcondition already holds.
    r = await authed_client.post(
        f"/api/v1/trips/{trip.trip_id}/confirm", json={"updated_at": STALE}
    )
    assert r.status_code == 409
    assert r.json()["code"] == "conflict"


@pytest.mark.parametrize(
    "state", ["preparing", "active", "completed", "dismissed"]
)
async def test_non_confirmable_states_conflict(
    authed_client, user, make_trip, state
):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState(state))
    token = await _get_token(authed_client, trip.trip_id)

    r = await authed_client.post(
        f"/api/v1/trips/{trip.trip_id}/confirm", json={"updated_at": token}
    )
    assert r.status_code == 409
    assert r.json()["code"] == "invalid_state"
    assert state in r.json()["detail"]

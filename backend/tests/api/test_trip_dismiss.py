"""POST /trips/{id}/dismiss: the other half of the detection gate.

Same optimistic-concurrency template as confirm (see test_trip_confirm), so
these tests cover what differs: which states dismiss answers, and that the
dismissed row survives as a tombstone rather than disappearing.
"""

import pytest

pytestmark = pytest.mark.asyncio

STALE = "2020-01-01T00:00:00Z"


async def _get_token(client, trip_id) -> str:
    r = await client.get(f"/api/v1/trips/{trip_id}")
    assert r.status_code == 200, r.text
    return r.json()["updated_at"]


async def test_dismiss_transitions_and_rotates_token(authed_client, user, make_trip):
    trip = await make_trip(user)
    token = await _get_token(authed_client, trip.trip_id)

    r = await authed_client.post(
        f"/api/v1/trips/{trip.trip_id}/dismiss", json={"updated_at": token}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "dismissed"
    assert body["updated_at"] != token, "token must rotate on a real transition"
    # The open ask is answered, so the trip stops counting against the user.
    assert body["needs_you_count"] == 0


async def test_dismissed_trip_survives_as_a_tombstone(authed_client, user, make_trip):
    trip = await make_trip(user)
    token = await _get_token(authed_client, trip.trip_id)
    await authed_client.post(
        f"/api/v1/trips/{trip.trip_id}/dismiss", json={"updated_at": token}
    )

    # The row outlives the detection so the next calendar sync cannot re-offer
    # what the user just rejected...
    r = await authed_client.get(f"/api/v1/trips/{trip.trip_id}")
    assert r.status_code == 200
    assert r.json()["state"] == "dismissed"

    listed = await authed_client.get("/api/v1/trips", params={"state": "dismissed"})
    assert [t["id"] for t in listed.json()["trips"]] == [str(trip.trip_id)]

    # ...but it is gone from the default list. Filtering server-side is what
    # keeps it out of every screen, not just the ones that remember to.
    default = await authed_client.get("/api/v1/trips")
    assert str(trip.trip_id) not in [t["id"] for t in default.json()["trips"]]


async def test_stale_token_conflicts(authed_client, user, make_trip):
    trip = await make_trip(user)
    r = await authed_client.post(
        f"/api/v1/trips/{trip.trip_id}/dismiss", json={"updated_at": STALE}
    )
    assert r.status_code == 409
    assert r.json()["code"] == "conflict"


async def test_repeat_dismiss_is_idempotent(authed_client, user, make_trip):
    trip = await make_trip(user)
    token = await _get_token(authed_client, trip.trip_id)

    first = await authed_client.post(
        f"/api/v1/trips/{trip.trip_id}/dismiss", json={"updated_at": token}
    )
    token2 = first.json()["updated_at"]

    repeat = await authed_client.post(
        f"/api/v1/trips/{trip.trip_id}/dismiss", json={"updated_at": token2}
    )
    assert repeat.status_code == 200
    assert repeat.json()["state"] == "dismissed"
    # A no-op must not invalidate tokens other clients hold.
    assert repeat.json()["updated_at"] == token2


async def test_stale_token_succeeds_when_already_dismissed(
    authed_client, user, make_trip
):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.dismissed)
    token = await _get_token(authed_client, trip.trip_id)
    # A retry whose earlier response was lost holds the pre-dismiss token, so
    # the postcondition check must run before the staleness check.
    r = await authed_client.post(
        f"/api/v1/trips/{trip.trip_id}/dismiss", json={"updated_at": STALE}
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "dismissed"
    assert r.json()["updated_at"] == token


@pytest.mark.parametrize("state", ["confirmed", "preparing", "active", "completed"])
async def test_dismiss_only_answers_the_detection_gate(
    authed_client, user, make_trip, state
):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState(state))
    token = await _get_token(authed_client, trip.trip_id)

    # Discarding a trip the user already confirmed is a different act; this
    # endpoint only ever answers "is this a trip?".
    r = await authed_client.post(
        f"/api/v1/trips/{trip.trip_id}/dismiss", json={"updated_at": token}
    )
    assert r.status_code == 409
    assert r.json()["code"] == "invalid_state"
    assert state in r.json()["detail"]


async def test_foreign_trip_is_indistinguishable_from_missing(
    authed_client, other_user, make_trip
):
    foreign = await make_trip(other_user)
    r = await authed_client.post(
        f"/api/v1/trips/{foreign.trip_id}/dismiss", json={"updated_at": STALE}
    )
    assert r.status_code == 404
    assert r.json()["code"] == "trip_not_found"

"""GET /trips and /trips/{id}: shape, ownership privacy, derived counts."""

import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def test_get_trip_shape(authed_client, user, make_trip):
    trip = await make_trip(
        user,
        evidence=[
            ("flight_event", "Calendar", "WN 288 · SFO to AUS", "Round trip · confirmed"),
            ("hotel_email", "Email", "Hotel confirmation", None),
        ],
    )

    r = await authed_client.get(f"/api/v1/trips/{trip.trip_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "detected"
    assert body["destination_name"] == "Denver, CO"
    assert body["state_line"] == "Found in your calendar"
    # A detection is itself an open ask: "is this a trip?" is the first gate.
    assert body["needs_you_count"] == 1
    # source_label display text maps onto the contract's source_kind enum
    assert [e["source"] for e in body["evidence"]] == ["google_calendar", "gmail"]
    # kind passes through verbatim; it drives the FLT/HTL/EVT tag boxes
    assert [e["kind"] for e in body["evidence"]] == ["flight_event", "hotel_email"]
    # detail is the caption under the summary; omitted when there is no caption
    assert [e.get("detail") for e in body["evidence"]] == ["Round trip · confirmed", None]
    assert "detail" not in body["evidence"][1]


async def test_missing_trip_is_404(authed_client):
    r = await authed_client.get(f"/api/v1/trips/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["code"] == "trip_not_found"


async def test_foreign_trip_is_indistinguishable_from_missing(
    authed_client, other_user, make_trip
):
    foreign = await make_trip(other_user)

    r = await authed_client.get(f"/api/v1/trips/{foreign.trip_id}")
    # Existence is private: same status AND same body as a random id, so an
    # attacker cannot probe which trip ids exist.
    missing = await authed_client.get(f"/api/v1/trips/{uuid.uuid4()}")
    assert r.status_code == missing.status_code == 404
    assert r.json() == missing.json()


async def test_list_filters_by_state_and_counts_needs_you(
    authed_client, user, make_trip, scene
):
    await make_trip(user, state=None)  # detected Denver alongside the scene

    r = await authed_client.get("/api/v1/trips")
    assert r.status_code == 200
    trips = {t["destination_name"]: t for t in r.json()["trips"]}
    assert set(trips) == {"Chicago, IL", "Denver, CO"}
    # One term per gate: Chicago's open ask is the scene's awaiting_user dinner,
    # Denver's is the unanswered detection itself.
    assert trips["Chicago, IL"]["needs_you_count"] == 1
    assert trips["Denver, CO"]["needs_you_count"] == 1

    r = await authed_client.get("/api/v1/trips", params={"state": "detected"})
    assert [t["destination_name"] for t in r.json()["trips"]] == ["Denver, CO"]

"""POST /trips: manual creation.

Idempotency-Key is required by the contract but not yet deduplicated (no
idempotency column until the pending_actions executor slice), so these tests
assert the header is demanded, not that repeats collapse.
"""

import uuid

import pytest

pytestmark = pytest.mark.asyncio

BODY = {
    "destination_name": "Austin, TX",
    "starts_on": "2026-09-09",
    "ends_on": "2026-09-12",
}


def _headers() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def test_create_minimal(authed_client, user):
    r = await authed_client.post("/api/v1/trips", json=BODY, headers=_headers())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["state"] == "confirmed"
    assert body["origin"] == "manual"
    assert body["destination_name"] == "Austin, TX"
    # Destination tz resolution is a later slice; home zone is the placeholder.
    assert body["timezone"] == "America/Los_Angeles"
    assert body["starts_on"] == "2026-09-09"
    assert body["ends_on"] == "2026-09-12"
    assert body.get("label") is None
    assert body["needs_you_count"] == 0


async def test_create_with_label_and_lodging(authed_client, user, db_session):
    from app.db.models import Trip

    r = await authed_client.post(
        "/api/v1/trips",
        json={**BODY, "label": "Client visit", "lodging_name": "Hotel Van Zandt"},
        headers=_headers(),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["label"] == "Client visit"
    # Lodging is not in TripOut yet; assert storage directly.
    stored = await db_session.get(Trip, uuid.UUID(body["id"]))
    assert stored.hotel_name == "Hotel Van Zandt"


async def test_city_only_destination_has_no_region(authed_client, user, db_session):
    from app.db.models import Trip

    r = await authed_client.post(
        "/api/v1/trips", json={**BODY, "destination_name": "Lisbon"}, headers=_headers()
    )
    assert r.status_code == 201, r.text
    stored = await db_session.get(Trip, uuid.UUID(r.json()["id"]))
    assert stored.destination_city == "Lisbon"
    assert stored.destination_region is None


async def test_dates_out_of_order_rejected(authed_client, user):
    r = await authed_client.post(
        "/api/v1/trips",
        json={**BODY, "starts_on": "2026-09-12", "ends_on": "2026-09-09"},
        headers=_headers(),
    )
    assert r.status_code == 422


async def test_missing_idempotency_key_rejected(authed_client, user):
    r = await authed_client.post("/api/v1/trips", json=BODY)
    assert r.status_code == 422


async def test_non_uuid_idempotency_key_rejected(authed_client, user):
    r = await authed_client.post(
        "/api/v1/trips", json=BODY, headers={"Idempotency-Key": "not-a-uuid"}
    )
    assert r.status_code == 422

"""GET/PATCH /me/preferences and GET /me/sources: lazy row, merge semantics."""

import pytest

pytestmark = pytest.mark.asyncio


async def test_preferences_default_shape(authed_client):
    r = await authed_client.get("/api/v1/me/preferences")
    assert r.status_code == 200, r.text
    body = r.json()
    for field in ("dietary", "activities", "amenities", "memberships", "preferred_times"):
        assert body[field] == []
    # Unset scalars are omitted from responses, never sent as null (ApiRoute).
    for field in (
        "price_level_max",
        "day_pass_budget_cents",
        "session_min_minutes",
        "session_max_minutes",
    ):
        assert field not in body
    assert body["allow_calendar_write"] is False
    assert body["allow_auto_book"] is False
    assert body["watch_schedule"] is True
    assert body["updated_at"]


async def test_preferences_require_auth(client):
    r = await client.get("/api/v1/me/preferences")
    assert r.status_code == 401
    assert r.json()["code"] == "unauthenticated"


async def test_patch_is_partial(authed_client):
    r = await authed_client.patch(
        "/api/v1/me/preferences",
        json={"activities": ["swim", "running"], "price_level_max": 2},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["activities"] == ["swim", "running"]
    assert body["price_level_max"] == 2
    # Untouched fields keep their defaults.
    assert body["dietary"] == []
    assert body["watch_schedule"] is True

    # And the change persists past the request.
    r = await authed_client.get("/api/v1/me/preferences")
    assert r.json()["activities"] == ["swim", "running"]


async def test_patch_bumps_updated_at(authed_client):
    from datetime import datetime

    before = (await authed_client.get("/api/v1/me/preferences")).json()["updated_at"]
    r = await authed_client.patch(
        "/api/v1/me/preferences", json={"allow_auto_book": True}
    )
    after = r.json()["updated_at"]
    assert datetime.fromisoformat(after) > datetime.fromisoformat(before)


async def test_patch_null_clears_scalar(authed_client):
    await authed_client.patch("/api/v1/me/preferences", json={"price_level_max": 2})
    r = await authed_client.patch(
        "/api/v1/me/preferences", json={"price_level_max": None}
    )
    assert r.status_code == 200, r.text
    assert "price_level_max" not in r.json()


async def test_patch_rejects_out_of_range(authed_client):
    r = await authed_client.patch(
        "/api/v1/me/preferences", json={"price_level_max": 9}
    )
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"


async def test_patch_rejects_min_over_stored_max(authed_client):
    await authed_client.patch(
        "/api/v1/me/preferences", json={"session_max_minutes": 90}
    )
    # The patch body alone looks fine; only the merged row violates the rule.
    r = await authed_client.patch(
        "/api/v1/me/preferences", json={"session_min_minutes": 120}
    )
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_range"

    # The rejected patch must not have half-applied.
    body = (await authed_client.get("/api/v1/me/preferences")).json()
    assert "session_min_minutes" not in body
    assert body["session_max_minutes"] == 90


async def test_sources_empty_and_own_only(authed_client, user, other_user, db_session):
    r = await authed_client.get("/api/v1/me/sources")
    assert r.status_code == 200
    # Spelled out rather than derived from CONNECTABLE_KINDS: a test that
    # computes its expectation from the constant under test asserts nothing.
    assert r.json() == {"sources": [], "connectable": ["google_calendar"]}

    from datetime import UTC, datetime

    from app.db.models import ConnectedSource, SourceKind, SourceStatus

    db_session.add(
        ConnectedSource(
            user_id=user.user_id,
            kind=SourceKind.google_calendar,
            status=SourceStatus.connected,
            secret_ref="mem:placeholder",
            last_synced_at=datetime.now(UTC),
        )
    )
    db_session.add(
        ConnectedSource(
            user_id=other_user.user_id,
            kind=SourceKind.gmail,
            status=SourceStatus.connected,
            secret_ref="mem:other",
        )
    )
    await db_session.commit()

    body = (await authed_client.get("/api/v1/me/sources")).json()
    assert len(body["sources"]) == 1
    src = body["sources"][0]
    assert src["kind"] == "google_calendar"
    assert src["status"] == "connected"
    assert src["connected_at"]
    assert src["last_synced_at"]
    # Independent of the rows: a kind stays offerable while a grant exists, and
    # the other user's gmail row does not make gmail connectable.
    assert body["connectable"] == ["google_calendar"]

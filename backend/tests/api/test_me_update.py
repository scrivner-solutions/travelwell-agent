"""PATCH /me: home timezone and display name on users itself.

home_timezone is NOT NULL with a 'UTC' server default, which doubles as the
"never asked" sentinel. That drives two rules this file pins: an explicit null
is a no-op rather than a clear (unlike the nullable preference scalars), and an
unknown zone is refused before it can be stored, because it later reaches
ZoneInfo() on every /today read.
"""

import pytest

pytestmark = pytest.mark.asyncio

EMAIL = "newcomer@example.com"


async def test_signup_leaves_the_sentinel(client, sent_codes):
    """A real sign-up sets no zone, so the client knows to offer its own."""
    await client.post("/api/v1/auth/email-code", json={"email": EMAIL})
    r = await client.post(
        "/api/v1/auth/email-code/verify",
        json={"email": EMAIL, "code": sent_codes[0][1]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["home_timezone"] == "UTC"


async def test_patch_stores_and_persists_zone(authed_client):
    r = await authed_client.patch(
        "/api/v1/me", json={"home_timezone": "Europe/Berlin"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["home_timezone"] == "Europe/Berlin"

    # And the change survives the request that made it.
    r = await authed_client.get("/api/v1/me")
    assert r.json()["home_timezone"] == "Europe/Berlin"


async def test_patch_accepts_non_canonical_alias(authed_client):
    """Browsers still report link names like Asia/Calcutta; zoneinfo takes them."""
    r = await authed_client.patch(
        "/api/v1/me", json={"home_timezone": "Asia/Calcutta"}
    )
    assert r.status_code == 200, r.text


async def test_patch_rejects_unknown_zone(authed_client):
    r = await authed_client.patch(
        "/api/v1/me", json={"home_timezone": "Mars/Olympus_Mons"}
    )
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"

    # The rejected patch must not have touched the stored zone.
    r = await authed_client.get("/api/v1/me")
    assert r.json()["home_timezone"] == "America/Los_Angeles"


async def test_patch_null_zone_is_a_noop(authed_client):
    """NOT NULL column: null means "leave it", not "clear it" as it does on
    the nullable preference scalars."""
    r = await authed_client.patch(
        "/api/v1/me", json={"display_name": "Kim", "home_timezone": None}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["home_timezone"] == "America/Los_Angeles"
    assert body["display_name"] == "Kim"


async def test_patch_is_partial(authed_client):
    r = await authed_client.patch("/api/v1/me", json={"display_name": "Kim"})
    assert r.status_code == 200, r.text
    # Untouched field keeps its stored value.
    assert r.json()["home_timezone"] == "America/Los_Angeles"


async def test_patch_requires_auth(client):
    r = await client.patch("/api/v1/me", json={"home_timezone": "Europe/Berlin"})
    assert r.status_code == 401
    assert r.json()["code"] == "unauthenticated"

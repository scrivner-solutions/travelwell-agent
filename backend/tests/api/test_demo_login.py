"""Per-tap demo accounts: minting, isolation, the name label, and the flag.

Each demo sign-in creates its own user with the full demo scene
(app/services/demo_scene.py), so testers never share mutable state.
"""

import re

import pytest

pytestmark = pytest.mark.asyncio

DEMO_EMAIL_SHAPE = re.compile(r"^demo-[0-9a-f]{8}@travelwell\.dev$")


async def test_demo_login_mints_account_with_scene(client):
    r = await client.post("/api/v1/auth/demo")

    assert r.status_code == 200, r.text
    body = r.json()
    assert DEMO_EMAIL_SHAPE.match(body["email"])
    assert body["display_name"] == "Demo Traveler"
    assert "twl_session" in client.cookies

    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["email"] == body["email"]

    # The scene arrived with the account: the three demo trips, ready to show.
    trips = (await client.get("/api/v1/trips")).json()["trips"]
    assert {t["destination_name"] for t in trips} == {
        "Chicago, IL",
        "New York, NY",
        "Austin, TX",
    }


async def test_demo_login_uses_given_name(client):
    r = await client.post("/api/v1/auth/demo", json={"name": "  Kim  "})

    assert r.status_code == 200
    assert r.json()["display_name"] == "Kim"


async def test_each_tap_is_its_own_account(client):
    first = (await client.post("/api/v1/auth/demo")).json()
    second = (await client.post("/api/v1/auth/demo")).json()

    assert first["email"] != second["email"]
    # The cookie now belongs to the second account; the first is untouched.
    me = await client.get("/api/v1/me")
    assert me.json()["email"] == second["email"]


async def test_demo_login_explicitly_disabled(client, monkeypatch):
    monkeypatch.setenv("DEMO_LOGIN_ENABLED", "0")

    r = await client.post("/api/v1/auth/demo")

    assert r.status_code == 403
    assert r.json()["code"] == "demo_disabled"
    assert "twl_session" not in client.cookies


async def test_demo_login_defaults_off_outside_dev(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")

    r = await client.post("/api/v1/auth/demo")

    assert r.status_code == 403
    assert r.json()["code"] == "demo_disabled"


async def test_demo_login_opt_in_outside_dev(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DEMO_LOGIN_ENABLED", "1")

    r = await client.post("/api/v1/auth/demo")

    assert r.status_code == 200
    assert "twl_session" in client.cookies

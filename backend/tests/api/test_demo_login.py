"""Per-tap demo accounts: minting, isolation, the name label, and the flag.

Each demo sign-in creates its own user with the full account
(app/services/demo_user/), so testers never share mutable state.
"""

import re

import pytest

from app.services.demo_user import data

pytestmark = pytest.mark.asyncio

DEMO_EMAIL_SHAPE = re.compile(r"^demo-[0-9a-f]{8}@travelwell\.dev$")


async def test_demo_login_mints_a_populated_account(client):
    r = await client.post("/api/v1/auth/demo")

    assert r.status_code == 200, r.text
    body = r.json()
    assert DEMO_EMAIL_SHAPE.match(body["email"])
    assert body["display_name"] == "Demo Traveler"
    assert "twl_session" in client.cookies

    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["email"] == body["email"]

    # Every trip in the roster except the dismissed tombstone, which the list
    # endpoint hides unless asked for by name.
    trips = (await client.get("/api/v1/trips")).json()["trips"]
    assert len(trips) == len(data.TRIPS) - 1
    assert "Nashville, TN" not in {t["destination_name"] for t in trips}


async def test_demo_account_covers_every_badge_the_ui_can_draw(client):
    """The roster exists to make each rendering reachable, not to be pretty.

    A screen showing nothing should mean a bug, so this fails the moment the
    fixture stops exercising one of the states the trip list renders.
    """
    await client.post("/api/v1/auth/demo")
    trips = (await client.get("/api/v1/trips")).json()["trips"]

    assert {t["plan_progress"] for t in trips} == {
        "none",
        "preparing",
        "planned",
        "booking",
    }
    # Absent rather than null when no work is open, so .get is the honest read.
    assert {k for t in trips if (k := t.get("needs_you_kind"))} == {
        "plan",
        "approval",
        "mixed",
    }
    # Detections need two or more before the compact row layout is ever used.
    assert len([t for t in trips if t["state"] == "detected"]) >= 2
    assert {"completed", "archived"} <= {t["state"] for t in trips}


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

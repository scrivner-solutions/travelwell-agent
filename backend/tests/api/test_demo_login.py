"""One-tap demo sign-in and its enable/disable flag matrix.

The `user` fixture creates demo@travelwell.dev — the same account
scripts/seed.py builds — so "seeded" here just means that fixture ran.
"""

import pytest

pytestmark = pytest.mark.asyncio


async def test_demo_login_signs_in(client, user):
    r = await client.post("/api/v1/auth/demo")

    assert r.status_code == 200, r.text
    assert r.json()["email"] == "demo@travelwell.dev"
    assert "twl_session" in client.cookies

    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["email"] == "demo@travelwell.dev"


async def test_demo_login_unseeded_is_503(client):
    r = await client.post("/api/v1/auth/demo")

    assert r.status_code == 503
    assert r.json()["code"] == "demo_unseeded"
    assert "twl_session" not in client.cookies


async def test_demo_login_explicitly_disabled(client, user, monkeypatch):
    monkeypatch.setenv("DEMO_LOGIN_ENABLED", "0")

    r = await client.post("/api/v1/auth/demo")

    assert r.status_code == 403
    assert r.json()["code"] == "demo_disabled"
    assert "twl_session" not in client.cookies


async def test_demo_login_defaults_off_outside_dev(client, user, monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")

    r = await client.post("/api/v1/auth/demo")

    assert r.status_code == 403
    assert r.json()["code"] == "demo_disabled"


async def test_demo_login_opt_in_outside_dev(client, user, monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DEMO_LOGIN_ENABLED", "1")

    r = await client.post("/api/v1/auth/demo")

    assert r.status_code == 200
    assert "twl_session" in client.cookies

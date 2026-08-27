"""Email-code sign-in flow, cookie lifecycle, and problem-shaped 401s."""

import pytest

pytestmark = pytest.mark.asyncio

EMAIL = "kim@example.com"


def _dev_code(email: str) -> str:
    # No email provider is wired yet; the code lives in the in-process store
    # the endpoint writes to (and logs). Reading it here mirrors what a
    # developer does with the server log.
    from app.api import sessions

    return sessions._codes[email][0]


async def test_full_sign_in_flow(client):
    r = await client.post("/api/v1/auth/email-code", json={"email": EMAIL})
    assert r.status_code == 202

    r = await client.post(
        "/api/v1/auth/email-code/verify",
        json={"email": EMAIL, "code": _dev_code(EMAIL)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["email"] == EMAIL
    assert "twl_session" in client.cookies

    r = await client.get("/api/v1/me")
    assert r.status_code == 200
    assert r.json()["email"] == EMAIL

    r = await client.post("/api/v1/auth/logout")
    assert r.status_code == 204
    assert "twl_session" not in client.cookies

    r = await client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.json()["code"] == "unauthenticated"
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_wrong_code_rejected(client):
    await client.post("/api/v1/auth/email-code", json={"email": EMAIL})
    real = _dev_code(EMAIL)
    wrong = "000000" if real != "000000" else "111111"

    r = await client.post(
        "/api/v1/auth/email-code/verify", json={"email": EMAIL, "code": wrong}
    )
    assert r.status_code == 400
    assert r.json()["code"] == "code_invalid"
    assert "twl_session" not in client.cookies


async def test_trips_requires_auth(client):
    r = await client.get("/api/v1/trips")
    assert r.status_code == 401
    assert r.json()["code"] == "unauthenticated"

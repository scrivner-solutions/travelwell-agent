"""Email-code sign-in flow, cookie lifecycle, and problem-shaped 401s."""

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.asyncio

EMAIL = "kim@example.com"


async def test_full_sign_in_flow(client, sent_codes):
    r = await client.post("/api/v1/auth/email-code", json={"email": EMAIL})
    assert r.status_code == 202
    assert sent_codes == [(EMAIL, sent_codes[0][1])]

    r = await client.post(
        "/api/v1/auth/email-code/verify",
        json={"email": EMAIL, "code": sent_codes[0][1]},
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


def _wrong(real: str) -> str:
    return "000000" if real != "000000" else "111111"


async def test_wrong_code_rejected(client, sent_codes):
    await client.post("/api/v1/auth/email-code", json={"email": EMAIL})
    real = sent_codes[0][1]

    r = await client.post(
        "/api/v1/auth/email-code/verify", json={"email": EMAIL, "code": _wrong(real)}
    )
    assert r.status_code == 400
    assert r.json()["code"] == "code_invalid"
    assert "twl_session" not in client.cookies


async def test_code_is_single_use(client, sent_codes):
    await client.post("/api/v1/auth/email-code", json={"email": EMAIL})
    code = sent_codes[0][1]
    body = {"email": EMAIL, "code": code}

    assert (await client.post("/api/v1/auth/email-code/verify", json=body)).status_code == 200
    client.cookies.clear()
    r = await client.post("/api/v1/auth/email-code/verify", json=body)
    assert r.status_code == 400


async def test_attempt_cap_consumes_code(client, sent_codes):
    from app.api.login_codes import CODE_MAX_ATTEMPTS

    await client.post("/api/v1/auth/email-code", json={"email": EMAIL})
    real = sent_codes[0][1]

    for _ in range(CODE_MAX_ATTEMPTS):
        r = await client.post(
            "/api/v1/auth/email-code/verify",
            json={"email": EMAIL, "code": _wrong(real)},
        )
        assert r.status_code == 400

    # The cap is spent, so even the real code no longer signs in.
    r = await client.post(
        "/api/v1/auth/email-code/verify", json={"email": EMAIL, "code": real}
    )
    assert r.status_code == 400


async def test_expired_code_rejected(client, sent_codes, db_session):
    await client.post("/api/v1/auth/email-code", json={"email": EMAIL})
    code = sent_codes[0][1]

    await db_session.execute(
        sa.text("update login_codes set expires_at = now() - interval '1 second'")
    )
    await db_session.commit()

    r = await client.post(
        "/api/v1/auth/email-code/verify", json={"email": EMAIL, "code": code}
    )
    assert r.status_code == 400


async def test_resend_cooldown_then_reissue(client, sent_codes, db_session):
    # Second request inside the cooldown sends nothing (still answers 202).
    await client.post("/api/v1/auth/email-code", json={"email": EMAIL})
    r = await client.post("/api/v1/auth/email-code", json={"email": EMAIL})
    assert r.status_code == 202
    assert len(sent_codes) == 1
    first = sent_codes[0][1]

    await db_session.execute(
        sa.text("update login_codes set created_at = now() - interval '2 minutes'")
    )
    await db_session.commit()

    # Past the cooldown a new code is issued and the old one is dead.
    await client.post("/api/v1/auth/email-code", json={"email": EMAIL})
    assert len(sent_codes) == 2
    second = sent_codes[1][1]

    if first != second:  # 1-in-a-million collision would void the assertion
        r = await client.post(
            "/api/v1/auth/email-code/verify", json={"email": EMAIL, "code": first}
        )
        assert r.status_code == 400
    r = await client.post(
        "/api/v1/auth/email-code/verify", json={"email": EMAIL, "code": second}
    )
    assert r.status_code == 200


async def test_trips_requires_auth(client):
    r = await client.get("/api/v1/trips")
    assert r.status_code == 401
    assert r.json()["code"] == "unauthenticated"

"""Google OAuth sign-in flow and the ALLOWED_SIGNIN_EMAILS staging gate.

The token exchange is stubbed at the Authlib class boundary
(authorize_access_token), so these tests cover everything on our side of the
wire: redirect construction, state cookie, user upsert, allowlist, and the
error redirects the callback hands the browser.
"""

from urllib.parse import parse_qs, urlsplit

import pytest
import sqlalchemy as sa
from authlib.integrations.starlette_client import OAuthError, StarletteOAuth2App

pytestmark = pytest.mark.asyncio

CALLBACK = "/api/v1/auth/oauth/google/callback?code=fake&state=fake"


@pytest.fixture
def google_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")


@pytest.fixture
def google_login(google_env, monkeypatch):
    """Stub the provider round-trip; returns an installer taking the userinfo."""

    def _install(userinfo=None, error=False):
        async def fake_authorize_access_token(self, request):
            if error:
                raise OAuthError(error="access_denied")
            return {"access_token": "fake", "userinfo": userinfo}

        monkeypatch.setattr(
            StarletteOAuth2App,
            "authorize_access_token",
            fake_authorize_access_token,
        )

    return _install


async def _user_rows(db_session):
    from app.db.models import User

    return (await db_session.execute(sa.select(User))).scalars().all()


async def test_start_redirects_to_google(client, google_env):
    r = await client.get("/api/v1/auth/oauth/google/start")

    assert r.status_code == 302
    url = urlsplit(r.headers["location"])
    assert (url.scheme, url.netloc) == ("https", "accounts.google.com")
    query = parse_qs(url.query)
    assert query["client_id"] == ["test-client-id"]
    assert query["redirect_uri"] == [
        "http://localhost:5173/api/v1/auth/oauth/google/callback"
    ]
    assert "openid" in query["scope"][0]
    assert query["state"][0]
    # The state authlib checks at the callback rides in its own cookie.
    assert "twl_oauth" in client.cookies


async def test_start_unconfigured_is_503(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

    r = await client.get("/api/v1/auth/oauth/google/start")

    assert r.status_code == 503
    assert r.json()["code"] == "oauth_unconfigured"


async def test_unknown_provider_is_404(client, google_env):
    r = await client.get("/api/v1/auth/oauth/apple/start")

    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


async def test_callback_signs_in_new_user(client, google_login, db_session):
    google_login({"email": "kim@example.com", "email_verified": True, "name": "Kim"})

    r = await client.get(CALLBACK)

    assert r.status_code == 302
    assert r.headers["location"] == "http://localhost:5173/"
    assert "twl_session" in client.cookies

    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["email"] == "kim@example.com"

    (row,) = await _user_rows(db_session)
    assert row.auth_provider.value == "google"
    assert row.display_name == "Kim"


async def test_callback_matches_existing_email_user(
    client, google_login, user, db_session
):
    google_login({"email": user.email, "email_verified": True, "name": "Someone"})

    r = await client.get(CALLBACK)

    assert r.status_code == 302
    me = await client.get("/api/v1/me")
    assert me.json()["email"] == user.email

    (row,) = await _user_rows(db_session)
    assert row.user_id == user.user_id
    # Original account is untouched, not converted.
    assert row.auth_provider.value == "email"
    assert row.display_name == "Test Traveler"


async def test_callback_rejects_unverified_email(client, google_login, db_session):
    google_login({"email": "kim@example.com", "email_verified": False})

    r = await client.get(CALLBACK)

    assert r.status_code == 302
    assert r.headers["location"].endswith("/sign-in?error=oauth_failed")
    assert "twl_session" not in client.cookies
    assert await _user_rows(db_session) == []


async def test_callback_enforces_allowlist(
    client, google_login, monkeypatch, db_session
):
    monkeypatch.setenv("ALLOWED_SIGNIN_EMAILS", "invited@example.com")
    google_login({"email": "stranger@example.com", "email_verified": True})

    r = await client.get(CALLBACK)

    assert r.status_code == 302
    assert r.headers["location"].endswith("/sign-in?error=not_allowed")
    assert "twl_session" not in client.cookies
    assert await _user_rows(db_session) == []


async def test_callback_handshake_failure_redirects(client, google_login):
    google_login(error=True)

    r = await client.get(CALLBACK)

    assert r.status_code == 302
    assert r.headers["location"].endswith("/sign-in?error=oauth_failed")
    assert "twl_session" not in client.cookies


async def test_email_code_respects_allowlist(client, monkeypatch, sent_codes, db_session):
    import sqlalchemy as sa

    monkeypatch.setenv("ALLOWED_SIGNIN_EMAILS", "invited@example.com")

    r = await client.post(
        "/api/v1/auth/email-code", json={"email": "stranger@example.com"}
    )
    # Still 202 so the allowlist cannot be probed; no code is ever issued.
    assert r.status_code == 202
    assert sent_codes == []
    assert (
        await db_session.scalar(sa.text("select count(*) from login_codes"))
    ) == 0

    r = await client.post(
        "/api/v1/auth/email-code/verify",
        json={"email": "stranger@example.com", "code": "000000"},
    )
    assert r.status_code == 400

"""The calendar connect handshake, disconnect, and what each one refuses.

The token exchange is stubbed at the Authlib class boundary the way
test_oauth.py stubs sign-in, so everything on our side of the wire is covered:
the parameters the redirect carries, the four ways a grant can come back
unusable, what lands in the database, and what disconnect destroys.

The refusals are the point of most of this file. A calendar grant that arrives
without a refresh token, or with the scope unchecked, still arrives as a
success from Google - and would read as a working connection until the first
background sync, which is a long way from the consent screen that caused it.
"""

from urllib.parse import parse_qs, urlsplit

import pytest
import pytest_asyncio
import sqlalchemy as sa
from authlib.integrations.starlette_client import OAuthError, StarletteOAuth2App
from sqlalchemy.exc import IntegrityError

from app.api.sources import CALENDAR_SCOPE, SECRET_KIND
from app.db.models import ConnectedSource, SourceKind, SourceStatus
from app.services.tokens import SecretNotFound, token_store

pytestmark = pytest.mark.asyncio

CONNECT = "/api/v1/me/sources/google_calendar/connect"
CALLBACK = "/api/v1/me/sources/google_calendar/callback?code=fake&state=fake"
KEY_HEX = bytes(range(32)).hex()


@pytest.fixture
def google_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", KEY_HEX)


@pytest.fixture
def granted(google_env, monkeypatch):
    """Stub Google's token response; returns an installer taking the token."""

    def _install(
        refresh_token="refresh-abc", scope=CALENDAR_SCOPE, error=False
    ):
        async def fake_authorize_access_token(self, request):
            if error:
                raise OAuthError(error="access_denied")
            token = {"access_token": "access-abc", "scope": scope}
            if refresh_token is not None:
                token["refresh_token"] = refresh_token
            return token

        monkeypatch.setattr(
            StarletteOAuth2App,
            "authorize_access_token",
            fake_authorize_access_token,
        )

    return _install


@pytest_asyncio.fixture
async def sources(db_session):
    async def _rows():
        return (
            (await db_session.execute(sa.select(ConnectedSource))).scalars().all()
        )

    return _rows


def _error(response) -> str:
    return parse_qs(urlsplit(response.headers["location"]).query)["connect_error"][0]


# --- starting the handshake -----------------------------------------------


async def test_connect_asks_google_for_a_durable_grant(authed_client, google_env):
    r = await authed_client.get(CONNECT)

    assert r.status_code == 302
    url = urlsplit(r.headers["location"])
    assert (url.scheme, url.netloc) == ("https", "accounts.google.com")
    query = parse_qs(url.query)
    # Both, or Google returns an access token that expires in an hour.
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["redirect_uri"] == [
        "http://localhost:5173/api/v1/me/sources/google_calendar/callback"
    ]
    assert query["state"][0]


async def test_connect_asks_for_the_calendar_scope_and_nothing_else(
    authed_client, google_env
):
    r = await authed_client.get(CONNECT)

    scopes = parse_qs(urlsplit(r.headers["location"]).query)["scope"][0].split()
    # Sign-in's scopes must not ride along: revoking the calendar would
    # otherwise take the ability to sign in with it.
    assert scopes == [CALENDAR_SCOPE]


async def test_connect_requires_a_signed_in_user(client, google_env):
    r = await client.get(CONNECT)

    assert r.status_code == 401
    assert r.json()["code"] == "unauthenticated"


async def test_connect_without_google_credentials_is_503(authed_client, monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", KEY_HEX)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

    r = await authed_client.get(CONNECT)

    assert r.status_code == 503
    assert r.json()["code"] == "oauth_unconfigured"


async def test_connect_refuses_before_google_when_no_key_is_configured(
    authed_client, google_env, monkeypatch
):
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)

    r = await authed_client.get(CONNECT)

    # Refused here rather than at the callback, so the user does not complete a
    # consent screen whose result we were never able to keep.
    assert r.status_code == 503
    assert r.json()["code"] == "token_store_unconfigured"


async def test_an_unsupported_source_kind_is_404(authed_client, google_env):
    r = await authed_client.get("/api/v1/me/sources/gmail/connect")

    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


# --- coming back ----------------------------------------------------------


async def test_callback_stores_the_grant_and_the_refresh_token(
    authed_client, user, db_session, granted, sources
):
    granted()

    r = await authed_client.get(CALLBACK)

    assert r.status_code == 302
    assert r.headers["location"].endswith("/profile?connected=google_calendar")

    (source,) = await sources()
    assert source.user_id == user.user_id
    assert source.status is SourceStatus.connected
    assert source.scopes == [CALENDAR_SCOPE]
    assert source.secret_ref
    # The reference is only worth having if it leads back to the token.
    assert await token_store(db_session).get(source.secret_ref) == "refresh-abc"


async def test_a_grant_with_no_refresh_token_is_refused(
    authed_client, granted, sources
):
    granted(refresh_token=None)

    r = await authed_client.get(CALLBACK)

    assert _error(r) == "no_refresh_token"
    # Nothing is recorded: a source row here would say connected and could not
    # survive the hour.
    assert await sources() == []


async def test_a_declined_scope_is_refused(authed_client, granted, sources):
    granted(scope="openid email")

    r = await authed_client.get(CALLBACK)

    assert _error(r) == "scope_declined"
    assert await sources() == []


async def test_a_failed_exchange_redirects_rather_than_erroring(
    authed_client, granted, sources
):
    granted(error=True)

    r = await authed_client.get(CALLBACK)

    assert r.status_code == 302
    assert _error(r) == "oauth_failed"
    assert await sources() == []


async def test_callback_requires_a_signed_in_user(client, granted):
    granted()

    r = await client.get(CALLBACK)

    # SameSite=Lax sends the session cookie on Google's redirect, so a missing
    # one means signed out, not a browser quirk.
    assert r.status_code == 401


async def test_reconsent_updates_the_one_grant_rather_than_adding_another(
    authed_client, db_session, granted, sources
):
    granted(refresh_token="refresh-first")
    await authed_client.get(CALLBACK)
    (first,) = await sources()

    granted(refresh_token="refresh-second")
    await authed_client.get(CALLBACK)

    rows = await sources()
    assert len(rows) == 1
    # Google mints a fresh refresh token on every consent; the reference the
    # row holds has to keep pointing at the current one.
    assert rows[0].secret_ref == first.secret_ref
    assert await token_store(db_session).get(rows[0].secret_ref) == "refresh-second"


# --- disconnecting --------------------------------------------------------


async def test_disconnect_destroys_the_token_and_keeps_the_row(
    authed_client, db_session, granted, sources
):
    granted()
    await authed_client.get(CALLBACK)
    (source,) = await sources()
    secret_ref = source.secret_ref

    r = await authed_client.delete("/api/v1/me/sources/google_calendar")

    assert r.status_code == 204
    await db_session.refresh(source)
    assert source.status is SourceStatus.revoked
    # Cleared, or the row points at a secret that is gone.
    assert source.secret_ref is None
    with pytest.raises(SecretNotFound):
        await token_store(db_session).get(secret_ref)


async def test_disconnect_is_idempotent(authed_client, granted):
    granted()
    await authed_client.get(CALLBACK)

    first = await authed_client.delete("/api/v1/me/sources/google_calendar")
    second = await authed_client.delete("/api/v1/me/sources/google_calendar")

    assert (first.status_code, second.status_code) == (204, 204)


async def test_disconnecting_something_never_connected_is_404(authed_client):
    r = await authed_client.delete("/api/v1/me/sources/google_calendar")

    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


async def test_a_revoked_source_still_appears_in_the_list(authed_client, granted):
    granted()
    await authed_client.get(CALLBACK)
    await authed_client.delete("/api/v1/me/sources/google_calendar")

    r = await authed_client.get("/api/v1/me/sources")

    # Disappearing would read as "never connected", which is a different fact.
    assert [s["status"] for s in r.json()["sources"]] == ["revoked"]


async def test_the_secret_kind_is_stable(authed_client, user, db_session, granted):
    """The kind is the store's address for this token; changing it orphans
    every grant already stored under the old one."""
    granted()
    await authed_client.get(CALLBACK)

    assert SECRET_KIND == "google_calendar_refresh_token"
    from app.services.tokens.encrypted_db import EncryptedDatabaseTokenStore

    store = EncryptedDatabaseTokenStore(db_session)
    ref = await store.put(user.user_id, SECRET_KIND, "refresh-abc")
    (source,) = (
        (await db_session.execute(sa.select(ConnectedSource))).scalars().all()
    )
    assert ref == source.secret_ref


async def test_a_connected_grant_cannot_exist_without_a_token(db_session, user):
    """The database refuses the row, not just the code paths that build it.

    Every writer here already sets status and secret_ref together, so this is
    about the writer that does not exist yet: a `connected` row with nothing
    behind it reads as a working calendar everywhere and fails only at sync.
    """
    db_session.add(
        ConnectedSource(
            user_id=user.user_id,
            kind=SourceKind.google_calendar,
            status=SourceStatus.connected,
        )
    )
    with pytest.raises(IntegrityError, match="connected_sources_check"):
        await db_session.commit()
    await db_session.rollback()

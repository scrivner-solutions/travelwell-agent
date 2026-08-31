"""Connecting a calendar: the durable OAuth grant, kept apart from sign-in.

Signing in with Google and connecting a Google Calendar look like the same
handshake and are not. Sign-in wants an identity once. A connection wants a
refresh token that outlives the browser, so it asks for `access_type=offline`
and `prompt=consent`; without both, Google hands back an access token good for
an hour and no way to renew it, and the connection looks like it worked right
up until the first background sync.

They are also deliberately separated. The scopes never mix, so revoking the
calendar cannot take sign-in down with it and the token stored here can never
be used to impersonate the user. The Authlib client is registered under its own
name for the same reason: handshake state lives in the session keyed by client
name, so a connect started while a sign-in is in flight does not overwrite it.

The callback needs to know who is connecting, and it can. The session cookie is
SameSite=Lax, which browsers do send on a top-level GET navigation, and Google's
redirect back to us is exactly that.
"""

import logging
import os
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api import auth
from app.api.deps import ApiRoute, CurrentUser, SessionDep
from app.api.problems import Problem
from app.api.schemas import SyncOut
from app.db.models import ConnectedSource, SourceKind, SourceStatus
from app.services.calendar import (
    CalendarUnavailable,
    CredentialRejected,
    calendar_client,
    sync_source,
)
from app.services.tokens import KeyUnavailable, SecretNotFound, token_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["profile"], route_class=ApiRoute)

# Reading events, and nothing else. Not `calendar.readonly`, which also exposes
# calendar metadata and settings we have no use for.
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"

# What the token store files this secret under. Per (user, kind), which is what
# makes re-consent an update rather than an orphaned row.
SECRET_KIND = "google_calendar_refresh_token"

# Its own Authlib registration, sharing the console client with sign-in but not
# its scopes or its handshake state.
_CLIENT_NAME = "google_calendar"

# The other three SourceKind values are vocabulary the schema already has, not
# integrations that exist.
_SUPPORTED = frozenset({SourceKind.google_calendar})

# How much calendar a sync pulls. Yesterday, because a trip in progress has a
# timeline that started before now; ninety days, because that is past the
# booking horizon any plan currently reasons about, and fetching a year of a
# busy calendar to answer questions about next month is pure cost.
SYNC_PAST = timedelta(days=1)
SYNC_FUTURE = timedelta(days=90)


def _kind_or_404(kind: SourceKind) -> None:
    if kind not in _SUPPORTED:
        raise Problem(404, "That source cannot be connected yet", "not_found")


def _calendar_client():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise Problem(503, "Google Calendar is not configured", "oauth_unconfigured")
    return OAuth().register(
        name=_CLIENT_NAME,
        client_id=client_id,
        client_secret=client_secret,
        client_kwargs={"scope": CALENDAR_SCOPE},
        # Only the two endpoints this flow uses. There is no id_token here, so
        # naming the OIDC ones would advertise a capability the client lacks.
        authorize_url=auth._GOOGLE_OIDC["authorize_url"],
        access_token_url=auth._GOOGLE_OIDC["access_token_url"],
    )


def _redirect_uri(kind: SourceKind) -> str:
    # Must match a redirect URI registered on the console client, character for
    # character. This is the literal string that ask is for.
    return f"{auth._public_base_url()}/api/v1/me/sources/{kind.value}/callback"


def _require_store(session: SessionDep):
    try:
        return token_store(session)
    except KeyUnavailable as exc:
        raise Problem(
            503,
            "Calendar connection is not configured",
            "token_store_unconfigured",
        ) from exc


async def _upsert_source(
    session: SessionDep,
    user_id,
    kind: SourceKind,
    secret_ref: str,
    scopes: list[str],
) -> None:
    """Re-consent updates the existing grant rather than adding a second one.

    `last_synced_at` is deliberately not cleared: re-granting access to the same
    calendar does not make the events we already cached wrong.
    """
    await session.execute(
        pg_insert(ConnectedSource)
        .values(
            user_id=user_id,
            kind=kind,
            status=SourceStatus.connected,
            scopes=scopes,
            secret_ref=secret_ref,
        )
        .on_conflict_do_update(
            constraint="connected_sources_user_id_kind_key",
            set_={
                "status": SourceStatus.connected,
                "scopes": scopes,
                "secret_ref": secret_ref,
            },
        )
    )


# status_code only documents the redirect the handler already returns; FastAPI
# cannot infer it from RedirectResponse and would otherwise declare a 200.
@router.get("/me/sources/{kind}/connect", status_code=status.HTTP_302_FOUND)
async def connect_source(
    kind: SourceKind, request: Request, user: CurrentUser, session: SessionDep
) -> RedirectResponse:
    _kind_or_404(kind)
    # Checked before the user goes to Google, not after: a grant we cannot store
    # is a consent screen the user has to sit through twice.
    _require_store(session)
    return await _calendar_client().authorize_redirect(
        request,
        _redirect_uri(kind),
        # Both are required. `offline` asks for a refresh token at all;
        # `consent` is what makes Google re-issue one on a repeat grant, where
        # it otherwise returns only an access token and no error.
        access_type="offline",
        prompt="consent",
    )


@router.get("/me/sources/{kind}/callback", status_code=status.HTTP_302_FOUND)
async def connect_callback(
    kind: SourceKind, request: Request, user: CurrentUser, session: SessionDep
) -> RedirectResponse:
    _kind_or_404(kind)
    base = auth._public_base_url()

    def failed(code: str) -> RedirectResponse:
        return RedirectResponse(f"{base}/profile?connect_error={code}", status_code=302)

    try:
        store = _require_store(session)
    except Problem:
        logger.error("Calendar grant obtained but no token store is configured")
        return failed("token_store_unconfigured")

    try:
        token = await _calendar_client().authorize_access_token(request)
    except OAuthError:
        logger.warning("Calendar connect callback failed", exc_info=True)
        return failed("oauth_failed")

    # Google returns what was actually granted, which is not always what was
    # asked for: the consent screen lets a user uncheck a scope, and the grant
    # then succeeds and is useless.
    granted = sorted(set((token.get("scope") or "").split()))
    if CALENDAR_SCOPE not in granted:
        return failed("scope_declined")

    refresh_token = token.get("refresh_token")
    if not refresh_token:
        # Storing the access token instead would connect for an hour. Refusing
        # here is what keeps a broken connection from being indistinguishable
        # from a working one.
        logger.warning("Calendar grant carried no refresh token; refusing to connect")
        return failed("no_refresh_token")

    secret_ref = await store.put(user.user_id, SECRET_KIND, refresh_token)
    await _upsert_source(session, user.user_id, kind, secret_ref, granted)
    # One transaction: a secret with no grant pointing at it is unreachable, and
    # a grant pointing at a secret that was never written is broken.
    await session.commit()
    return RedirectResponse(f"{base}/profile?connected={kind.value}", status_code=302)


@router.delete("/me/sources/{kind}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_source(
    kind: SourceKind, user: CurrentUser, session: SessionDep
) -> Response:
    """Forget the token and mark the grant revoked, keeping the row.

    The row is the record that a connection existed, which is what lets
    /me/sources say "disconnected" instead of silently showing nothing, and what
    explains the calendar_events still in the cache.

    Revoking at Google's end is deliberately not done here. It is an outbound
    HTTP call, and the seam that owns outbound calls to Google is the calendar
    client, which does not exist yet. Until then the local token is destroyed,
    so the grant is unusable by us whether or not Google still lists it.
    """
    _kind_or_404(kind)
    source = (
        await session.execute(
            sa.select(ConnectedSource).where(
                ConnectedSource.user_id == user.user_id,
                ConnectedSource.kind == kind,
            )
        )
    ).scalar_one_or_none()
    if source is None:
        raise Problem(404, "That source is not connected", "not_found")

    if source.secret_ref is not None:
        await _require_store(session).delete(source.secret_ref)
        source.secret_ref = None
    source.status = SourceStatus.revoked
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _connected_source(
    session: SessionDep, user_id, kind: SourceKind
) -> ConnectedSource:
    source = (
        await session.execute(
            sa.select(ConnectedSource).where(
                ConnectedSource.user_id == user_id,
                ConnectedSource.kind == kind,
            )
        )
    ).scalar_one_or_none()
    if source is None:
        raise Problem(404, "That source is not connected", "not_found")
    return source


@router.post("/me/sources/{kind}/sync")
async def sync_connected_source(
    kind: SourceKind, user: CurrentUser, session: SessionDep
) -> SyncOut:
    """Pull a window of the calendar into the cache, now.

    Explicit rather than scheduled, because there is no scheduler yet and a
    feature nobody can trigger cannot be shown to work. Whatever runs this on a
    timer later calls the same service.
    """
    _kind_or_404(kind)
    source = await _connected_source(session, user.user_id, kind)
    if source.status is SourceStatus.revoked or source.secret_ref is None:
        raise Problem(
            409,
            "That source is disconnected",
            "source_disconnected",
            "Connect it again before syncing.",
        )

    try:
        refresh_token = await _require_store(session).get(source.secret_ref)
    except SecretNotFound as exc:
        # The row points at a secret that is gone, so the grant is unusable
        # even though the row says connected. Saying so beats a 500.
        source.status = SourceStatus.error
        await session.commit()
        raise Problem(
            409,
            "That source needs reconnecting",
            "source_needs_reconnect",
            "The stored credential is missing.",
        ) from exc

    now = datetime.now(UTC)
    try:
        result = await sync_source(
            session,
            source,
            calendar_client(refresh_token),
            start=now - SYNC_PAST,
            end=now + SYNC_FUTURE,
        )
    except CredentialRejected as exc:
        # sync_source marked the source `error`; committing is what keeps that,
        # and it is the half of this failure worth persisting.
        await session.commit()
        raise Problem(
            409,
            "That source needs reconnecting",
            "source_needs_reconnect",
            "Google no longer accepts the stored grant.",
        ) from exc
    except CalendarUnavailable as exc:
        # Transient and the grant is still good, so the source is left alone
        # rather than marked broken.
        logger.warning("Calendar sync failed: %s", exc)
        raise Problem(
            503, "Could not reach the calendar", "calendar_unavailable"
        ) from exc

    await session.commit()
    return SyncOut(
        created=result.created,
        updated=result.updated,
        unchanged=result.unchanged,
        last_synced_at=source.last_synced_at,
    )

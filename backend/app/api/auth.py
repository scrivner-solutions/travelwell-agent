"""Auth endpoints: email-code sign-in, Google OAuth, logout, and /me.

BFF pattern per the contract: the session lives in an httpOnly cookie the
frontend can never read; openapi-fetch just sends credentials. OAuth is the
server-side redirect flow: the browser only visits our /start and /callback
URLs, so provider tokens never reach the frontend.
"""

import logging
import os
import secrets

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api import login_codes, sessions
from app.api.deps import ApiRoute, CurrentUser, SessionDep
from app.api.problems import Problem
from app.api.schemas import (
    DemoLoginRequest,
    EmailCodeRequest,
    EmailCodeVerify,
    UserOut,
    UserUpdateIn,
)
from app.db.models import AuthProvider, User
from app.services import mailer
from app.services.demo_scene import build_demo_scene

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"], route_class=ApiRoute)


def _set_session_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        key=sessions.SESSION_COOKIE,
        value=sessions.issue_session(user_id),
        max_age=sessions.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=sessions.cookie_secure(),
        path="/",
    )


def _public_base_url() -> str:
    # The origin the browser is on (vite dev server, or the deployed
    # frontend). Proxies make the Host header untrustworthy, so it is config.
    return os.getenv("PUBLIC_BASE_URL", "http://localhost:5173").rstrip("/")


def _email_allowed(email: str) -> bool:
    """Staging gate: unset/empty ALLOWED_SIGNIN_EMAILS means open sign-up."""
    allowed = os.getenv("ALLOWED_SIGNIN_EMAILS", "").strip()
    if not allowed:
        return True
    return email.lower() in {
        entry.strip().lower() for entry in allowed.split(",") if entry.strip()
    }


@router.post("/auth/email-code", status_code=status.HTTP_202_ACCEPTED)
async def request_email_code(body: EmailCodeRequest, session: SessionDep) -> Response:
    if _email_allowed(body.email):
        # None on resend cooldown: the earlier code is still in their inbox.
        code = await login_codes.issue(session, body.email)
        if code is not None:
            await mailer.send_sign_in_code(body.email, code)
    # 202 unconditionally so addresses cannot be enumerated.
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/auth/email-code/verify")
async def verify_email_code(
    body: EmailCodeVerify, response: Response, session: SessionDep
) -> UserOut:
    if not await login_codes.verify(session, body.email, body.code):
        raise Problem(400, "Invalid or expired code", "code_invalid")

    user = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if user is None:
        user = User(email=body.email, auth_provider=AuthProvider.email)
        session.add(user)
        await session.commit()

    _set_session_cookie(response, str(user.user_id))
    return UserOut.from_model(user)


def _demo_login_enabled() -> bool:
    """Hackathon demo entry: on by default in dev/test only; a deployed
    environment must opt in explicitly with DEMO_LOGIN_ENABLED=1."""
    flag = os.getenv("DEMO_LOGIN_ENABLED", "").lower()
    if flag in ("1", "true"):
        return True
    if flag in ("0", "false"):
        return False
    return sessions.dev_mode()


@router.post("/auth/demo")
async def demo_login(
    response: Response, session: SessionDep, body: DemoLoginRequest | None = None
) -> UserOut:
    """Mint a fresh demo account pre-populated with the demo scene.

    Per-tap accounts keep testers isolated (mutations are real and would
    collide on a shared account) and build the scene's dates fresh, so the
    demo never goes stale. The optional name is just a label, not a
    credential: the account lives only in this browser's session cookie.
    """
    if not _demo_login_enabled():
        raise Problem(403, "Demo sign-in is disabled", "demo_disabled")

    name = (body.name or "").strip() if body else ""
    user = User(
        email=f"demo-{secrets.token_hex(4)}@travelwell.dev",
        display_name=name or "Demo Traveler",
        auth_provider=AuthProvider.email,
        home_timezone="America/Los_Angeles",
    )
    session.add(user)
    await session.flush()
    await build_demo_scene(session, user)
    await session.commit()

    _set_session_cookie(response, str(user.user_id))
    return UserOut.from_model(user)


# Pinned instead of discovered so /start never blocks on a metadata fetch;
# these are Google's stable, documented OIDC endpoints.
_GOOGLE_OIDC = {
    "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "access_token_url": "https://oauth2.googleapis.com/token",
    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
    "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
    "issuer": "https://accounts.google.com",
}


def _google_client():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise Problem(503, "Google sign-in is not configured", "oauth_unconfigured")
    # Per-request registry: handshake state lives in the session cookie, not
    # the client, and env config stays changeable without a reimport.
    return OAuth().register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        client_kwargs={"scope": "openid email profile"},
        **_GOOGLE_OIDC,
    )


def _provider_or_404(provider: str) -> None:
    if provider != "google":
        raise Problem(404, "Unknown sign-in provider", "not_found")


@router.get("/auth/oauth/{provider}/start")
async def start_oauth(provider: str, request: Request) -> RedirectResponse:
    _provider_or_404(provider)
    redirect_uri = f"{_public_base_url()}/api/v1/auth/oauth/google/callback"
    return await _google_client().authorize_redirect(request, redirect_uri)


@router.get("/auth/oauth/{provider}/callback")
async def oauth_callback(
    provider: str, request: Request, session: SessionDep
) -> RedirectResponse:
    _provider_or_404(provider)
    client = _google_client()
    base = _public_base_url()
    try:
        token = await client.authorize_access_token(request)
        userinfo = token.get("userinfo") or await client.userinfo(token=token)
    except OAuthError:
        logger.warning("Google OAuth callback failed", exc_info=True)
        return RedirectResponse(f"{base}/sign-in?error=oauth_failed", status_code=302)

    email = userinfo.get("email")
    if not email or not userinfo.get("email_verified"):
        return RedirectResponse(f"{base}/sign-in?error=oauth_failed", status_code=302)
    if not _email_allowed(email):
        return RedirectResponse(f"{base}/sign-in?error=not_allowed", status_code=302)

    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            display_name=userinfo.get("name"),
            auth_provider=AuthProvider.google,
        )
        session.add(user)
        await session.commit()

    response = RedirectResponse(f"{base}/", status_code=302)
    _set_session_cookie(response, str(user.user_id))
    return response


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(key=sessions.SESSION_COOKIE, path="/")
    return response


@router.get("/me")
async def get_me(user: CurrentUser) -> UserOut:
    return UserOut.from_model(user)


@router.patch("/me")
async def update_me(
    body: UserUpdateIn, user: CurrentUser, session: SessionDep
) -> UserOut:
    """Fields on users itself; preferences live on PATCH /me/preferences."""
    patch = body.model_dump(exclude_unset=True)
    if "display_name" in patch:
        user.display_name = patch["display_name"]
    # home_timezone is NOT NULL: an explicit null is a no-op, not a clear.
    if patch.get("home_timezone") is not None:
        user.home_timezone = patch["home_timezone"]
    await session.commit()
    return UserOut.from_model(user)

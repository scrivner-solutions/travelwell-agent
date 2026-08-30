"""Closed-by-default session gate for the whole ASGI app.

`get_fast_api_app()` returns the application object, so this service *is* an
ADK server we added routes to: its surface is exposed unless we close it, and
`google-adk` is pinned to a range, so a minor version can add public routes
with no change here. A per-route dependency only closes what we remember to
decorate; this closes everything and names the exceptions instead.

Middleware, not a router dependency: FastAPI copies router dependencies into
each route as it is registered, so one appended after `get_fast_api_app()` has
run reaches neither ADK's routes nor the a2a routes attached during lifespan.
"""

from __future__ import annotations

from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.problems import problem_response
from app.api.sessions import SESSION_COOKIE, dev_mode, read_session

# Anonymous by necessity and nothing else: the deploy smoke check, which has to
# answer before any user exists, and the sign-in steps, which cannot require
# being signed in. Everything else on this app is behind a session.
PUBLIC_PATHS = frozenset({"/readyz"})
PUBLIC_PREFIXES = ("/api/v1/auth/",)


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def _signed_in(scope: Scope) -> bool:
    # Signature only, no database round trip. This gate answers "did we mint
    # this session"; the routes that need the user still resolve it through
    # CurrentUser, which is what checks the row still exists.
    token = HTTPConnection(scope).cookies.get(SESSION_COOKIE)
    return token is not None and read_session(token) is not None


def _passes(scope: Scope) -> bool:
    # Off locally: the ADK dev UI (mounted by web=dev_mode()) drives /run_sse,
    # /list-apps and the session routes from a browser holding no session
    # cookie, so a gate here would only break tooling it is not protecting.
    if dev_mode():
        return True
    # Preflight carries no cookies by spec, and CORSMiddleware answers it from
    # inside this one.
    if scope.get("method") == "OPTIONS":
        return True
    return is_public(scope["path"]) or _signed_in(scope)


class AuthGateMiddleware:
    """401s every request that is not allowlisted above.

    Plain ASGI, not BaseHTTPMiddleware: that wrapper handles only `http`
    scopes, and /run_live is a WebSocket route that no OpenAPI-based audit of
    this app can even see. It also sits between /run_sse and its stream.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or _passes(scope):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            # Refusing the handshake before accepting it; the client sees the
            # connection rejected rather than an HTTP body.
            await send({"type": "websocket.close", "code": 1008})
            return
        response = problem_response(401, "Not signed in", "unauthenticated")
        await response(scope, receive, send)

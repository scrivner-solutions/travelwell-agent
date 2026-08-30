"""The closed-by-default gate over ADK's own surface (app/api/gate.py).

conftest sets APP_ENV=test, so the gate is inert for the rest of the suite and
these tests opt into staging behaviour explicitly, the way test_demo_login.py
already does.
"""

import pytest

# Routes ADK mounts that survive web=False. Each one either spends money, runs
# the agent, or reads and writes session state for an arbitrary user_id.
ADK_RUNTIME_PATHS = [
    ("get", "/list-apps"),
    ("get", "/version"),
    ("get", "/health"),
    ("post", "/run"),
    ("post", "/run_sse"),
    ("get", "/apps/app/users/anyone/sessions"),
    ("post", "/apps/app/users/anyone/sessions"),
    ("patch", "/apps/app/users/anyone/memory"),
    ("get", "/apps/app/users/anyone/sessions/s1/artifacts"),
]


@pytest.fixture
def staging(monkeypatch):
    """dev_mode() is read per request, so flipping the env is enough."""
    monkeypatch.setenv("APP_ENV", "staging")


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", ADK_RUNTIME_PATHS)
async def test_adk_routes_are_closed_to_anonymous(staging, client, method, path):
    response = await getattr(client, method)(path)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "unauthenticated"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", ADK_RUNTIME_PATHS)
async def test_adk_routes_open_to_a_session(staging, authed_client, method, path):
    """The gate is the only thing being measured here: any status but 401 means
    the request reached ADK, whatever ADK then made of it."""
    response = await getattr(authed_client, method)(path)
    assert response.status_code != 401


@pytest.mark.asyncio
async def test_forged_cookie_does_not_pass(staging, client):
    from app.api.sessions import SESSION_COOKIE

    client.cookies.set(SESSION_COOKIE, "not-a-real-token")
    response = await client.get("/list-apps")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_readyz_stays_anonymous(staging, client):
    """The deploy smoke check runs before any user exists."""
    response = await client.get("/readyz")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_sign_in_stays_anonymous(staging, client):
    """Signing out (and so the rest of /api/v1/auth) cannot require a session."""
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_dev_keeps_the_adk_tooling_reachable(client):
    """APP_ENV=test here, matching a local run: the dev UI drives these."""
    response = await client.get("/list-apps")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_websocket_handshake_is_refused(staging):
    """/run_live is a WebSocket route, so it never appears in the OpenAPI
    document and no HTTP client fixture can reach it. Driven at the ASGI layer
    instead, which is the layer the gate actually sits at."""
    from app.api.gate import AuthGateMiddleware

    reached = False

    async def downstream(scope, receive, send):
        nonlocal reached
        reached = True

    sent = []

    async def send(message):
        sent.append(message)

    scope = {"type": "websocket", "path": "/run_live", "headers": []}
    await AuthGateMiddleware(downstream)(scope, None, send)

    assert reached is False
    assert sent == [{"type": "websocket.close", "code": 1008}]

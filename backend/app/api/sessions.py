"""Session cookie signing.

Sessions are stateless: the twl_session cookie carries a signed, timestamped
user_id (itsdangerous), so no session table is needed and logout is just
clearing the cookie. schema.sql intentionally has no sessions table. Email
sign-in codes live in the login_codes table (app/api/login_codes.py).
"""

import logging
import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

SESSION_COOKIE = "twl_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30

_DEV_SECRET = "dev-insecure-session-secret"


def dev_mode() -> bool:
    """Explicit local/test opt-in: allows the dev secret and logged sign-in codes."""
    return os.getenv("APP_ENV", "").lower() in ("dev", "test")


def _resolve_secret() -> str:
    secret = os.getenv("SESSION_SECRET")
    if secret:
        return secret
    if dev_mode():
        logger.warning("SESSION_SECRET unset; using the insecure dev secret")
        return _DEV_SECRET
    # The signing secret IS the security model; a public fallback would let
    # anyone mint sessions for any user_id.
    raise RuntimeError(
        "SESSION_SECRET is not set. Set it to a long random string, "
        "or set APP_ENV=dev for local development."
    )


# Resolved at import so a misconfigured deployment fails at startup, not on
# the first sign-in.
_SECRET = _resolve_secret()
_SERIALIZER = URLSafeTimedSerializer(_SECRET, salt="twl-session")


def secret() -> str:
    """Shared with the OAuth-state session middleware in fast_api_app."""
    return _SECRET


def cookie_secure() -> bool:
    return os.getenv("SESSION_COOKIE_SECURE", "").lower() in ("1", "true")


def issue_session(user_id: str) -> str:
    return _SERIALIZER.dumps(user_id)


def read_session(token: str) -> str | None:
    try:
        return _SERIALIZER.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None

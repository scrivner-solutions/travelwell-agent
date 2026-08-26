"""Session cookie signing and the dev email-code store.

Sessions are stateless: the twl_session cookie carries a signed, timestamped
user_id (itsdangerous), so no session table is needed and logout is just
clearing the cookie. schema.sql intentionally has no sessions table.

Email codes are a dev placeholder: kept in process memory and written to the
server log instead of being emailed. Single-process only; a real email
provider and a persistent store come with a later auth slice.
"""

import logging
import os
import secrets
import time

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

SESSION_COOKIE = "twl_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
CODE_TTL_SECONDS = 600
CODE_MAX_ATTEMPTS = 5

_DEV_SECRET = "dev-insecure-session-secret"


def _serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("SESSION_SECRET")
    if not secret:
        secret = _DEV_SECRET
        logger.warning("SESSION_SECRET is not set; using the insecure dev secret")
    return URLSafeTimedSerializer(secret, salt="twl-session")


def issue_session(user_id: str) -> str:
    return _serializer().dumps(user_id)


def read_session(token: str) -> str | None:
    try:
        return _serializer().loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None


# email (lowercased) -> (code, expires_at_monotonic, attempts_left)
_codes: dict[str, tuple[str, float, int]] = {}


def issue_code(email: str) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    _codes[email.lower()] = (code, time.monotonic() + CODE_TTL_SECONDS, CODE_MAX_ATTEMPTS)
    return code


def verify_code(email: str, code: str) -> bool:
    key = email.lower()
    entry = _codes.get(key)
    if entry is None:
        return False
    stored, expires_at, attempts_left = entry
    if time.monotonic() > expires_at or attempts_left <= 0:
        _codes.pop(key, None)
        return False
    if not secrets.compare_digest(stored, code):
        _codes[key] = (stored, expires_at, attempts_left - 1)
        return False
    _codes.pop(key, None)
    return True

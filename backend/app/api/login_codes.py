"""Email sign-in codes, one live code per address, stored in Postgres.

The database holds an HMAC of the code, never the code: a six-digit code is
brute-forced instantly from a leaked plain hash, but the HMAC key lives only
in SESSION_SECRET. Expiry and the resend cooldown compare against the
database clock (now()), so multiple app instances need no clock agreement.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import sessions
from app.db.models import LoginCode

CODE_TTL_SECONDS = 600
CODE_MAX_ATTEMPTS = 5
# With ALLOWED_SIGNIN_EMAILS unset sign-up is open, so without a cooldown the
# endpoint is a mail-bomb button for any address once a provider is wired.
RESEND_COOLDOWN_SECONDS = 60


def _digest(email: str, code: str) -> str:
    # Domain-separated from the cookie serializer's use of the same secret;
    # binding the email means a row only ever verifies its own address.
    payload = f"login-code:{email}:{code}".encode()
    return hmac.new(sessions.secret().encode(), payload, hashlib.sha256).hexdigest()


async def issue(session: AsyncSession, email: str) -> str | None:
    """Store a fresh code for the address and return it, or None on cooldown."""
    key = email.lower()
    # Opportunistic sweep so never-verified addresses don't accumulate rows.
    await session.execute(sa.delete(LoginCode).where(LoginCode.expires_at < sa.func.now()))
    recent = await session.scalar(
        sa.select(LoginCode.email).where(
            LoginCode.email == key,
            LoginCode.created_at > sa.func.now() - timedelta(seconds=RESEND_COOLDOWN_SECONDS),
        )
    )
    if recent is not None:
        await session.commit()
        return None

    code = f"{secrets.randbelow(1_000_000):06d}"
    fresh = {
        "code_hmac": _digest(key, code),
        "expires_at": sa.func.now() + timedelta(seconds=CODE_TTL_SECONDS),
        "attempts_left": CODE_MAX_ATTEMPTS,
        "created_at": sa.func.now(),
    }
    await session.execute(
        pg_insert(LoginCode)
        .values(email=key, **fresh)
        .on_conflict_do_update(index_elements=[LoginCode.email], set_=fresh)
    )
    await session.commit()
    return code


async def verify(session: AsyncSession, email: str, code: str) -> bool:
    """Check a code; a correct one is consumed, a wrong one costs an attempt."""
    key = email.lower()
    # Atomic decrement-and-read: parallel guesses cannot race past the cap.
    stored = (
        await session.execute(
            sa.update(LoginCode)
            .where(
                LoginCode.email == key,
                LoginCode.attempts_left > 0,
                LoginCode.expires_at > sa.func.now(),
            )
            .values(attempts_left=LoginCode.attempts_left - 1)
            .returning(LoginCode.code_hmac)
        )
    ).scalar_one_or_none()
    if stored is None:
        await session.commit()
        return False
    ok = hmac.compare_digest(stored, _digest(key, code))
    if ok:
        await session.execute(sa.delete(LoginCode).where(LoginCode.email == key))
    await session.commit()
    return ok

"""The token store backed by `stored_secrets`, AES-GCM encrypted.

Chosen over one Secret Manager secret per user: that costs an IAM binding and
a quota unit per signup, and makes a local run need cloud credentials. The
trade is that the key and the ciphertext live in systems we already run, so
losing the database is not by itself losing the tokens.

This module is the only thing that reads the table. Everything else holds a
reference from `put` and cannot tell this backend from any other.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import StoredSecret
from app.services.tokens.crypto import decrypt, encrypt, load_key
from app.services.tokens.ports import SecretKind, SecretNotFound, UnknownSecretRef

# Refs carry the scheme that minted them so a backend swap fails loudly on an
# old reference instead of returning nothing and reading as "never connected".
_SCHEME = "db"


def _parse(ref: str) -> uuid.UUID:
    scheme, _, rest = ref.partition(":")
    if scheme != _SCHEME:
        raise UnknownSecretRef(f"{ref!r} was not minted by the database store")
    try:
        return uuid.UUID(rest)
    except ValueError as exc:
        raise UnknownSecretRef(f"{ref!r} is not a well-formed reference") from exc


def _aad(user_id: uuid.UUID, kind: SecretKind) -> bytes:
    """Bind the ciphertext to the row that owns it, so a value moved to another
    user's row fails to authenticate rather than decrypting for the wrong one."""
    return f"{user_id}:{kind}".encode()


class EncryptedDatabaseTokenStore:
    """Implements TokenStore. The caller owns the transaction: `put` and
    `delete` do not commit, so storing a token and updating `secret_ref` are
    one unit of work or neither."""

    def __init__(self, session: AsyncSession, *, key: bytes | None = None) -> None:
        self._session = session
        # Eager, not lazy: a missing key is a deployment fault, and finding out
        # at construction beats finding out halfway through an OAuth callback.
        self._key = key if key is not None else load_key()

    async def put(
        self, user_id: uuid.UUID, kind: SecretKind, secret: str
    ) -> str:
        nonce, ciphertext = encrypt(self._key, secret, _aad(user_id, kind))
        stmt = (
            pg_insert(StoredSecret)
            .values(
                user_id=user_id, kind=kind, nonce=nonce, ciphertext=ciphertext
            )
            .on_conflict_do_update(
                constraint="stored_secrets_user_id_kind_key",
                set_={
                    "nonce": nonce,
                    "ciphertext": ciphertext,
                    "updated_at": sa.func.now(),
                },
            )
            .returning(StoredSecret.secret_id)
        )
        secret_id = (await self._session.execute(stmt)).scalar_one()
        return f"{_SCHEME}:{secret_id}"

    async def get(self, ref: str) -> str:
        secret_id = _parse(ref)
        row = (
            await self._session.execute(
                sa.select(
                    StoredSecret.user_id,
                    StoredSecret.kind,
                    StoredSecret.nonce,
                    StoredSecret.ciphertext,
                ).where(StoredSecret.secret_id == secret_id)
            )
        ).one_or_none()
        if row is None:
            raise SecretNotFound(f"no secret stored under {ref!r}")
        return decrypt(
            self._key, row.nonce, row.ciphertext, _aad(row.user_id, row.kind)
        )

    async def delete(self, ref: str) -> None:
        await self._session.execute(
            sa.delete(StoredSecret).where(StoredSecret.secret_id == _parse(ref))
        )

"""Secret storage, and the one place that chooses a backend.

Swapping backends is meant to be two edits: write a class implementing
TokenStore in this package, and return it from `token_store` below. Nothing
outside this module names an implementation, so nothing outside it changes.

There is no environment switch, unlike `provider_for` in the reservation
package. A booking names its provider per row because two bookings really can
be held by different systems; a secret does not. One deployment keeps its
secrets in one place, and an override would mostly be a way to read them from
somewhere they were never written.

`InMemoryTokenStore` is deliberately not exported here. It is a test double,
and keeping it off the package's public surface is what stops a deployment
from ever selecting a store that forgets every grant on restart.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.tokens.crypto import DecryptionFailed, KeyUnavailable
from app.services.tokens.encrypted_db import EncryptedDatabaseTokenStore
from app.services.tokens.ports import (
    SecretKind,
    SecretNotFound,
    TokenStore,
    UnknownSecretRef,
)

__all__ = [
    "DecryptionFailed",
    "KeyUnavailable",
    "SecretKind",
    "SecretNotFound",
    "TokenStore",
    "UnknownSecretRef",
    "token_store",
]


def token_store(session: AsyncSession) -> TokenStore:
    """The store this deployment uses. Raises KeyUnavailable if it is not
    configured, which is the correct time to find out."""
    return EncryptedDatabaseTokenStore(session)

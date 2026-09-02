"""The secret-storage seam: what any token store must be able to do.

A calendar grant is only useful if the refresh token outlives the request that
obtained it, so something has to hold a long-lived secret on a user's behalf.
Where it is held is a deployment question that has already changed once and
will change again -- an encrypted column today, a per-user managed secret or a
KMS-wrapped blob later -- and none of the calendar code should have an opinion
about it.

So the port is `put` -> a reference, `get` that reference back, `delete` it.
Callers hold the reference and nothing else; `connected_sources.secret_ref` is
where it comes to rest. A reference is opaque: only the store that minted one
may parse it.

Nothing here may mention columns, encryption, key material or a project id. A
concept that only makes sense for one backend does not belong in the interface
every backend has to implement.

Implementations live beside this file and are chosen by `token_store`.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

# What a secret is for. Free text rather than an enum: the store never reads
# it, and constraining it would make adding a second grant a migration.
SecretKind = str


class SecretNotFound(LookupError):
    """No secret is stored under that reference.

    Raised rather than returning None on purpose. A missing secret and a user
    who never connected look identical to a caller that gets None, and only one
    of them means the grant is broken.
    """


class UnknownSecretRef(SecretNotFound):
    """The reference was not minted by this store.

    Its own subclass because it means the store was swapped without migrating
    the references, which is an operator error, not a missing row.
    """


@runtime_checkable
class TokenStore(Protocol):
    """One place secrets are kept.

    Implementations are addressed only through the reference they return.
    That is not a preference: it is what lets the backend change without every
    caller learning the new shape, and it is why `get` takes a reference rather
    than the pair that produced it.
    """

    async def put(
        self, user_id: uuid.UUID, kind: SecretKind, secret: str
    ) -> str:
        """Store `secret` and return its reference.

        Idempotent per `(user_id, kind)`: storing again replaces the value and
        returns the reference the caller already holds. Re-consent is the
        normal path -- Google mints a fresh refresh token every time -- and an
        upsert keeps `secret_ref` valid throughout, where a new reference each
        time would leave the old row orphaned and the column briefly stale.
        """
        ...

    async def get(self, ref: str) -> str:
        """Read a secret back. Raises SecretNotFound if it is not there."""
        ...

    async def delete(self, ref: str) -> None:
        """Forget a secret. Succeeds whether or not it was there, so
        disconnecting twice is not an error."""
        ...

"""A token store that keeps secrets in the process. For tests only.

Exists so a test that is about the OAuth handshake does not have to be about
encryption keys as well. It holds the same contract as the real store, and the
contract suite runs against both -- a fake that is easier to satisfy than the
thing it stands in for proves nothing.
"""

from __future__ import annotations

import uuid

from app.services.tokens.ports import SecretKind, SecretNotFound, UnknownSecretRef

_SCHEME = "mem"


class InMemoryTokenStore:
    """Implements TokenStore. Not safe across processes, which is the point:
    it must never be reachable from a configuration a deployment can select."""

    def __init__(self) -> None:
        self._by_ref: dict[str, str] = {}
        self._refs: dict[tuple[uuid.UUID, SecretKind], str] = {}

    async def put(
        self, user_id: uuid.UUID, kind: SecretKind, secret: str
    ) -> str:
        ref = self._refs.setdefault(
            (user_id, kind), f"{_SCHEME}:{uuid.uuid4()}"
        )
        self._by_ref[ref] = secret
        return ref

    async def get(self, ref: str) -> str:
        self._check(ref)
        try:
            return self._by_ref[ref]
        except KeyError as exc:
            raise SecretNotFound(f"no secret stored under {ref!r}") from exc

    async def delete(self, ref: str) -> None:
        self._check(ref)
        self._by_ref.pop(ref, None)
        for key, stored in list(self._refs.items()):
            if stored == ref:
                del self._refs[key]

    @staticmethod
    def _check(ref: str) -> None:
        if not ref.startswith(f"{_SCHEME}:"):
            raise UnknownSecretRef(f"{ref!r} was not minted by the in-memory store")

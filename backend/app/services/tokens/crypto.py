"""AES-GCM over a single key from the environment.

Split from storage so the two failure modes stay separate: a key that is the
wrong shape is an environment problem, and it should be provable without a
database. Nothing here knows what a secret is for or where the ciphertext goes.

Key rotation is deliberately not handled. Re-encrypting every row under a new
key needs a version marker alongside each ciphertext, and adding one later is a
`smallint not null default 1` -- existing rows are correct under the default,
so deferring it costs nothing and building it now would ship a column that can
only ever hold one value.
"""

from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_ENV = "TOKEN_ENCRYPTION_KEY"
KEY_BYTES = 32
NONCE_BYTES = 12


class KeyUnavailable(RuntimeError):
    """The encryption key is missing or is not 32 bytes in any known encoding."""


class DecryptionFailed(ValueError):
    """The ciphertext did not authenticate under this key.

    Means one of: the wrong key, a corrupted row, or a ciphertext moved between
    users. All three are the same instruction -- do not trust this value - so
    they are one error and the caller is not asked to tell them apart.
    """


def _decode(raw: str) -> bytes | None:
    """Accept whatever `openssl rand` was reached for.

    Hex, base64 and urlsafe base64 are all ordinary ways to write 32 bytes, and
    which one a secret was generated with is not visible from here. Guessing
    wrong is a staging-only failure, which is the expensive kind.

    Raw text is deliberately not accepted, though 32 random bytes would be a
    valid key: it would make every 32-character string one, so `openssl rand
    -hex 16` would quietly install a half-strength key instead of failing.
    """
    text = raw.strip()
    for decode in (
        lambda s: binascii.unhexlify(s),
        lambda s: base64.b64decode(s, validate=True),
        lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)),
    ):
        try:
            candidate = decode(text)
        except (binascii.Error, ValueError):
            continue
        if len(candidate) == KEY_BYTES:
            return candidate
    return None


def load_key() -> bytes:
    """Read the key from the environment. Raises KeyUnavailable."""
    raw = os.getenv(KEY_ENV)
    if not raw:
        raise KeyUnavailable(
            f"{KEY_ENV} is unset. Calendar grants cannot be stored without it; "
            "it is a Secret Manager entry, not something to invent locally."
        )
    key = _decode(raw)
    if key is None:
        raise KeyUnavailable(
            f"{KEY_ENV} must be {KEY_BYTES} bytes written as hex or base64 "
            "(urlsafe accepted). Try: openssl rand -base64 32"
        )
    return key


def encrypt(key: bytes, plaintext: str, aad: bytes) -> tuple[bytes, bytes]:
    """Returns (nonce, ciphertext). A fresh nonce every call: reusing one under
    the same key is what breaks GCM outright, so it is never a parameter."""
    nonce = os.urandom(NONCE_BYTES)
    return nonce, AESGCM(key).encrypt(nonce, plaintext.encode(), aad)


def decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> str:
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, aad).decode()
    except InvalidTag as exc:
        raise DecryptionFailed("ciphertext did not authenticate") from exc

"""Key loading and AES-GCM, provable without a database.

The point of splitting these out: a key in the wrong encoding is a deployment
fault that shows up in staging, and a test that needs Postgres to catch it is a
test nobody runs while writing the deploy step.
"""

import base64
import binascii

import pytest

from app.services.tokens.crypto import (
    KEY_ENV,
    DecryptionFailed,
    KeyUnavailable,
    decrypt,
    encrypt,
    load_key,
)

KEY = bytes(range(32))
AAD = b"user:kind"


@pytest.mark.parametrize(
    "written",
    [
        pytest.param(binascii.hexlify(KEY).decode(), id="hex"),
        pytest.param(base64.b64encode(KEY).decode(), id="base64"),
        pytest.param(
            base64.urlsafe_b64encode(KEY).decode().rstrip("="), id="urlsafe-unpadded"
        ),
        pytest.param(f"  {base64.b64encode(KEY).decode()}\n", id="surrounding-whitespace"),
    ],
)
def test_every_ordinary_way_of_writing_32_bytes_is_accepted(monkeypatch, written):
    monkeypatch.setenv(KEY_ENV, written)
    assert len(load_key()) == 32


@pytest.mark.parametrize(
    "written",
    [
        pytest.param("", id="empty"),
        pytest.param("too-short", id="short"),
        pytest.param(binascii.hexlify(bytes(16)).decode(), id="16-bytes-of-hex"),
        pytest.param("x" * 32, id="32-plain-characters"),
    ],
)
def test_a_key_that_is_not_32_bytes_is_refused(monkeypatch, written):
    monkeypatch.setenv(KEY_ENV, written)
    with pytest.raises(KeyUnavailable):
        load_key()


def test_a_missing_key_names_itself(monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    with pytest.raises(KeyUnavailable, match=KEY_ENV):
        load_key()


def test_round_trip():
    nonce, ciphertext = encrypt(KEY, "1//refresh-token", AAD)
    assert decrypt(KEY, nonce, ciphertext, AAD) == "1//refresh-token"


def test_the_same_plaintext_twice_gives_different_ciphertext():
    """A fresh nonce per call, so equal secrets are not visibly equal."""
    first = encrypt(KEY, "same", AAD)
    second = encrypt(KEY, "same", AAD)
    assert first != second


def test_a_flipped_bit_is_caught():
    nonce, ciphertext = encrypt(KEY, "1//refresh-token", AAD)
    tampered = bytes([ciphertext[0] ^ 1]) + ciphertext[1:]
    with pytest.raises(DecryptionFailed):
        decrypt(KEY, nonce, tampered, AAD)


def test_different_associated_data_does_not_decrypt():
    nonce, ciphertext = encrypt(KEY, "1//refresh-token", AAD)
    with pytest.raises(DecryptionFailed):
        decrypt(KEY, nonce, ciphertext, b"someone:else")


def test_a_different_key_does_not_decrypt():
    nonce, ciphertext = encrypt(KEY, "1//refresh-token", AAD)
    with pytest.raises(DecryptionFailed):
        decrypt(bytes(reversed(KEY)), nonce, ciphertext, AAD)

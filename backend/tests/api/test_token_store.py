"""The TokenStore contract, run against every implementation.

Parametrized on purpose. A fake that is easier to satisfy than the real store
is worse than no fake: the tests that use it pass, and the thing they stand in
for is the thing that breaks. Anything only one backend can promise belongs
below the contract suite, not inside it.
"""

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.services.tokens.crypto import DecryptionFailed
from app.services.tokens.encrypted_db import EncryptedDatabaseTokenStore
from app.services.tokens.memory import InMemoryTokenStore
from app.services.tokens.ports import SecretNotFound, TokenStore, UnknownSecretRef

pytestmark = pytest.mark.asyncio

KEY = bytes(range(32))
OTHER_KEY = bytes(reversed(range(32)))
KIND = "google_refresh_token"


@pytest_asyncio.fixture(params=["memory", "database"])
async def store(request, db_session):
    if request.param == "memory":
        return InMemoryTokenStore()
    return EncryptedDatabaseTokenStore(db_session, key=KEY)


# --- the contract ---------------------------------------------------------


async def test_both_implementations_satisfy_the_protocol(store):
    assert isinstance(store, TokenStore)


async def test_put_then_get_returns_the_secret(store, user):
    ref = await store.put(user.user_id, KIND, "1//refresh-token")
    assert await store.get(ref) == "1//refresh-token"


async def test_put_is_idempotent_per_user_and_kind(store, user):
    """Re-consent must not orphan the reference `secret_ref` already holds."""
    first = await store.put(user.user_id, KIND, "old")
    second = await store.put(user.user_id, KIND, "new")
    assert first == second
    assert await store.get(first) == "new"


async def test_kinds_are_stored_separately(store, user):
    calendar = await store.put(user.user_id, KIND, "calendar")
    gmail = await store.put(user.user_id, "gmail_refresh_token", "mail")
    assert calendar != gmail
    assert await store.get(calendar) == "calendar"
    assert await store.get(gmail) == "mail"


async def test_users_are_stored_separately(store, user, other_user):
    mine = await store.put(user.user_id, KIND, "mine")
    theirs = await store.put(other_user.user_id, KIND, "theirs")
    assert mine != theirs
    assert await store.get(mine) == "mine"
    assert await store.get(theirs) == "theirs"


async def test_get_after_delete_raises_rather_than_returning_nothing(store, user):
    ref = await store.put(user.user_id, KIND, "gone")
    await store.delete(ref)
    with pytest.raises(SecretNotFound):
        await store.get(ref)


async def test_delete_is_idempotent(store, user):
    """Disconnecting twice is not an error; the second call has nothing to do."""
    ref = await store.put(user.user_id, KIND, "gone")
    await store.delete(ref)
    await store.delete(ref)


async def test_a_reference_from_another_store_is_rejected(store):
    with pytest.raises(UnknownSecretRef):
        await store.get(f"someoneelse:{uuid.uuid4()}")


async def test_a_malformed_reference_is_rejected(store):
    with pytest.raises(SecretNotFound):
        await store.get("not-a-reference")


# --- only the encrypted store can promise these ---------------------------


async def test_the_plaintext_is_not_in_the_table(db_session, user):
    store = EncryptedDatabaseTokenStore(db_session, key=KEY)
    await store.put(user.user_id, KIND, "1//refresh-token")
    stored = (
        await db_session.execute(sa.text("select ciphertext from stored_secrets"))
    ).scalar_one()
    assert b"refresh-token" not in bytes(stored)


async def test_every_write_uses_a_fresh_nonce(db_session, user):
    """Nonce reuse under one key is what breaks GCM, so the same plaintext
    twice must not produce the same row."""
    store = EncryptedDatabaseTokenStore(db_session, key=KEY)
    await store.put(user.user_id, KIND, "same")
    first = (
        await db_session.execute(sa.text("select nonce from stored_secrets"))
    ).scalar_one()
    await store.put(user.user_id, KIND, "same")
    second = (
        await db_session.execute(sa.text("select nonce from stored_secrets"))
    ).scalar_one()
    assert bytes(first) != bytes(second)


async def test_the_wrong_key_fails_loudly(db_session, user):
    ref = await EncryptedDatabaseTokenStore(db_session, key=KEY).put(
        user.user_id, KIND, "1//refresh-token"
    )
    with pytest.raises(DecryptionFailed):
        await EncryptedDatabaseTokenStore(db_session, key=OTHER_KEY).get(ref)


async def test_a_ciphertext_moved_between_users_does_not_decrypt(
    db_session, user, other_user
):
    """The row is bound into the ciphertext, so lifting one user's secret into
    another user's row yields an error rather than the wrong person's token."""
    store = EncryptedDatabaseTokenStore(db_session, key=KEY)
    mine = await store.put(user.user_id, KIND, "mine")
    theirs = await store.put(other_user.user_id, KIND, "theirs")
    row = (
        await db_session.execute(
            sa.text(
                "select nonce, ciphertext from stored_secrets where user_id = :u"
            ),
            {"u": user.user_id},
        )
    ).one()
    await db_session.execute(
        sa.text(
            "update stored_secrets set nonce = :n, ciphertext = :c "
            "where user_id = :u"
        ),
        {"n": row.nonce, "c": row.ciphertext, "u": other_user.user_id},
    )
    assert await store.get(mine) == "mine"
    with pytest.raises(DecryptionFailed):
        await store.get(theirs)


async def test_secrets_go_when_the_user_does(db_session, user):
    store = EncryptedDatabaseTokenStore(db_session, key=KEY)
    await store.put(user.user_id, KIND, "1//refresh-token")
    await db_session.execute(
        sa.text("delete from users where user_id = :u"), {"u": user.user_id}
    )
    remaining = (
        await db_session.execute(sa.text("select count(*) from stored_secrets"))
    ).scalar_one()
    assert remaining == 0

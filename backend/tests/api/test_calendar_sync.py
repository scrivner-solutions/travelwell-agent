"""Sync: what it writes, what it refuses to touch, and the endpoint over it.

The service half runs against the fake client, because everything it does is a
pure function of what the client returned - which is the reason the port has
exactly one method. The endpoint half goes through the real router with the
client patched at the package boundary.

The two `trip_id` tests are the point of most of this file. Detection decides
which trip an event belongs to; sync must never guess, and must never overwrite
the answer on a later run.
"""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.db.models import CalendarEvent, ConnectedSource, SourceKind, SourceStatus
from app.services.calendar import content_hash, sync_source
from app.services.calendar.fake import FakeCalendarClient
from app.services.calendar.ports import (
    CalendarUnavailable,
    CredentialRejected,
    RemoteEvent,
)

pytestmark = pytest.mark.asyncio

WINDOW = (datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 12, 1, tzinfo=UTC))


def remote(**over) -> RemoteEvent:
    base = {
        "external_id": "evt-1",
        "title": "Standup",
        "starts_at": datetime(2026, 9, 2, 16, tzinfo=UTC),
        "ends_at": datetime(2026, 9, 2, 16, 30, tzinfo=UTC),
        "status": "confirmed",
        "busy": True,
        "location": None,
    }
    return RemoteEvent(**(base | over))


@pytest_asyncio.fixture
async def source(db_session, user) -> ConnectedSource:
    row = ConnectedSource(
        user_id=user.user_id,
        kind=SourceKind.google_calendar,
        status=SourceStatus.connected,
        scopes=["https://www.googleapis.com/auth/calendar.events.readonly"],
        secret_ref="mem:placeholder",
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


@pytest_asyncio.fixture
async def rows(db_session):
    async def _rows():
        return (
            (
                await db_session.execute(
                    sa.select(CalendarEvent).order_by(CalendarEvent.external_id)
                )
            )
            .scalars()
            .all()
        )

    return _rows


# --- the hash -------------------------------------------------------------


def test_the_hash_is_stable_across_equal_events():
    assert content_hash(remote()) == content_hash(remote())


@pytest.mark.parametrize(
    "change",
    [
        {"title": "Standup (moved)"},
        {"location": "Room 2"},
        {"starts_at": datetime(2026, 9, 2, 17, tzinfo=UTC)},
        {"ends_at": datetime(2026, 9, 2, 17, tzinfo=UTC)},
        {"status": "cancelled"},
        {"busy": False},
    ],
)
def test_every_field_sync_writes_moves_the_hash(change):
    # busy included: a guest declining changes nothing else about the event,
    # so without it the row would never be updated.
    assert content_hash(remote(**change)) != content_hash(remote())


def test_the_hash_does_not_confuse_adjacent_fields():
    # Concatenation without a separator makes these two collide.
    a = remote(title="Room", location="2")
    b = remote(title="Room2", location="")
    assert content_hash(a) != content_hash(b)


# --- the service ----------------------------------------------------------


async def test_a_first_sync_creates_rows(db_session, source, rows):
    result = await sync_source(
        db_session, source, FakeCalendarClient([remote()]), start=WINDOW[0], end=WINDOW[1]
    )
    await db_session.commit()

    assert (result.created, result.updated, result.unchanged) == (1, 0, 0)
    (row,) = await rows()
    assert (row.title, row.busy, row.status) == ("Standup", True, "confirmed")
    assert row.source_id == source.source_id
    assert row.user_id == source.user_id


async def test_an_unchanged_event_is_touched_not_rewritten(db_session, source, rows):
    client = FakeCalendarClient([remote()])
    await sync_source(db_session, source, client, start=WINDOW[0], end=WINDOW[1])
    await db_session.commit()
    (first,) = await rows()
    before = first.last_seen_at

    result = await sync_source(
        db_session, source, client, start=WINDOW[0], end=WINDOW[1]
    )
    await db_session.commit()

    assert (result.created, result.updated, result.unchanged) == (0, 0, 1)
    (row,) = await rows()
    assert row.last_seen_at >= before


async def test_a_changed_event_updates_in_place(db_session, source, rows):
    await sync_source(
        db_session, source, FakeCalendarClient([remote()]), start=WINDOW[0], end=WINDOW[1]
    )
    await db_session.commit()
    (before,) = await rows()

    result = await sync_source(
        db_session,
        source,
        FakeCalendarClient([remote(title="Standup (moved)")]),
        start=WINDOW[0],
        end=WINDOW[1],
    )
    await db_session.commit()

    assert (result.created, result.updated, result.unchanged) == (0, 1, 0)
    rows_after = await rows()
    assert len(rows_after) == 1
    assert rows_after[0].cal_event_id == before.cal_event_id
    assert rows_after[0].title == "Standup (moved)"


async def test_sync_never_sets_trip_id(db_session, source, rows):
    await sync_source(
        db_session, source, FakeCalendarClient([remote()]), start=WINDOW[0], end=WINDOW[1]
    )
    await db_session.commit()

    (row,) = await rows()
    # Which trip an event belongs to is detection's answer, not sync's.
    assert row.trip_id is None


async def test_a_later_sync_does_not_clobber_a_detected_trip(
    db_session, source, rows, make_trip, user
):
    trip = await make_trip(user)
    await sync_source(
        db_session, source, FakeCalendarClient([remote()]), start=WINDOW[0], end=WINDOW[1]
    )
    await db_session.commit()
    (row,) = await rows()
    row.trip_id = trip.trip_id
    await db_session.commit()

    await sync_source(
        db_session,
        source,
        FakeCalendarClient([remote(title="Standup (moved)")]),
        start=WINDOW[0],
        end=WINDOW[1],
    )
    await db_session.commit()

    (after,) = await rows()
    assert after.title == "Standup (moved)"
    # The update list omits trip_id on purpose; this is what that protects.
    assert after.trip_id == trip.trip_id


async def test_a_cancellation_is_stored_rather_than_deleted(db_session, source, rows):
    await sync_source(
        db_session, source, FakeCalendarClient([remote()]), start=WINDOW[0], end=WINDOW[1]
    )
    await db_session.commit()

    await sync_source(
        db_session,
        source,
        FakeCalendarClient([remote(status="cancelled", busy=False)]),
        start=WINDOW[0],
        end=WINDOW[1],
    )
    await db_session.commit()

    (row,) = await rows()
    # A tombstone, not a missing row: "removed" and "never synced" are
    # different facts and the timeline filter depends on telling them apart.
    assert (row.status, row.busy) == ("cancelled", False)


async def test_a_successful_sync_stamps_the_source(db_session, source):
    await sync_source(
        db_session, source, FakeCalendarClient([]), start=WINDOW[0], end=WINDOW[1]
    )
    await db_session.commit()

    assert source.last_synced_at is not None
    assert source.status is SourceStatus.connected


async def test_a_sync_clears_an_earlier_error(db_session, source):
    source.status = SourceStatus.error
    await db_session.commit()

    await sync_source(
        db_session, source, FakeCalendarClient([]), start=WINDOW[0], end=WINDOW[1]
    )
    await db_session.commit()

    # A sync that worked is the only evidence that the grant recovered.
    assert source.status is SourceStatus.connected


async def test_a_rejected_credential_marks_the_source_and_re_raises(
    db_session, source
):
    client = FakeCalendarClient(raises=CredentialRejected("revoked"))

    with pytest.raises(CredentialRejected):
        await sync_source(db_session, source, client, start=WINDOW[0], end=WINDOW[1])
    await db_session.commit()

    assert source.status is SourceStatus.error
    assert source.last_synced_at is None


async def test_an_outage_leaves_the_source_alone(db_session, source):
    client = FakeCalendarClient(raises=CalendarUnavailable("502"))

    with pytest.raises(CalendarUnavailable):
        await sync_source(db_session, source, client, start=WINDOW[0], end=WINDOW[1])
    await db_session.commit()

    # The grant is still good; marking it broken would make a blip permanent.
    assert source.status is SourceStatus.connected


async def test_the_window_is_passed_through_to_the_client(db_session, source):
    client = FakeCalendarClient([])

    await sync_source(db_session, source, client, start=WINDOW[0], end=WINDOW[1])

    assert client.calls == [WINDOW]


# --- the endpoint ---------------------------------------------------------


@pytest.fixture
def stub_client(monkeypatch):
    """Patch the client the route builds, leaving everything else real."""

    def _install(client):
        import app.api.sources as sources

        monkeypatch.setattr(sources, "calendar_client", lambda token: client)
        return client

    return _install


@pytest_asyncio.fixture
async def connected(authed_client, user, db_session, monkeypatch):
    """A real grant, stored through the real token store."""
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", bytes(range(32)).hex())
    from app.api.sources import SECRET_KIND
    from app.services.tokens import token_store

    ref = await token_store(db_session).put(user.user_id, SECRET_KIND, "refresh-abc")
    db_session.add(
        ConnectedSource(
            user_id=user.user_id,
            kind=SourceKind.google_calendar,
            status=SourceStatus.connected,
            scopes=["https://www.googleapis.com/auth/calendar.events.readonly"],
            secret_ref=ref,
        )
    )
    await db_session.commit()
    return authed_client


async def test_sync_endpoint_reports_what_it_wrote(connected, stub_client, rows):
    stub_client(FakeCalendarClient([remote(), remote(external_id="evt-2")]))

    r = await connected.post("/api/v1/me/sources/google_calendar/sync")

    assert r.status_code == 200
    body = r.json()
    assert (body["created"], body["updated"], body["unchanged"]) == (2, 0, 0)
    assert body["last_synced_at"]
    assert len(await rows()) == 2


async def test_sync_endpoint_asks_for_a_window_around_today(connected, stub_client):
    client = stub_client(FakeCalendarClient([]))

    await connected.post("/api/v1/me/sources/google_calendar/sync")

    (start, end) = client.calls[0]
    now = datetime.now(UTC)
    # Yesterday forward, because a trip in progress started before now.
    assert timedelta(hours=23) < now - start < timedelta(hours=25)
    assert timedelta(days=89) < end - now < timedelta(days=91)


async def test_sync_requires_a_connected_source(authed_client):
    r = await authed_client.post("/api/v1/me/sources/google_calendar/sync")

    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


async def test_syncing_a_disconnected_source_is_refused(connected, stub_client):
    stub_client(FakeCalendarClient([]))
    await connected.delete("/api/v1/me/sources/google_calendar")

    r = await connected.post("/api/v1/me/sources/google_calendar/sync")

    assert r.status_code == 409
    assert r.json()["code"] == "source_disconnected"


async def test_a_rejected_grant_surfaces_as_needs_reconnect(
    connected, stub_client, db_session
):
    stub_client(FakeCalendarClient(raises=CredentialRejected("revoked")))

    r = await connected.post("/api/v1/me/sources/google_calendar/sync")

    assert r.status_code == 409
    assert r.json()["code"] == "source_needs_reconnect"
    source = (
        await db_session.execute(sa.select(ConnectedSource))
    ).scalar_one()
    await db_session.refresh(source)
    # The mark is the half of this failure worth keeping.
    assert source.status is SourceStatus.error


async def test_an_outage_surfaces_as_unavailable_and_leaves_the_source(
    connected, stub_client, db_session
):
    stub_client(FakeCalendarClient(raises=CalendarUnavailable("502")))

    r = await connected.post("/api/v1/me/sources/google_calendar/sync")

    assert r.status_code == 503
    assert r.json()["code"] == "calendar_unavailable"
    source = (await db_session.execute(sa.select(ConnectedSource))).scalar_one()
    await db_session.refresh(source)
    assert source.status is SourceStatus.connected


async def test_sync_requires_a_signed_in_user(client):
    r = await client.post("/api/v1/me/sources/google_calendar/sync")

    assert r.status_code == 401


# --- the timeline filter this made live -----------------------------------


async def test_a_cancelled_event_does_not_reach_the_timeline(
    connected, stub_client, db_session, user, make_trip
):
    """The bug the status filter exists for, end to end.

    Latent until this session: the demo seed only ever wrote real events, so
    nothing in the database could be cancelled. The client now asks Google for
    deletions on purpose, so the first real sync writes them, and without the
    filter a cancelled meeting renders as a commitment the traveler still has.
    """
    trip = await make_trip(user)
    stub_client(
        FakeCalendarClient(
            [remote(external_id="live"), remote(external_id="gone", status="cancelled")]
        )
    )
    await connected.post("/api/v1/me/sources/google_calendar/sync")

    # Detection's job, done by hand here: both rows belong to the trip.
    await db_session.execute(
        sa.update(CalendarEvent).values(trip_id=trip.trip_id)
    )
    await db_session.commit()

    r = await connected.get(f"/api/v1/trips/{trip.trip_id}/timeline")

    assert r.status_code == 200
    titles = [
        e["calendar_event"]["title"]
        for e in r.json()["entries"]
        if e["entry_type"] == "calendar_event"
    ]
    assert titles == ["Standup"]

    stored = (await db_session.execute(sa.select(CalendarEvent))).scalars().all()
    # Both rows are stored; only one of them is a commitment.
    assert len(stored) == 2
    assert len([e for e in stored if e.status == "cancelled"]) == 1

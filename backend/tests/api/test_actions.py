"""The propose -> approve -> execute -> verify machine, end to end.

What these are really testing is transitions, because transitions are what the
app has never had. Every seeded reservation is born in its final state, so
`pending` and `canceled` have never existed at runtime and `holding` has never
become anything. A test that asserts only the final status would pass against
the same fake the seed already is, so the walks below assert the whole
sequence.

The runner does not run here: httpx's ASGITransport skips lifespan, so nothing
starts it, and `drive_once` is called directly against a clock the test moves.
That is deliberate - a booking test that sleeps is a slow test and eventually
a flaky one.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.asyncio


def key() -> str:
    return str(uuid.uuid4())


class Clock:
    """A hand-cranked clock. The executor and the provider share it, so a
    booking advances exactly as far as a test says and not one tick more."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 8, 30, 18, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


async def drive(clock: Clock):
    import app.db.engine as db
    from app.services.actions import drive_once

    return await drive_once(db.SessionFactory, clock=clock)


async def find_item(client, trip_id: str, name: str) -> dict:
    plan = (await client.get(f"/api/v1/trips/{trip_id}/plan")).json()
    item = next(i for i in plan["items"] if i["title"] == name)
    return item


async def keep(client, trip_id: str, name: str) -> dict:
    """Answer the suggestion, then return the item. Booking is the gate after
    this one, so almost every test here has to pass through it first."""
    item = await find_item(client, trip_id, name)
    if item["status"] in ("planned", "changed"):
        return item
    response = await client.post(
        f"/api/v1/plan-items/{item['id']}/accept",
        json={"updated_at": item["updated_at"]},
    )
    assert response.status_code == 200, response.text
    return await find_item(client, trip_id, name)


async def propose(client, trip_id: str, item_id: str, **payload) -> dict:
    response = await client.post(
        "/api/v1/actions",
        headers={"Idempotency-Key": key()},
        json={
            "action_type": "make_reservation",
            "trip_id": trip_id,
            "plan_item_id": item_id,
            "payload": payload,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def approve(client, action: dict) -> dict:
    response = await client.post(
        f"/api/v1/actions/{action['id']}/approve",
        json={"updated_at": action["updated_at"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def read(client, action_id: str) -> dict:
    response = await client.get(f"/api/v1/actions/{action_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def test_booking_walks_every_state_it_claims_to_have(authed_client, scene):
    """pending -> holding -> confirmed, each one actually observed.

    The point of the simulator is reaching states the seed cannot. A booking
    that arrives at `confirmed` without passing through the other two would
    reproduce the seed's limitation in code.
    """
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    assert action["status"] == "proposed"
    assert action["summary"]["where"] == "Beatrix"
    assert action["summary"]["party_size"] == 2
    # Nothing has happened yet: proposing is not booking.
    assert "reservation" not in action

    approved = await approve(authed_client, action)
    assert approved["status"] == "approved"

    clock = Clock()
    seen: list[tuple[str, str | None]] = []

    async def step(seconds: float = 0.0) -> dict:
        clock.advance(seconds)
        await drive(clock)
        current = await read(authed_client, action["id"])
        seen.append((current["status"], (current.get("reservation") or {}).get("status")))
        return current

    await step()        # claim, submit, reservation row created
    await step(1)       # still inside the hold window
    await step(2)       # the table is being held
    await step(6)       # settled
    final = await step()

    assert seen == [
        ("executing", "pending"),
        ("executing", "pending"),
        ("executing", "holding"),
        ("completed", "confirmed"),
        ("completed", "confirmed"),
    ], seen
    assert final["reservation"]["confirmation_code"]
    assert final["reservation"]["party_size"] == 2


async def test_confirmed_booking_is_verified_not_just_believed(authed_client, scene, db_session):
    """`verification` holds what the provider said, read back after settling."""
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    await approve(authed_client, action)

    clock = Clock()
    for _ in range(4):
        await drive(clock)
        clock.advance(4)

    row = (
        await db_session.execute(
            sa.text(
                "select status, verification, execution_result from pending_actions "
                "where action_id = :id"
            ),
            {"id": action["id"]},
        )
    ).one()
    status, verification, execution_result = row
    assert status == "completed"
    # Evidence, not a belief: what we were told, kept apart from what we decided.
    assert verification["status"] == "confirmed"
    assert verification["provider"] == "travelwell"
    assert execution_result["handle"]["reference"].startswith("twl_")


async def test_a_refusal_is_reported_with_its_reason_and_a_way_forward(
    authed_client, scene
):
    """A declined booking fails the action and offers to hand off.

    Party size is the steering: a venue that will not seat twelve online is a
    real rule, which is what makes a rehearsed refusal explainable rather than
    a coin flip nobody can reproduce.
    """
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=12)
    await approve(authed_client, action)

    clock = Clock()
    statuses = []
    for _ in range(4):
        await drive(clock)
        statuses.append((await read(authed_client, action["id"]))["status"])
        clock.advance(4)

    final = await read(authed_client, action["id"])
    assert final["status"] == "failed"
    assert final["failure"]["code"] == "provider_declined"
    assert "parties over 8" in final["failure"]["message"]
    # The honest fallback: we could not, here is where you can.
    assert final["failure"]["external_url"].startswith("https://")
    # A refusal never holds a table, so `holding` must not appear on this path.
    assert (final.get("reservation") or {}).get("status") == "failed"
    assert final["reservation"]["failure_reason"]
    # A refusal must not carry a confirmation of anything.
    assert "confirmation_code" not in final["reservation"]


async def test_the_item_walks_the_booking_track_so_the_row_can_say_so(
    authed_client, scene
):
    """planned -> working -> confirmed, which is what the timeline row renders.

    `itemBadge` reads the item's status, not the reservation, and `working` and
    `confirmed` exist for booking and nothing else writes them - the demo seed
    pairs them with a `holding` and a `confirmed` reservation. Without this the
    sheet says "Booked" and the row it was opened from says nothing at all.
    """
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    assert item["status"] == "planned"
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    await approve(authed_client, action)

    clock = Clock()
    seen = [(await find_item(authed_client, scene.trip_id, "Beatrix"))["status"]]
    for _ in range(5):
        await drive(clock)
        seen.append((await find_item(authed_client, scene.trip_id, "Beatrix"))["status"])
        clock.advance(4)

    assert seen[0] == "working", seen
    assert seen[-1] == "confirmed", seen
    assert seen.index("working") < seen.index("confirmed")


async def test_approving_marks_the_item_as_being_booked(authed_client, scene):
    """Before the executor has ticked even once.

    The row has to be able to say "Booking…" the instant the user says yes, and
    the plan query follows an item at `working` on its own — so if this waited
    for the executor, a sheet closed in that first second would strand the row
    until the next navigation. That is a bug this test exists to keep fixed.
    """
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    await approve(authed_client, action)
    # No drive() call at all.
    assert (await find_item(authed_client, scene.trip_id, "Beatrix"))["status"] == "working"


async def test_an_unsupported_action_never_strands_the_item(authed_client, scene, db_session):
    """Any failure hands the item back; nothing stays at `working` forever."""
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    await approve(authed_client, action)
    assert (await find_item(authed_client, scene.trip_id, "Beatrix"))["status"] == "working"

    # Force a failure the executor refuses by name, without touching the item.
    await db_session.execute(
        sa.text("update pending_actions set type = 'send_invite' where action_id = :id"),
        {"id": action["id"]},
    )
    await db_session.commit()
    await drive(Clock())

    assert (await read(authed_client, action["id"]))["status"] == "failed"
    assert (await find_item(authed_client, scene.trip_id, "Beatrix"))["status"] == "planned"


async def test_booking_is_the_gate_after_keeping(authed_client, scene):
    """An unanswered suggestion cannot be booked. Two gates, in order."""
    item = await find_item(authed_client, scene.trip_id, "Beatrix")
    assert item["status"] == "awaiting_user"
    response = await authed_client.post(
        "/api/v1/actions",
        headers={"Idempotency-Key": key()},
        json={
            "action_type": "make_reservation",
            "trip_id": scene.trip_id,
            "plan_item_id": item["id"],
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "invalid_state"


async def test_a_hand_off_never_claims_the_item_is_booked(
    authed_client, scene, monkeypatch
):
    """external_link completes without a table being held, so the item goes back
    to waiting for one. Only a real confirmation earns `confirmed`."""
    monkeypatch.setenv("RESERVATION_PROVIDER", "external_link")
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    await approve(authed_client, action)
    clock = Clock()
    await drive(clock)
    clock.advance(1)
    await drive(clock)

    assert (await read(authed_client, action["id"]))["status"] == "completed"
    assert (await find_item(authed_client, scene.trip_id, "Beatrix"))["status"] == "planned"


async def test_a_failed_booking_returns_the_item_to_where_it_was(authed_client, scene):
    """Execution does not plan. The window stays and is bookable again; only
    the booking failed, and the row says so off the reservation."""
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    before = item["status"]
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=12)
    await approve(authed_client, action)

    clock = Clock()
    for _ in range(4):
        await drive(clock)
        clock.advance(4)

    after = await find_item(authed_client, scene.trip_id, "Beatrix")
    # Back where it started, not stuck at `working` and not skipped.
    assert after["status"] == before == "planned"
    assert after["reservation"]["status"] == "failed"


async def test_external_link_hands_off_instead_of_pretending(
    authed_client, scene, monkeypatch
):
    """The fallback is a complete path, not a degraded one.

    It books nothing and says so: the action completes because producing the
    link *is* the outcome, and the reservation rests at `pending` because
    nobody has booked it. What must not happen is the executor waiting forever
    on a table that will never be held.
    """
    monkeypatch.setenv("RESERVATION_PROVIDER", "external_link")
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    await approve(authed_client, action)

    clock = Clock()
    await drive(clock)
    clock.advance(1)
    await drive(clock)

    final = await read(authed_client, action["id"])
    assert final["status"] == "completed"
    assert final["reservation"]["provider"] == "external_link"
    assert final["reservation"]["status"] == "pending"
    assert final["reservation"]["external_url"].startswith("https://")
    assert "confirmation_code" not in final["reservation"]


async def test_the_same_key_proposes_one_action(authed_client, scene, db_session):
    """Idempotency is real here, unlike on POST /trips: the column exists."""
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    idem = key()
    body = {
        "action_type": "make_reservation",
        "trip_id": scene.trip_id,
        "plan_item_id": item["id"],
        "payload": {"party_size": 2},
    }
    first = await authed_client.post(
        "/api/v1/actions", headers={"Idempotency-Key": idem}, json=body
    )
    second = await authed_client.post(
        "/api/v1/actions", headers={"Idempotency-Key": idem}, json=body
    )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    count = (
        await db_session.execute(sa.text("select count(*) from pending_actions"))
    ).scalar_one()
    assert count == 1


async def test_resubmitting_a_booking_cannot_double_book(authed_client, scene):
    """The action's key is the provider's key, so one guarantee runs end to end."""
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    await approve(authed_client, action)
    clock = Clock()
    await drive(clock)

    import app.db.engine as db
    from app.db.models import PendingAction, ReservationProvider
    from app.services.reservations import BookingRequest, provider_for

    async with db.SessionFactory() as session:
        row = await session.get(PendingAction, uuid.UUID(action["id"]))
        placed = row.execution_result["handle"]["reference"]
        idem = row.idempotency_key

    provider = provider_for(ReservationProvider.travelwell, clock=clock)
    again = await provider.place(
        BookingRequest(
            place_name="Beatrix",
            slot_at=clock(),
            party_size=2,
            idempotency_key=idem,
        )
    )
    assert again.reference == placed


async def test_approve_is_guarded_by_the_token_it_was_read_with(authed_client, scene):
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    stale = "2020-01-01T00:00:00+00:00"
    response = await authed_client.post(
        f"/api/v1/actions/{action['id']}/approve", json={"updated_at": stale}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


async def test_approving_twice_returns_the_same_action(authed_client, scene):
    """A retry whose response was lost deserves the action, not a conflict."""
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    first = await approve(authed_client, action)
    second = await authed_client.post(
        f"/api/v1/actions/{action['id']}/approve",
        json={"updated_at": action["updated_at"]},
    )
    assert second.status_code == 200
    assert second.json()["id"] == first["id"]
    assert second.json()["status"] == "approved"


async def test_unimplemented_action_types_are_refused_by_name(authed_client, scene):
    """Better a clear refusal than a handler that quietly does nothing."""
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    response = await authed_client.post(
        "/api/v1/actions",
        headers={"Idempotency-Key": key()},
        json={
            "action_type": "create_calendar_event",
            "trip_id": scene.trip_id,
            "plan_item_id": item["id"],
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "action_unsupported"


async def test_a_past_trip_takes_no_new_actions(authed_client, scene, db_session):
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    await db_session.execute(
        sa.text("update trips set state = 'completed' where trip_id = :id"),
        {"id": scene.trip_id},
    )
    await db_session.commit()
    response = await authed_client.post(
        "/api/v1/actions",
        headers={"Idempotency-Key": key()},
        json={
            "action_type": "make_reservation",
            "trip_id": scene.trip_id,
            "plan_item_id": item["id"],
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "trip_past"


async def test_another_users_action_is_not_found(client, scene, other_user, sign_in, authed_client):
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    sign_in(client, other_user)
    assert (await client.get(f"/api/v1/actions/{action['id']}")).status_code == 404


async def test_a_booking_that_never_settles_stops_waiting(authed_client, scene, db_session):
    """Denver's seeded reservation says "Holding a table" forever. Nothing in
    the app should be able to do that for real."""
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    await approve(authed_client, action)

    clock = Clock()
    await drive(clock)
    assert (await read(authed_client, action["id"]))["status"] == "executing"

    from app.services.actions import EXECUTION_DEADLINE

    clock.advance(EXECUTION_DEADLINE.total_seconds() + 1)
    await drive(clock)

    final = await read(authed_client, action["id"])
    assert final["status"] == "failed"
    assert final["failure"]["code"] == "provider_timeout"


async def test_cancel_releases_a_confirmed_booking(authed_client, scene):
    """`canceled` is in the enum and no flow has ever reached it."""
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    booking = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    await approve(authed_client, booking)
    clock = Clock()
    for _ in range(4):
        await drive(clock)
        clock.advance(4)
    assert (await read(authed_client, booking["id"]))["reservation"]["status"] == "confirmed"

    response = await authed_client.post(
        "/api/v1/actions",
        headers={"Idempotency-Key": key()},
        json={
            "action_type": "cancel_reservation",
            "trip_id": scene.trip_id,
            "plan_item_id": item["id"],
        },
    )
    assert response.status_code == 201, response.text
    cancel = response.json()
    await approve(authed_client, cancel)
    await drive(clock)

    final = await read(authed_client, cancel["id"])
    assert final["status"] == "completed"
    assert final["reservation"]["status"] == "canceled"


async def test_the_stream_reports_progress_and_closes_on_the_result(authed_client, scene):
    """SSE is how the screen finds out, since approving returns immediately."""
    item = await keep(authed_client, scene.trip_id, "Beatrix")
    action = await propose(authed_client, scene.trip_id, item["id"], party_size=2)
    await approve(authed_client, action)

    clock = Clock()
    for _ in range(4):
        await drive(clock)
        clock.advance(4)

    async with authed_client.stream(
        "GET", f"/api/v1/actions/{action['id']}/events"
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in response.aiter_text()])

    assert "event: status" in body
    assert "event: trace" in body
    assert "event: result" in body
    # The copy never speaks as "I"; the product does not have a first person.
    assert '"I ' not in body

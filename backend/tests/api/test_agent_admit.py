"""Stage 1 against a real database: the claim, the sweep, and the gate.

The sweep gets three tests rather than one because a gate needs three
demonstrations: that it fires, that it stays quiet for the *right* reason, and
that it sits where the thing it judges is visible. The third is
`test_sweep_unblocks_a_trip_its_orphan_was_holding` - it is the only one that
fails if someone moves `reap_stale_runs` after the at-most-one check, which is
the regression that would quietly restore the bug this slice exists to fix.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from tests.api.test_agent_context import TZ, build_scene

# Every test here is async; a module-level mark beats repeating the decorator.
pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 2, 14, tzinfo=TZ)


@pytest.fixture
def scene(user):
    return build_scene(user)


async def _session():
    import app.db.engine as db

    return db.SessionFactory()


async def make_event(user, *, kind, trip_id=None, payload=None, received_at=None):
    import app.db.engine as db
    from app.db.models import AgentEvent

    async with db.SessionFactory() as session:
        event = AgentEvent(
            user_id=user.user_id,
            trip_id=trip_id,
            kind=kind,
            payload=payload or {},
            occurred_at=NOW,
        )
        if received_at is not None:
            event.received_at = received_at
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event


async def make_run(trip_id, *, started_at, status=None):
    import app.db.engine as db
    from app.db.models import AgentRun, RunKind, RunStatus

    async with db.SessionFactory() as session:
        run = AgentRun(
            trip_id=trip_id,
            kind=RunKind.pretrip_plan,
            status=status or RunStatus.running,
            started_at=started_at,
            model="gemini-test",
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run


async def reload_run(run_id):
    import app.db.engine as db
    from app.db.models import AgentRun

    async with db.SessionFactory() as session:
        return await session.get(AgentRun, run_id)


async def reload_event(event_id):
    import app.db.engine as db
    from app.db.models import AgentEvent

    async with db.SessionFactory() as session:
        return await session.get(AgentEvent, event_id)


async def admit_event(event_id, *, now=NOW):
    import app.db.engine as db
    from app.agent.admit import admit
    from app.db.models import AgentEvent

    async with db.SessionFactory() as session:
        event = await session.get(AgentEvent, event_id)
        return await admit(session, event, now=now)


# ---------------------------------------------------------------------------
# The sweep


async def test_sweep_cancels_a_run_past_the_timeout(scene):
    import app.db.engine as db
    from app.agent.admit import reap_stale_runs
    from app.db.models import RunStatus

    trip_id = await scene()
    run = await make_run(trip_id, started_at=NOW - timedelta(hours=2))

    async with db.SessionFactory() as session:
        reaped = await reap_stale_runs(session, now=NOW)
        await session.commit()

    assert reaped == 1
    after = await reload_run(run.run_id)
    # canceled, not failed: the provider may well have answered and the process
    # died before writing, and `failed` is what the replay path reads.
    assert after.status is RunStatus.canceled
    assert after.finished_at == NOW
    assert "swept by admit" in after.error


async def test_sweep_leaves_a_run_inside_the_timeout_alone(scene):
    import app.db.engine as db
    from app.agent.admit import reap_stale_runs
    from app.db.models import RunStatus

    trip_id = await scene()
    run = await make_run(trip_id, started_at=NOW - timedelta(seconds=30))

    async with db.SessionFactory() as session:
        reaped = await reap_stale_runs(session, now=NOW)
        await session.commit()

    assert reaped == 0
    assert (await reload_run(run.run_id)).status is RunStatus.running


async def test_sweep_unblocks_a_trip_its_orphan_was_holding(scene, user):
    """The ordering test. An orphaned run makes the trip look busy; the sweep
    has to happen before the check, or the trip is blocked for ever."""
    from app.db.models import EventDisposition, EventKind, RunStatus

    trip_id = await scene()
    orphan = await make_run(trip_id, started_at=NOW - timedelta(hours=2))

    event = await make_event(user, kind=EventKind.scheduled_activation, trip_id=trip_id)
    run = await admit_event(event.event_id)

    assert run is not None, "the orphan blocked admission; sweep ran too late"
    assert (await reload_run(orphan.run_id)).status is RunStatus.canceled
    assert (await reload_event(event.event_id)).disposition is (
        EventDisposition.accepted
    )
    assert run.status is RunStatus.running


# ---------------------------------------------------------------------------
# Classification


async def test_activation_on_a_confirmed_trip_creates_its_run(scene, user):
    from app.db.models import EventDisposition, EventKind, RunKind

    trip_id = await scene()
    event = await make_event(user, kind=EventKind.scheduled_activation, trip_id=trip_id)

    run = await admit_event(event.event_id)

    assert run is not None
    assert run.kind is RunKind.pretrip_plan
    assert run.trip_id == trip_id
    # The point of committing them together: accepted and no run cannot happen.
    assert run.trigger_event_id == event.event_id
    assert (await reload_event(event.event_id)).disposition is (
        EventDisposition.accepted
    )


async def test_a_live_run_drops_the_second_event_rather_than_paying_twice(scene, user):
    import app.db.engine as db
    from app.db.models import AgentRun, EventDisposition, EventKind

    trip_id = await scene()
    first = await make_event(user, kind=EventKind.scheduled_activation, trip_id=trip_id)
    assert await admit_event(first.event_id) is not None

    second = await make_event(
        user, kind=EventKind.scheduled_activation, trip_id=trip_id
    )
    assert await admit_event(second.event_id) is None

    assert (await reload_event(second.event_id)).disposition is (
        EventDisposition.dropped_immaterial
    )
    async with db.SessionFactory() as session:
        count = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(AgentRun)
                .where(AgentRun.trip_id == trip_id)
            )
        ).scalar_one()
    assert count == 1


async def test_a_trip_past_its_activation_states_is_immaterial(scene, user):
    import app.db.engine as db
    from app.db.models import EventDisposition, EventKind, Trip, TripState

    trip_id = await scene()
    async with db.SessionFactory() as session:
        trip = await session.get(Trip, trip_id)
        trip.state = TripState.completed
        await session.commit()

    event = await make_event(user, kind=EventKind.scheduled_activation, trip_id=trip_id)
    assert await admit_event(event.event_id) is None
    assert (await reload_event(event.event_id)).disposition is (
        EventDisposition.dropped_immaterial
    )


async def test_an_activation_not_yet_due_is_not_run_early(scene, user):
    import app.db.engine as db
    from app.db.models import EventDisposition, EventKind, Trip

    trip_id = await scene()
    async with db.SessionFactory() as session:
        trip = await session.get(Trip, trip_id)
        trip.activation_at = NOW + timedelta(days=1)
        await session.commit()

    event = await make_event(user, kind=EventKind.scheduled_activation, trip_id=trip_id)
    assert await admit_event(event.event_id) is None
    assert (await reload_event(event.event_id)).disposition is (
        EventDisposition.dropped_immaterial
    )


async def test_an_activation_for_a_missing_trip_drops_no_trip(user):
    from app.db.models import EventDisposition, EventKind

    event = await make_event(user, kind=EventKind.scheduled_activation, trip_id=None)
    assert await admit_event(event.event_id) is None
    assert (await reload_event(event.event_id)).disposition is (
        EventDisposition.dropped_no_trip
    )


async def test_a_user_message_resolves_a_trip_but_has_no_run_to_go_to(scene, user):
    """user_request is unbuilt. The drop is about our capability, and the
    disposition says so rather than pretending the event was meaningless."""
    import app.db.engine as db
    from app.agent.admit import DropReason, classify
    from app.db.models import AgentEvent, EventDisposition, EventKind

    trip_id = await scene()
    event = await make_event(
        user, kind=EventKind.user_text, payload={"text": "find me a pool"}
    )

    async with db.SessionFactory() as session:
        row = await session.get(AgentEvent, event.event_id)
        decision = await classify(session, row, now=NOW)

    assert decision.disposition is EventDisposition.dropped_immaterial
    assert decision.reason is DropReason.run_kind_not_built
    assert decision.trip_id == trip_id


# ---------------------------------------------------------------------------
# The claim


async def test_claim_takes_the_oldest_pending_event_and_nothing_when_empty(user):
    import app.db.engine as db
    from app.agent.admit import claim_pending
    from app.db.models import EventKind

    older = await make_event(
        user,
        kind=EventKind.user_text,
        received_at=datetime(2026, 9, 1, 9, tzinfo=UTC),
    )
    await make_event(
        user,
        kind=EventKind.user_text,
        received_at=datetime(2026, 9, 1, 10, tzinfo=UTC),
    )

    async with db.SessionFactory() as session:
        claimed = await claim_pending(session)
        assert claimed is not None
        assert claimed.event_id == older.event_id
        await session.rollback()

    async with db.SessionFactory() as session:
        from app.db.models import AgentEvent, EventDisposition

        await session.execute(
            sa.update(AgentEvent).values(disposition=EventDisposition.accepted)
        )
        await session.commit()

    async with db.SessionFactory() as session:
        assert await claim_pending(session) is None


# ---------------------------------------------------------------------------
# The endpoint


async def test_post_events_records_a_pending_row(authed_client, scene):
    from app.db.models import EventDisposition

    trip_id = await scene()

    response = await authed_client.post(
        "/api/v1/events",
        json={"kind": "ui_action", "trip_id": str(trip_id), "payload": {"a": 1}},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    assert response.status_code == 202, response.text
    stored = await reload_event(uuid.UUID(response.json()["event_id"]))
    # Classification happens once, in the worker's claim, not a second time
    # here, so the row is still pending when the response is written.
    assert stored.disposition is EventDisposition.pending
    assert stored.trip_id == trip_id


async def test_a_retried_post_lands_on_the_event_that_already_exists(
    authed_client, scene
):
    """The header the contract requires, doing what its description promises.
    For scheduled_activation the difference is a second paid run."""
    import app.db.engine as db
    from app.db.models import AgentEvent

    trip_id = await scene()
    body = {"kind": "scheduled_activation", "trip_id": str(trip_id), "payload": {}}
    headers = {"Idempotency-Key": str(uuid.uuid4())}

    first = await authed_client.post("/api/v1/events", json=body, headers=headers)
    second = await authed_client.post("/api/v1/events", json=body, headers=headers)

    assert first.status_code == second.status_code == 202
    assert first.json()["event_id"] == second.json()["event_id"]
    async with db.SessionFactory() as session:
        count = (
            await session.execute(sa.select(sa.func.count()).select_from(AgentEvent))
        ).scalar_one()
    assert count == 1


async def test_post_events_refuses_a_producer_owned_kind(authed_client):
    response = await authed_client.post(
        "/api/v1/events",
        json={"kind": "calendar_changed", "payload": {}},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "event_kind_not_client_originated"


async def test_post_events_will_not_target_someone_elses_trip(
    authed_client, scene, other_user
):
    """Same 404 as a missing trip: existence is private."""
    trip_id = await scene()

    import app.db.engine as db
    from app.db.models import Trip

    async with db.SessionFactory() as session:
        theirs = await session.get(Trip, trip_id)
        theirs.user_id = other_user.user_id
        await session.commit()

    response = await authed_client.post(
        "/api/v1/events",
        json={"kind": "ui_action", "trip_id": str(trip_id), "payload": {}},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 404


async def test_post_events_is_behind_the_auth_gate(client):
    """Not a proxy for the gate's config: an unauthenticated post, refused."""
    response = await client.post(
        "/api/v1/events",
        json={"kind": "ui_action", "payload": {}},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 401, response.text

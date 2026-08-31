"""The whole pipeline against a real database, with a scripted model.

This is the coverage that makes retiring the prototype ADK layer a deletion
*into* a test rather than out of one. Nine of the ten stages are deterministic,
so `FakeLLM` reaches every one of them with no network and no credentials -
which is why this lives in `tests/api`, where CI runs, and not in
`tests/integration`, which CI deliberately skips.
"""

import json
from datetime import datetime, timedelta

import pytest

from tests.api.test_agent_context import DAY_ONE, TZ, build_scene, run_gather


@pytest.fixture
def gather_scene(user):
    return build_scene(user)

NOW = datetime(2026, 9, 2, 14, tzinfo=TZ)
MODEL = "gemini-test"


def plan_for(ctx) -> dict:
    """A valid proposal built from the ids this context actually contains.

    Constructed rather than hardcoded: the candidate ids are positional and move
    whenever the pre-rank changes, and a test that pins them fails for a reason
    that has nothing to do with what it is asserting.
    """
    window = next(
        w for w in ctx.windows if any(w.id in c.window_ids for c in ctx.candidates)
    )
    candidate = next(c for c in ctx.candidates if window.id in c.window_ids)
    start_h, start_m = (int(part) for part in window.start.split(":"))
    end = f"{start_h + 1:02d}:{start_m:02d}"
    return {
        "headline": "Room for a swim",
        "window_notes": [
            {"window_id": window.id, "gap_explanation": "Between your commitments."}
        ],
        "items": [
            {
                "window_id": window.id,
                "kind": "activity",
                "start": window.start,
                "end": end,
                "options": [
                    {
                        "candidate_id": candidate.id,
                        "reason": "The pool you asked for, close to the hotel.",
                        "matched_preferences": ["pool"],
                        "state": "selected",
                        "rank": 1,
                    }
                ],
            }
        ],
    }


async def run_pipeline(trip_id, responses):
    import app.db.engine as db
    from app.agent.llm import FakeLLM
    from app.agent.runs import run_pretrip_plan

    client = FakeLLM(responses)
    async with db.SessionFactory() as session:
        outcome = await run_pretrip_plan(
            session, trip_id=trip_id, client=client, model=MODEL, now=NOW
        )
    return outcome, client


async def rows(model, **filters):
    import sqlalchemy as sa

    import app.db.engine as db

    async with db.SessionFactory() as session:
        stmt = sa.select(model)
        for column, value in filters.items():
            stmt = stmt.where(getattr(model, column) == value)
        return list((await session.execute(stmt)).scalars())


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_run_turns_a_trip_into_a_published_plan(gather_scene):
    from app.db.models import (
        AgentRun,
        ItemStatus,
        Notification,
        Plan,
        PlanItem,
        PlanItemOption,
        PlanStatus,
        RunStatus,
        WellnessWindow,
    )

    trip_id = await gather_scene()
    gathered = await run_gather(trip_id)
    outcome, client = await run_pipeline(trip_id, [json.dumps(plan_for(gathered.context))])

    assert outcome.status == RunStatus.completed
    assert client.call_count == 1

    plans = await rows(Plan, trip_id=trip_id)
    assert [p.version for p in plans] == [1]
    assert plans[0].status == PlanStatus.proposed
    assert plans[0].generated_by_run_id == outcome.run_id

    items = await rows(PlanItem, trip_id=trip_id)
    assert len(items) == 1
    # Published, so the keep/skip gate: `suggested` never reaches a client.
    assert items[0].status == ItemStatus.awaiting_user

    options = await rows(PlanItemOption, item_id=items[0].item_id)
    assert len(options) == 1

    windows = await rows(WellnessWindow, trip_id=trip_id)
    assert len(windows) == len(gathered.context.windows)

    runs = await rows(AgentRun, trip_id=trip_id)
    assert runs[0].status == RunStatus.completed
    assert runs[0].context_snapshot["trip"]["destination"] == "Chicago"
    assert runs[0].model == MODEL

    notifications = await rows(Notification, trip_id=trip_id)
    assert notifications[0].kind == "plan_ready"
    assert notifications[0].cta["deep_link"] == f"/trip?trip={trip_id}"


@pytest.mark.asyncio
async def test_display_fields_come_from_our_records_not_the_model(gather_scene):
    """The model supplies an id and prose. Everything a user reads as fact is ours."""
    from app.db.models import Place, PlanItem, PlanItemOption

    trip_id = await gather_scene()
    gathered = await run_gather(trip_id)
    proposal = plan_for(gathered.context)
    await run_pipeline(trip_id, [json.dumps(proposal)])

    items = await rows(PlanItem, trip_id=trip_id)
    option = (await rows(PlanItemOption, item_id=items[0].item_id))[0]
    place = (await rows(Place, place_id=option.place_id))[0]

    assert option.display_name == place.name
    assert option.display_summary == place.summary
    assert option.reason == proposal["items"][0]["options"][0]["reason"]
    assert option.duration_minutes == 60


@pytest.mark.asyncio
async def test_bind_leaves_items_at_suggested_until_publish(gather_scene):
    """The two halves of decision 3, asserted apart.

    Bind writing `awaiting_user` directly would pass every other test in this
    file, which is exactly why the pre-publish state is checked on its own.
    """
    import app.db.engine as db
    from app.agent.runs import bind, publish_plan
    from app.agent.schemas import PlanProposal
    from app.db.models import ItemStatus, PlanStatus, Trip

    trip_id = await gather_scene()
    gathered = await run_gather(trip_id)
    proposal = PlanProposal.model_validate(plan_for(gathered.context))

    async with db.SessionFactory() as session:
        trip = await session.get(Trip, trip_id)
        run = await _running_run(session, trip_id)
        plan = await bind(session, gathered, proposal, trip=trip, run=run)

        items = await rows_in(session, plan.plan_id)
        assert plan.status == PlanStatus.draft
        assert [i.status for i in items] == [ItemStatus.suggested]

        flipped = await publish_plan(session, plan)
        assert flipped == 1
        assert plan.status == PlanStatus.proposed
        items = await rows_in(session, plan.plan_id)
        assert [i.status for i in items] == [ItemStatus.awaiting_user]
        await session.rollback()


async def _running_run(session, trip_id):
    from app.db.models import AgentRun, RunKind, RunStatus

    run = AgentRun(trip_id=trip_id, kind=RunKind.pretrip_plan, status=RunStatus.running)
    session.add(run)
    await session.flush()
    return run


async def rows_in(session, plan_id):
    import sqlalchemy as sa

    from app.db.models import PlanItem

    result = await session.execute(
        sa.select(PlanItem).where(PlanItem.plan_id == plan_id).execution_options(
            populate_existing=True
        )
    )
    return list(result.scalars())


@pytest.mark.asyncio
async def test_publish_does_not_touch_items_the_agent_handles_itself(gather_scene):
    """`planned` items are written directly and the flip must skip them."""
    import app.db.engine as db
    from app.agent.runs import publish_plan
    from app.db.models import ItemKind, ItemStatus, Plan, PlanItem, PlanStatus

    trip_id = await gather_scene()
    async with db.SessionFactory() as session:
        plan = Plan(trip_id=trip_id, version=1, status=PlanStatus.draft)
        session.add(plan)
        await session.flush()
        session.add_all([
            PlanItem(
                plan_id=plan.plan_id, trip_id=trip_id, kind=ItemKind.activity,
                scheduled_start=datetime.combine(DAY_ONE, datetime.min.time(), TZ),
                status=ItemStatus.planned,
            ),
            PlanItem(
                plan_id=plan.plan_id, trip_id=trip_id, kind=ItemKind.activity,
                scheduled_start=datetime.combine(DAY_ONE, datetime.min.time(), TZ),
            ),
        ])
        await session.flush()

        assert await publish_plan(session, plan) == 1
        statuses = sorted(i.status for i in await rows_in(session, plan.plan_id))
        assert statuses == [ItemStatus.awaiting_user, ItemStatus.planned]
        await session.rollback()


# ---------------------------------------------------------------------------
# The paths that must not write a plan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_empty_decision_space_never_calls_the_model(empty_trip):
    """A model call with nothing to choose from buys nothing and adds a
    hallucination opportunity. `FakeLLM` with no script raises if reached."""
    from app.db.models import AgentRun, Plan, PlanItem, RunStatus

    trip_id = await empty_trip()
    outcome, client = await run_pipeline(trip_id, [])

    assert outcome.status == RunStatus.completed
    assert client.call_count == 0
    assert outcome.item_count == 0
    assert (await rows(Plan, trip_id=trip_id))[0].version == 1
    assert await rows(PlanItem, trip_id=trip_id) == []
    assert (await rows(AgentRun, trip_id=trip_id))[0].result["invoked"] is False


@pytest.mark.asyncio
async def test_a_failed_verify_writes_the_run_and_no_plan_rows(gather_scene):
    """The asymmetry Commit lives with: the spend stays auditable, the plan
    tables stay clean."""
    from app.db.models import AgentRun, Plan, RunStatus

    trip_id = await gather_scene()
    gathered = await run_gather(trip_id)
    bad = plan_for(gathered.context)
    bad["items"][0]["window_id"] = "w-does-not-exist"

    outcome, client = await run_pipeline(trip_id, [json.dumps(bad), json.dumps(bad)])

    assert outcome.status == RunStatus.failed
    assert outcome.error == "verify:invalid"
    assert client.call_count == 2
    assert await rows(Plan, trip_id=trip_id) == []

    run = (await rows(AgentRun, trip_id=trip_id))[0]
    assert run.status == RunStatus.failed
    assert run.error.startswith("verify:invalid")
    assert run.result["violations"][0]["code"] == "unknown_window"
    assert run.context_snapshot is not None


@pytest.mark.asyncio
async def test_a_second_run_supersedes_the_first(gather_scene):
    from app.db.models import Plan, PlanStatus

    trip_id = await gather_scene()
    gathered = await run_gather(trip_id)
    script = [json.dumps(plan_for(gathered.context))]

    await run_pipeline(trip_id, script)
    await run_pipeline(trip_id, script)

    plans = sorted(await rows(Plan, trip_id=trip_id), key=lambda p: p.version)
    assert [p.version for p in plans] == [1, 2]
    assert plans[0].status == PlanStatus.superseded
    assert plans[1].status == PlanStatus.proposed


@pytest.fixture
def empty_trip(user):
    """A trip with no commitments and nothing cached within walking distance."""

    async def _build():
        import app.db.engine as db
        from app.db.models import Trip, TripOrigin, TripState

        async with db.SessionFactory() as session:
            trip = Trip(
                user_id=user.user_id,
                destination_city="Reykjavik",
                timezone="Atlantic/Reykjavik",
                start_date=DAY_ONE,
                end_date=DAY_ONE + timedelta(days=1),
                state=TripState.confirmed,
                origin=TripOrigin.manual,
                hotel_name="Nowhere in the cache",
                hotel_lat=64.1466,
                hotel_lng=-21.9426,
            )
            session.add(trip)
            await session.commit()
            return trip.trip_id

    return _build

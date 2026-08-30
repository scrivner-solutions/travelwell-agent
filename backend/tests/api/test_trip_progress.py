"""plan_progress and needs_you_kind: the two rollups a trip row renders.

Both come from TRIP_PROGRESS_SQL in one pass, so the cases worth covering are
the ones where the query has to *exclude* something -- a superseded plan, a
skipped item -- and the precedence order between working and settled states.
"""

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.asyncio


@pytest.fixture
def make_plan(clean_tables):
    """A plan on a trip with items at the given statuses, options omitted."""

    async def _make(trip, *statuses, plan_status="proposed"):
        from datetime import datetime, timedelta

        import app.db.engine as db
        from app.db.models import ItemKind, ItemStatus, Plan, PlanItem, PlanStatus

        start = datetime.now().astimezone() + timedelta(days=30)
        async with db.SessionFactory() as session:
            plan = Plan(
                trip_id=trip.trip_id,
                version=1,
                status=PlanStatus(plan_status),
                headline="Test plan",
            )
            session.add(plan)
            await session.flush()
            for n, status in enumerate(statuses):
                session.add(
                    PlanItem(
                        plan_id=plan.plan_id,
                        trip_id=trip.trip_id,
                        kind=ItemKind.activity,
                        status=ItemStatus(status),
                        scheduled_start=start + timedelta(hours=n),
                    )
                )
            await session.commit()
            return plan

    return _make


@pytest.fixture
def make_action(clean_tables):
    """pending_actions has no ORM model yet; textual insert, as the seed does."""

    async def _make(trip, user, *, status="proposed", approval_required=True):
        import app.db.engine as db

        async with db.engine.begin() as conn:
            await conn.execute(
                sa.text(
                    """
                    insert into pending_actions
                        (trip_id, user_id, type, status, approval_required,
                         proposed_payload)
                    values (:trip, :user, 'make_reservation', :status,
                            :approval, '{}'::jsonb)
                    """
                ),
                {
                    "trip": trip.trip_id,
                    "user": user.user_id,
                    "status": status,
                    "approval": approval_required,
                },
            )

    return _make


async def _row(client, trip_id) -> dict:
    r = await client.get(f"/api/v1/trips/{trip_id}")
    assert r.status_code == 200, r.text
    return r.json()


async def test_trip_without_a_plan_reports_none(authed_client, user, make_trip):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.confirmed)
    body = await _row(authed_client, trip.trip_id)

    # A confirmed trip far from its start date has nothing to say, and silence
    # is the correct rendering of "nothing has happened and nothing should have".
    assert body["plan_progress"] == "none"
    assert body["needs_you_count"] == 0
    assert body.get("needs_you_kind") is None


async def test_all_items_decided_reports_planned(
    authed_client, user, make_trip, make_plan
):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.confirmed)
    await make_plan(trip, "planned", "confirmed")

    assert (await _row(authed_client, trip.trip_id))["plan_progress"] == "planned"


async def test_one_undecided_item_blocks_planned(
    authed_client, user, make_trip, make_plan
):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.confirmed)
    await make_plan(trip, "planned", "suggested")

    # "Planned" means the whole plan is settled; a partially accepted plan is
    # not a weaker version of that, it is a different thing.
    assert (await _row(authed_client, trip.trip_id))["plan_progress"] == "none"


async def test_skipped_items_do_not_block_planned(
    authed_client, user, make_trip, make_plan
):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.confirmed)
    await make_plan(trip, "planned", "skipped", "removed")

    # Skipping is a decision, so a skipped item is decided, not outstanding.
    assert (await _row(authed_client, trip.trip_id))["plan_progress"] == "planned"


async def test_empty_plan_is_not_planned(authed_client, user, make_trip, make_plan):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.confirmed)
    await make_plan(trip)

    # Vacuous truth is the trap here: zero undecided items out of zero items
    # would otherwise read as an accepted plan.
    assert (await _row(authed_client, trip.trip_id))["plan_progress"] == "none"


async def test_working_item_reports_booking(authed_client, user, make_trip, make_plan):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.confirmed)
    await make_plan(trip, "planned", "working")

    # The working badge takes the slot the settled one will get back.
    assert (await _row(authed_client, trip.trip_id))["plan_progress"] == "booking"


async def test_preparing_outranks_the_item_rollup(
    authed_client, user, make_trip, make_plan
):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.preparing)
    await make_plan(trip, "planned")

    # The agent is mid-run, so what the current items say is already stale.
    assert (await _row(authed_client, trip.trip_id))["plan_progress"] == "preparing"


async def test_superseded_plan_is_invisible(authed_client, user, make_trip, make_plan):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.confirmed)
    await make_plan(trip, "awaiting_user", "suggested", plan_status="superseded")
    body = await _row(authed_client, trip.trip_id)

    # Leftovers from a replaced version must not ask the user for anything;
    # filtering by item status alone would have counted them.
    assert body["plan_progress"] == "none"
    assert body["needs_you_count"] == 0


async def test_draft_plan_is_invisible(authed_client, user, make_trip, make_plan):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.confirmed)
    await make_plan(trip, "awaiting_user", plan_status="draft")

    assert (await _row(authed_client, trip.trip_id))["needs_you_count"] == 0


async def test_plan_decisions_name_the_plan_gate(
    authed_client, user, make_trip, make_plan
):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.confirmed)
    await make_plan(trip, "awaiting_user", "awaiting_user", "planned")
    body = await _row(authed_client, trip.trip_id)

    assert body["needs_you_count"] == 2
    assert body["needs_you_kind"] == "plan"


async def test_approvals_name_the_approval_gate(
    authed_client, user, make_trip, make_plan, make_action
):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.confirmed)
    await make_plan(trip, "planned")
    await make_action(trip, user)
    body = await _row(authed_client, trip.trip_id)

    assert body["needs_you_count"] == 1
    assert body["needs_you_kind"] == "approval"


async def test_both_gates_open_reports_mixed(
    authed_client, user, make_trip, make_plan, make_action
):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.confirmed)
    await make_plan(trip, "awaiting_user")
    await make_action(trip, user)
    body = await _row(authed_client, trip.trip_id)

    # Two kinds of work cannot be named by one phrase, so the row falls back
    # to the count.
    assert body["needs_you_count"] == 2
    assert body["needs_you_kind"] == "mixed"


async def test_action_not_needing_approval_is_not_an_ask(
    authed_client, user, make_trip, make_action
):
    from app.db.models import TripState

    trip = await make_trip(user, state=TripState.confirmed)
    await make_action(trip, user, approval_required=False)
    body = await _row(authed_client, trip.trip_id)

    assert body["needs_you_count"] == 0
    assert body.get("needs_you_kind") is None


async def test_detection_counts_without_naming_a_kind(authed_client, user, make_trip):
    trip = await make_trip(user)
    body = await _row(authed_client, trip.trip_id)

    # Gate 1 lives in its own section, so it contributes to the count the tab
    # badge sums but never labels a row in the trips list.
    assert body["state"] == "detected"
    assert body["needs_you_count"] == 1
    assert body.get("needs_you_kind") is None


async def test_scene_reports_an_unfinished_plan(authed_client, scene):
    body = await _row(authed_client, scene.trip_id)

    # Chicago has two suggested items and one awaiting_user, so it is neither
    # planned nor silent.
    assert body["plan_progress"] == "none"
    assert body["needs_you_count"] == 1
    assert body["needs_you_kind"] == "plan"

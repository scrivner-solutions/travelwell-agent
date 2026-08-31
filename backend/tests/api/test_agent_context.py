"""Gather against a real database: a trip goes in, a TripContext comes out.

The milestone this belongs to has no model in it. Everything asserted here is a
projection or an arithmetic result, which is the point - nine of the ten stages
are supposed to be answerable without a provider.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

TZ = ZoneInfo("America/Chicago")
DAY_ONE = date(2026, 9, 9)


def build_scene(user):
    """A two-day Chicago trip with three commitments and three cached places.

    One commitment is declined (`busy=False`), which is the case that tells
    the two `is_busy` implementations apart.

    A plain factory rather than the fixture itself, so another module can reuse
    the scene by declaring its own one-line fixture. Importing a fixture works
    but reads to every linter as a redefinition at each use site.
    """

    async def _build():
        import app.db.engine as db
        from app.db.models import (
            CalendarEvent,
            ConnectedSource,
            SourceKind,
            Trip,
            TripOrigin,
            TripState,
            UserPreferences,
        )
        from app.db.models import Place as PlaceRow

        def at(day: date, hour: int, minute: int = 0) -> datetime:
            return datetime.combine(day, time(hour, minute), TZ)

        async with db.SessionFactory() as session:
            trip = Trip(
                user_id=user.user_id,
                destination_city="Chicago",
                timezone="America/Chicago",
                start_date=DAY_ONE,
                end_date=DAY_ONE + timedelta(days=1),
                state=TripState.confirmed,
                origin=TripOrigin.calendar_detection,
                hotel_name="The Gwen",
                hotel_lat=41.8924,
                hotel_lng=-87.6252,
            )
            source = ConnectedSource(
                user_id=user.user_id, kind=SourceKind.google_calendar
            )
            session.add_all([trip, source])
            await session.flush()

            session.add_all([
                CalendarEvent(
                    user_id=user.user_id,
                    source_id=source.source_id,
                    trip_id=trip.trip_id,
                    external_id="ev-1",
                    title="Workshop day 1",
                    starts_at=at(DAY_ONE, 9),
                    ends_at=at(DAY_ONE, 17),
                    content_hash="h1",
                ),
                CalendarEvent(
                    user_id=user.user_id,
                    source_id=source.source_id,
                    trip_id=trip.trip_id,
                    external_id="ev-2",
                    title="Team dinner\x07",
                    starts_at=at(DAY_ONE, 19, 30),
                    ends_at=at(DAY_ONE, 21),
                    content_hash="h2",
                ),
                CalendarEvent(
                    user_id=user.user_id,
                    source_id=source.source_id,
                    trip_id=trip.trip_id,
                    external_id="ev-3",
                    title="Standup they declined",
                    starts_at=at(DAY_ONE + timedelta(days=1), 10),
                    ends_at=at(DAY_ONE + timedelta(days=1), 11),
                    busy=False,
                    content_hash="h3",
                ),
            ])
            session.add(
                UserPreferences(
                    user_id=user.user_id,
                    activities=["swim"],
                    amenities=["pool"],
                    dietary=["vegetarian"],
                    day_pass_budget_cents=2000,
                    session_min_minutes=45,
                    session_max_minutes=90,
                )
            )
            weekday_hours = {
                "mon": [360, 1320], "tue": [360, 1320], "wed": [360, 1320],
                "thu": [360, 1320], "fri": [360, 1290], "sat": [420, 1200],
                "sun": [420, 1200],
            }
            session.add_all([
                PlaceRow(
                    provider_ref="p-pool", kind="workout", name="Lakeshore",
                    lat=41.8887, lng=-87.6180, amenities=["pool"],
                    day_pass_cents=2000, hours=weekday_hours,
                ),
                PlaceRow(
                    provider_ref="p-gym", kind="workout", name="Hotel gym",
                    lat=41.8924, lng=-87.6252, amenities=["treadmill"],
                    day_pass_cents=0, hours=weekday_hours,
                ),
                PlaceRow(
                    provider_ref="p-far", kind="workout", name="Evanston pool",
                    lat=42.0451, lng=-87.6877, amenities=["pool"],
                    day_pass_cents=0, hours=weekday_hours,
                ),
                PlaceRow(
                    provider_ref="p-pricey", kind="workout", name="Athletic Club",
                    lat=41.8814, lng=-87.6246, amenities=["pool"],
                    day_pass_cents=3500, hours=weekday_hours,
                ),
            ])
            await session.commit()
            return trip.trip_id

    return _build


@pytest.fixture
def gather_scene(user):
    return build_scene(user)


async def run_gather(trip_id):
    import app.db.engine as db
    from app.agent.context import gather

    async with db.SessionFactory() as session:
        return await gather(
            session,
            trip_id,
            run_kind="pretrip_plan",
            prompt_version="pretrip-v1",
            now=datetime(2026, 9, 2, 14, tzinfo=TZ),
        )


@pytest.mark.asyncio
async def test_windows_are_the_gaps_between_commitments(gather_scene):
    result = await run_gather(await gather_scene())
    day_one = [w for w in result.context.windows if w.day == DAY_ONE]
    assert [(w.start, w.end) for w in day_one] == [
        ("07:00", "09:00"),
        ("17:00", "19:30"),
        # After dinner is genuinely free and nobody swims at 9pm. Windows are
        # capacity, not demand: leaving this one empty is the planner's call,
        # not something to filter out here.
        ("21:00", "22:00"),
    ]
    assert day_one[1].bounded_by == ["Workshop day 1", "Team dinner"]


@pytest.mark.asyncio
async def test_a_free_day_is_one_window(gather_scene):
    result = await run_gather(await gather_scene())
    day_two = [w for w in result.context.windows if w.day == DAY_ONE + timedelta(days=1)]
    assert len(day_two) == 1 and day_two[0].minutes == 900


@pytest.mark.asyncio
async def test_a_declined_commitment_does_not_carve_a_window(gather_scene):
    """Gather consumes `app.services.calendar.is_busy`; it defines no rule.

    The declined standup sits inside day two and the day is still one window.
    This is the accuser for a second `is_busy` growing here again: a local rule
    that treats every row as busy splits the day and turns this red.
    """
    result = await run_gather(await gather_scene())
    day_two = [w for w in result.context.windows if w.day == DAY_ONE + timedelta(days=1)]
    assert len(day_two) == 1
    assert "Standup they declined" in [c.title for c in result.context.commitments]


@pytest.mark.asyncio
async def test_commitment_titles_are_cleaned_but_keep_their_own_voice(gather_scene):
    result = await run_gather(await gather_scene())
    titles = [c.title for c in result.context.commitments]
    assert titles == ["Workshop day 1", "Team dinner", "Standup they declined"]


@pytest.mark.asyncio
async def test_candidates_are_filtered_by_budget_and_distance(gather_scene):
    result = await run_gather(await gather_scene())
    names = [c.name for c in result.context.candidates]
    assert "Athletic Club" not in names, "over the $20 day pass cap"
    assert "Evanston pool" not in names, "outside walking range"
    assert names == ["Lakeshore", "Hotel gym"], "pool matches the preference first"


@pytest.mark.asyncio
async def test_the_id_map_resolves_candidates_back_to_places(gather_scene):
    result = await run_gather(await gather_scene())
    assert set(result.candidate_places) == {c.id for c in result.context.candidates}
    assert set(result.window_intervals) == {w.id for w in result.context.windows}


@pytest.mark.asyncio
async def test_preferences_are_projected_into_the_model_vocabulary(gather_scene):
    result = await run_gather(await gather_scene())
    assert "45-90 min" in result.context.preference_vocabulary()
    assert result.context.preferences.workout_kinds == ["swim"]


@pytest.mark.asyncio
async def test_the_context_is_not_an_empty_decision_space(gather_scene):
    result = await run_gather(await gather_scene())
    assert not result.context.is_empty_decision_space()


@pytest.mark.asyncio
async def test_the_context_is_serializable_as_a_snapshot(gather_scene):
    """`agent_runs.context_snapshot` is JSONB; it has to round-trip."""
    import json

    result = await run_gather(await gather_scene())
    dumped = json.dumps(result.context.model_dump(mode="json"), sort_keys=True)
    assert json.loads(dumped)["meta"]["run_kind"] == "pretrip_plan"

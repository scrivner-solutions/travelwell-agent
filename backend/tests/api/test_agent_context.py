"""Gather against a real database: a trip goes in, a TripContext comes out.

The milestone this belongs to has no model in it. Everything asserted here is a
projection or an arithmetic result, which is the point - nine of the ten stages
are supposed to be answerable without a provider.
"""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

TZ = ZoneInfo("America/Chicago")
DAY_ONE = date(2026, 9, 9)


def build_scene(user):
    """A two-day Chicago trip with three commitments and three cached places.

    The calendar rows carry no trip reference, because none exists: gather
    finds them by owner and date overlap, the way the timeline does.

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
            SourceStatus,
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
                user_id=user.user_id,
                kind=SourceKind.google_calendar,
                status=SourceStatus.connected,
                secret_ref="mem:placeholder",
            )
            session.add_all([trip, source])
            await session.flush()

            session.add_all([
                CalendarEvent(
                    user_id=user.user_id,
                    source_id=source.source_id,
                    external_id="ev-1",
                    title="Workshop day 1",
                    starts_at=at(DAY_ONE, 9),
                    ends_at=at(DAY_ONE, 17),
                    content_hash="h1",
                ),
                CalendarEvent(
                    user_id=user.user_id,
                    source_id=source.source_id,
                    external_id="ev-2",
                    title="Team dinner\x07",
                    starts_at=at(DAY_ONE, 19, 30),
                    ends_at=at(DAY_ONE, 21),
                    content_hash="h2",
                ),
                CalendarEvent(
                    user_id=user.user_id,
                    source_id=source.source_id,
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


async def run_gather(trip_id, *, provider=None, run_kind="pretrip_plan"):
    import app.db.engine as db
    from app.agent.context import gather

    async with db.SessionFactory() as session:
        return await gather(
            session,
            trip_id,
            run_kind=run_kind,
            prompt_version="pretrip-v1",
            now=datetime(2026, 9, 2, 14, tzinfo=TZ),
            provider=provider,
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


async def _add_event(user_id, external_id, title, starts_at, ends_at, **cols):
    """One calendar row for `user_id`, on their Google source (one per user)."""
    from sqlalchemy import select

    import app.db.engine as db
    from app.db.models import CalendarEvent, ConnectedSource, SourceKind, SourceStatus

    async with db.SessionFactory() as session:
        source_id = (
            await session.execute(
                select(ConnectedSource.source_id).where(
                    ConnectedSource.user_id == user_id,
                    ConnectedSource.kind == SourceKind.google_calendar,
                )
            )
        ).scalar_one_or_none()
        if source_id is None:
            source = ConnectedSource(
                user_id=user_id,
                kind=SourceKind.google_calendar,
                status=SourceStatus.connected,
                secret_ref=f"mem:{external_id}",
            )
            session.add(source)
            await session.flush()
            source_id = source.source_id
        session.add(
            CalendarEvent(
                user_id=user_id,
                source_id=source_id,
                external_id=external_id,
                title=title,
                starts_at=starts_at,
                ends_at=ends_at,
                content_hash=external_id,
                **cols,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_another_travelers_meeting_is_not_a_commitment(gather_scene, other_user):
    """Owner scope is load-bearing. A date overlap alone matches every calendar
    in the table, and a gather that reads other people's meetings would plan
    this traveler's day around them without anything visible going wrong."""
    trip_id = await gather_scene()
    day_two = DAY_ONE + timedelta(days=1)
    await _add_event(
        other_user.user_id,
        "theirs",
        "Their private thing",
        datetime.combine(day_two, time(12), TZ),
        datetime.combine(day_two, time(14), TZ),
        busy=True,
    )

    result = await run_gather(trip_id)
    assert "Their private thing" not in [c.title for c in result.context.commitments]
    assert len([w for w in result.context.windows if w.day == day_two]) == 1


@pytest.mark.asyncio
async def test_a_cancelled_event_neither_shows_nor_carves(gather_scene, user):
    """Sync keeps cancellations as tombstones. A tombstone with `busy` unset
    reads as blocking time under `is_busy`, so the status filter is what keeps
    a meeting the traveler already lost from costing them the window."""
    trip_id = await gather_scene()
    day_two = DAY_ONE + timedelta(days=1)
    await _add_event(
        user.user_id,
        "gone",
        "Cancelled sync",
        datetime.combine(day_two, time(12), TZ),
        datetime.combine(day_two, time(14), TZ),
        status="cancelled",
    )

    result = await run_gather(trip_id)
    assert "Cancelled sync" not in [c.title for c in result.context.commitments]
    assert len([w for w in result.context.windows if w.day == day_two]) == 1


@pytest.mark.asyncio
async def test_gather_and_the_timeline_read_the_same_events(
    gather_scene, authed_client, user
):
    """The two readers share one query. This is the accuser if either grows
    its own again: an event in the trip window that one shows and the other
    does not turns this red."""
    trip_id = await gather_scene()
    day_two = DAY_ONE + timedelta(days=1)
    # Straddles the trip's last midnight: in the window by overlap, and the
    # kind of edge a hand-rolled second query gets wrong.
    await _add_event(
        user.user_id,
        "late",
        "Late flight",
        datetime.combine(day_two, time(23), TZ),
        datetime.combine(day_two + timedelta(days=1), time(1), TZ),
    )

    result = await run_gather(trip_id)
    via_gather = sorted(result.commitment_events.values())

    r = await authed_client.get(f"/api/v1/trips/{trip_id}/timeline")
    assert r.status_code == 200
    via_timeline = sorted(
        uuid.UUID(e["calendar_event"]["id"])
        for e in r.json()["entries"]
        if e["entry_type"] == "calendar_event"
    )
    assert via_gather == via_timeline and len(via_gather) == 4


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


# ---------------------------------------------------------------------------
# Coverage: whether anybody actually looked around the traveler
# ---------------------------------------------------------------------------


class CountingProvider:
    """Counts calls, because "did this bill?" is the property under test."""

    name = "counting"

    def __init__(self, result=()):
        self.result = list(result)
        self.calls = 0

    async def search_nearby(self, query):
        self.calls += 1
        return list(self.result)

    async def geocode(self, query):
        return None


def a_provider_place(ref: str, name: str, lat: float, lng: float):
    from app.db.models import PlaceKind
    from app.services.places.ports import ProviderPlace

    return ProviderPlace(
        provider_ref=ref, kind=PlaceKind.food, name=name, lat=lat, lng=lng
    )


@pytest.fixture
def fetching_allowed(monkeypatch):
    """tests/conftest.py pins fetching off; these tests drive a counting fake."""
    monkeypatch.setenv("PLACES_FETCH_ENABLED", "1")


@pytest.mark.asyncio
async def test_gather_looks_at_the_area_and_reports_that_it_looked(
    gather_scene, fetching_allowed
):
    provider = CountingProvider()
    result = await run_gather(await gather_scene(), provider=provider)
    assert provider.calls == 1, "one call covering the radius, not one per kind"
    assert result.coverage.authoritative is True
    assert result.coverage.reasons() == []


@pytest.mark.asyncio
async def test_what_the_provider_returns_reaches_the_candidates(
    gather_scene, fetching_allowed
):
    """The fill has to feed the read, not just the bookkeeping table."""
    provider = CountingProvider(
        [a_provider_place("new-1", "Fetched Cafe", 41.8925, -87.6250)]
    )
    result = await run_gather(await gather_scene(), provider=provider)
    assert "Fetched Cafe" in [c.name for c in result.context.candidates]


@pytest.mark.asyncio
async def test_gather_does_not_bill_when_the_deployment_says_no(gather_scene):
    """The suite-wide default. `PLACES_FETCH_ENABLED` is off and outranks us."""
    provider = CountingProvider()
    result = await run_gather(await gather_scene(), provider=provider)
    assert provider.calls == 0
    assert result.coverage.authoritative is False
    assert result.coverage.reasons() == ["places_coverage:policy_declined"]


@pytest.mark.asyncio
async def test_the_daily_checkin_reads_what_the_planner_already_paid_for(
    gather_scene, fetching_allowed
):
    """Fetching is enabled and it still does not fetch: the run kind decides."""
    provider = CountingProvider()
    result = await run_gather(
        await gather_scene(), provider=provider, run_kind="daily_checkin"
    )
    assert provider.calls == 0
    assert result.coverage.authoritative is False


async def unanchor(trip_id):
    """Strip every coordinate off the trip, as `create_trip` leaves it."""
    import sqlalchemy as sa

    import app.db.engine as db
    from app.db.models import Trip

    async with db.SessionFactory() as session:
        await session.execute(
            sa.update(Trip)
            .where(Trip.trip_id == trip_id)
            .values(
                hotel_lat=None,
                hotel_lng=None,
                destination_lat=None,
                destination_lng=None,
            )
        )
        await session.commit()
    return trip_id


@pytest.mark.asyncio
async def test_a_trip_with_nowhere_to_be_near_never_claims_a_search(
    gather_scene, fetching_allowed
):
    trip_id = await unanchor(await gather_scene())

    provider = CountingProvider()
    result = await run_gather(trip_id, provider=provider)
    assert provider.calls == 0, "no origin means no query to make"
    assert result.coverage.authoritative is False
    assert result.coverage.reasons() == ["places_coverage:not_attempted"]


@pytest.mark.asyncio
async def test_the_reason_travels_into_the_context_snapshot(gather_scene):
    """`degraded` is what the replay and the model see; it has to carry this."""
    result = await run_gather(await gather_scene(), provider=CountingProvider())
    assert "places_coverage:policy_declined" in result.context.meta.degraded



@pytest.mark.asyncio
async def test_a_trip_with_no_coordinates_offers_no_candidates(gather_scene):
    """An unanchored trip must reach the model with nothing, not with everything.

    The coverage test above proves gather is *honest* about not having searched.
    It says nothing about what came back from the cache anyway, and that is the
    whole bug: with no origin the distance filter is skipped rather than failing
    closed, so every `Place` row in the database becomes a candidate for a trip
    that could be on another continent. `Evanston pool` is the witness - the
    anchored run is already proven to exclude it as too far.
    """
    result = await run_gather(await unanchor(await gather_scene()))

    names = [c.name for c in result.context.candidates]
    assert "Evanston pool" not in names, (
        "a place the anchored run rejects as too far cannot become eligible by "
        "the trip losing its coordinates"
    )
    assert names == [], f"no origin means no candidates, got {names}"
    assert result.context.is_empty_decision_space(), (
        "this is the property that matters: an empty decision space is what "
        "stops the run before it spends a model call planning the wrong city"
    )

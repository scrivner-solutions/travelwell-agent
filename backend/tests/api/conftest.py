"""Fixtures for the /api/v1 integration suite.

Runs against a real Postgres. Once per session a dedicated *_test database is
dropped, recreated, and migrated to head, so every run also proves that
`alembic upgrade head` works on an empty database. Each test starts from
truncated tables and builds its own scene through the ORM models (calendar
tables stay textual SQL, mirroring ADR-001 point 3).

DATABASE_URL is forced to the test database before any app import, so the
suite can never touch the dev database. Point TEST_DATABASE_URL elsewhere to
override; the database name must end in `_test` because it gets dropped.
"""

import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parents[2]

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://travelwell:travelwell@localhost:5432/travelwell_test",
)
if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise RuntimeError(
        "TEST_DATABASE_URL must name a *_test database: the suite drops and "
        f"recreates it. Got {TEST_DATABASE_URL!r}."
    )

# Must happen before any `app.*` import (the engine reads it at import time);
# app imports therefore live inside fixtures, never at module top.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("DISABLE_TELEMETRY", "true")

# Everything the initial migration creates, modeled or not. Truncated together
# so FK order never matters; CASCADE covers any table a future migration adds.
ALL_TABLES = (
    "users, user_preferences, connected_sources, trips, trip_evidence, "
    "calendar_events, places, wellness_windows, plans, plan_items, "
    "plan_item_options, pending_actions, reservations, agent_runs, "
    "agent_events, notifications"
)


@pytest.fixture(scope="session", autouse=True)
def database():
    """Fresh test database at migration head; app engine rebound to NullPool.

    NullPool matters: pytest-asyncio gives every test its own event loop, and
    pooled asyncpg connections are bound to the loop they were created on.
    With NullPool each session gets a fresh connection, so nothing leaks
    across loops.
    """
    sync_url = make_url(TEST_DATABASE_URL.replace("+asyncpg", "+psycopg"))
    admin = sa.create_engine(
        sync_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as conn:
        conn.execute(
            sa.text(f'drop database if exists "{sync_url.database}" with (force)')
        )
        conn.execute(sa.text(f'create database "{sync_url.database}"'))
    admin.dispose()

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")

    import app.db.engine as db

    db.engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    db.SessionFactory = async_sessionmaker(db.engine, expire_on_commit=False)
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(database):
    import app.db.engine as db

    async with db.engine.begin() as conn:
        await conn.execute(sa.text(f"truncate {ALL_TABLES} cascade"))


@pytest_asyncio.fixture
async def db_session(clean_tables):
    """Direct database access for assertions the API does not expose."""
    import app.db.engine as db

    async with db.SessionFactory() as session:
        yield session


@pytest.fixture(scope="session")
def app_instance(database):
    from app.fast_api_app import app

    return app


@pytest_asyncio.fixture
async def client(app_instance):
    transport = httpx.ASGITransport(app=app_instance)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c


async def _create_user(email: str) -> object:
    import app.db.engine as db
    from app.db.models import AuthProvider, User

    async with db.SessionFactory() as session:
        user = User(
            email=email,
            display_name="Test Traveler",
            auth_provider=AuthProvider.email,
            home_timezone="America/Los_Angeles",
        )
        session.add(user)
        await session.commit()
        return user


@pytest_asyncio.fixture
async def user(clean_tables):
    return await _create_user("demo@travelwell.dev")


@pytest_asyncio.fixture
async def other_user(clean_tables):
    return await _create_user("other@travelwell.dev")


def _sign_in(client: httpx.AsyncClient, user) -> None:
    from app.api.sessions import SESSION_COOKIE, issue_session

    client.cookies.set(SESSION_COOKIE, issue_session(str(user.user_id)))


@pytest.fixture
def sign_in():
    return _sign_in


@pytest_asyncio.fixture
async def authed_client(client, user):
    _sign_in(client, user)
    return client


@pytest.fixture
def make_trip(clean_tables):
    """Factory for a bare trip in any lifecycle state, starting in the future."""

    async def _make(
        user,
        *,
        state=None,
        city="Denver",
        region="CO",
        tz="America/Denver",
        start_in=30,
        nights=3,
        evidence=(),
    ):
        import app.db.engine as db
        from app.db.models import Trip, TripEvidence, TripOrigin, TripState

        # Trip-local today, not the system date: /today computes day counts
        # in the trip's zone, and the two dates differ around midnight.
        base = datetime.now(ZoneInfo(tz)).date()
        async with db.SessionFactory() as session:
            trip = Trip(
                user_id=user.user_id,
                destination_city=city,
                destination_region=region,
                timezone=tz,
                start_date=base + timedelta(days=start_in),
                end_date=base + timedelta(days=start_in + nights),
                state=state or TripState.detected,
                origin=TripOrigin.calendar_detection,
                detection_confidence=0.9,
                evidence=[
                    TripEvidence(
                        kind=kind, source_label=label, summary=summary, detail=detail
                    )
                    for kind, label, summary, detail in evidence
                ],
            )
            session.add(trip)
            await session.commit()
            return trip

    return _make


@pytest_asyncio.fixture
async def scene(user):
    """A mid-trip scene mirroring the seed's Chicago day-2-of-4, with traps.

    Anchored to *trip-local* today (America/Chicago), not the system date, so
    the /today filters line up no matter when the suite runs.

    Traps baked in for the filters under test:
    - an `expired` window earlier today (must lose to the open one),
    - an open window tomorrow (must lose to today's),
    - a `skipped` item today (hidden everywhere),
    - an `awaiting_user` item (visible, and drives needs_you_count = 1).
    """
    import app.db.engine as db
    from app.db.models import (
        ItemKind,
        ItemStatus,
        OptionState,
        Plan,
        PlanItem,
        PlanItemOption,
        PlanStatus,
        Trip,
        TripOrigin,
        TripState,
        WellnessWindow,
        WindowStatus,
    )

    tz = ZoneInfo("America/Chicago")
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)

    def at(day: date, hour: int, minute: int = 0) -> datetime:
        return datetime.combine(day, time(hour, minute), tz)

    async with db.SessionFactory() as session:
        trip = Trip(
            user_id=user.user_id,
            destination_city="Chicago",
            destination_region="IL",
            timezone="America/Chicago",
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=2),
            state=TripState.active,
            origin=TripOrigin.calendar_detection,
        )
        session.add(trip)
        await session.flush()

        w_open = WellnessWindow(
            trip_id=trip.trip_id,
            local_date=today,
            starts_at=at(today, 17, 30),
            ends_at=at(today, 19, 0),
            label="90 minutes free",
            gap_explanation="Between your workshop and dinner, 5:30 to 7:00.",
            bounds=[
                {
                    "kind": "calendar_event",
                    "tag": "CAL",
                    "title": "Workshop, Room 4B",
                    "detail": "Ends 5:30 PM",
                    "source_label": "Calendar",
                },
                {
                    "kind": "plan_item",
                    "tag": "PLAN",
                    "title": "Dinner you kept",
                    "detail": "Starts 7:30 PM",
                    "source_label": "This plan",
                },
            ],
            status=WindowStatus.open,
        )
        w_expired = WellnessWindow(
            trip_id=trip.trip_id,
            local_date=today,
            starts_at=at(today, 7, 0),
            ends_at=at(today, 8, 0),
            label="Morning hour that passed",
            bounds=[],
            status=WindowStatus.expired,
        )
        w_tomorrow = WellnessWindow(
            trip_id=trip.trip_id,
            local_date=tomorrow,
            starts_at=at(tomorrow, 6, 45),
            ends_at=at(tomorrow, 8, 0),
            label="75 minutes before the keynote",
            bounds=[],
            status=WindowStatus.open,
        )
        session.add_all([w_open, w_expired, w_tomorrow])
        await session.flush()

        plan = Plan(
            trip_id=trip.trip_id,
            version=1,
            status=PlanStatus.proposed,
            headline="Room for 2 workouts and a dinner",
        )
        session.add(plan)
        await session.flush()

        def item(window, kind, status, start, end, options):
            it = PlanItem(
                plan_id=plan.plan_id,
                trip_id=trip.trip_id,
                window_id=window.window_id if window else None,
                kind=kind,
                status=status,
                scheduled_start=start,
                scheduled_end=end,
            )
            it.options = [
                PlanItemOption(state=state, rank=rank, **fields)
                for rank, (state, fields) in enumerate(options)
            ]
            return it

        sel, alt, rej = (
            OptionState.selected,
            OptionState.alternative,
            OptionState.rejected,
        )
        workout = item(
            w_open, ItemKind.activity, ItemStatus.suggested,
            at(today, 17, 30), at(today, 18, 45),
            [
                (sel, {
                    "display_name": "YMCA",
                    "display_summary": "Pool + treadmill · 75 min",
                    "reason": "Fits your 90-minute opening",
                    "distance_minutes": 7, "duration_minutes": 75,
                    "matched_preferences": ["Swim", "45-90 min"],
                }),
                (alt, {"display_name": "Hotel fitness room", "distance_minutes": 0}),
                (rej, {
                    "display_name": "Chicago Athletic Club",
                    "rejection_reason": "11 minutes each way left you tight",
                }),
            ],
        )
        dinner = item(
            None, ItemKind.meal, ItemStatus.awaiting_user,
            at(today, 19, 30), at(today, 21, 0),
            [
                (sel, {
                    "display_name": "Beatrix",
                    "display_summary": "Healthy American · $$",
                    "reason": "Matches your vegetarian preference",
                    "distance_minutes": 5,
                    "matched_preferences": ["Vegetarian"],
                }),
                (rej, {
                    "display_name": "Aba",
                    "rejection_reason": "$$$, above the budget you set",
                }),
            ],
        )
        run = item(
            None, ItemKind.activity, ItemStatus.suggested,
            at(tomorrow, 6, 45), at(tomorrow, 7, 30),
            [(sel, {"display_name": "Lakefront Trail", "distance_minutes": 12})],
        )
        hidden = item(
            None, ItemKind.activity, ItemStatus.skipped,
            at(today, 12, 15), at(today, 12, 45),
            [(alt, {"display_name": "Walk the Riverwalk"})],
        )
        session.add_all([workout, dinner, run, hidden])

        source_id = (
            await session.execute(
                sa.text(
                    """
                    insert into connected_sources (user_id, kind, status)
                    values (:uid, 'google_calendar', 'connected')
                    returning source_id
                    """
                ),
                {"uid": user.user_id},
            )
        ).scalar_one()
        cal_events = [
            (at(today, 8, 0), at(today, 12, 0), "Conference", "McCormick Place"),
            (at(today, 14, 0), at(today, 17, 30), "Workshop", "Room 4B"),
            (at(tomorrow, 9, 0), at(tomorrow, 10, 30), "Keynote", "Main hall"),
        ]
        for i, (starts, ends, title, location) in enumerate(cal_events):
            await session.execute(
                sa.text(
                    """
                    insert into calendar_events
                      (user_id, source_id, trip_id, external_id, title, location,
                       starts_at, ends_at, content_hash)
                    values
                      (:uid, :sid, :tid, :ext, :title, :loc, :starts, :ends, :hash)
                    """
                ),
                {
                    "uid": user.user_id,
                    "sid": source_id,
                    "tid": trip.trip_id,
                    "ext": f"test_evt_{i}",
                    "title": title,
                    "loc": location,
                    "starts": starts,
                    "ends": ends,
                    "hash": f"test_{i}",
                },
            )

        await session.commit()

    return SimpleNamespace(
        trip_id=str(trip.trip_id),
        timezone="America/Chicago",
        today=today,
        tomorrow=tomorrow,
        # 3 calendar events + 3 visible items (workout, dinner, run); the
        # skipped item and the expired/tomorrow windows never surface.
        visible_items_today=["YMCA", "Beatrix"],
        visible_item_tomorrow="Lakefront Trail",
        total_timeline_entries=6,
    )

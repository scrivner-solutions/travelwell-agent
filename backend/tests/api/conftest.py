"""Fixtures for the /api/v1 integration suite.

Runs against a real Postgres. Once per session a dedicated *_test database is
dropped, recreated, and migrated to head, so every run also proves that
`alembic upgrade head` works on an empty database. Each test starts from
truncated tables and builds its own scene through the ORM models (calendar
tables stay textual SQL, mirroring ADR-001 point 3).

DATABASE_URL is forced to the test database before any app import, so the
suite can never touch the dev database. Point TEST_DATABASE_URL elsewhere to
override (backend/.env is read, so a worktree can keep its own); the database
name must end in `_test` because it gets dropped.
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
from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Parallel worktrees would otherwise all drop and recreate one shared
# `travelwell_test`, failing each other's runs. Reading .env lets each keep
# its own; a real environment variable still wins.
load_dotenv()

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://travelwell:travelwell@localhost:5432/travelwell_test",
)
if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise RuntimeError(
        "TEST_DATABASE_URL must name a *_test database: the suite drops and "
        f"recreates it. Got {TEST_DATABASE_URL!r}."
    )

# Must happen before any `app.*` import (the engine reads it at import time);
# app imports therefore live inside fixtures, never at module top.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# Sessions fail hard without a secret outside dev/test (sessions.py).
os.environ.setdefault("APP_ENV", "test")
# Pinned rather than defaulted: migrations/env.py calls load_dotenv(), so a
# worktree's backend/.env would otherwise decide what the redirect tests assert.
os.environ["PUBLIC_BASE_URL"] = "http://localhost:5173"

def all_tables() -> str:
    """Every modeled table, derived rather than listed.

    This was a hand-written list, under a comment claiming CASCADE would reach
    any table a future migration added. The real rule is narrower, and both
    convenient summaries of it are wrong: an unlisted table is truncated if and
    only if it has a foreign key INTO a listed table. `stored_secrets` was
    missing from the list and truncated anyway, through `user_id -> users`.
    `area_fills` has no foreign key in either direction, so nothing reached it,
    and tests read each other's rows.

    The failure is silent. It surfaces as an assertion inside whichever test
    happens to run second, which reads as a bug in that test rather than here.

    Deriving from `Base.metadata` is not a new mechanism. The repo already
    treats the ORM models as the schema source and generates `docs/schema.sql`
    from this same metadata, so the hand-written list was a second copy of a
    list the repo already maintains. That is the load-bearing assumption: a
    table created by a migration but never modeled would still be missed, and
    `alembic check` is what keeps that from existing.
    """
    # Imported here, not at module scope: this file forces DATABASE_URL before
    # anything under `app` is allowed to load.
    from app.db.models import Base

    return ", ".join(sorted(t.name for t in Base.metadata.sorted_tables))


@pytest.fixture(scope="session", autouse=True)
def database():
    """Fresh test database at migration head; app engine rebound to NullPool.

    NullPool matters: pytest-asyncio gives every test its own event loop, and
    pooled connections are bound to the loop they were created on. With
    NullPool each session gets a fresh connection, so nothing leaks across
    loops.
    """
    import app.db.engine as db

    sync_url = db.database_url()
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

    db.engine = create_async_engine(db.database_url(), poolclass=NullPool)
    db.SessionFactory = async_sessionmaker(db.engine, expire_on_commit=False)
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(database):
    import app.db.engine as db

    async with db.engine.begin() as conn:
        await conn.execute(sa.text(f"truncate {all_tables()} cascade"))


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


@pytest.fixture
def sent_codes(monkeypatch):
    """Sign-in emails captured at the mailer seam, as (address, code) tuples."""
    from app.services import mailer

    sent: list[tuple[str, str]] = []

    async def capture(email: str, code: str) -> None:
        sent.append((email, code))

    monkeypatch.setattr(mailer, "send_sign_in_code", capture)
    return sent


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
        activation_in=None,
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
                activation_at=(
                    None
                    if activation_in is None
                    else datetime.now(ZoneInfo(tz)) + timedelta(days=activation_in)
                ),
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

        def item(window, kind, status, start, end, options, needs_res=False):
            it = PlanItem(
                plan_id=plan.plan_id,
                trip_id=trip.trip_id,
                window_id=window.window_id if window else None,
                kind=kind,
                status=status,
                scheduled_start=start,
                scheduled_end=end,
                needs_reservation=needs_res,
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
        # `awaiting_user`, not `suggested`: this plan is `proposed`, and an item
        # is only `suggested` while its plan is a draft, which no read returns.
        workout = item(
            w_open, ItemKind.activity, ItemStatus.awaiting_user,
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
            needs_res=True,
        )
        run = item(
            None, ItemKind.activity, ItemStatus.awaiting_user,
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
                    insert into connected_sources (user_id, kind, status, secret_ref)
                    values (:uid, 'google_calendar', 'connected', 'mem:placeholder')
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
                      (user_id, source_id, external_id, title, location,
                       starts_at, ends_at, content_hash)
                    values
                      (:uid, :sid, :ext, :title, :loc, :starts, :ends, :hash)
                    """
                ),
                {
                    "uid": user.user_id,
                    "sid": source_id,
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

"""Seed the local database with a demo user and trips.

Idempotent: re-running wipes and recreates the demo user's trips. Dates are
relative to today so the seed never goes stale. Sign in from the frontend with
the demo email; the one-time code appears in the backend server log.

Usage (from backend/, with the compose Postgres up and migrations applied):
    uv run python scripts/seed.py
"""

import asyncio
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlalchemy import delete, select, text

DEMO_EMAIL = "demo@travelwell.dev"
CHICAGO_TZ = ZoneInfo("America/Chicago")


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), CHICAGO_TZ)


async def main() -> None:
    load_dotenv()

    from app.db.engine import SessionFactory, engine
    from app.db.models import (
        AuthProvider,
        ItemKind,
        ItemStatus,
        OptionState,
        Plan,
        PlanItem,
        PlanItemOption,
        PlanStatus,
        Trip,
        TripEvidence,
        TripOrigin,
        TripState,
        User,
        WellnessWindow,
        WindowStatus,
    )

    today = date.today()

    async with SessionFactory() as session:
        user = (
            await session.execute(select(User).where(User.email == DEMO_EMAIL))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                email=DEMO_EMAIL,
                display_name="Demo Traveler",
                auth_provider=AuthProvider.email,
                home_timezone="America/Los_Angeles",
            )
            session.add(user)
            await session.flush()

        await session.execute(delete(Trip).where(Trip.user_id == user.user_id))

        chicago = Trip(
            user_id=user.user_id,
            destination_city="Chicago",
            destination_region="IL",
            destination_lat=41.8871,
            destination_lng=-87.6270,
            timezone="America/Chicago",
            # Mid-trip (day 2 of 4): the Today screen's richest state, matching
            # the design prototype's default scene.
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=2),
            label="Conference trip",
            hotel_name="The Gwen",
            hotel_address="521 N Rush St, Chicago, IL 60611",
            hotel_lat=41.8924,
            hotel_lng=-87.6252,
            state=TripState.active,
            origin=TripOrigin.calendar_detection,
            detection_confidence=0.93,
            evidence=[
                TripEvidence(
                    kind="flight_event",
                    source_label="Calendar",
                    summary="UA 1142 · SFO to ORD",
                    detail="Lands 9:40 AM · confirmed",
                    source_ref="cal_evt_ua1142",
                ),
                TripEvidence(
                    kind="hotel_email",
                    source_label="Email",
                    summary="The Gwen",
                    detail="521 N Rush St · 3 nights",
                    source_ref="msg_gwen_conf",
                ),
                TripEvidence(
                    kind="conference_event",
                    source_label="Calendar",
                    summary="TechConf Chicago",
                    detail="McCormick Place · all-day blocks",
                    source_ref="cal_evt_techconf",
                ),
            ],
        )

        newyork = Trip(
            user_id=user.user_id,
            destination_city="New York",
            destination_region="NY",
            timezone="America/New_York",
            start_date=today + timedelta(days=21),
            end_date=today + timedelta(days=24),
            label="Client visit",
            state=TripState.confirmed,
            origin=TripOrigin.manual,
        )

        # Detected but unconfirmed: exercises the detection -> confirm flow
        # (Phase 1 exit criterion) and the /confirm 409 path.
        austin = Trip(
            user_id=user.user_id,
            destination_city="Austin",
            destination_region="TX",
            timezone="America/Chicago",
            start_date=today + timedelta(days=45),
            end_date=today + timedelta(days=48),
            label="Client visit",
            state=TripState.detected,
            origin=TripOrigin.calendar_detection,
            detection_confidence=0.71,
            evidence=[
                TripEvidence(
                    kind="flight_event",
                    source_label="Calendar",
                    summary="WN 288 · SFO to AUS",
                    detail="Round trip · confirmed",
                    source_ref="cal_evt_wn288",
                ),
                TripEvidence(
                    kind="calendar_block",
                    source_label="Calendar",
                    summary="Client onsite",
                    detail="3 day block",
                    source_ref="cal_evt_onsite",
                ),
            ],
        )

        session.add_all([chicago, newyork, austin])
        await session.flush()

        # --- Chicago plan layer (windows -> plan v1 -> items -> options) ---
        # Scene from the design prototype: day 2 of 4, a 90-minute evening
        # window and a dinner tonight, a morning run tomorrow.
        d2, d3 = today, today + timedelta(days=1)

        w_evening = WellnessWindow(
            trip_id=chicago.trip_id,
            local_date=d2,
            starts_at=_at(d2, 17, 30),
            ends_at=_at(d2, 19, 0),
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
        w_morning = WellnessWindow(
            trip_id=chicago.trip_id,
            local_date=d3,
            starts_at=_at(d3, 6, 45),
            ends_at=_at(d3, 8, 0),
            label="75 minutes before the keynote",
            gap_explanation="Your first commitment is the 9:00 keynote.",
            bounds=[
                {
                    "kind": "calendar_event",
                    "tag": "CAL",
                    "title": "Conference keynote",
                    "detail": "Starts 9:00 AM",
                    "source_label": "Calendar",
                },
                {
                    "kind": "itinerary",
                    "tag": "HTL",
                    "title": "The Gwen",
                    "detail": "Trail is 12 minutes away",
                    "source_label": "Email",
                },
            ],
            status=WindowStatus.open,
        )
        session.add_all([w_evening, w_morning])
        await session.flush()

        plan = Plan(
            trip_id=chicago.trip_id,
            version=1,
            status=PlanStatus.proposed,
            headline="Room for 3 workouts and a dinner",
            provenance_summary=(
                "Prepared a week out · read 11 calendar events · found 3 open windows"
            ),
        )
        session.add(plan)
        await session.flush()

        def item(window, kind, start, end, needs_res, options):
            it = PlanItem(
                plan_id=plan.plan_id,
                trip_id=chicago.trip_id,
                window_id=window.window_id if window else None,
                kind=kind,
                status=ItemStatus.suggested,
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
        items = [
            item(
                w_evening, ItemKind.activity, _at(d2, 17, 30), _at(d2, 18, 45), False,
                [
                    (sel, dict(
                        display_name="YMCA",
                        display_summary="Pool + treadmill · 75 min",
                        reason="Fits your 90-minute opening",
                        distance_minutes=7, duration_minutes=75,
                        matched_preferences=["Swim", "45-90 min"],
                    )),
                    (alt, dict(
                        display_name="Hotel fitness room",
                        display_summary="Treadmill + weights · 40 min",
                        reason="No travel time at all",
                        distance_minutes=0, duration_minutes=40,
                    )),
                    (rej, dict(
                        display_name="Chicago Athletic Club",
                        display_summary="Lap pool · 60 min",
                        rejection_reason=(
                            "11 minutes each way left you tight for a 7:30 table"
                        ),
                        distance_minutes=11, duration_minutes=60,
                    )),
                ],
            ),
            item(
                None, ItemKind.meal, _at(d2, 19, 30), _at(d2, 21, 0), True,
                [
                    (sel, dict(
                        display_name="Beatrix",
                        display_summary="Healthy American · $$",
                        reason="Matches your vegetarian preference",
                        distance_minutes=5,
                        matched_preferences=["Vegetarian", "$$ or less"],
                    )),
                    (rej, dict(
                        display_name="Aba",
                        display_summary="Mediterranean · $$$",
                        rejection_reason="$$$, above the budget you set",
                        distance_minutes=9,
                    )),
                    (rej, dict(
                        display_name="Hotel restaurant",
                        rejection_reason="No vegetarian main after 7 PM",
                        distance_minutes=0,
                    )),
                ],
            ),
            item(
                w_morning, ItemKind.activity, _at(d3, 6, 45), _at(d3, 7, 30), False,
                [
                    (sel, dict(
                        display_name="Lakefront Trail",
                        display_summary="40-minute run · flat loop",
                        reason="Back with time to shower",
                        distance_minutes=12, duration_minutes=40,
                        matched_preferences=["Running", "Mornings"],
                    )),
                    (alt, dict(
                        display_name="Riverwalk loop",
                        display_summary="30-minute run",
                        reason="Closer, if you wake up late",
                        distance_minutes=4, duration_minutes=30,
                    )),
                    (rej, dict(
                        display_name="Hotel fitness room",
                        rejection_reason="You were indoors the day before",
                        distance_minutes=0,
                    )),
                ],
            ),
        ]
        session.add_all(items)

        # --- Calendar events (unmodeled tables: textual SQL, ADR-001 pt 3) ---
        source_id = (
            await session.execute(
                text(
                    """
                    insert into connected_sources (user_id, kind, status)
                    values (:uid, 'google_calendar', 'connected')
                    on conflict (user_id, kind) do update set status = 'connected'
                    returning source_id
                    """
                ),
                {"uid": user.user_id},
            )
        ).scalar_one()
        cal_events = [
            (_at(d2, 8, 0), _at(d2, 12, 0), "Conference", "McCormick Place"),
            (_at(d2, 12, 0), _at(d2, 13, 30), "Lunch with the team", None),
            (_at(d2, 14, 0), _at(d2, 17, 30), "Workshop", "Room 4B"),
            (_at(d3, 9, 0), _at(d3, 10, 30), "Keynote", "Main hall"),
            (_at(d3, 19, 0), _at(d3, 21, 0), "Team dinner", "Booked by the client"),
        ]
        for i, (starts, ends, title, location) in enumerate(cal_events):
            await session.execute(
                text(
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
                    "tid": chicago.trip_id,
                    "ext": f"seed_evt_{i}",
                    "title": title,
                    "loc": location,
                    "starts": starts,
                    "ends": ends,
                    "hash": f"seed_{i}",
                },
            )

        await session.commit()

        print(f"Seeded user {DEMO_EMAIL} ({user.user_id})")
        print(f"  {chicago.destination_city}: {chicago.start_date} to {chicago.end_date} [{chicago.state}]")
        print(f"  {newyork.destination_city}: {newyork.start_date} to {newyork.end_date} [{newyork.state}]")
        print("Sign in with this email; the code is printed in the backend log.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

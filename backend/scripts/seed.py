"""Seed the local database with a demo user and trips.

Idempotent: re-running wipes and recreates the demo user's trips. Dates are
relative to today so the seed never goes stale. Sign in from the frontend with
the demo email; the one-time code appears in the backend server log.

Usage (from backend/, with the compose Postgres up and migrations applied):
    uv run python scripts/seed.py
"""

import asyncio
from datetime import date, timedelta

from dotenv import load_dotenv
from sqlalchemy import delete, select

DEMO_EMAIL = "demo@travelwell.dev"


async def main() -> None:
    load_dotenv()

    from app.db.engine import SessionFactory, engine
    from app.db.models import (
        AuthProvider,
        Trip,
        TripEvidence,
        TripOrigin,
        TripState,
        User,
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
            start_date=today + timedelta(days=2),
            end_date=today + timedelta(days=5),
            label="Conference trip",
            hotel_name="The Gwen",
            hotel_address="521 N Rush St, Chicago, IL 60611",
            hotel_lat=41.8924,
            hotel_lng=-87.6252,
            state=TripState.preparing,
            origin=TripOrigin.calendar_detection,
            detection_confidence=0.93,
            evidence=[
                TripEvidence(
                    kind="flight_event",
                    source_label="Calendar",
                    summary="Flight UA 1142 - SFO to ORD",
                    source_ref="cal_evt_ua1142",
                ),
                TripEvidence(
                    kind="hotel_email",
                    source_label="Email",
                    summary="Hotel confirmation - The Gwen, 3 nights",
                    source_ref="msg_gwen_conf",
                ),
                TripEvidence(
                    kind="conference_event",
                    source_label="Calendar",
                    summary="TechConf Chicago - all-day blocks",
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

        session.add_all([chicago, newyork])
        await session.commit()

        print(f"Seeded user {DEMO_EMAIL} ({user.user_id})")
        print(f"  {chicago.destination_city}: {chicago.start_date} to {chicago.end_date} [{chicago.state}]")
        print(f"  {newyork.destination_city}: {newyork.start_date} to {newyork.end_date} [{newyork.state}]")
        print("Sign in with this email; the code is printed in the backend log.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

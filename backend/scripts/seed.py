"""Seed the local database with the demo user and their trips.

Idempotent: re-running clears the demo user's data and rebuilds it, keeping the
user row so an open session cookie still works. The account's contents live in
app/services/demo_user/data.py, shared with POST /auth/demo.

Sign in from the frontend with the demo email; the one-time code appears in the
backend server log (or just use the Demo sign-in button).

Usage (from backend/, with the compose Postgres up and migrations applied):
    uv run python scripts/seed.py
"""

import asyncio

from dotenv import load_dotenv
from sqlalchemy import select

DEMO_EMAIL = "demo@travelwell.dev"


async def main() -> None:
    load_dotenv()

    from app.db.engine import SessionFactory, engine
    from app.db.models import Trip
    from app.services.demo_user import build_demo_user

    async with SessionFactory() as session:
        user = await build_demo_user(session, DEMO_EMAIL)
        await session.commit()

        # Read the roster back rather than reporting what we meant to write.
        trips = (
            await session.execute(
                select(Trip)
                .where(Trip.user_id == user.user_id)
                .order_by(Trip.start_date)
            )
        ).scalars()

        print(f"Seeded user {DEMO_EMAIL} ({user.user_id})")
        for trip in trips:
            print(
                f"  {trip.destination_city:<10} {trip.start_date} to {trip.end_date}"
                f"  [{trip.state.value}]"
            )
        print("Sign in with this email; the code is printed in the backend log.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

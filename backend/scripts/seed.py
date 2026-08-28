"""Seed the local database with a demo user and trips.

Idempotent: re-running wipes and recreates the demo user's trips. The scene
itself lives in app/services/demo_scene.py, shared with POST /auth/demo.
Sign in from the frontend with the demo email; the one-time code appears in
the backend server log (or just use the Demo sign-in button).

Usage (from backend/, with the compose Postgres up and migrations applied):
    uv run python scripts/seed.py
"""

import asyncio

from dotenv import load_dotenv
from sqlalchemy import delete, select

DEMO_EMAIL = "demo@travelwell.dev"


async def main() -> None:
    load_dotenv()

    from app.db.engine import SessionFactory, engine
    from app.db.models import AuthProvider, ConnectedSource, Trip, User, UserPreferences
    from app.services.demo_scene import build_demo_scene

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
        await session.execute(
            delete(UserPreferences).where(UserPreferences.user_id == user.user_id)
        )
        # Cascades the user's calendar_events too; they are recreated below.
        await session.execute(
            delete(ConnectedSource).where(ConnectedSource.user_id == user.user_id)
        )

        chicago, newyork, _austin = await build_demo_scene(session, user)
        await session.commit()

        print(f"Seeded user {DEMO_EMAIL} ({user.user_id})")
        print(f"  {chicago.destination_city}: {chicago.start_date} to {chicago.end_date} [{chicago.state}]")
        print(f"  {newyork.destination_city}: {newyork.start_date} to {newyork.end_date} [{newyork.state}]")
        print("Sign in with this email; the code is printed in the backend log.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

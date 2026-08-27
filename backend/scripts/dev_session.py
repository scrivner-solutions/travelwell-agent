"""Print a signed twl_session cookie value for a dev user (default: demo).

Dev/e2e tooling: Playwright signs in by cookie because the email-code flow
only surfaces its code in the server log. Uses the same signer as the app,
so it honors SESSION_SECRET when set and the insecure dev default otherwise.

Usage (from backend/):
    uv run python scripts/dev_session.py [email]
"""

import asyncio
import sys

from sqlalchemy import text


async def main() -> None:
    from app.api.sessions import issue_session
    from app.db.engine import engine

    email = sys.argv[1] if len(sys.argv) > 1 else "demo@travelwell.dev"
    async with engine.connect() as conn:
        user_id = (
            await conn.execute(
                text("select user_id from users where email = :email"),
                {"email": email},
            )
        ).scalar_one()
    await engine.dispose()
    print(issue_session(str(user_id)))


if __name__ == "__main__":
    asyncio.run(main())

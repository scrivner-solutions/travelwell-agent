"""Async engine and session factory (unit-of-work per request).

Endpoints get a session via the get_session dependency and commit explicitly;
nothing auto-commits. The engine connects lazily, so importing this module is
safe even when no database is running.

DATABASE_URL alone picks the target: dev container, Cloud SQL unix socket, or
a hosted Postgres over TCP. This module owns the driver and the per-target
connect args so no caller re-derives them.
"""

import os
from collections.abc import AsyncIterator

from sqlalchemy import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://travelwell:travelwell@localhost:5432/travelwell"
)

# psycopg3 runs both async and sync, so the app and Alembic share one driver.
DRIVER = "postgresql+psycopg"

# An empty host is the Cloud SQL socket form (host=/cloudsql/... in the query).
_LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1"})


def database_url() -> URL:
    """The configured target, forced onto the driver we support."""
    url = make_url(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
    return url.set(drivername=DRIVER)


def connect_args() -> dict[str, str]:
    """Require TLS off-box; a unix socket and localhost are already private."""
    if (database_url().host or "") in _LOCAL_HOSTS:
        return {}
    return {"sslmode": "require"}


engine = create_async_engine(
    database_url(), pool_pre_ping=True, connect_args=connect_args()
)

SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session

"""Async engine and session factory (unit-of-work per request).

Endpoints get a session via the get_session dependency and commit explicitly;
nothing auto-commits. The engine connects lazily, so importing this module is
safe even when no database is running.
"""

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://travelwell:travelwell@localhost:5432/travelwell"
)


def database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


engine = create_async_engine(database_url(), pool_pre_ping=True)

SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session

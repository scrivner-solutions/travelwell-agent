"""Profile endpoints: wellness preferences, autonomy toggles, connected sources.

Preferences are one row per user, created lazily on first read or write so
sign-up needs no extra step. The autonomy toggles are stored here; enforcement
lives with the action executor (later slice), which reads them before acting.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, SessionDep
from app.api.problems import Problem
from app.api.schemas import (
    PreferencesOut,
    PreferencesUpdateIn,
    SourcesOut,
    preferences_to_out,
    source_to_out,
)
from app.db.models import ConnectedSource, UserPreferences

router = APIRouter(tags=["profile"])


async def _get_or_create_preferences(
    session: AsyncSession, user_id: uuid.UUID
) -> UserPreferences:
    prefs = await session.get(UserPreferences, user_id)
    if prefs is None:
        prefs = UserPreferences(user_id=user_id)
        session.add(prefs)
        await session.flush()
        # Pull the server-side column defaults into the instance.
        await session.refresh(prefs)
    return prefs


@router.get("/me/preferences")
async def get_preferences(user: CurrentUser, session: SessionDep) -> PreferencesOut:
    prefs = await _get_or_create_preferences(session, user.user_id)
    out = preferences_to_out(prefs)
    await session.commit()
    return out


@router.patch("/me/preferences")
async def update_preferences(
    body: PreferencesUpdateIn, user: CurrentUser, session: SessionDep
) -> PreferencesOut:
    prefs = await _get_or_create_preferences(session, user.user_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(prefs, field, value)
    # Cross-field rule checked on the merged row, not the patch body: a patch
    # touching only one bound must still respect the stored other bound.
    if (
        prefs.session_min_minutes is not None
        and prefs.session_max_minutes is not None
        and prefs.session_min_minutes > prefs.session_max_minutes
    ):
        raise Problem(
            422,
            "Invalid session length range",
            "invalid_range",
            "session_min_minutes cannot exceed session_max_minutes",
        )
    prefs.updated_at = datetime.now(UTC)
    out = preferences_to_out(prefs)
    await session.commit()
    return out


@router.get("/me/sources")
async def list_connected_sources(
    user: CurrentUser, session: SessionDep
) -> SourcesOut:
    rows = (
        (
            await session.execute(
                select(ConnectedSource)
                .where(ConnectedSource.user_id == user.user_id)
                .order_by(ConnectedSource.created_at)
            )
        )
        .scalars()
        .all()
    )
    return SourcesOut(sources=[source_to_out(row) for row in rows])

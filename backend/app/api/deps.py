"""Shared FastAPI dependencies for the /api/v1 surface."""

import uuid
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problems import Problem
from app.api.sessions import SESSION_COOKIE, read_session
from app.db.engine import get_session
from app.db.models import User

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(request: Request, session: SessionDep) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if token is None:
        raise Problem(401, "Not signed in", "unauthenticated")
    user_id = read_session(token)
    if user_id is None:
        raise Problem(401, "Not signed in", "unauthenticated", "Session expired or invalid")
    user = await session.get(User, uuid.UUID(user_id))
    if user is None:
        raise Problem(401, "Not signed in", "unauthenticated", "Unknown session user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

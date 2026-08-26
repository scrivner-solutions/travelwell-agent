"""Auth endpoints: email-code sign-in, logout, and /me.

BFF pattern per the contract: the session lives in an httpOnly cookie the
frontend can never read; openapi-fetch just sends credentials.
OAuth start (/auth/oauth/{provider}/start) is a later slice.
"""

import logging
import os

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from app.api import sessions
from app.api.deps import CurrentUser, SessionDep
from app.api.problems import Problem
from app.api.schemas import EmailCodeRequest, EmailCodeVerify, UserOut
from app.db.models import AuthProvider, User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


def _cookie_secure() -> bool:
    return os.getenv("SESSION_COOKIE_SECURE", "").lower() in ("1", "true")


def _set_session_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        key=sessions.SESSION_COOKIE,
        value=sessions.issue_session(user_id),
        max_age=sessions.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        path="/",
    )


@router.post("/auth/email-code", status_code=status.HTTP_202_ACCEPTED)
async def request_email_code(body: EmailCodeRequest) -> Response:
    code = sessions.issue_code(body.email)
    # Dev placeholder: no email provider is wired yet, so the code goes to the
    # server log. WARNING so it surfaces without any logging config. The 202
    # is unconditional so addresses cannot be enumerated.
    logger.warning("Sign-in code for %s: %s (dev mode, read it from this log)", body.email, code)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/auth/email-code/verify")
async def verify_email_code(
    body: EmailCodeVerify, response: Response, session: SessionDep
) -> UserOut:
    if not sessions.verify_code(body.email, body.code):
        raise Problem(400, "Invalid or expired code", "code_invalid")

    user = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if user is None:
        user = User(email=body.email, auth_provider=AuthProvider.email)
        session.add(user)
        await session.commit()

    _set_session_cookie(response, str(user.user_id))
    return UserOut.from_model(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(key=sessions.SESSION_COOKIE, path="/")
    return response


@router.get("/me")
async def get_me(user: CurrentUser) -> UserOut:
    return UserOut.from_model(user)

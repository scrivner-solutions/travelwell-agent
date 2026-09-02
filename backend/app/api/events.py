"""The agent's inbound surface: one row in, nothing else.

AGENT_DESIGN.md section 5 is explicit that everything wanting agent behaviour
"inserts an `agent_events` row and stops", and this route does exactly that.
It deliberately does **not** classify: admission happens once, inside the
worker's claim transaction, so there is no second copy of the rules here that
could drift out of agreement with it. `RunRef.run_id` is therefore absent, which
the settled contract allows - it is populated only if admission ever moves into
the request path.

Voice is not a backend concept - the frontend turns speech into text and posts
this same body with `kind='user_voice'`.

Producer-owned kinds are refused. `calendar_changed` and the rest carry payload
conventions their producers write (the sync job's `{cal_event_id, change, old,
new}`), and a client that could post them could forge a conflict against a plan
it does not like.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Header, status
from pydantic import BaseModel, Field

from app.api.deps import ApiRoute, CurrentUser, SessionDep
from app.api.problems import Problem
from app.api.trips import owned_trip
from app.db.models import AgentEvent, EventDisposition, EventKind

router = APIRouter(route_class=ApiRoute, tags=["agent"])

# Kinds a client may legitimately originate. The rest belong to the scheduler,
# the calendar sync job, or the reservation provider.
CLIENT_EVENT_KINDS = frozenset(
    {
        EventKind.user_text,
        EventKind.user_voice,
        EventKind.ui_action,
        EventKind.scheduled_activation,
    }
)


class EventCreate(BaseModel):
    kind: EventKind
    trip_id: uuid.UUID | None = None
    # No default: the contract has payload required, and a default is exactly
    # what would make it optional in the schema the frontend types from.
    payload: dict = Field(
        description="Kind-specific payload (transcript text, UI intent name, etc.)."
    )


class RunRef(BaseModel):
    event_id: uuid.UUID
    run_id: uuid.UUID | None = Field(
        default=None,
        description="Present when the event started (or joined) an agent run.",
    )


@router.post(
    "/events",
    response_model=RunRef,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="submitEvent",
    summary="Submit a user event (voice, text, or UI intent) to the agent event spine",
)
async def submit_event(
    body: EventCreate,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: Annotated[uuid.UUID, Header(alias="Idempotency-Key")],
) -> RunRef:
    """202, not 201: the row exists, and whether it becomes a run is the
    worker's decision, not this request's.

    A repeated Idempotency-Key returns the event that already exists rather
    than a second one, which for `scheduled_activation` is the difference
    between a retry and a second paid run.
    """
    if body.kind not in CLIENT_EVENT_KINDS:
        raise Problem(
            422,
            "That event kind is not accepted here",
            "event_kind_not_client_originated",
            f"{body.kind} is written by its producer, not posted by a client.",
        )
    if body.trip_id is not None:
        await owned_trip(session, user, body.trip_id)

    existing = (
        await session.execute(
            sa.select(AgentEvent).where(
                AgentEvent.user_id == user.user_id,
                AgentEvent.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return RunRef(event_id=existing.event_id)

    event = AgentEvent(
        user_id=user.user_id,
        trip_id=body.trip_id,
        kind=body.kind,
        payload=body.payload,
        disposition=EventDisposition.pending,
        occurred_at=datetime.now(UTC),
        idempotency_key=idempotency_key,
    )
    session.add(event)
    await session.commit()
    return RunRef(event_id=event.event_id)

"""What the traveler says about their own plan, answered in one round trip.

This is the second inbound surface, and the difference from `/events` is worth
stating because "there is one inbound surface" was a deliberate rule. `/events`
is the *unattended* spine: a producer drops a row and stops, and the worker
decides later whether it becomes a run. Nothing about that shape can answer a
person who is looking at the screen waiting for a sentence back.

So the rule it keeps is the one that matters - every agent behaviour still has
an `agent_events` row as its trace root, written here before anything runs - and
the rule it does not keep is admission, because there is nothing to admit: the
trip is named in the URL by the person who owns it. `admit.classify` exists to
work out which trip an unattended event meant and whether that trip wants a run.
Neither question arises here, so there is no copy of its table to drift.

`Idempotency-Key` is required for the same reason `/events` requires it: a
retry whose response was lost must not pay for a second model call. The stored
run is replayed instead, which is why `agent_runs.result` carries the reply.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from app.agent.assistant import UTTERANCE_LIMIT, respond
from app.api.deps import ApiRoute, CurrentUser, SessionDep
from app.api.problems import Problem
from app.api.trips import owned_trip
from app.db.models import AgentEvent, AgentRun, EventDisposition, EventKind, RunStatus

router = APIRouter(route_class=ApiRoute, tags=["agent"])


class AssistantAsk(BaseModel):
    utterance: str = Field(
        min_length=1,
        max_length=UTTERANCE_LIMIT,
        description="What the traveler said, verbatim. Voice is transcribed client-side.",
    )


class AssistantChangeOut(BaseModel):
    item_id: uuid.UUID
    name: str
    status: str


class AssistantTurnOut(BaseModel):
    run_id: uuid.UUID
    reply: str = Field(description="One sentence for the traveler. Never empty.")
    applied: list[AssistantChangeOut] = Field(
        description="Plan items this turn actually moved, in the order they were applied."
    )


def _client_and_model():
    # Imported inside the handler for the reason worker._default_client gives:
    # constructing a genai client reads ambient credentials, and importing a
    # router module must not.
    from app.agent.gemini import GeminiClient, default_model

    model = default_model()
    return GeminiClient(model=model), model


async def _replay(session, event: AgentEvent) -> AssistantTurnOut | None:
    """The stored answer for an idempotency key we have already served."""
    run = (
        await session.execute(
            sa.select(AgentRun)
            .where(AgentRun.trigger_event_id == event.event_id)
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is None or run.status is not RunStatus.completed:
        # A failed or still-running turn is not an answer to replay. Falling
        # through re-runs it, which is the behaviour a retry is asking for.
        return None
    result = run.result or {}
    return AssistantTurnOut(
        run_id=run.run_id,
        reply=result.get("reply", ""),
        applied=[
            AssistantChangeOut(
                item_id=uuid.UUID(change["item_id"]),
                name=change.get("name", ""),
                status="skipped",
            )
            for change in result.get("applied", [])
        ],
    )


@router.post(
    "/trips/{trip_id}/assistant",
    operation_id="askAssistant",
    summary="Say something about this trip's plan and have the agent act on it",
)
async def ask_assistant(
    trip_id: uuid.UUID,
    body: AssistantAsk,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: Annotated[uuid.UUID, Header(alias="Idempotency-Key")],
) -> AssistantTurnOut:
    """One utterance, interpreted against this trip's plan, applied, answered.

    The 200 means the turn happened, not that anything changed: "nothing here
    matches that" is a successful turn with an empty `applied`. A caller that
    wants to know whether the plan moved reads `applied`, not the status code.
    """
    trip = await owned_trip(session, user, trip_id)

    existing = (
        await session.execute(
            sa.select(AgentEvent).where(
                AgentEvent.user_id == user.user_id,
                AgentEvent.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        replayed = await _replay(session, existing)
        if replayed is not None:
            return replayed
        event = existing
    else:
        event = AgentEvent(
            user_id=user.user_id,
            trip_id=trip.trip_id,
            kind=EventKind.user_text,
            payload={"text": body.utterance},
            # Accepted at the moment it is written, because this path runs it
            # in the same request. `pending` would be a lie the worker would
            # then try to claim.
            disposition=EventDisposition.accepted,
            occurred_at=datetime.now(UTC),
            idempotency_key=idempotency_key,
        )
        session.add(event)
        await session.commit()

    client, model = _client_and_model()
    try:
        outcome = await respond(
            session,
            trip_id=trip.trip_id,
            utterance=body.utterance,
            client=client,
            model=model,
            now=datetime.now(UTC),
            trigger_event_id=event.event_id,
        )
    except Exception as exc:
        # The run row already carries the code, the violations and the spend;
        # this is the traveler's half of the same fact. 502 rather than 500:
        # nothing about their request was wrong.
        raise Problem(
            502,
            "The agent could not answer that",
            "agent_run_failed",
            "The request reached the agent and it did not produce a usable "
            "answer. Nothing on the plan was changed.",
        ) from exc

    return AssistantTurnOut(
        run_id=outcome.run_id,
        reply=outcome.reply,
        applied=[
            AssistantChangeOut(item_id=c.item_id, name=c.name, status=c.status)
            for c in outcome.applied
        ],
    )

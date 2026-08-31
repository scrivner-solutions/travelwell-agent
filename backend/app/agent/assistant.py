"""One utterance in, one decision out: the layer that reads what a traveler said.

The fixed UI can express "skip this item" with a button. What it cannot express
is *why*, or which item, in the traveler's own words - "I'm tired today, skip
the gym" names an item by category, a day by relative word, and a reason that is
not a second request. That gap is this module.

Same ten-stage discipline as `runs.py`, four stages shorter because there is
nothing to schedule. Gather reads the cheap half of the context and never
fetches; Frame produces the same canonical bytes; Invoke goes through the one
provider seam; Verify is the narrow waist; and the *controller* applies, from a
validated object, exactly the mutations the schema can express and no others.

Two bounds live here rather than in the prompt, because a bound a prompt asks
for is a request and a bound the controller enforces is a guarantee:

- **Skip, never remove.** `removed` is a tombstone the planner is told not to
  re-offer, and there is no route back from it. An utterance is not enough
  evidence for an irreversible answer, so the strong form is unreachable from
  here even if the model asks for it.
- **This trip's items only.** Verify already rejects an id the model was not
  shown, and the controller checks `trip_id` again on the row it loaded. The
  two checks read the same fact from different places on purpose: verification
  reads the payload we sent, the controller reads the database.

It writes plan item rows and an `agent_runs` row. It reaches no provider and no
executor - `test_agent_layering` makes the second one structural.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import sqlalchemy as sa
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import clean_untrusted, gather
from app.agent.llm import LlmClient, LlmRequest
from app.agent.prompts import ASSISTANT_PROMPT_VERSION, ASSISTANT_V1
from app.agent.runs import RunFailed, Spend, decode, render_violations
from app.agent.schemas import (
    _STRICT,
    MAX_SCHEMA_VIOLATIONS,
    TripContext,
    Violation,
    ViolationCode,
    sanitize_prose,
)
from app.db.models import AgentRun, ItemStatus, Plan, RunKind, RunStatus, Trip

# Interpreting one sentence against a plan of a dozen items is not the planner's
# job. `low` is the cheapest thinking level the provider offers and this is the
# task it was meant for; the pretrip run stays on `high`.
ASSISTANT_EFFORT = "low"

# An upper bound on a list is `maxItems`, which is the one keyword Vertex will
# not compile, so it lives in Verify like `too_many_items` does. Three is
# already generous: one sentence asking for four things is a sentence that was
# misread, and applying it would quietly gut the plan.
MAX_ACTIONS = 3

UTTERANCE_LIMIT = 500
REPLY_LIMIT = 280
REASON_LIMIT = 120

# What the controller says when the model's own sentence does not survive the
# prose tier. Generated from what actually happened rather than stored, so it
# can never disagree with the rows.
NOTHING_CHANGED = "Nothing on this plan matches that."


# --------------------------------------------------------------------------
# The wire schema: everything the model is allowed to say
# --------------------------------------------------------------------------


class AssistantAction(BaseModel):
    """`kind` is a `Literal` rather than a `pattern`: Vertex binds `enum` and
    silently ignores `pattern`, so a one-member Literal is the only spelling
    that actually constrains the field. A second verb is a second member."""

    model_config = _STRICT

    kind: Literal["skip_item"]
    item_id: str = Field(max_length=64)
    reason: str = Field(default="", max_length=REASON_LIMIT)


class AssistantDecision(BaseModel):
    model_config = _STRICT

    reply: str = Field(default="", max_length=REPLY_LIMIT)
    # `min_length` would be wrong here - no actions is a real answer, and the
    # commonest one. The upper bound is `too_many_actions` in Verify.
    actions: list[AssistantAction] = Field(default_factory=list)


# --------------------------------------------------------------------------
# What the caller gets back
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemChange:
    """One row the controller actually moved, named as the traveler sees it."""

    item_id: uuid.UUID
    name: str
    status: str


@dataclass(frozen=True)
class Refusal:
    """An action the model asked for that the controller would not carry out.

    Kept and returned rather than swallowed. A model that keeps asking to skip
    confirmed items is a prompt problem, and it only shows up if the refusals
    are counted somewhere.
    """

    item_id: str
    code: str
    name: str = ""  # empty when the id matched no item we could name


@dataclass(frozen=True)
class AssistantOutcome:
    run_id: uuid.UUID
    reply: str
    applied: tuple[ItemChange, ...] = ()
    refused: tuple[Refusal, ...] = ()
    spend: Spend = field(default_factory=Spend)


# --------------------------------------------------------------------------
# Frame
# --------------------------------------------------------------------------


def frame_utterance(ctx: TripContext, utterance: str, *, model: str) -> LlmRequest:
    """Context and utterance into the exact bytes that go over the wire.

    The utterance travels in the payload and never in the system prompt. That
    is what keeps the cacheable prefix stable, and it is also the injection
    boundary: the frozen text tells the model the payload is the traveler's
    words rather than instructions, and the schema means the worst a crafted
    sentence can win is a skip of an item that traveler already owns.
    """
    return LlmRequest(
        model=model,
        system=ASSISTANT_V1,
        payload=json.dumps(
            {
                "context": ctx.model_dump(mode="json"),
                "utterance": clean_untrusted(utterance, UTTERANCE_LIMIT),
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        output_schema=AssistantDecision,
        effort=ASSISTANT_EFFORT,
    )


# --------------------------------------------------------------------------
# Verify
# --------------------------------------------------------------------------


def verify_decision(
    payload: dict, ctx: TripContext
) -> AssistantDecision | list[Violation]:
    """Payload in, a sanitized `AssistantDecision` or the violations that stopped it.

    Referential integrity only. Whether an item *can* be skipped is a question
    about database state the model was never shown, so answering it here would
    fail a run over something the model could not have got right; the controller
    refuses those instead.
    """
    try:
        decision = AssistantDecision.model_validate(payload)
    except ValidationError as exc:
        return [
            Violation(
                ViolationCode.schema_mismatch,
                ".".join(str(part) for part in error["loc"]) or "$",
                f"{error['msg']} (got {error.get('input')!r})",
            )
            for error in exc.errors()[:MAX_SCHEMA_VIOLATIONS]
        ]
    except Exception as exc:  # a non-dict payload, or anything not pydantic's
        return [Violation(ViolationCode.schema_mismatch, "$", str(exc).splitlines()[0])]

    violations: list[Violation] = []
    if len(decision.actions) > MAX_ACTIONS:
        violations.append(
            Violation(
                ViolationCode.too_many_actions,
                "actions",
                f"{len(decision.actions)} actions, at most {MAX_ACTIONS}",
            )
        )
    known = {item.item_id for item in (ctx.current_plan.items if ctx.current_plan else ())}
    for index, action in enumerate(decision.actions):
        if action.item_id not in known:
            violations.append(
                Violation(
                    ViolationCode.unknown_item,
                    f"actions.{index}.item_id",
                    f"{action.item_id!r} is not an item in the current plan",
                )
            )
    if violations:
        return violations

    decision.reply = sanitize_prose(decision.reply, REPLY_LIMIT)
    for action in decision.actions:
        action.reason = sanitize_prose(action.reason, REASON_LIMIT)
    return decision


async def invoke_verified(
    client: LlmClient,
    request: LlmRequest,
    ctx: TripContext,
    *,
    max_repairs: int = 1,
) -> tuple[AssistantDecision, Spend]:
    """One invoke, at most one repair, for structural violations only.

    The same shape as `runs.invoke_verified` and deliberately not shared with
    it: the two differ in their verify function and their result type, and a
    generic over both would be more machinery than the eight lines it saves.
    """
    turns: list[str] = []
    spend = Spend()
    for attempt in range(max_repairs + 1):
        response = await client.complete(request, turns=tuple(turns))
        spend = spend.plus(response)
        try:
            result = verify_decision(decode(response), ctx)
        except RunFailed as failed:
            failed.spend = spend
            raise
        if isinstance(result, AssistantDecision):
            return result, spend
        if attempt == max_repairs:
            failure = RunFailed("verify:invalid", violations=result)
            failure.spend = spend
            raise failure
        turns += [response.text, render_violations(result)]
    raise AssertionError("unreachable")  # pragma: no cover


# --------------------------------------------------------------------------
# The controller: the only thing here that writes
# --------------------------------------------------------------------------


def item_name(item) -> str:
    """What the traveler sees on the row, by the same rule the context used."""
    selected = next((o for o in item.options if o.state == "selected"), None)
    return selected.display_name if selected else ""


async def apply_decision(
    session: AsyncSession,
    decision: AssistantDecision,
    *,
    trip: Trip,
    plan: Plan,
    now: datetime,
) -> tuple[list[ItemChange], list[Refusal]]:
    """Carry out what the decision asked for, within the bounds this file owns.

    The status rules are imported from `app.api.plan` rather than restated. Which
    statuses are still open to a decision is one rule for the whole server, and a
    second copy would drift the first time a status is added - the same reason
    `context._current_plan_summary` borrows `current_plan` instead of rewriting
    the query.
    """
    from app.api.plan import _OPEN_TO_DECISION, _recompute_plan_status

    by_id = {str(item.item_id): item for item in plan.items}
    applied: list[ItemChange] = []
    refused: list[Refusal] = []
    seen: set[str] = set()

    for action in decision.actions:
        if action.item_id in seen:
            continue  # Asking twice is one skip; the second is not a refusal.
        seen.add(action.item_id)
        item = by_id.get(action.item_id)
        if item is None or item.trip_id != trip.trip_id:
            # Verify already rejected ids we never sent. This catches the other
            # case: an id we did send, on a plan that moved underneath us.
            refused.append(Refusal(action.item_id, "not_in_plan"))
            continue
        if item.status == ItemStatus.skipped:
            continue  # Postcondition first, as every gate in `api/plan.py` is.
        if item.status not in _OPEN_TO_DECISION:
            refused.append(
                Refusal(action.item_id, f"status:{item.status.value}", item_name(item))
            )
            continue
        item.status = ItemStatus.skipped
        item.updated_at = now
        applied.append(
            ItemChange(item.item_id, item_name(item), ItemStatus.skipped.value)
        )

    if applied:
        _recompute_plan_status(plan)
    return applied, refused


_HELD = {
    "confirmed": "is booked, so it stays on the plan",
    "working": "is being booked right now, so it stays on the plan",
    "removed": "is already off the plan",
    "not_in_plan": "is not on this plan",
}


def _refusal_sentence(refusal: Refusal) -> str:
    subject = refusal.name or "That item"
    tail = _HELD.get(refusal.code.removeprefix("status:"), "cannot be taken off")
    return f"{subject} {tail}."


def compose_reply(
    decision: AssistantDecision,
    applied: Sequence[ItemChange],
    refused: Sequence[Refusal] = (),
) -> str:
    """What actually happened, in words - never what the model hoped would.

    The model writes its sentence at decision time, before the controller has
    decided what it will carry out, so an optimistic reply survives a refusal
    and tells the traveler their booked session was cancelled when it was not.
    Measured live: "I am tired today, skip the gym" against a confirmed YMCA
    booking returned `applied: []`, `refused: [status:confirmed]`, and the
    model's "The YMCA session has been removed from today's plan."

    So the model's prose is only usable when the controller did exactly what
    the model asked. The moment anything is refused, the reply is composed from
    the outcome instead. A reply is never left empty.
    """
    if refused:
        lines = [_refusal_sentence(r) for r in refused]
        names = [c.name for c in applied if c.name]
        if names:
            lines.insert(0, f"Off the plan: {', '.join(names)}.")
        return " ".join(lines)
    if decision.reply:
        return decision.reply
    if not applied:
        return NOTHING_CHANGED
    names = [c.name for c in applied if c.name] or ["That"]
    return f"Off the plan: {', '.join(names)}."


# --------------------------------------------------------------------------
# Admit to Emit
# --------------------------------------------------------------------------


async def respond(
    session: AsyncSession,
    *,
    trip_id: uuid.UUID,
    utterance: str,
    client: LlmClient,
    model: str,
    now: datetime,
    trigger_event_id: uuid.UUID | None = None,
) -> AssistantOutcome:
    """One `user_request` run: what they said, what it meant, what changed.

    Transaction shape follows `run_pretrip_plan` for the same reason. The run
    row is committed before the model is called, so the spend stays auditable
    even when the write after it fails, and the failure path writes
    `status='failed'` in its own transaction.
    """
    from app.api.plan import reject_if_past
    from app.api.trips import current_plan

    trip = (
        await session.execute(sa.select(Trip).where(Trip.trip_id == trip_id))
    ).scalar_one()
    # A finished trip's plan is a record, and a record does not take edits. The
    # same 409 the buttons raise, raised before anything is spent on it.
    reject_if_past(trip)

    run = AgentRun(
        trip_id=trip_id,
        trigger_event_id=trigger_event_id,
        kind=RunKind.user_request,
        status=RunStatus.running,
        model=model,
        started_at=now,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    # Held as a plain value, not read back off `run` in the failure path. The
    # rollback there expires every instance in the session, so reading a column
    # off the ORM object would attempt IO inside exception handling and raise
    # `MissingGreenlet` over the top of the failure being recorded.
    run_id = run.run_id

    try:
        gathered = await gather(
            session,
            trip_id,
            run_kind=RunKind.user_request.value,
            prompt_version=ASSISTANT_PROMPT_VERSION,
            now=now,
        )
        ctx = gathered.context
        run.context_snapshot = ctx.model_dump(mode="json")
        await session.commit()

        plan = await current_plan(session, trip_id)
        if plan is None or not plan.items:
            # No plan is not a failure and is not worth a model call: there is
            # nothing an utterance about the plan could refer to.
            run.status = RunStatus.completed
            run.finished_at = now
            reply = "There is no plan for this trip yet."
            run.result = {
                "reply": reply,
                "applied": [],
                "invoked": False,
                "spend": Spend().as_result(),
            }
            await session.commit()
            return AssistantOutcome(run_id=run.run_id, reply=reply)

        decision, spend = await invoke_verified(
            client, frame_utterance(ctx, utterance, model=model), ctx
        )
        applied, refused = await apply_decision(
            session, decision, trip=trip, plan=plan, now=now
        )
        reply = compose_reply(decision, applied, refused)

        run.status = RunStatus.completed
        run.finished_at = now
        # The reply is stored, not just returned. A retry whose response was
        # lost has to be answerable without paying for a second invoke, and the
        # sentence the traveler saw is part of what the run means.
        run.result = {
            "reply": reply,
            "applied": [
                {"item_id": str(c.item_id), "name": c.name} for c in applied
            ],
            "refused": [{"item_id": r.item_id, "code": r.code} for r in refused],
            "invoked": True,
            "spend": spend.as_result(),
        }
        await session.commit()
        return AssistantOutcome(
            run_id=run.run_id,
            reply=reply,
            applied=tuple(applied),
            refused=tuple(refused),
            spend=spend,
        )
    except Exception as exc:
        await session.rollback()
        code = exc.code if isinstance(exc, RunFailed) else f"error:{type(exc).__name__}"
        violations = exc.violations if isinstance(exc, RunFailed) else ()
        spent = exc.spend if isinstance(exc, RunFailed) else None
        run = await session.get(AgentRun, run_id)
        run.status = RunStatus.failed
        run.finished_at = now
        run.error = str(exc)[:500]
        run.result = {
            "code": code,
            "violations": [
                {"code": str(v.code), "path": v.path, "detail": v.detail}
                for v in violations
            ],
            "spend": (spent or Spend()).as_result(),
        }
        await session.commit()
        raise

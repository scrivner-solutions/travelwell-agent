"""Stages 3 through 10: Frame, Invoke, Decode, Verify, Repair, Bind, Commit, Emit.

Nine of the ten stages are deterministic. Only Invoke is not, and it is reached
through the `LlmClient` protocol, so the whole pipeline runs under `FakeLLM`
with no network and no credentials - which is what lets it be tested in the CI
selection rather than in `tests/integration`.

This module writes rows. It must never import `app/services/actions/`: the
harness proposes, the executor acts, and `tests/unit/test_agent_layering.py`
enforces the direction.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, time
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import Gathered, gather
from app.agent.llm import LlmClient, LlmRequest, LlmResponse
from app.agent.prompts import PRETRIP_V1, PROMPT_VERSION
from app.agent.schemas import (
    Candidate,
    ContextWindow,
    PlanProposal,
    TripContext,
    Violation,
    to_minutes,
)
from app.db.models import (
    AgentRun,
    ItemKind,
    Notification,
    OptionState,
    Place,
    Plan,
    PlanItem,
    PlanItemOption,
    PlanStatus,
    RunKind,
    RunStatus,
    Trip,
    WellnessWindow,
    WindowStatus,
)

# Pinned per run kind, never varied per request: changing it mid-flight
# invalidates the cached prefix.
PRETRIP_EFFORT = "high"

EMPTY_HEADLINE = "No openings this trip"


class RunFailed(Exception):
    """A run that stopped for a named reason, in the pipeline's vocabulary.

    `code` is what gets written to `agent_runs.error`, so it is a stable token
    (`decode:truncated`, `verify:invalid`) rather than a sentence.
    """

    def __init__(
        self, code: str, violations: Sequence[Violation] = (), detail: str = ""
    ) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.violations = tuple(violations)
        self.detail = detail
        # Set by invoke_verified on the way out. A failure spends real tokens,
        # and the most expensive outcome is a run that repaired and still lost.
        self.spend: Spend | None = None


@dataclass(frozen=True)
class Spend:
    """What an invoke actually cost, repair turn included.

    Accumulated across attempts rather than read off the last response: a
    repair means two calls, so taking the final one undercounts exactly the
    runs that cost double.
    """

    calls: int = 0
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def repairs(self) -> int:
        """The first call is the invoke; everything after it is a repair."""
        return max(self.calls - 1, 0)

    def plus(self, response: LlmResponse) -> Spend:
        totals = dict(self.usage)
        for key, value in response.usage.items():
            totals[key] = totals.get(key, 0) + value
        return Spend(calls=self.calls + 1, usage=totals)

    def as_result(self) -> dict:
        return {"calls": self.calls, "repairs": self.repairs, "usage": self.usage}


@dataclass(frozen=True)
class Invocation:
    """A verified proposal and what it cost to get one."""

    proposal: PlanProposal
    spend: Spend


@dataclass
class RunOutcome:
    run_id: uuid.UUID
    status: RunStatus
    plan_id: uuid.UUID | None = None
    item_count: int = 0
    headline: str = ""
    error: str = ""
    violations: tuple[Violation, ...] = field(default_factory=tuple)
    invoked: bool = False


# --------------------------------------------------------------------------
# Stage 3: Frame
# --------------------------------------------------------------------------


def frame(
    ctx: TripContext,
    *,
    model: str,
    system: str = PRETRIP_V1,
    effort: str = PRETRIP_EFFORT,
) -> LlmRequest:
    """A context into the exact bytes that go over the wire.

    Serialization is canonical - sorted keys, fixed separators - so two runs
    over the same context produce byte-identical payloads and a replay is a
    diff rather than a guess.
    """
    return LlmRequest(
        model=model,
        system=system,
        payload=json.dumps(
            ctx.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ),
        output_schema=PlanProposal,
        effort=effort,
    )


# --------------------------------------------------------------------------
# Stages 5 and 6: Decode and Verify
# --------------------------------------------------------------------------


def decode(response: LlmResponse) -> dict:
    """Response to payload dict, or a `RunFailed` naming the provider problem.

    `stop_reason` is checked before the body is parsed: a truncated structured
    output is invalid JSON, and reporting that as a parse failure sends whoever
    reads the run after a schema problem that is not there.
    """
    if response.stop_reason == "refusal":
        raise RunFailed("decode:refusal")
    if response.stop_reason == "max_tokens":
        raise RunFailed("decode:truncated")
    try:
        payload = json.loads(response.text)
    except (ValueError, TypeError) as exc:
        raise RunFailed("decode:malformed", detail=str(exc)) from exc
    if not isinstance(payload, dict):
        raise RunFailed("decode:malformed", detail=f"top level {type(payload).__name__}")
    return payload


def render_violations(violations: Sequence[Violation]) -> str:
    """Codes and paths, never free prose.

    The repair turn is a machine telling a machine what was wrong. Rewriting the
    task in prose is both more expensive and less specific than the codes Verify
    already produced.
    """
    lines = [
        "The previous response was rejected by validation. Fix exactly these "
        "and return the whole object again.",
    ]
    lines += [f"- {v.code} at {v.path}: {v.detail}" for v in violations]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Stages 4 and 7: Invoke and Repair
# --------------------------------------------------------------------------


async def invoke_verified(
    client: LlmClient,
    request: LlmRequest,
    ctx: TripContext,
    *,
    max_repairs: int = 1,
) -> Invocation:
    """One invoke, and at most one repair turn, for structural violations only.

    Exactly one repair on purpose. It fixes the common case cheaply, and an
    unbounded loop would hide the signal that matters - the repair rate is how
    a wrong prompt or schema announces itself. Which is only true if the repair
    count survives the call, hence `Invocation` rather than a bare proposal.
    """
    turns: list[str] = []
    spend = Spend()
    for attempt in range(max_repairs + 1):
        response = await client.complete(request, turns=tuple(turns))
        spend = spend.plus(response)
        try:
            result = verify_response(response, ctx)
        except RunFailed as failed:
            # decode failures raise from in here, after the tokens are gone.
            failed.spend = spend
            raise
        if isinstance(result, PlanProposal):
            return Invocation(proposal=result, spend=spend)
        if attempt == max_repairs:
            failure = RunFailed("verify:invalid", violations=result)
            failure.spend = spend
            raise failure
        turns += [response.text, render_violations(result)]
    raise AssertionError("unreachable")  # pragma: no cover


def verify_response(
    response: LlmResponse, ctx: TripContext
) -> PlanProposal | list[Violation]:
    from app.agent.schemas import verify

    return verify(decode(response), ctx)


# --------------------------------------------------------------------------
# Stage 8: Bind
# --------------------------------------------------------------------------


def _at(day, hhmm: str, tz: ZoneInfo) -> datetime:
    """Trip-local "HH:MM" to an aware timestamp. The model never saw an offset."""
    minutes = to_minutes(hhmm)
    return datetime.combine(day, time(minutes // 60, minutes % 60), tzinfo=tz)


def window_label(minutes: int) -> str:
    return f"{minutes} minutes free"


def _bounds(window: ContextWindow) -> list[dict]:
    """Display-shaped provenance for the window's edges.

    `detail` stays null: `bounded_by` carries titles in order and not which side
    each one bounds, so "Ends 5:30 PM" cannot be recovered here without changing
    what `windows.py` returns.
    """
    return [
        {
            "kind": "calendar_event",
            "tag": "CAL",
            "title": title,
            "detail": None,
            "source_label": "Calendar",
        }
        for title in window.bounded_by
    ]


def provenance_summary(ctx: TripContext) -> str:
    """Code-generated from what was actually read, not from what the model said."""
    parts = []
    if ctx.commitments:
        parts.append("your calendar")
    if ctx.trip.hotel is not None:
        parts.append("your hotel")
    if ctx.candidates:
        parts.append(f"{len(ctx.candidates)} places nearby")
    return "From " + ", ".join(parts) if parts else "From your trip dates"


async def bind(
    session: AsyncSession,
    gathered: Gathered,
    proposal: PlanProposal,
    *,
    trip: Trip,
    run: AgentRun,
) -> Plan:
    """Resolve the proposal into rows. Hallucination becomes impossible here.

    Every id resolves through a map built in Gather that never travelled through
    the model, and every display field is copied from our own records. The
    model's prose survives only in `reason`, `rejection_reason` and
    `matched_preferences`, which are the fields it was asked for.

    The plan is written `draft` and its items are left at the `suggested` server
    default. Publishing is a separate transition (`publish_plan`) - see
    tracks/OWNER.md decision 3.
    """
    ctx = gathered.context
    tz = ZoneInfo(trip.timezone)
    windows_by_id = {w.id: w for w in ctx.windows}
    candidates_by_id: dict[str, Candidate] = {c.id: c for c in ctx.candidates}
    notes = {n.window_id: n.gap_explanation for n in proposal.window_notes}

    place_ids = set(gathered.candidate_places.values())
    places: dict[uuid.UUID, Place] = {}
    if place_ids:
        rows = await session.execute(
            sa.select(Place).where(Place.place_id.in_(place_ids))
        )
        places = {p.place_id: p for p in rows.scalars()}

    version = (
        await session.scalar(
            sa.select(sa.func.coalesce(sa.func.max(Plan.version), 0)).where(
                Plan.trip_id == trip.trip_id
            )
        )
    ) or 0

    plan = Plan(
        trip_id=trip.trip_id,
        version=version + 1,
        status=PlanStatus.draft,
        headline=proposal.headline or None,
        provenance_summary=provenance_summary(ctx),
        generated_by_run_id=run.run_id,
    )
    session.add(plan)
    await session.flush()

    # Every computed window is persisted, filled or not: an empty window with a
    # gap_explanation is a product surface, not a leftover.
    window_rows: dict[str, WellnessWindow] = {}
    filled = {item.window_id for item in proposal.items}
    for context_window in ctx.windows:
        interval = gathered.window_intervals[context_window.id]
        row = WellnessWindow(
            trip_id=trip.trip_id,
            local_date=context_window.day,
            starts_at=interval.start,
            ends_at=interval.end,
            label=window_label(context_window.minutes),
            gap_explanation=notes.get(context_window.id) or None,
            bounds=_bounds(context_window),
            status=(
                WindowStatus.filled
                if context_window.id in filled
                else WindowStatus.open
            ),
        )
        session.add(row)
        window_rows[context_window.id] = row
    await session.flush()

    for proposed in proposal.items:
        context_window = windows_by_id[proposed.window_id]
        start = _at(context_window.day, proposed.start, tz)
        end = _at(context_window.day, proposed.end, tz)
        item = PlanItem(
            plan_id=plan.plan_id,
            trip_id=trip.trip_id,
            window_id=window_rows[proposed.window_id].window_id,
            kind=ItemKind(proposed.kind),
            scheduled_start=start,
            scheduled_end=end,
            # Left at the `suggested` server default. See the docstring.
        )
        session.add(item)
        await session.flush()

        duration = int((end - start).total_seconds() // 60)
        for option in proposed.options:
            place_id = gathered.candidate_places[option.candidate_id]
            place = places.get(place_id)
            candidate = candidates_by_id[option.candidate_id]
            session.add(
                PlanItemOption(
                    item_id=item.item_id,
                    place_id=place_id,
                    state=OptionState(option.state),
                    rank=option.rank,
                    display_name=place.name if place else candidate.name,
                    display_summary=place.summary if place else candidate.summary,
                    reason=option.reason or None,
                    rejection_reason=option.rejection_reason or None,
                    distance_minutes=candidate.walk_minutes,
                    duration_minutes=duration,
                    matched_preferences=list(option.matched_preferences),
                )
            )
            # The booking gate is a later decision on the selected option, so
            # needs_reservation stays at its false default here.

    await session.flush()
    return plan


# --------------------------------------------------------------------------
# Publishing: the one transition that surfaces a plan
# --------------------------------------------------------------------------


async def publish_plan(session: AsyncSession, plan: Plan) -> int:
    """Draft to proposed, and `suggested` items to `awaiting_user`, together.

    One statement over one version, not a fan-out. Items the agent handles
    itself are written `planned` directly and are deliberately not touched:
    the WHERE clause is what keeps that true as more item states appear.

    Ratified in tracks/OWNER.md decision 3. `suggested` is the state of an item
    inside a draft plan and never reaches a client; `awaiting_user` is the one
    keep/skip gate.
    """
    plan.status = PlanStatus.proposed
    result = await session.execute(
        sa.update(PlanItem)
        .where(PlanItem.plan_id == plan.plan_id, PlanItem.status == "suggested")
        .values(status="awaiting_user")
    )
    await session.flush()
    return result.rowcount or 0


async def supersede_previous(session: AsyncSession, trip_id: uuid.UUID) -> None:
    await session.execute(
        sa.update(Plan)
        .where(Plan.trip_id == trip_id, Plan.status != "superseded")
        .values(status="superseded")
    )


# --------------------------------------------------------------------------
# Stage 10: Emit
# --------------------------------------------------------------------------


def notification_for(trip: Trip, plan: Plan, item_count: int) -> Notification:
    """A pending row is the truthful record that something was worth telling.

    Delivery is a later slice's problem; nothing here sends anything.
    """
    body = (
        f"{item_count} things to consider before you go."
        if item_count
        else "No openings worth filling on this trip."
    )
    return Notification(
        user_id=trip.user_id,
        trip_id=trip.trip_id,
        run_id=plan.generated_by_run_id,
        kind="plan_ready",
        title=plan.headline or "Your plan is ready",
        body=body,
        cta={"label": "Review plan", "deep_link": f"/trip?trip={trip.trip_id}"},
    )


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


async def run_pretrip_plan(
    session: AsyncSession,
    *,
    trip_id: uuid.UUID,
    client: LlmClient,
    model: str,
    now: datetime,
    trigger_event_id: uuid.UUID | None = None,
    run: AgentRun | None = None,
) -> RunOutcome:
    """Admit-to-Emit for one `pretrip_plan` run.

    Transaction shape is deliberate and is the one asymmetry worth naming:
    Invoke costs money and Commit can still fail after it. The run row is
    committed *before* the model is called, and the failure path writes
    `status='failed'` in its own transaction, so the spend stays auditable and
    the run replayable while the plan tables stay clean.

    `run` is the row `app.agent.admit` already committed alongside the event's
    disposition; passing it is what keeps "never accepted without a run" true.
    Without one this creates its own, which is the path scripts/run_agent.py
    takes.
    """
    trip = (
        await session.execute(sa.select(Trip).where(Trip.trip_id == trip_id))
    ).scalar_one()

    if run is None:
        run = AgentRun(
            trip_id=trip_id,
            trigger_event_id=trigger_event_id,
            kind=RunKind.pretrip_plan,
            status=RunStatus.running,
            model=model,
            started_at=now,
        )
        session.add(run)
    else:
        run.model = model
    await session.commit()
    await session.refresh(run)

    invoked = False
    try:
        gathered = await gather(
            session,
            trip_id,
            run_kind=RunKind.pretrip_plan.value,
            prompt_version=PROMPT_VERSION,
            now=now,
        )
        run.context_snapshot = gathered.context.model_dump(mode="json")
        await session.commit()

        ctx = gathered.context
        spend = Spend()
        if ctx.is_empty_decision_space():
            # Stages 3 through 7 skipped entirely. A model call with nothing to
            # choose from buys nothing and adds a hallucination opportunity.
            proposal = PlanProposal(headline=EMPTY_HEADLINE)
        else:
            invoked = True
            invocation = await invoke_verified(client, frame(ctx, model=model), ctx)
            proposal = invocation.proposal
            spend = invocation.spend

        await supersede_previous(session, trip_id)
        plan = await bind(session, gathered, proposal, trip=trip, run=run)
        await publish_plan(session, plan)
        item_count = len(proposal.items)
        session.add(notification_for(trip, plan, item_count))

        run.status = RunStatus.completed
        run.finished_at = now
        run.result = {
            "plan_id": str(plan.plan_id),
            "version": plan.version,
            "items": item_count,
            "invoked": invoked,
            # Recorded even when zero: "we did not call the model" and "nobody
            # wrote down what the call cost" have to look different.
            "spend": spend.as_result(),
        }
        await session.commit()
        return RunOutcome(
            run_id=run.run_id,
            status=RunStatus.completed,
            plan_id=plan.plan_id,
            item_count=item_count,
            headline=proposal.headline,
            invoked=invoked,
        )
    except Exception as exc:
        await session.rollback()
        code = exc.code if isinstance(exc, RunFailed) else f"error:{type(exc).__name__}"
        violations = exc.violations if isinstance(exc, RunFailed) else ()
        run = await session.get(AgentRun, run.run_id)
        run.status = RunStatus.failed
        run.finished_at = now
        run.error = str(exc)[:500]
        spent = exc.spend if isinstance(exc, RunFailed) else None
        run.result = {
            "code": code,
            "violations": [
                {"code": str(v.code), "path": v.path, "detail": v.detail}
                for v in violations
            ],
            "spend": (spent or Spend()).as_result(),
        }
        await session.commit()
        return RunOutcome(
            run_id=run.run_id,
            status=RunStatus.failed,
            error=code,
            violations=violations,
            invoked=invoked,
        )

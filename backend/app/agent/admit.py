"""Stage 1: Admit - the gate every trigger passes before a token is spent.

Everything that wants agent behaviour inserts an `agent_events` row and stops
(AGENT_DESIGN.md section 5). This module turns those rows into runs.
Classification is code and never calls a model, so cost, latency and
notification noise are all decided here.

The claim is `for update skip locked`: two workers never take the same event,
and a worker that dies mid-classification rolls its event back to `pending`.

That rollback is why the reaper lives in this module rather than in a cron.
Section 5 says a dying worker leaves "no run started", which holds only until
the run row is committed - and `run_pretrip_plan` commits it *before* the model
call deliberately, so the spend stays auditable. Death in the window between
leaves the run `running` for ever while its event returns to `pending` to be
paid for again. Five such rows exist in the dev database. The
`agent_runs_one_running_uq` index section 5 proposes would turn each into a
permanent block on its trip, so the sweep must run before the check that index
enforces, and that check is here.
"""

import enum
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AgentEvent,
    AgentRun,
    EventDisposition,
    EventKind,
    RunKind,
    RunStatus,
    Trip,
    TripState,
)

logger = logging.getLogger(__name__)

# Generous against a slow Vertex call plus repairs, short enough that a trip is
# not blocked for an afternoon. A parameter rather than an env var because the
# tests need to control it and nothing in production has asked to.
RUN_TIMEOUT = timedelta(minutes=10)

REAPED_ERROR = "no result within {timeout}; swept by admit"

# One of six declared RunKinds is implemented. Everything else is classified
# honestly and dropped rather than silently accepted into a run that cannot
# execute; `dropped_immaterial` is the record of what we chose to ignore.
BUILT_RUN_KINDS = frozenset({RunKind.pretrip_plan})

# Section 5's activation states verbatim. `upcoming` is dead per the trip enum
# audit, but admitting a state nothing sets is harmless while excluding one
# something still sets drops a trip's only plan, so it stays until the audit's
# deletion lands and this set is the single place to cut it.
ACTIVATION_STATES = frozenset(
    {TripState.confirmed, TripState.upcoming, TripState.preparing}
)

USER_EVENT_KINDS = frozenset(
    {EventKind.user_text, EventKind.user_voice, EventKind.ui_action}
)


class DropReason(enum.StrEnum):
    """Why an event was not accepted. Logged, never stored: `agent_events`
    has four dispositions and this is the detail underneath the drop."""

    no_trip = "no_trip"
    trip_state = "trip_state"
    not_yet_due = "not_yet_due"
    run_kind_not_built = "run_kind_not_built"
    already_running = "already_running"


@dataclass(frozen=True)
class Decision:
    """What classification concluded about one event."""

    disposition: EventDisposition
    run_kind: RunKind | None = None
    trip_id: uuid.UUID | None = None
    reason: DropReason | None = None


async def reap_stale_runs(
    session: AsyncSession, *, now: datetime, timeout: timedelta = RUN_TIMEOUT
) -> int:
    """Cancel runs that have been `running` past the timeout, and say how many.

    `canceled` rather than `failed`: the run may well have succeeded at the
    provider and died before writing, so this records that we stopped waiting,
    not that the work is known to have gone wrong. The distinction matters
    because `failed` is the status the replay path reads.

    Not committed here. The caller owns the transaction, and the point of the
    sweep is to be in the same one as the check it unblocks.
    """
    cutoff = now - timeout
    result = await session.execute(
        sa.update(AgentRun)
        .where(AgentRun.status == RunStatus.running, AgentRun.started_at < cutoff)
        .values(
            status=RunStatus.canceled,
            finished_at=now,
            error=REAPED_ERROR.format(timeout=timeout),
        )
    )
    reaped = result.rowcount or 0
    if reaped:
        logger.warning("admit swept %d run(s) stuck in running", reaped)
    return reaped


async def _resolve_trip(session: AsyncSession, event: AgentEvent) -> uuid.UUID | None:
    """A user event's trip: the payload's, else the single active trip, else
    the nearest upcoming one (section 5)."""
    if event.trip_id is not None:
        return event.trip_id
    payload_trip = event.payload.get("trip_id") if event.payload else None
    if payload_trip:
        return uuid.UUID(str(payload_trip))

    active = (
        (
            await session.execute(
                sa.select(Trip.trip_id).where(
                    Trip.user_id == event.user_id, Trip.state == TripState.active
                )
            )
        )
        .scalars()
        .all()
    )
    if len(active) == 1:
        return active[0]

    return (
        await session.execute(
            sa.select(Trip.trip_id)
            .where(
                Trip.user_id == event.user_id,
                Trip.state.in_(ACTIVATION_STATES),
            )
            .order_by(Trip.start_date)
            .limit(1)
        )
    ).scalar_one_or_none()


async def classify(
    session: AsyncSession, event: AgentEvent, *, now: datetime
) -> Decision:
    """Section 5's table, for the run kinds that exist.

    Deliberately total: every event kind reaches a disposition, and the ones
    whose run kind is unbuilt are dropped with a reason rather than accepted
    into a run that would never execute.
    """
    if event.kind is EventKind.scheduled_activation:
        trip = (
            await session.execute(sa.select(Trip).where(Trip.trip_id == event.trip_id))
        ).scalar_one_or_none()
        if trip is None:
            return Decision(EventDisposition.dropped_no_trip, reason=DropReason.no_trip)
        if trip.state not in ACTIVATION_STATES:
            return Decision(
                EventDisposition.dropped_immaterial, reason=DropReason.trip_state
            )
        if trip.activation_at is not None and trip.activation_at > now:
            return Decision(
                EventDisposition.dropped_immaterial, reason=DropReason.not_yet_due
            )
        return Decision(
            EventDisposition.accepted,
            run_kind=RunKind.pretrip_plan,
            trip_id=trip.trip_id,
        )

    if event.kind in USER_EVENT_KINDS:
        trip_id = await _resolve_trip(session, event)
        if trip_id is None:
            return Decision(EventDisposition.dropped_no_trip, reason=DropReason.no_trip)
        # user_request is not built; the trip resolved, so the drop is about our
        # capability, not about the event.
        return Decision(
            EventDisposition.dropped_immaterial,
            trip_id=trip_id,
            reason=DropReason.run_kind_not_built,
        )

    return Decision(
        EventDisposition.dropped_immaterial, reason=DropReason.run_kind_not_built
    )


async def admit(
    session: AsyncSession,
    event: AgentEvent,
    *,
    now: datetime,
    timeout: timedelta = RUN_TIMEOUT,
) -> AgentRun | None:
    """Classify one event and, if accepted, create its run in the same commit.

    Order is the whole point. The sweep runs first so a dead worker's orphan
    cannot mask a live trip, then the at-most-one-running check, then the
    insert. Committing the disposition together with the run row means an
    event is never `accepted` without a run existing; a crash after this commit
    under-runs rather than paying twice, which is the safe direction.
    """
    await reap_stale_runs(session, now=now, timeout=timeout)

    decision = await classify(session, event, now=now)
    run: AgentRun | None = None

    if decision.disposition is EventDisposition.accepted:
        assert decision.run_kind is not None and decision.trip_id is not None
        if decision.run_kind not in BUILT_RUN_KINDS:
            decision = Decision(
                EventDisposition.dropped_immaterial,
                trip_id=decision.trip_id,
                reason=DropReason.run_kind_not_built,
            )
        elif await _running_run_id(session, decision.trip_id) is not None:
            # A run already in flight will produce the plan this event asks
            # for. `agent_runs_one_running_uq` is the eventual enforcement and
            # must not land before the sweep above, or an orphan blocks the
            # trip for ever.
            decision = Decision(
                EventDisposition.dropped_immaterial,
                trip_id=decision.trip_id,
                reason=DropReason.already_running,
            )
        else:
            run = AgentRun(
                trip_id=decision.trip_id,
                trigger_event_id=event.event_id,
                kind=decision.run_kind,
                status=RunStatus.running,
                # From the injected clock, not the column default: the sweep
                # above compares against `now`, and a run whose start time comes
                # from a different clock than the logic judging it is a run the
                # sweep can cancel the instant it is created.
                started_at=now,
            )
            session.add(run)

    event.disposition = decision.disposition
    await session.commit()
    if run is not None:
        await session.refresh(run)
    logger.info(
        "admit %s -> %s%s",
        event.kind,
        decision.disposition,
        f" ({decision.reason})" if decision.reason else "",
    )
    return run


async def _running_run_id(
    session: AsyncSession, trip_id: uuid.UUID
) -> uuid.UUID | None:
    return (
        await session.execute(
            sa.select(AgentRun.run_id)
            .where(AgentRun.trip_id == trip_id, AgentRun.status == RunStatus.running)
            .limit(1)
        )
    ).scalar_one_or_none()


async def claim_pending(session: AsyncSession) -> AgentEvent | None:
    """Take the oldest pending event, locked against other workers.

    `skip locked` rather than a plain `for update`: a second worker steps past
    a row someone else holds instead of queueing behind it.
    """
    return (
        await session.execute(
            sa.select(AgentEvent)
            .where(AgentEvent.disposition == EventDisposition.pending)
            .order_by(AgentEvent.received_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
    ).scalar_one_or_none()

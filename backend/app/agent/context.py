"""Stage 2, Gather: a trip id in, the exact bytes the model will see out.

`TripContext` is not a dump of what we know. It is a projection into a fixed
shape, and the shape is what makes the rest of the pipeline checkable: every id
the model may write is one this stage put in, so Bind resolves rather than
looks up, and anything unresolvable is a violation instead of a query.

Everything here is deterministic. Two runs over the same database produce the
same context, which is what makes `agent_runs.context_snapshot` a replay input
rather than a log line.
"""

from __future__ import annotations

import json
import unicodedata
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import windows as windows_mod
from app.agent.candidates import build_candidates, haversine_metres
from app.agent.schemas import (
    Candidate,
    Commitment,
    ContextMeta,
    ContextPreferences,
    ContextWindow,
    CurrentPlanItem,
    CurrentPlanSummary,
    Hotel,
    SessionMinutes,
    TripContext,
    TripFacts,
)
from app.db.models import CalendarEvent, Place, Trip, UserPreferences
from app.services.calendar import is_busy

# Section budgets from AGENT_DESIGN.md section 6. Candidates is the only elastic
# one; the rest are bounded by the trip itself.
CANDIDATE_TOKEN_BUDGET = 2500
CONTEXT_TOKEN_CEILING = 8000

# A place we cannot show as near the traveler is a place we cannot describe the
# only way that matters ("12 min walk"), so distance is a filter, not a column.
MAX_CANDIDATE_METRES = 8_000.0

TITLE_LIMIT = 120


class ContextTooLarge(RuntimeError):
    """The assembled context exceeded the hard ceiling.

    Raised rather than truncated further: past the ceiling something upstream is
    wrong, and silently shrinking the context would hide it behind a plan that
    is merely worse.
    """


@dataclass(frozen=True)
class Gathered:
    """The context, plus the maps Bind needs to turn ids back into rows.

    The windows are computed, not yet persisted - `wellness_windows` rows are
    written at Commit, so a run that never commits leaves nothing behind.
    """

    context: TripContext
    candidate_places: dict[str, uuid.UUID] = field(default_factory=dict)
    window_intervals: dict[str, windows_mod.FreeWindow] = field(default_factory=dict)
    commitment_events: dict[str, uuid.UUID] = field(default_factory=dict)


def clean_untrusted(text: str, limit: int = TITLE_LIMIT) -> str:
    """Strip control characters and cap length. Nothing else.

    Not `sanitize_prose`: this is the *user's* text, not the agent's. A meeting
    called "my standup" is correct first person and must survive, where the same
    words written by the model would not. Both are untrusted; only one of them
    has a voice to keep.

    The real containment is structural anyway - a planning run exposes no
    side-effecting tool, the output schema can only name ids from this context,
    and every external effect needs a `pending_actions` row and a human. The
    worst a successful injection reaches is a bad plan.
    """
    cleaned = "".join(
        ch for ch in text if ch == " " or unicodedata.category(ch)[0] != "C"
    )
    cleaned = " ".join(cleaned.split())
    return cleaned[:limit]


def degraded_counts(candidates: Sequence[Candidate]) -> list[str]:
    """One `unchecked_<constraint>:<count>` token per constraint left unverified.

    A count, not a flag: "three of forty" and "forty of forty" are different
    situations and only one of them means the cache is empty. The invariant this
    serves - unknowns must never empty a slot - already holds by construction,
    because the filter admits unknowns rather than excluding them; this is the
    part that makes the admission visible instead of silent.
    """
    tally: Counter[str] = Counter()
    for candidate in candidates:
        tally.update(candidate.unknown)
    return [f"unchecked_{token}:{tally[token]}" for token in sorted(tally)]


def estimate_tokens(value: object) -> int:
    """Deterministic size proxy: canonical JSON, four characters per token.

    A real tokenizer would be a provider dependency in a stage that is supposed
    to have none, and the budget only needs to be stable, not exact.
    """
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return len(encoded) // 4


def _local(moment: datetime, tz: ZoneInfo) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=tz)
    return moment.astimezone(tz)


def _hhmm(moment: datetime) -> str:
    return f"{moment.hour:02d}:{moment.minute:02d}"


def _trip_days(trip: Trip) -> list[date]:
    span = (trip.end_date - trip.start_date).days
    return [trip.start_date + timedelta(days=offset) for offset in range(span + 1)]


def _origin(trip: Trip) -> tuple[float, float] | None:
    """Where the traveler starts from: the hotel, else the destination."""
    if trip.hotel_lat is not None and trip.hotel_lng is not None:
        return (trip.hotel_lat, trip.hotel_lng)
    if trip.destination_lat is not None and trip.destination_lng is not None:
        return (trip.destination_lat, trip.destination_lng)
    return None


def _preferences(row: UserPreferences | None) -> ContextPreferences:
    if row is None:
        return ContextPreferences()
    session = None
    if row.session_min_minutes is not None and row.session_max_minutes is not None:
        session = SessionMinutes(
            min=row.session_min_minutes, max=row.session_max_minutes
        )
    return ContextPreferences(
        dietary=list(row.dietary or ()),
        workout_kinds=list(row.activities or ()),
        facilities=list(row.amenities or ()),
        memberships=list(row.memberships or ()),
        price_level_max=row.price_level_max,
        day_pass_max_cents=row.day_pass_budget_cents,
        session_minutes=session,
        preferred_times=list(row.preferred_times or ()),
    )


def _fit_candidates(candidates: list, budget: int = CANDIDATE_TOKEN_BUDGET) -> list:
    """Drop from the tail until the section fits.

    The tail is the worst of the pre-rank, which is the whole reason
    `candidates.py` ranks before this runs: truncation that drops arbitrary
    candidates would remove ones the model would have picked.
    """
    kept = list(candidates)
    while kept and estimate_tokens([c.model_dump() for c in kept]) > budget:
        kept.pop()
    return kept


async def gather(
    session: AsyncSession,
    trip_id: uuid.UUID,
    *,
    run_kind: str,
    prompt_version: str,
    now: datetime,
    degraded: list[str] | None = None,
) -> Gathered:
    """Read everything the run needs and project it into a `TripContext`."""
    trip = (
        await session.execute(select(Trip).where(Trip.trip_id == trip_id))
    ).scalar_one()
    tz = ZoneInfo(trip.timezone)

    prefs_row = (
        await session.execute(
            select(UserPreferences).where(UserPreferences.user_id == trip.user_id)
        )
    ).scalar_one_or_none()
    preferences = _preferences(prefs_row)

    events = list(
        (
            await session.execute(
                select(CalendarEvent)
                .where(CalendarEvent.trip_id == trip_id)
                .order_by(CalendarEvent.starts_at)
            )
        ).scalars()
    )

    commitments: list[Commitment] = []
    commitment_events: dict[str, uuid.UUID] = {}
    busy: list[windows_mod.BusyInterval] = []
    for index, event in enumerate(events, start=1):
        start, end = _local(event.starts_at, tz), _local(event.ends_at, tz)
        title = clean_untrusted(event.title)
        event_id = f"e{index}"
        commitment_events[event_id] = event.cal_event_id
        commitments.append(
            Commitment(
                id=event_id,
                title=title,
                day=start.date(),
                start=_hhmm(start),
                end=_hhmm(end),
            )
        )
        if is_busy(event):
            busy.append(windows_mod.BusyInterval(start=start, end=end, title=title))

    minimum = (
        preferences.session_minutes.min
        if preferences.session_minutes is not None
        else windows_mod.DEFAULT_MIN_MINUTES
    )
    free = windows_mod.free_windows(
        busy, _trip_days(trip), tz, min_minutes=minimum
    )
    context_windows: list[ContextWindow] = []
    window_intervals: dict[str, windows_mod.FreeWindow] = {}
    for index, window in enumerate(free, start=1):
        window_id = f"w{index}"
        window_intervals[window_id] = window
        context_windows.append(
            ContextWindow(
                id=window_id,
                day=window.day,
                start=_hhmm(window.start),
                end=_hhmm(window.end),
                minutes=window.minutes,
                bounded_by=list(window.bounded_by),
            )
        )

    places = await _nearby_places(session, _origin(trip))
    candidates, candidate_places = build_candidates(
        places, context_windows, preferences, _origin(trip)
    )
    candidates = _fit_candidates(candidates)
    kept = {c.id for c in candidates}
    candidate_places = {k: v for k, v in candidate_places.items() if k in kept}

    context = TripContext(
        meta=ContextMeta(
            prompt_version=prompt_version,
            generated_at=now.isoformat(),
            run_kind=run_kind,
            degraded=[*(degraded or ()), *degraded_counts(candidates)],
        ),
        trip=_trip_facts(trip),
        commitments=commitments,
        windows=context_windows,
        preferences=preferences,
        candidates=candidates,
        current_plan=await _current_plan_summary(session, trip_id, tz),
    )

    size = estimate_tokens(context.model_dump(mode="json"))
    if size > CONTEXT_TOKEN_CEILING:
        raise ContextTooLarge(
            f"context for trip {trip_id} is ~{size} tokens, ceiling is "
            f"{CONTEXT_TOKEN_CEILING}"
        )

    return Gathered(
        context=context,
        candidate_places=candidate_places,
        window_intervals=window_intervals,
        commitment_events=commitment_events,
    )


def _trip_facts(trip: Trip) -> TripFacts:
    hotel = None
    if trip.hotel_name:
        hotel = Hotel(
            name=clean_untrusted(trip.hotel_name),
            lat=trip.hotel_lat,
            lng=trip.hotel_lng,
        )
    return TripFacts(
        destination=trip.destination_city,
        label=trip.label,
        start_date=trip.start_date,
        end_date=trip.end_date,
        timezone=trip.timezone,
        hotel=hotel,
    )


async def _nearby_places(
    session: AsyncSession, origin: tuple[float, float] | None
) -> list[Place]:
    """The cache, filtered to walking range of the traveler.

    Filtered in Python rather than SQL: without PostGIS the query would be a
    bounding box that still needs the real distance afterwards, and the cache is
    small. Track B owns filling this table; nothing here calls the Places API.
    """
    rows = list((await session.execute(select(Place))).scalars())
    if origin is None:
        return rows
    near = []
    for place in rows:
        if place.lat is None or place.lng is None:
            continue
        if haversine_metres(origin[0], origin[1], place.lat, place.lng) <= (
            MAX_CANDIDATE_METRES
        ):
            near.append(place)
    return near


async def _current_plan_summary(
    session: AsyncSession, trip_id: uuid.UUID, tz: ZoneInfo
) -> CurrentPlanSummary | None:
    """Summarise the live plan for a replan run.

    Uses `api.trips.current_plan` rather than a third copy of the query: which
    plan is "current" is one rule for the whole server, and the exclusion of
    draft and superseded versions is load-bearing enough that a second
    implementation would eventually disagree with the one the UI reads.
    """
    from app.api.trips import current_plan

    plan = await current_plan(session, trip_id)
    if plan is None:
        return None
    items = []
    for item in plan.items:
        selected = next((o for o in item.options if o.state == "selected"), None)
        end = item.scheduled_end or item.scheduled_start
        items.append(
            CurrentPlanItem(
                item_id=str(item.item_id),
                window_id=str(item.window_id) if item.window_id else None,
                name=selected.display_name if selected else "",
                start=_hhmm(_local(item.scheduled_start, tz)),
                end=_hhmm(_local(end, tz)),
                status=str(item.status),
            )
        )
    return CurrentPlanSummary(
        version=plan.version, headline=plan.headline, items=items
    )

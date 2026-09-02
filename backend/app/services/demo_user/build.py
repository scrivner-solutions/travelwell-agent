"""Turns app/services/demo_user/data.py into rows.

Two entry points, and they are a pair: `wipe_demo_user` clears exactly the
tables `build_demo_user` writes, so the seed script's idempotency cannot drift
from the scene's reach. The caller owns the transaction; nothing here commits.

Seven tables (places, calendar_events, agent_events, agent_runs,
pending_actions, reservations, notifications) are seeded with textual SQL. All
of them have ORM models now; the SQL is a bulk-insert convenience here, not a
missing model.
"""

import json
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuthProvider,
    ConnectedSource,
    Plan,
    PlanItem,
    PlanItemOption,
    Trip,
    TripEvidence,
    TripState,
    User,
    UserPreferences,
    WellnessWindow,
)
from app.services.demo_user import data
from app.services.demo_user.data import T, TripSpec

# Trips that have cleared the confirm gate carry a wake-up time; detected and
# dismissed ones never do. Same T-7d midnight trip-local rule the /confirm
# handler applies, so seeded rows are indistinguishable from real ones.
ACTIVATED_STATES = frozenset(
    {
        TripState.confirmed,
        TripState.upcoming,
        TripState.preparing,
        TripState.active,
        TripState.completed,
        TripState.archived,
    }
)
ACTIVATION_LEAD = timedelta(days=7)

# Child-first, and ordered so no statement removes a row another still points
# at: notifications cite runs, plan_items cite windows, agent_runs cite events.
WIPE_SQL = [
    "delete from notifications where user_id = :uid",
    "delete from reservations where trip_id in (select trip_id from trips where user_id = :uid)",
    "delete from pending_actions where user_id = :uid",
    "delete from plan_items where trip_id in (select trip_id from trips where user_id = :uid)",
    "delete from plans where trip_id in (select trip_id from trips where user_id = :uid)",
    "delete from wellness_windows where trip_id in (select trip_id from trips where user_id = :uid)",
    "delete from agent_runs where trip_id in (select trip_id from trips where user_id = :uid)",
    "delete from agent_events where user_id = :uid",
    "delete from calendar_events where user_id = :uid",
    "delete from trips where user_id = :uid",
    "delete from connected_sources where user_id = :uid",
    "delete from user_preferences where user_id = :uid",
]


async def wipe_demo_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Clear everything build_demo_user writes, leaving the user row itself.

    Keeping the row means a developer's session cookie survives a re-seed.
    `places` is deliberately untouched: it is a shared provider cache with no
    user_id, and other accounts reference the same rows.
    """
    for statement in WIPE_SQL:
        await session.execute(text(statement), {"uid": user_id})


async def build_demo_user(
    session: AsyncSession, email: str, *, display_name: str | None = None
) -> User:
    """Create (or re-populate) the demo account for `email` and return the user."""
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            display_name=display_name or data.DISPLAY_NAME,
            auth_provider=AuthProvider.email,
            home_timezone=data.HOME_TIMEZONE,
        )
        session.add(user)
        await session.flush()
    else:
        await wipe_demo_user(session, user.user_id)
        user.display_name = display_name or data.DISPLAY_NAME
        user.home_timezone = data.HOME_TIMEZONE

    places = await _upsert_places(session)
    session.add(UserPreferences(user_id=user.user_id, **data.PREFERENCES))
    sources = _add_sources(session, user)
    await session.flush()

    for spec in data.TRIPS:
        await _build_trip(session, user, spec, places, sources)

    return user


# --- places ---------------------------------------------------------------


async def _upsert_places(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Insert the venue cache, reusing rows another demo account already made."""
    ids: dict[str, uuid.UUID] = {}
    for place in data.PLACES:
        row = await session.execute(
            text(
                """
                insert into places
                  (provider_ref, kind, name, summary, address, lat, lng,
                   price_level, day_pass_cents, amenities, hours, photo_url,
                   reservable_via)
                values
                  (:ref, cast(:kind as place_kind), :name, :summary, :address,
                   :lat, :lng, :price, :pass, :amenities,
                   cast(:hours as jsonb), :photo,
                   cast(:reservable as reservation_provider))
                on conflict (provider_ref) do update set fetched_at = now()
                returning place_id
                """
            ),
            {
                "ref": place.provider_ref,
                "kind": place.kind,
                "name": place.name,
                "summary": place.summary,
                "address": place.address,
                "lat": place.lat,
                "lng": place.lng,
                "price": place.price_level,
                "pass": place.day_pass_cents,
                "amenities": list(place.amenities),
                "hours": json.dumps(place.hours) if place.hours else None,
                "photo": place.photo_url,
                "reservable": place.reservable_via,
            },
        )
        ids[place.key] = row.scalar_one()
    return ids


def _add_sources(session: AsyncSession, user: User) -> dict[str, ConnectedSource]:
    now = datetime.now(UTC)
    sources = {
        spec.key: ConnectedSource(
            user_id=user.user_id,
            kind=spec.kind,
            status=spec.status,
            scopes=spec.scopes,
            last_synced_at=now - timedelta(minutes=spec.synced_minutes_ago),
        )
        for spec in data.SOURCES
    }
    session.add_all(list(sources.values()))
    return sources


# --- one trip -------------------------------------------------------------


def _resolver(start: date, timezone: str):
    """Trip-relative wall clock -> an aware datetime in the trip's own zone."""
    tz = ZoneInfo(timezone)

    def at(moment: T) -> datetime:
        return datetime.combine(
            start + timedelta(days=moment.day), time(moment.hour, moment.minute), tz
        )

    return at


async def _build_trip(
    session: AsyncSession,
    user: User,
    spec: TripSpec,
    places: dict[str, uuid.UUID],
    sources: dict[str, ConnectedSource],
) -> None:
    today = date.today()
    start = today + timedelta(days=spec.starts_in_days)
    end = start + timedelta(days=spec.nights)
    at = _resolver(start, spec.timezone)
    tz = ZoneInfo(spec.timezone)

    activation = None
    if spec.state in ACTIVATED_STATES:
        activation = datetime.combine(start - ACTIVATION_LEAD, time(0, 0), tz)

    hotel = data_place(spec.hotel)
    trip = Trip(
        user_id=user.user_id,
        destination_city=spec.city,
        destination_region=spec.region,
        destination_lat=spec.lat,
        destination_lng=spec.lng,
        timezone=spec.timezone,
        start_date=start,
        end_date=end,
        label=spec.label,
        hotel_name=hotel.name if hotel else None,
        hotel_address=hotel.address if hotel else None,
        hotel_lat=hotel.lat if hotel else None,
        hotel_lng=hotel.lng if hotel else None,
        hotel_place_id=places[spec.hotel] if spec.hotel else None,
        state=spec.state,
        origin=spec.origin,
        detection_confidence=spec.detection_confidence,
        activation_at=activation,
        evidence=[
            TripEvidence(
                kind=e.kind,
                source_label=e.source_label,
                summary=e.summary,
                detail=e.detail,
                source_ref=e.source_ref,
            )
            for e in spec.evidence
        ],
    )
    session.add(trip)
    await session.flush()

    await _add_calendar_events(session, user, spec, sources, at)
    windows = _add_windows(session, trip, spec, at)
    await session.flush()

    events = await _add_agent_events(session, user, trip, spec, at)
    runs = await _add_agent_runs(session, trip, spec, at, events)
    items = await _add_plans(session, trip, spec, at, places, windows, runs)
    await _add_actions(session, user, trip, spec, at, items)
    await _add_reservations(session, trip, spec, at, places, items)
    await _add_notifications(session, user, trip, spec, at, runs)


def data_place(key: str | None):
    if key is None:
        return None
    return next(p for p in data.PLACES if p.key == key)


async def _add_calendar_events(session, user, spec, sources, at) -> None:
    source_id = sources["calendar"].source_id
    for event in spec.calendar_events:
        await session.execute(
            text(
                """
                insert into calendar_events
                  (user_id, source_id, external_id, title, location,
                   starts_at, ends_at, status, content_hash)
                values
                  (:uid, :sid, :ext, :title, :loc, :starts, :ends,
                   :status, :hash)
                """
            ),
            {
                "uid": user.user_id,
                "sid": source_id,
                # External ids are unique per source and every demo account gets
                # its own sources, so the trip-scoped key cannot collide.
                "ext": f"evt_{event.key}",
                "title": event.title,
                "loc": event.location,
                "starts": at(event.starts),
                "ends": at(event.ends),
                "status": event.status,
                "hash": f"h_{event.key}",
            },
        )


def _add_windows(session, trip, spec, at) -> dict[str, WellnessWindow]:
    windows = {
        w.key: WellnessWindow(
            trip_id=trip.trip_id,
            local_date=trip.start_date + timedelta(days=w.local_day),
            starts_at=at(w.starts),
            ends_at=at(w.ends),
            label=w.label,
            gap_explanation=w.gap_explanation,
            bounds=[b._asdict() for b in w.bounds],
            status=w.status,
        )
        for w in spec.windows
    }
    session.add_all(list(windows.values()))
    return windows


async def _add_agent_events(session, user, trip, spec, at) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    for event in spec.events:
        row = await session.execute(
            text(
                """
                insert into agent_events
                  (user_id, trip_id, kind, payload, disposition, occurred_at)
                values
                  (:uid, :tid, cast(:kind as event_kind), cast(:payload as jsonb),
                   cast(:disp as event_disposition), :occurred)
                returning event_id
                """
            ),
            {
                "uid": user.user_id,
                "tid": trip.trip_id,
                "kind": event.kind,
                "payload": json.dumps(event.payload),
                "disp": event.disposition,
                "occurred": at(event.occurred),
            },
        )
        ids[event.key] = row.scalar_one()
    return ids


async def _add_agent_runs(session, trip, spec, at, events) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    for run in spec.runs:
        row = await session.execute(
            text(
                """
                insert into agent_runs
                  (trip_id, trigger_event_id, kind, status, context_snapshot,
                   result, model, error, started_at, finished_at)
                values
                  (:tid, :eid, cast(:kind as run_kind), cast(:status as run_status),
                   cast(:ctx as jsonb), cast(:result as jsonb), :model, :error,
                   :started, :finished)
                returning run_id
                """
            ),
            {
                "tid": trip.trip_id,
                "eid": events[run.trigger_event] if run.trigger_event else None,
                "kind": run.kind,
                "status": run.status,
                "ctx": json.dumps(run.context_snapshot),
                "result": json.dumps(run.result) if run.result else None,
                "model": run.model,
                "error": run.error,
                "started": at(run.started),
                "finished": at(run.finished) if run.finished else None,
            },
        )
        ids[run.key] = row.scalar_one()
    return ids


async def _add_plans(
    session, trip, spec, at, places, windows, runs
) -> dict[str, PlanItem]:
    items: dict[str, PlanItem] = {}
    for plan_spec in spec.plans:
        plan = Plan(
            trip_id=trip.trip_id,
            version=plan_spec.version,
            status=plan_spec.status,
            headline=plan_spec.headline,
            provenance_summary=plan_spec.provenance_summary,
            generated_by_run_id=runs[plan_spec.run],
        )
        session.add(plan)
        await session.flush()

        for item_spec in plan_spec.items:
            item = PlanItem(
                plan_id=plan.plan_id,
                trip_id=trip.trip_id,
                window_id=(
                    windows[item_spec.window].window_id if item_spec.window else None
                ),
                kind=item_spec.kind,
                status=item_spec.status,
                scheduled_start=at(item_spec.starts),
                scheduled_end=at(item_spec.ends),
                needs_reservation=item_spec.needs_reservation,
                calendar_event_ref=item_spec.calendar_event_ref,
                options=[
                    PlanItemOption(
                        place_id=places[o.place],
                        state=o.state,
                        rank=rank,
                        display_name=o.display_name,
                        display_summary=o.display_summary,
                        reason=o.reason,
                        rejection_reason=o.rejection_reason,
                        distance_minutes=o.distance_minutes,
                        duration_minutes=o.duration_minutes,
                        matched_preferences=list(o.matched_preferences),
                    )
                    for rank, o in enumerate(item_spec.options)
                ],
            )
            session.add(item)
            items[item_spec.key] = item
        await session.flush()
    return items


async def _add_actions(session, user, trip, spec, at, items) -> None:
    for action in spec.actions:
        await session.execute(
            text(
                """
                insert into pending_actions
                  (trip_id, user_id, type, status, approval_required,
                   subject_item_id, proposed_payload, execution_result,
                   verification, idempotency_key, proposed_at, approved_at,
                   executed_at)
                values
                  (:tid, :uid, cast(:type as action_type),
                   cast(:status as action_status), :approval, :item,
                   cast(:payload as jsonb), cast(:result as jsonb),
                   cast(:verify as jsonb), :key, :proposed, :approved, :executed)
                """
            ),
            {
                "tid": trip.trip_id,
                "uid": user.user_id,
                "type": action.type,
                "status": action.status,
                "approval": action.approval_required,
                "item": (
                    items[action.subject_item].item_id if action.subject_item else None
                ),
                "payload": json.dumps(action.proposed_payload),
                "result": (
                    json.dumps(action.execution_result)
                    if action.execution_result
                    else None
                ),
                "verify": (
                    json.dumps(action.verification) if action.verification else None
                ),
                # Unique across accounts; real keys are opaque per-attempt tokens.
                "key": f"{user.user_id}:{action.key}",
                "proposed": at(action.proposed),
                "approved": at(action.approved) if action.approved else None,
                "executed": at(action.executed) if action.executed else None,
            },
        )


async def _add_reservations(session, trip, spec, at, places, items) -> None:
    for res in spec.reservations:
        await session.execute(
            text(
                """
                insert into reservations
                  (trip_id, item_id, place_id, provider, status, slot_at,
                   party_size, confirmation_code, failure_reason, external_url)
                values
                  (:tid, :item, :place, cast(:provider as reservation_provider),
                   cast(:status as reservation_status), :slot, :party,
                   :code, :failure, :url)
                """
            ),
            {
                "tid": trip.trip_id,
                "item": items[res.item].item_id if res.item else None,
                "place": places[res.place] if res.place else None,
                "provider": res.provider,
                "status": res.status,
                "slot": at(res.slot),
                "party": res.party_size,
                "code": res.confirmation_code,
                "failure": res.failure_reason,
                "url": res.external_url,
            },
        )


async def _add_notifications(session, user, trip, spec, at, runs) -> None:
    for note in spec.notifications:
        await session.execute(
            text(
                """
                insert into notifications
                  (user_id, trip_id, run_id, kind, title, body, cta, status,
                   created_at, sent_at, opened_at)
                values
                  (:uid, :tid, :rid, :kind, :title, :body, cast(:cta as jsonb),
                   cast(:status as notification_status), :created, :sent, :opened)
                """
            ),
            {
                "uid": user.user_id,
                "tid": trip.trip_id,
                "rid": runs[note.run] if note.run else None,
                "kind": note.kind,
                "title": note.title,
                "body": note.body,
                "cta": json.dumps(note.cta) if note.cta else None,
                "status": note.status,
                "created": at(note.created),
                "sent": at(note.sent) if note.sent else None,
                "opened": at(note.opened) if note.opened else None,
            },
        )


__all__ = ["build_demo_user", "wipe_demo_user"]

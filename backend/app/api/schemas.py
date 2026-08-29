"""Pydantic schemas for the /api/v1 surface.

These mirror docs/openapi.yaml, not the tables (ADR-001 point 6): the contract
carries derived fields (destination_name, needs_you_count, state_line) that no
table stores, so mapping from models is explicit, never automatic.
"""

import enum
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import available_timezones

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.db.models import (
    AuthProvider,
    ConnectedSource,
    ItemKind,
    ItemStatus,
    OptionState,
    Plan,
    PlanItem,
    PlanItemOption,
    PlanStatus,
    Reservation,
    ReservationProvider,
    ReservationStatus,
    SourceKind,
    SourceStatus,
    Trip,
    TripEvidence,
    TripOrigin,
    TripState,
    UserPreferences,
    WellnessWindow,
    WindowStatus,
)


class EmailCodeRequest(BaseModel):
    email: EmailStr


class EmailCodeVerify(BaseModel):
    email: EmailStr
    code: str


class DemoLoginRequest(BaseModel):
    name: str | None = Field(default=None, max_length=80)


# Built once: available_timezones() walks the tzdata tree on every call.
_IANA_ZONES = frozenset(available_timezones())

# users.home_timezone is NOT NULL default 'UTC', so 'UTC' doubles as "never
# asked" — no real home zone is literally UTC (Britain is Europe/London).
UNSET_HOME_TIMEZONE = "UTC"


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None = None
    auth_provider: AuthProvider
    created_at: datetime
    home_timezone: str

    @classmethod
    def from_model(cls, user) -> "UserOut":
        return cls(
            id=user.user_id,
            email=user.email,
            display_name=user.display_name,
            auth_provider=user.auth_provider,
            created_at=user.created_at,
            home_timezone=user.home_timezone,
        )


class UserUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    home_timezone: str | None = None

    @field_validator("home_timezone")
    @classmethod
    def _known_zone(cls, v: str | None) -> str | None:
        # Stored unvalidated, this reaches ZoneInfo() on every /today read.
        if v is not None and v not in _IANA_ZONES:
            raise ValueError("unknown IANA timezone")
        return v


class TripCreateIn(BaseModel):
    destination_name: str
    starts_on: date
    ends_on: date
    lodging_name: str | None = None
    label: str | None = None

    @model_validator(mode="after")
    def _dates_ordered(self) -> "TripCreateIn":
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on must not be before starts_on")
        return self


class TripEvidenceOut(BaseModel):
    source: SourceKind
    summary: str
    detail: str | None = None
    kind: str


class PlanProgress(enum.StrEnum):
    """The one badge a trip row carries. `none` renders as no badge at all."""

    none = "none"
    preparing = "preparing"
    planned = "planned"
    booking = "booking"


class NeedsYouKind(enum.StrEnum):
    """Which gate the open work belongs to, so a row can name the ask."""

    plan = "plan"
    approval = "approval"
    mixed = "mixed"


@dataclass(frozen=True)
class TripProgress:
    """Per-trip rollup over plan_items and pending_actions, computed in one query."""

    needs_you_count: int
    needs_you_kind: NeedsYouKind | None
    plan_progress: PlanProgress


EMPTY_PROGRESS = TripProgress(
    needs_you_count=0, needs_you_kind=None, plan_progress=PlanProgress.none
)


class TripOut(BaseModel):
    id: uuid.UUID
    state: TripState
    origin: TripOrigin
    destination_name: str
    label: str | None = None
    timezone: str
    starts_on: date
    ends_on: date
    detection_confidence: float | None = None
    evidence: list[TripEvidenceOut] = []
    state_line: str
    plan_progress: PlanProgress
    needs_you_count: int
    needs_you_kind: NeedsYouKind | None = None
    updated_at: datetime


class TripListOut(BaseModel):
    trips: list[TripOut]


class WindowBoundOut(BaseModel):
    tag: str
    title: str
    detail: str | None = None
    source_label: str | None = None


class WellnessWindowOut(BaseModel):
    id: uuid.UUID
    status: WindowStatus
    starts_at: datetime
    ends_at: datetime
    label: str
    gap_explanation: str | None = None
    bounds: list[WindowBoundOut] = []


class PlanItemOptionOut(BaseModel):
    id: uuid.UUID
    state: OptionState
    display_name: str
    display_summary: str | None = None
    reason: str | None = None
    distance_minutes: int | None = None
    duration_minutes: int | None = None
    matched_preferences: list[str] = []
    rejection_reason: str | None = None


class ReservationOut(BaseModel):
    """A booking the agent attempted for an item.

    `failure_reason` is stored but deliberately not carried: the contract does
    not have it, so a client can say a booking was refused and not why. Adding
    it is D17's call, with the retry it implies.
    """

    id: uuid.UUID
    status: ReservationStatus
    provider: ReservationProvider
    # Present iff status = confirmed; the database enforces it (reservations_check).
    confirmation_code: str | None = None
    reserved_for: datetime | None = None
    external_url: str | None = None


class PlanItemOut(BaseModel):
    id: uuid.UUID
    kind: ItemKind
    status: ItemStatus
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    window_id: uuid.UUID | None = None
    # The opening, embedded: the review card leads with it, and a per-item
    # provenance fetch would make that card cost one request each.
    window: WellnessWindowOut | None = None
    needs_reservation: bool = False
    why: list[str] = []
    selected_option: PlanItemOptionOut | None = None
    # Selected + alternatives, by rank. Rejected ones are reachable only through
    # provenance, so a card cannot offer a choice that would erase its reason.
    options: list[PlanItemOptionOut] = []
    # The newest attempt only. Retries are a list in the database; a card asks
    # "where does this booking stand", which is a question about the last one.
    reservation: ReservationOut | None = None
    updated_at: datetime


class PlanOut(BaseModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    version: int
    status: PlanStatus
    headline: str
    provenance_summary: str | None = None
    items: list[PlanItemOut] = []
    updated_at: datetime


class ProvenanceOut(BaseModel):
    """"How I got here": the opening, and every candidate considered for it."""

    item_id: uuid.UUID
    window: WellnessWindowOut | None = None
    considered: list[PlanItemOptionOut] = []


class TodayViewOut(BaseModel):
    trip_id: uuid.UUID
    day_label: str
    state_word: str
    state_detail: str | None = None
    timezone: str
    window: WellnessWindowOut | None = None
    next_up: list[PlanItemOut] = []


class CalendarEventSummaryOut(BaseModel):
    id: uuid.UUID
    title: str
    location_name: str | None = None


class TimelineEntryOut(BaseModel):
    entry_type: str  # 'calendar_event' | 'plan_item'
    starts_at: datetime
    ends_at: datetime | None = None
    calendar_event: CalendarEventSummaryOut | None = None
    plan_item: PlanItemOut | None = None


class TimelineOut(BaseModel):
    entries: list[TimelineEntryOut]


class PreferencesOut(BaseModel):
    dietary: list[str]
    activities: list[str]
    amenities: list[str]
    memberships: list[str]
    preferred_times: list[str]
    price_level_max: int | None = None
    day_pass_budget_cents: int | None = None
    session_min_minutes: int | None = None
    session_max_minutes: int | None = None
    allow_calendar_write: bool
    allow_auto_book: bool
    watch_schedule: bool
    updated_at: datetime


class PreferencesUpdateIn(BaseModel):
    """Partial update: only fields present in the body are applied
    (model_dump(exclude_unset=True)); explicit null clears a nullable scalar.
    Defaults below are never used, they only make every field optional."""

    dietary: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    amenities: list[str] = Field(default_factory=list)
    memberships: list[str] = Field(default_factory=list)
    preferred_times: list[str] = Field(default_factory=list)
    price_level_max: int | None = Field(default=None, ge=1, le=4)
    day_pass_budget_cents: int | None = Field(default=None, ge=0)
    session_min_minutes: int | None = Field(default=None, ge=5, le=600)
    session_max_minutes: int | None = Field(default=None, ge=5, le=600)
    allow_calendar_write: bool = False
    allow_auto_book: bool = False
    watch_schedule: bool = True


class ConnectedSourceOut(BaseModel):
    id: uuid.UUID
    kind: SourceKind
    status: SourceStatus
    connected_at: datetime
    last_synced_at: datetime | None = None


class SourcesOut(BaseModel):
    sources: list[ConnectedSourceOut]


def preferences_to_out(prefs: UserPreferences) -> PreferencesOut:
    return PreferencesOut(
        dietary=prefs.dietary,
        activities=prefs.activities,
        amenities=prefs.amenities,
        memberships=prefs.memberships,
        preferred_times=prefs.preferred_times,
        price_level_max=prefs.price_level_max,
        day_pass_budget_cents=prefs.day_pass_budget_cents,
        session_min_minutes=prefs.session_min_minutes,
        session_max_minutes=prefs.session_max_minutes,
        allow_calendar_write=prefs.allow_calendar_write,
        allow_auto_book=prefs.allow_auto_book,
        watch_schedule=prefs.watch_schedule,
        updated_at=prefs.updated_at,
    )


def source_to_out(source: ConnectedSource) -> ConnectedSourceOut:
    return ConnectedSourceOut(
        id=source.source_id,
        kind=source.kind,
        status=source.status,
        connected_at=source.created_at,
        last_synced_at=source.last_synced_at,
    )


def window_to_out(window: WellnessWindow) -> WellnessWindowOut:
    return WellnessWindowOut(
        id=window.window_id,
        status=window.status,
        starts_at=window.starts_at,
        ends_at=window.ends_at,
        label=window.label,
        gap_explanation=window.gap_explanation,
        bounds=[
            WindowBoundOut(
                tag=b.get("tag", ""),
                title=b.get("title", ""),
                detail=b.get("detail"),
                source_label=b.get("source_label"),
            )
            for b in window.bounds
        ],
    )


def option_to_out(option: PlanItemOption) -> PlanItemOptionOut:
    return PlanItemOptionOut(
        id=option.option_id,
        state=option.state,
        display_name=option.display_name,
        display_summary=option.display_summary,
        reason=option.reason,
        distance_minutes=option.distance_minutes,
        duration_minutes=option.duration_minutes,
        matched_preferences=option.matched_preferences,
        rejection_reason=option.rejection_reason,
    )


def reservation_to_out(reservation: Reservation) -> ReservationOut:
    return ReservationOut(
        id=reservation.reservation_id,
        status=reservation.status,
        provider=reservation.provider,
        confirmation_code=reservation.confirmation_code,
        reserved_for=reservation.slot_at,
        external_url=reservation.external_url,
    )


def plan_item_to_out(item: PlanItem) -> PlanItemOut:
    # The rendered title is the selected option's name; a freshly skipped or
    # still-deciding item falls back to its best-ranked candidate so the
    # timeline never shows a blank card. options is ordered by rank.
    selected = next(
        (o for o in item.options if o.state == OptionState.selected), None
    )
    face = selected or next(iter(item.options), None)
    return PlanItemOut(
        id=item.item_id,
        kind=item.kind,
        status=item.status,
        title=face.display_name if face else item.kind.value.capitalize(),
        starts_at=item.scheduled_start,
        ends_at=item.scheduled_end,
        window_id=item.window_id,
        # Every caller reaches items through a loader that eager-loads this;
        # under asyncio a lazy load here would raise, not silently query.
        window=window_to_out(item.window) if item.window else None,
        needs_reservation=item.needs_reservation,
        why=list(face.matched_preferences) if face else [],
        selected_option=option_to_out(selected) if selected else None,
        options=[
            option_to_out(o) for o in item.options if o.state != OptionState.rejected
        ],
        # Eager-loaded like window and ordered newest-first by the relationship.
        reservation=(
            reservation_to_out(item.reservations[0]) if item.reservations else None
        ),
        updated_at=item.updated_at,
    )


def plan_to_out(plan: Plan) -> PlanOut:
    # Skipped and removed items stay in the payload: the review flow has to be
    # able to show what was declined, and the row count is the plan's own.
    #
    # plans has no updated_at column, so the contract's field is the newest
    # thing under the plan. Concurrency tokens are per item, never this one.
    return PlanOut(
        id=plan.plan_id,
        trip_id=plan.trip_id,
        version=plan.version,
        status=plan.status,
        headline=plan.headline or "",
        provenance_summary=plan.provenance_summary,
        items=[plan_item_to_out(i) for i in plan.items],
        updated_at=max(
            [i.updated_at for i in plan.items] + [plan.created_at], default=plan.created_at
        ),
    )


# Real trust indicators, server-derived (contract: Trip.state_line).
_STATE_LINES: dict[TripState, str] = {
    TripState.detected: "Found in your calendar",
    TripState.confirmed: "Confirmed - will start preparing closer to the trip",
    TripState.upcoming: "Upcoming - watching your schedule",
    TripState.preparing: "Preparing - building your plan",
    TripState.active: "Active - watching your schedule",
    TripState.completed: "Completed",
    TripState.archived: "Archived",
    TripState.dismissed: "Dismissed",
}

# trip_evidence.source_label is display text ('Calendar', 'Email'); the
# contract wants the source_kind enum.
_SOURCE_LABEL_TO_KIND: dict[str, SourceKind] = {
    "calendar": SourceKind.google_calendar,
    "email": SourceKind.gmail,
    "apple calendar": SourceKind.apple_calendar,
}


def evidence_to_out(row: TripEvidence) -> TripEvidenceOut:
    source = _SOURCE_LABEL_TO_KIND.get(
        row.source_label.lower(), SourceKind.manual_import
    )
    return TripEvidenceOut(
        source=source, summary=row.summary, detail=row.detail, kind=row.kind
    )


def trip_to_out(trip: Trip, progress: TripProgress) -> TripOut:
    destination_name = trip.destination_city
    if trip.destination_region:
        destination_name = f"{trip.destination_city}, {trip.destination_region}"
    return TripOut(
        id=trip.trip_id,
        state=trip.state,
        origin=trip.origin,
        destination_name=destination_name,
        label=trip.label,
        timezone=trip.timezone,
        starts_on=trip.start_date,
        ends_on=trip.end_date,
        # Stored as float32 (REAL); round away the widening noise.
        detection_confidence=(
            round(trip.detection_confidence, 4)
            if trip.detection_confidence is not None
            else None
        ),
        evidence=[evidence_to_out(e) for e in trip.evidence],
        state_line=_STATE_LINES[trip.state],
        plan_progress=progress.plan_progress,
        needs_you_count=progress.needs_you_count,
        needs_you_kind=progress.needs_you_kind,
        updated_at=trip.updated_at,
    )

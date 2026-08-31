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
    ActionStatus,
    ActionType,
    AuthProvider,
    ConnectedSource,
    ItemKind,
    ItemStatus,
    OptionState,
    PendingAction,
    PlaceKind,
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
from app.services.places.matching import RankedPlace


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
    evidence: list[TripEvidenceOut]
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
    # No default here or below: a default is what makes Pydantic declare the
    # field optional, and the contract requires it. Every caller passes it.
    bounds: list[WindowBoundOut]


class PlanItemOptionOut(BaseModel):
    id: uuid.UUID
    state: OptionState
    display_name: str
    display_summary: str | None = None
    reason: str | None = None
    distance_minutes: int | None = None
    duration_minutes: int | None = None
    matched_preferences: list[str]
    rejection_reason: str | None = None


class ReservationOut(BaseModel):
    """A booking attempted for an item.

    `failure_reason` was withheld while nothing could be done about a refusal.
    Retrying is now a second action against the same item, so the reason is
    what the user acts on, and a booking that says only "refused" makes the
    retry a guess.
    """

    id: uuid.UUID
    status: ReservationStatus
    provider: ReservationProvider
    # Present iff status = confirmed; the database enforces it (reservations_check).
    confirmation_code: str | None = None
    reserved_for: datetime | None = None
    # Not null in the database, so no default: the confirmation line reads
    # "Party of 2 - Confirmation #4F21B" and only ever had half its facts.
    party_size: int
    failure_reason: str | None = None
    # Where to book it yourself: the whole answer for a place we cannot book,
    # and the honest fallback when a provider declines.
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
    needs_reservation: bool
    why: list[str]
    selected_option: PlanItemOptionOut | None = None
    # Selected + alternatives, by rank. Rejected ones are reachable only through
    # provenance, so a card cannot offer a choice that would erase its reason.
    options: list[PlanItemOptionOut]
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
    items: list[PlanItemOut]
    updated_at: datetime


class ProvenanceOut(BaseModel):
    """"How I got here": the opening, and every candidate considered for it."""

    item_id: uuid.UUID
    window: WellnessWindowOut | None = None
    considered: list[PlanItemOptionOut]


class TodayViewOut(BaseModel):
    trip_id: uuid.UUID
    day_label: str
    state_word: str
    state_detail: str | None = None
    timezone: str
    window: WellnessWindowOut | None = None
    next_up: list[PlanItemOut]


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
    # Which kinds this build can actually put through an OAuth handshake, so the
    # client can offer Connect for a kind the user has no row for yet.
    connectable: list[SourceKind]


class SyncOut(BaseModel):
    """What one sync run did. Counts rather than a bare ok, because "nothing
    changed" and "nothing was returned" are different answers and only one of
    them is a problem."""

    created: int
    updated: int
    unchanged: int
    last_synced_at: datetime


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
        party_size=reservation.party_size,
        failure_reason=reservation.failure_reason,
        external_url=reservation.external_url,
    )


def item_face(item: PlanItem) -> PlanItemOption | None:
    """The option an item is shown as: the selected one, else its best-ranked
    candidate so a still-deciding item never renders blank. options is ordered
    by rank."""
    selected = next(
        (o for o in item.options if o.state == OptionState.selected), None
    )
    return selected or next(iter(item.options), None)


def item_title(item: PlanItem) -> str:
    """What this item is called. Derived, because plan_items has no title
    column: the name belongs to the option, and the option can be swapped."""
    face = item_face(item)
    return face.display_name if face else item.kind.value.capitalize()


def plan_item_to_out(item: PlanItem) -> PlanItemOut:
    selected = next(
        (o for o in item.options if o.state == OptionState.selected), None
    )
    face = item_face(item)
    return PlanItemOut(
        id=item.item_id,
        kind=item.kind,
        status=item.status,
        title=item_title(item),
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


# --- Actions (pending_actions) -------------------------------------------


class ActionCreateIn(BaseModel):
    """Propose an action. What it will do is assembled server-side.

    The client names the act and the item, not the place: letting a request
    carry its own place and time would make the endpoint a way to book
    anything at all, rather than a way to book the plan the user is looking at.
    `payload` is the small set of choices that are genuinely the user's.
    """

    action_type: ActionType
    trip_id: uuid.UUID
    plan_item_id: uuid.UUID | None = None
    payload: dict = Field(default_factory=dict)


class ActionFailureOut(BaseModel):
    """Why an action did not complete, in terms the user can act on.

    `alternatives` is in the contract and not here: suggesting other places
    needs the places cache, which is Slice 6. Serving an empty list would say
    "we looked and found nothing", which is not what happened.
    """

    code: str
    message: str
    # "Book directly" - the honest offer when we could not book it for them.
    external_url: str | None = None


class PendingActionOut(BaseModel):
    id: uuid.UUID
    action_type: ActionType
    status: ActionStatus
    trip_id: uuid.UUID
    plan_item_id: uuid.UUID | None = None
    # What / when / where for the confirm sheet, assembled here so the sheet
    # shows what will actually be sent rather than re-deriving it and drifting.
    summary: dict | None = None
    failure: ActionFailureOut | None = None
    # The booking this action produced, once there is one to show.
    reservation: ReservationOut | None = None
    updated_at: datetime


def action_updated_at(action: PendingAction) -> datetime:
    """The row has no updated_at column; its three timestamps are the history.

    The newest of them is the value the approve token is checked against, so
    it has to move whenever the row does - which it does, because every state
    change here writes one of the three.
    """
    return max(
        t
        for t in (action.proposed_at, action.approved_at, action.executed_at)
        if t is not None
    )


def pending_action_to_out(
    action: PendingAction, reservation: Reservation | None = None
) -> PendingActionOut:
    result = action.execution_result or {}
    failure = result.get("failure")
    return PendingActionOut(
        id=action.action_id,
        action_type=action.action_type,
        status=action.status,
        trip_id=action.trip_id,
        plan_item_id=action.subject_item_id,
        summary=(action.proposed_payload or {}).get("summary"),
        failure=ActionFailureOut(**failure) if failure else None,
        reservation=reservation_to_out(reservation) if reservation else None,
        updated_at=action_updated_at(action),
    )


class ExplorePlaceOut(BaseModel):
    """One card and one pin: the list and the map read the same row.

    The first four derived fields are computed per request against this user's
    preferences and this trip's anchor, so two users looking at the same cached
    place see different reasons for it.
    """

    id: uuid.UUID
    kind: PlaceKind
    name: str
    summary: str | None = None
    address: str | None = None
    # Null together. A cached place without a point still earns a card; it just
    # cannot be pinned, and the map must not invent a location for it.
    lat: float | None = None
    lng: float | None = None
    price_level: int | None = None
    day_pass_cents: int | None = None
    # Absent means the provider never told us; `[]` means it has none. The
    # default is load-bearing rather than dead: `ApiRoute` omits None, so
    # without it the schema would declare a field the response drops.
    amenities: list[str] | None = None
    photo_url: str | None = None
    reservable_via: ReservationProvider | None = None
    matched_preferences: list[str]
    # What could not be judged about this place, phrased for the user. Always
    # present, usually empty. Read it next to `matched_preferences`: two chips
    # out of four preferences means something different when the other two were
    # unanswerable rather than unmet.
    unknown_notes: list[str]
    # Why this sits outside what the user said, rather than dropping it. A
    # candidate that vanishes silently cannot be argued with.
    over_budget_reason: str | None = None
    # Measured; the minutes are a walking-pace estimate over a straight line.
    distance_meters: int | None = None
    walk_minutes: int | None = None


class ExploreAnchorOut(BaseModel):
    """Where the map opens and what distances are measured from."""

    name: str
    # The hotel when the trip has one, else the destination centre.
    is_hotel: bool
    lat: float | None = None
    lng: float | None = None


class ExploreKindOut(BaseModel):
    """A category chip. The count is over the whole radius, not the filter, so
    switching chips never changes the other chips' numbers."""

    kind: PlaceKind
    count: int


class ExploreOut(BaseModel):
    trip_id: uuid.UUID
    # Absent when the trip has neither hotel nor destination coordinates: the
    # cards still rank, and every distance is null.
    anchor: ExploreAnchorOut | None = None
    radius_m: int
    kinds: list[ExploreKindOut]
    places: list[ExplorePlaceOut]


def explore_place_to_out(ranked: RankedPlace) -> ExplorePlaceOut:
    place = ranked.place
    return ExplorePlaceOut(
        id=place.place_id,
        kind=place.kind,
        name=place.name,
        summary=place.summary,
        address=place.address,
        lat=place.lat,
        lng=place.lng,
        price_level=place.price_level,
        day_pass_cents=place.day_pass_cents,
        amenities=None if place.amenities is None else list(place.amenities),
        photo_url=place.photo_url,
        reservable_via=place.reservable_via,
        matched_preferences=ranked.matched_preferences,
        unknown_notes=ranked.unknown_notes,
        over_budget_reason=ranked.over_budget_reason,
        distance_meters=ranked.distance_meters,
        walk_minutes=ranked.walk_minutes,
    )


class ResolvedLocationOut(BaseModel):
    """Free text resolved to a point. `query` is echoed so a client that fired
    several lookups can tell the answers apart."""

    query: str
    name: str
    lat: float
    lng: float
    timezone: str | None = None

"""Pydantic schemas for the /api/v1 surface.

These mirror docs/openapi.yaml, not the tables (ADR-001 point 6): the contract
carries derived fields (destination_name, needs_you_count, state_line) that no
table stores, so mapping from models is explicit, never automatic.
"""

import enum
import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, model_validator

from app.db.models import (
    AuthProvider,
    ItemKind,
    ItemStatus,
    OptionState,
    PlanItem,
    PlanItemOption,
    Trip,
    TripEvidence,
    TripOrigin,
    TripState,
    WellnessWindow,
    WindowStatus,
)


class SourceKind(enum.StrEnum):
    google_calendar = "google_calendar"
    gmail = "gmail"
    apple_calendar = "apple_calendar"
    manual_import = "manual_import"


class EmailCodeRequest(BaseModel):
    email: EmailStr


class EmailCodeVerify(BaseModel):
    email: EmailStr
    code: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None = None
    auth_provider: AuthProvider
    created_at: datetime

    @classmethod
    def from_model(cls, user) -> "UserOut":
        return cls(
            id=user.user_id,
            email=user.email,
            display_name=user.display_name,
            auth_provider=user.auth_provider,
            created_at=user.created_at,
        )


class TripCreateIn(BaseModel):
    destination_name: str
    starts_on: date
    ends_on: date
    lodging_name: str | None = None

    @model_validator(mode="after")
    def _dates_ordered(self) -> "TripCreateIn":
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on must not be before starts_on")
        return self


class TripEvidenceOut(BaseModel):
    source: SourceKind
    summary: str
    kind: str


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
    needs_you_count: int
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


class PlanItemOut(BaseModel):
    id: uuid.UUID
    kind: ItemKind
    status: ItemStatus
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    window_id: uuid.UUID | None = None
    why: list[str] = []
    selected_option: PlanItemOptionOut | None = None
    updated_at: datetime


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
        why=list(face.matched_preferences) if face else [],
        selected_option=option_to_out(selected) if selected else None,
        updated_at=item.updated_at,
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
    return TripEvidenceOut(source=source, summary=row.summary, kind=row.kind)


def trip_to_out(trip: Trip, needs_you_count: int) -> TripOut:
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
        needs_you_count=needs_you_count,
        updated_at=trip.updated_at,
    )

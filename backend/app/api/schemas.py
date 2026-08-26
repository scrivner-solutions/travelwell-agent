"""Pydantic schemas for the /api/v1 surface.

These mirror docs/openapi.yaml, not the tables (ADR-001 point 6): the contract
carries derived fields (destination_name, needs_you_count, state_line) that no
table stores, so mapping from models is explicit, never automatic.
"""

import enum
import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, model_validator

from app.db.models import AuthProvider, Trip, TripEvidence, TripOrigin, TripState


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


class TripOut(BaseModel):
    id: uuid.UUID
    state: TripState
    origin: TripOrigin
    destination_name: str
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
    kind = _SOURCE_LABEL_TO_KIND.get(row.source_label.lower(), SourceKind.manual_import)
    return TripEvidenceOut(source=kind, summary=row.summary)


def trip_to_out(trip: Trip, needs_you_count: int) -> TripOut:
    destination_name = trip.destination_city
    if trip.destination_region:
        destination_name = f"{trip.destination_city}, {trip.destination_region}"
    return TripOut(
        id=trip.trip_id,
        state=trip.state,
        origin=trip.origin,
        destination_name=destination_name,
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

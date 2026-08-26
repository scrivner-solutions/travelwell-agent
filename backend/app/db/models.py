"""SQLAlchemy 2.0 typed models for the walking-skeleton tables.

Storage layer only; API shapes live in app/api/schemas.py (ADR-001 point 6).
All DDL, including the Postgres enum types, is created by migrations, never by
metadata.create_all: every pg enum here is declared with create_type=False.

Covered so far: users, trips, trip_evidence. The remaining tables exist in the
database via the initial migration and are reached with textual SQL until their
vertical slice lands; migrations/env.py limits drift comparison to the tables
modeled here, so partial coverage does not trip `alembic check`.
"""

import enum
import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AuthProvider(enum.StrEnum):
    google = "google"
    apple = "apple"
    email = "email"


class TripState(enum.StrEnum):
    detected = "detected"
    confirmed = "confirmed"
    upcoming = "upcoming"
    preparing = "preparing"
    active = "active"
    completed = "completed"
    archived = "archived"
    dismissed = "dismissed"


class TripOrigin(enum.StrEnum):
    calendar_detection = "calendar_detection"
    manual = "manual"
    import_ = "import"


def _pg_enum(py_enum: type[enum.StrEnum], name: str) -> pg.ENUM:
    return pg.ENUM(
        py_enum,
        name=name,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(pg.CITEXT(), unique=True)
    display_name: Mapped[str | None]
    auth_provider: Mapped[AuthProvider] = mapped_column(
        _pg_enum(AuthProvider, "auth_provider")
    )
    home_timezone: Mapped[str] = mapped_column(server_default=sa.text("'UTC'::text"))
    created_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))

    trips: Mapped[list["Trip"]] = relationship(
        back_populates="user", passive_deletes=True
    )


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        sa.Index(
            "trips_activation_idx",
            "state",
            "activation_at",
            postgresql_where=sa.text("state in ('confirmed', 'upcoming')"),
        ),
        sa.Index("trips_user_state_idx", "user_id", "state"),
        # Name matches what Postgres auto-generated for the unnamed CHECK in
        # schema.sql; alembic's by-name comparison needs the exact match.
        sa.CheckConstraint("end_date >= start_date", name="trips_check"),
    )

    trip_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.user_id", ondelete="CASCADE")
    )
    destination_city: Mapped[str]
    destination_region: Mapped[str | None]
    destination_lat: Mapped[float | None] = mapped_column(sa.Double)
    destination_lng: Mapped[float | None] = mapped_column(sa.Double)
    timezone: Mapped[str]
    start_date: Mapped[date]
    end_date: Mapped[date]
    label: Mapped[str | None]
    hotel_name: Mapped[str | None]
    hotel_address: Mapped[str | None]
    hotel_lat: Mapped[float | None] = mapped_column(sa.Double)
    hotel_lng: Mapped[float | None] = mapped_column(sa.Double)
    # FK to places lives in the database; places is not modeled yet, so the
    # constraint is filtered out of drift comparison in migrations/env.py.
    hotel_place_id: Mapped[uuid.UUID | None]
    state: Mapped[TripState] = mapped_column(
        _pg_enum(TripState, "trip_state"),
        server_default=sa.text("'detected'::trip_state"),
    )
    origin: Mapped[TripOrigin] = mapped_column(_pg_enum(TripOrigin, "trip_origin"))
    detection_confidence: Mapped[float | None] = mapped_column(sa.REAL)
    activation_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))

    user: Mapped[User] = relationship(back_populates="trips")
    evidence: Mapped[list["TripEvidence"]] = relationship(
        back_populates="trip",
        order_by="TripEvidence.detected_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TripEvidence(Base):
    __tablename__ = "trip_evidence"
    __table_args__ = (sa.Index("trip_evidence_trip_idx", "trip_id"),)

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    kind: Mapped[str]
    source_label: Mapped[str]
    summary: Mapped[str]
    source_ref: Mapped[str | None]
    detected_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))

    trip: Mapped[Trip] = relationship(back_populates="evidence")

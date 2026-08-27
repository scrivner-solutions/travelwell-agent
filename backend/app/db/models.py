"""SQLAlchemy 2.0 typed models for the walking-skeleton tables.

Storage layer only; API shapes live in app/api/schemas.py (ADR-001 point 6).
All DDL, including the Postgres enum types, is created by migrations, never by
metadata.create_all: every pg enum here is declared with create_type=False.

Covered so far: users, trips, trip_evidence, wellness_windows, plans,
plan_items, plan_item_options. The remaining tables exist in the database via
the initial migration and are reached with textual SQL until their vertical
slice lands; migrations/env.py limits drift comparison to the tables modeled
here, so partial coverage does not trip `alembic check`.
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


class WindowStatus(enum.StrEnum):
    open = "open"
    filled = "filled"
    expired = "expired"
    superseded = "superseded"


class PlanStatus(enum.StrEnum):
    draft = "draft"
    proposed = "proposed"
    partially_accepted = "partially_accepted"
    accepted = "accepted"
    superseded = "superseded"


class ItemStatus(enum.StrEnum):
    suggested = "suggested"
    awaiting_user = "awaiting_user"
    planned = "planned"
    confirmed = "confirmed"
    working = "working"
    changed = "changed"
    skipped = "skipped"
    removed = "removed"


class ItemKind(enum.StrEnum):
    activity = "activity"
    meal = "meal"


class OptionState(enum.StrEnum):
    selected = "selected"
    alternative = "alternative"
    rejected = "rejected"


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


class WellnessWindow(Base):
    __tablename__ = "wellness_windows"
    __table_args__ = (
        sa.Index("wellness_windows_trip_idx", "trip_id", "local_date"),
        sa.CheckConstraint("ends_at > starts_at", name="wellness_windows_check"),
    )

    window_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    local_date: Mapped[date]
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    label: Mapped[str]
    gap_explanation: Mapped[str | None]
    # Display-shaped provenance rows; soft references by design (schema.sql):
    # bounds must survive the bounding event being deleted.
    bounds: Mapped[list[dict]] = mapped_column(
        pg.JSONB(), server_default=sa.text("'[]'::jsonb")
    )
    status: Mapped[WindowStatus] = mapped_column(
        _pg_enum(WindowStatus, "window_status"),
        server_default=sa.text("'open'::window_status"),
    )
    computed_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (
        sa.Index("plans_trip_idx", "trip_id", "status"),
        sa.UniqueConstraint("trip_id", "version", name="plans_trip_id_version_key"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    version: Mapped[int]
    status: Mapped[PlanStatus] = mapped_column(
        _pg_enum(PlanStatus, "plan_status"),
        server_default=sa.text("'proposed'::plan_status"),
    )
    headline: Mapped[str | None]
    provenance_summary: Mapped[str | None]
    # FK to agent_runs lives in the database; agent_runs is not modeled yet,
    # so the constraint is filtered out of drift comparison (env.py).
    generated_by_run_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))

    items: Mapped[list["PlanItem"]] = relationship(
        back_populates="plan",
        order_by="PlanItem.scheduled_start",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PlanItem(Base):
    __tablename__ = "plan_items"
    __table_args__ = (
        sa.Index("plan_items_trip_status_idx", "trip_id", "status"),
        sa.Index("plan_items_window_idx", "window_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("plans.plan_id", ondelete="CASCADE")
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    window_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("wellness_windows.window_id")
    )
    kind: Mapped[ItemKind] = mapped_column(_pg_enum(ItemKind, "item_kind"))
    status: Mapped[ItemStatus] = mapped_column(
        _pg_enum(ItemStatus, "item_status"),
        server_default=sa.text("'suggested'::item_status"),
    )
    scheduled_start: Mapped[datetime]
    scheduled_end: Mapped[datetime | None]
    needs_reservation: Mapped[bool] = mapped_column(server_default=sa.text("false"))
    calendar_event_ref: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))

    plan: Mapped[Plan] = relationship(back_populates="items")
    window: Mapped[WellnessWindow | None] = relationship()
    options: Mapped[list["PlanItemOption"]] = relationship(
        back_populates="item",
        order_by="PlanItemOption.rank",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PlanItemOption(Base):
    __tablename__ = "plan_item_options"
    __table_args__ = (
        sa.Index("plan_item_options_item_idx", "item_id", "state", "rank"),
        sa.Index(
            "plan_item_options_selected_uq",
            "item_id",
            unique=True,
            postgresql_where=sa.text("state = 'selected'::option_state"),
        ),
        sa.CheckConstraint(
            "(state = 'rejected'::option_state) = (rejection_reason is not null)",
            name="plan_item_options_check",
        ),
    )

    option_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("plan_items.item_id", ondelete="CASCADE")
    )
    # FK to places lives in the database; places is not modeled yet (env.py).
    place_id: Mapped[uuid.UUID | None]
    state: Mapped[OptionState] = mapped_column(_pg_enum(OptionState, "option_state"))
    rank: Mapped[int] = mapped_column(sa.SmallInteger, server_default=sa.text("0"))
    display_name: Mapped[str]
    display_summary: Mapped[str | None]
    reason: Mapped[str | None]
    rejection_reason: Mapped[str | None]
    distance_minutes: Mapped[int | None] = mapped_column(sa.SmallInteger)
    duration_minutes: Mapped[int | None] = mapped_column(sa.SmallInteger)
    matched_preferences: Mapped[list[str]] = mapped_column(
        pg.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]")
    )

    item: Mapped[PlanItem] = relationship(back_populates="options")


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
    # Caption under the summary; last to match migration 0002's ADD COLUMN.
    detail: Mapped[str | None]

    trip: Mapped[Trip] = relationship(back_populates="evidence")

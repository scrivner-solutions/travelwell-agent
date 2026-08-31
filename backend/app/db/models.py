"""SQLAlchemy 2.0 typed models for the TravelWell schema.

Storage layer only; API shapes live in app/api/schemas.py (ADR-001 point 6).
Every table in docs/schema.sql is modeled here, and that file is generated
from this metadata by scripts/dump_schema.py.

All DDL is applied by migrations, never by metadata.create_all: the pg enums
keep create_type=False so op.create_table cannot re-create a type the database
already has. The dump script emits the types explicitly instead.
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


class SourceKind(enum.StrEnum):
    google_calendar = "google_calendar"
    gmail = "gmail"
    apple_calendar = "apple_calendar"
    manual_import = "manual_import"


class SourceStatus(enum.StrEnum):
    connected = "connected"
    error = "error"
    revoked = "revoked"


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


class PlaceKind(enum.StrEnum):
    workout = "workout"
    food = "food"
    outdoor = "outdoor"
    recovery = "recovery"
    lodging = "lodging"


class AreaFillOutcome(enum.StrEnum):
    """What happened on one *attempted* fetch of an area.

    Not a copy of the exception hierarchy for its own sake: the three values
    earn different retry windows. `ok` reached the provider, and zero results
    means the area is genuinely thin. `error` is an outage and must not consume
    the freshness window a good fetch earns. `unavailable` means we never got as
    far as a request.
    """

    ok = "ok"
    error = "error"
    unavailable = "unavailable"


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


class ReservationProvider(enum.StrEnum):
    travelwell = "travelwell"
    opentable = "opentable"
    external_link = "external_link"


class ReservationStatus(enum.StrEnum):
    pending = "pending"
    holding = "holding"
    confirmed = "confirmed"
    failed = "failed"
    canceled = "canceled"


class ActionType(enum.StrEnum):
    make_reservation = "make_reservation"
    cancel_reservation = "cancel_reservation"
    create_calendar_event = "create_calendar_event"
    update_calendar_event = "update_calendar_event"
    delete_calendar_event = "delete_calendar_event"
    send_invite = "send_invite"


class ActionStatus(enum.StrEnum):
    proposed = "proposed"
    approved = "approved"
    executing = "executing"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class EventKind(enum.StrEnum):
    scheduled_activation = "scheduled_activation"
    scheduled_daily = "scheduled_daily"
    user_text = "user_text"
    user_voice = "user_voice"
    ui_action = "ui_action"
    calendar_changed = "calendar_changed"
    trip_changed = "trip_changed"
    reservation_changed = "reservation_changed"
    external_context = "external_context"


class EventDisposition(enum.StrEnum):
    pending = "pending"
    dropped_no_trip = "dropped_no_trip"
    dropped_immaterial = "dropped_immaterial"
    accepted = "accepted"


class RunKind(enum.StrEnum):
    pretrip_plan = "pretrip_plan"
    replan_conflict = "replan_conflict"
    user_request = "user_request"
    reservation_flow = "reservation_flow"
    daily_checkin = "daily_checkin"
    trip_detection = "trip_detection"


class RunStatus(enum.StrEnum):
    running = "running"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class NotificationStatus(enum.StrEnum):
    pending = "pending"
    sent = "sent"
    opened = "opened"
    dismissed = "dismissed"


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
    home_timezone: Mapped[str] = mapped_column(
        server_default=sa.text("'UTC'::text"), doc="IANA name"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))

    trips: Mapped[list["Trip"]] = relationship(
        back_populates="user", passive_deletes=True
    )


class UserPreferences(Base):
    """One row per user. Drives Explore filters, plan ranking, and the "Matched
    from your profile" provenance chips.
    """

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    dietary: Mapped[list[str]] = mapped_column(
        pg.ARRAY(sa.Text()),
        server_default=sa.text("'{}'::text[]"),
        doc="{'vegetarian'}",
    )
    activities: Mapped[list[str]] = mapped_column(
        pg.ARRAY(sa.Text()),
        server_default=sa.text("'{}'::text[]"),
        doc="{'swim','running'}",
    )
    amenities: Mapped[list[str]] = mapped_column(
        pg.ARRAY(sa.Text()),
        server_default=sa.text("'{}'::text[]"),
        doc="{'pool','treadmill'}",
    )
    memberships: Mapped[list[str]] = mapped_column(
        pg.ARRAY(sa.Text()),
        server_default=sa.text("'{}'::text[]"),
        doc="{'ymca_reciprocity','hotel_gym'}",
    )
    price_level_max: Mapped[int | None] = mapped_column(
        sa.SmallInteger, doc='2 = "$$ or less"'
    )
    day_pass_budget_cents: Mapped[int | None] = mapped_column(doc="$20 cap in the demo")
    session_min_minutes: Mapped[int | None] = mapped_column(
        sa.SmallInteger, doc="45-90 min preference"
    )
    session_max_minutes: Mapped[int | None] = mapped_column(sa.SmallInteger)
    allow_calendar_write: Mapped[bool] = mapped_column(server_default=sa.text("false"))
    allow_auto_book: Mapped[bool] = mapped_column(server_default=sa.text("false"))
    watch_schedule: Mapped[bool] = mapped_column(server_default=sa.text("true"))
    updated_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))
    # Last to match migration 0003's ADD COLUMN.
    preferred_times: Mapped[list[str]] = mapped_column(
        pg.ARRAY(sa.Text()),
        server_default=sa.text("'{}'::text[]"),
        doc="{'mornings'}",
    )
    # Last to match migration 0030's ADD COLUMN. Keep new columns below this
    # line, not grouped with related ones - ADD COLUMN appends physically and
    # `check_schema_drift.sh` diffs pg_dump, which is order-sensitive.
    target_sessions: Mapped[int | None] = mapped_column(
        sa.SmallInteger,
        doc="how many sessions the traveler wants across a trip, not per day",
    )


class LoginCode(Base):
    """One live email sign-in code per address; only the code's HMAC is stored.

    No FK to users: a code is issued before the account may exist.
    """

    __tablename__ = "login_codes"

    email: Mapped[str] = mapped_column(pg.CITEXT(), primary_key=True)
    code_hmac: Mapped[str]
    expires_at: Mapped[datetime]
    attempts_left: Mapped[int] = mapped_column(sa.SmallInteger)
    created_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))


class ConnectedSource(Base):
    """OAuth grants. The token itself is held by the token store; only its
    reference is here, so the storage backend can change without a migration."""

    __tablename__ = "connected_sources"
    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "kind", name="connected_sources_user_id_kind_key"
        ),
        # A grant with no token reference cannot be acted on, so "connected"
        # would be a claim nothing can honour.
        sa.CheckConstraint(
            "status <> 'connected'::source_status or secret_ref is not null",
            name="connected_sources_check",
        ),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.user_id", ondelete="CASCADE")
    )
    kind: Mapped[SourceKind] = mapped_column(_pg_enum(SourceKind, "source_kind"))
    # No server default: none of the three members describes a row nobody has
    # acted on, and NOT NULL then names the column a caller forgot to set.
    status: Mapped[SourceStatus] = mapped_column(_pg_enum(SourceStatus, "source_status"))
    scopes: Mapped[list[str]] = mapped_column(
        pg.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]")
    )
    secret_ref: Mapped[str | None] = mapped_column(
        doc="Opaque token-store reference; only the store that minted it may parse it"
    )
    last_synced_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))



class StoredSecret(Base):
    """Long-lived secrets, encrypted at rest, addressed only by reference.

    A separate table rather than a column on `connected_sources` because the
    reference has to stay meaningful when the backend is not this table: a
    caller holding `secret_ref` must not care which store answers it.
    """

    __tablename__ = "stored_secrets"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "kind", name="stored_secrets_user_id_kind_key"),
    )

    secret_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.user_id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(doc="What the secret is for, e.g. google_refresh_token")
    nonce: Mapped[bytes] = mapped_column(
        sa.LargeBinary, doc="AES-GCM nonce, freshly generated on every write"
    )
    ciphertext: Mapped[bytes] = mapped_column(sa.LargeBinary)
    created_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))


class Trip(Base):
    """Identity: one contiguous period of displacement from home. The
    destination_*/timezone/hotel_* columns are the single stay, denormalized;
    the one-stay cap is a temporary restriction, not the definition. Lifting
    it adds a trip_stays child table, not a redefinition.
    """

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
    timezone: Mapped[str] = mapped_column(doc="IANA, e.g. America/Chicago")
    start_date: Mapped[date]
    end_date: Mapped[date]
    label: Mapped[str | None] = mapped_column(doc="'Conference trip'")
    hotel_name: Mapped[str | None] = mapped_column(doc="'The Gwen'")
    hotel_address: Mapped[str | None]
    hotel_lat: Mapped[float | None] = mapped_column(sa.Double)
    hotel_lng: Mapped[float | None] = mapped_column(sa.Double)
    # Named because schema.sql adds it by a separate ALTER, not inline.
    hotel_place_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("places.place_id", name="trips_hotel_place_fk")
    )
    state: Mapped[TripState] = mapped_column(
        _pg_enum(TripState, "trip_state"),
        server_default=sa.text("'detected'::trip_state"),
    )
    origin: Mapped[TripOrigin] = mapped_column(_pg_enum(TripOrigin, "trip_origin"))
    detection_confidence: Mapped[float | None] = mapped_column(
        sa.REAL, doc="calendar-detected trips"
    )
    activation_at: Mapped[datetime | None] = mapped_column(
        doc="T-7d wake-up; scheduler scans this"
    )
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
    """A free interval the agent found ("5:30 PM · 90 minutes free")."""

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
    local_date: Mapped[date] = mapped_column(doc="trip-timezone day")
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    label: Mapped[str] = mapped_column(doc="'90 minutes free'")
    gap_explanation: Mapped[str | None] = mapped_column(
        doc="'Between your workshop and dinner…'"
    )
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
    """A generated plan version. Re-planning creates a new version and marks the
    old one superseded - history is kept for the audit trail.
    """

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
    headline: Mapped[str | None] = mapped_column(
        doc="'Room for 3 workouts and a dinner'"
    )
    provenance_summary: Mapped[str | None] = mapped_column(
        doc="'From your calendar and hotel email'"
    )
    # Named because schema.sql adds it by a separate ALTER, not inline.
    generated_by_run_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("agent_runs.run_id", name="plans_run_fk")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))

    items: Mapped[list["PlanItem"]] = relationship(
        back_populates="plan",
        order_by="PlanItem.scheduled_start",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PlanItem(Base):
    """One recommendation slot: "YMCA at 5:30", "Beatrix at 7:30". The timeline
    screen = calendar_events UNION plan_items ordered by time.
    """

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
    # A list because the schema permits retries: no unique constraint on
    # reservations.item_id, so a failed hold can be followed by a second attempt.
    # Newest first, and the API surfaces only that one.
    reservations: Mapped[list["Reservation"]] = relationship(
        back_populates="item",
        order_by="Reservation.created_at.desc()",
        passive_deletes=True,
    )


class PlanItemOption(Base):
    """Every candidate the agent considered for a slot - selected, alternatives
    ("Other options" sheet), and rejected ones with the reason shown in "Also
    considered". Swapping = flipping option_state, no data loss.
    """

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
    place_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("places.place_id"))
    state: Mapped[OptionState] = mapped_column(_pg_enum(OptionState, "option_state"))
    rank: Mapped[int] = mapped_column(sa.SmallInteger, server_default=sa.text("0"))
    display_name: Mapped[str] = mapped_column(doc="denormalized for stable display")
    display_summary: Mapped[str | None] = mapped_column(
        doc="'Pool + treadmill · 75 min'"
    )
    reason: Mapped[str | None] = mapped_column(doc="'Fits your 90-minute opening'")
    rejection_reason: Mapped[str | None] = mapped_column(
        doc="'$$$, above the budget you set'"
    )
    distance_minutes: Mapped[int | None] = mapped_column(sa.SmallInteger)
    duration_minutes: Mapped[int | None] = mapped_column(sa.SmallInteger)
    matched_preferences: Mapped[list[str]] = mapped_column(
        pg.ARRAY(sa.Text()),
        server_default=sa.text("'{}'::text[]"),
        doc="{'swim','45-90 min'}",
    )

    item: Mapped[PlanItem] = relationship(back_populates="options")


class PendingAction(Base):
    """Every external side effect the app performs, durable and auditable.

    Nothing books, cancels or writes a calendar directly: a caller proposes,
    a user approves, and the executor claims the row and carries it out. That
    is why `proposed_payload` is what *will* be done rather than what was --
    the row is written before the effect exists, so a crash mid-execution
    leaves a claim to resume rather than an effect nobody recorded.
    """

    __tablename__ = "pending_actions"
    __table_args__ = (
        sa.Index(
            "pending_actions_status_idx",
            "status",
            postgresql_where=sa.text("status in ('proposed', 'approved', 'executing')"),
        ),
        sa.Index("pending_actions_trip_idx", "trip_id"),
        sa.CheckConstraint(
            "status not in ('completed') or (execution_result is not null)",
            name="pending_actions_check",
        ),
    )

    action_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.user_id", ondelete="CASCADE")
    )
    # Column is `type`; the attribute is not, because the contract and the rest
    # of the code say action_type and shadowing the builtin reads badly.
    action_type: Mapped[ActionType] = mapped_column(
        "type", _pg_enum(ActionType, "action_type")
    )
    status: Mapped[ActionStatus] = mapped_column(
        _pg_enum(ActionStatus, "action_status"),
        server_default=sa.text("'proposed'::action_status"),
    )
    approval_required: Mapped[bool] = mapped_column(server_default=sa.text("true"))
    subject_item_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("plan_items.item_id")
    )
    proposed_payload: Mapped[dict] = mapped_column(
        pg.JSONB, doc="what will be done, exactly"
    )
    # What the provider returned when the effect was submitted, and what we
    # re-read afterwards to confirm it. Two fields because "we sent it" and
    # "we checked it landed" are different claims, and only the second is
    # evidence.
    execution_result: Mapped[dict | None] = mapped_column(
        pg.JSONB, doc="what the tool reported"
    )
    verification: Mapped[dict | None] = mapped_column(
        pg.JSONB, doc="what we re-read to confirm"
    )
    # Unique across the whole table, so callers namespace it per user the way
    # the demo seed does; two users must not be able to collide or read across.
    idempotency_key: Mapped[str | None] = mapped_column(unique=True, doc="retry safety")
    proposed_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))
    approved_at: Mapped[datetime | None]
    executed_at: Mapped[datetime | None]

    trip: Mapped["Trip"] = relationship()


class Reservation(Base):
    """Reservation record - created by a completed make_reservation action, or in
    'failed' with failure_reason when the provider declines the hold (the
    "Beatrix declined the 7:30 hold" flow). Never 'confirmed' until the
    provider's confirmation is verified.
    """

    __tablename__ = "reservations"
    __table_args__ = (
        sa.Index("reservations_trip_idx", "trip_id", "status"),
        sa.CheckConstraint(
            "status <> 'confirmed'::reservation_status or confirmation_code is not null",
            name="reservations_check",
        ),
    )

    reservation_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    # Nullable and SET NULL: a reservation outlives the item it was made for, so
    # a cancellation still has something to report against.
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("plan_items.item_id", ondelete="SET NULL")
    )
    place_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("places.place_id"))
    provider: Mapped[ReservationProvider] = mapped_column(
        _pg_enum(ReservationProvider, "reservation_provider")
    )
    status: Mapped[ReservationStatus] = mapped_column(
        _pg_enum(ReservationStatus, "reservation_status"),
        server_default=sa.text("'pending'::reservation_status"),
    )
    slot_at: Mapped[datetime]
    party_size: Mapped[int] = mapped_column(
        sa.SmallInteger, server_default=sa.text("1")
    )
    confirmation_code: Mapped[str | None] = mapped_column(doc="'#4F21B'")
    failure_reason: Mapped[str | None]
    external_url: Mapped[str | None] = mapped_column(doc="OpenTable fallback link")
    created_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))

    item: Mapped[PlanItem | None] = relationship(back_populates="reservations")


class TripEvidence(Base):
    """ "Based on" list in trip detection: flight event, hotel email, conference
    events. Stores summaries + source refs, never raw email bodies.
    """

    __tablename__ = "trip_evidence"
    __table_args__ = (sa.Index("trip_evidence_trip_idx", "trip_id"),)

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(doc="'flight_event','hotel_email',...")
    source_label: Mapped[str] = mapped_column(doc="'Calendar', 'Email'")
    summary: Mapped[str] = mapped_column(doc="'UA 1142 · SFO to ORD'")
    source_ref: Mapped[str | None] = mapped_column(doc="external event/message id")
    detected_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))
    # Caption under the summary; last to match migration 0002's ADD COLUMN.
    detail: Mapped[str | None]

    trip: Mapped[Trip] = relationship(back_populates="evidence")


class CalendarEvent(Base):
    """Trip-relevant calendar cache: derived display fields, no raw payloads."""

    __tablename__ = "calendar_events"
    __table_args__ = (
        sa.UniqueConstraint(
            "source_id",
            "external_id",
            name="calendar_events_source_id_external_id_key",
        ),
        # Two readers, two orders. Detection filters by trip; the timeline
        # filters by owner and date overlap, because which trip an event
        # BELONGS to is a judgement and whether it CONSTRAINS the traveler is
        # arithmetic. Neither index replaces the other.
        sa.Index("calendar_events_trip_time_idx", "trip_id", "starts_at"),
        sa.Index("calendar_events_user_time_idx", "user_id", "starts_at"),
    )

    cal_event_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.user_id", ondelete="CASCADE")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("connected_sources.source_id", ondelete="CASCADE")
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    external_id: Mapped[str] = mapped_column(doc="provider event id")
    title: Mapped[str]
    location: Mapped[str | None]
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(
        server_default=sa.text("'confirmed'::text"), doc="provider status"
    )
    # Change detection on sync.
    content_hash: Mapped[str] = mapped_column(doc="change detection on sync")
    last_seen_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))
    # Declared last because migration 0011 adds it with ALTER TABLE ADD COLUMN,
    # which appends. docs/schema.sql is generated from this class and diffed
    # against the migrated database column-for-column, so declaration order
    # here is physical order there. `alembic check` cannot see this: it
    # compares presence and type, not position.
    busy: Mapped[bool | None] = mapped_column(
        doc="Does this block time? NULL = not yet classified, which is not 'free'"
    )


class Place(Base):
    """Venue cache; the provider stays authoritative and rows age out by TTL."""

    __tablename__ = "places"

    place_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    provider_ref: Mapped[str | None] = mapped_column(unique=True, doc="Google place_id")
    kind: Mapped[PlaceKind] = mapped_column(_pg_enum(PlaceKind, "place_kind"))
    name: Mapped[str]
    summary: Mapped[str | None] = mapped_column(doc="'Pool + treadmill'")
    address: Mapped[str | None]
    lat: Mapped[float | None] = mapped_column(sa.Double)
    lng: Mapped[float | None] = mapped_column(sa.Double)
    price_level: Mapped[int | None] = mapped_column(
        sa.SmallInteger, doc="$..$$$$ for food"
    )
    # Three values, same rule as `amenities`: a number is the price, 0 is free
    # or membership-included, NULL is unpriced by the provider. NULL must not
    # be read as "cheap" -- it is the value a budget filter cannot judge.
    day_pass_cents: Mapped[int | None] = mapped_column(doc="0 = free / membership")
    # NULL is a third value and is load-bearing: the provider never told us.
    # `{}` means we asked and the venue has none. Google supplies no amenities
    # field at all, so every row it writes is NULL rather than empty.
    amenities: Mapped[list[str] | None] = mapped_column(pg.ARRAY(sa.Text()))
    hours: Mapped[dict | None] = mapped_column(
        pg.JSONB, doc="per-weekday open/close minutes"
    )
    photo_url: Mapped[str | None]
    reservable_via: Mapped[ReservationProvider | None] = mapped_column(
        _pg_enum(ReservationProvider, "reservation_provider")
    )
    fetched_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))


class AreaFillRecord(Base):
    """One area, and the last attempt to fill it from the provider.

    `places.fetched_at` makes staleness a property of a ROW, which cannot answer
    the question that costs money: has anyone ever looked here? An area with no
    rows and an area that is genuinely empty are the same absence, so the cheap
    proxy "is there a fresh row near this point" refetches an empty
    neighbourhood on every planning run forever.

    Written only when a fetch was actually attempted. A declined fetch leaves no
    row, because a row here is a claim about the provider, not about us.
    """

    __tablename__ = "area_fills"

    area_fill_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    # Rounded coordinates, radius and kinds. Rounding is what makes two nearby
    # requests one area; see `area_key()` in the places layer, which owns the
    # format and is the only thing that may construct it.
    area_key: Mapped[str] = mapped_column(unique=True, doc="rounded lat/lng, radius, kinds")
    outcome: Mapped[AreaFillOutcome] = mapped_column(
        _pg_enum(AreaFillOutcome, "area_fill_outcome")
    )
    # Meaningful only when outcome is `ok`; a failed attempt found nothing
    # because it never asked, which is not the same as an empty area.
    result_count: Mapped[int] = mapped_column(sa.SmallInteger, server_default=sa.text("0"))
    fetched_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))


class BasemapArea(Base):
    """Street, water and park geometry for one area, cached as drawn.

    The Explore map is a real map or it is a diagram of dots, and the
    difference is this table. OpenStreetMap gives the geometry away, so unlike
    `area_fills` the ceiling here is politeness to a community server rather
    than money -- which is why there is no outcome enum: nothing bills, so a
    failed attempt costs only the retry.

    Geometry is stored in degrees, not pixels. The map's scale is
    content-dependent -- it changes the moment a category chip hides the
    furthest pin -- so a cached projection would be stale before the first tap.
    """

    __tablename__ = "basemap_areas"

    basemap_area_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    # Rounded centre and radius. `area_key()` in the basemap layer owns the
    # format and is the only thing that may construct one.
    area_key: Mapped[str] = mapped_column(unique=True, doc="rounded lat/lng and radius")
    # Each way is one flat [lat, lng, lat, lng, ...] run. Flat rather than
    # nested pairs because the payload is almost entirely numbers and the
    # nesting cost more bytes than it explained.
    roads_major: Mapped[list] = mapped_column(pg.JSONB, doc="motorway/trunk/primary")
    roads_minor: Mapped[list] = mapped_column(pg.JSONB, doc="secondary/tertiary")
    water: Mapped[list] = mapped_column(pg.JSONB, doc="closed rings")
    parks: Mapped[list] = mapped_column(pg.JSONB, doc="closed rings")
    # Only fetched for the closest buckets. At a 12.5 m pixel a footprint is a
    # three-pixel speck, and a city of them is a grey haze over the streets.
    buildings: Mapped[list] = mapped_column(pg.JSONB, doc="closed rings, close zooms only")
    # An area with no geometry is a real answer -- open sea, a sparse suburb --
    # so emptiness cannot be the signal to refetch. This timestamp is.
    fetched_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))


class AgentEvent(Base):
    """Trace root: every inbound trigger lands here before anything runs."""

    __tablename__ = "agent_events"
    __table_args__ = (
        # NULLs are distinct in Postgres, so producer-written events need no
        # exemption from this and every client retry lands on its own row.
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="agent_events_idempotency_uq"
        ),
        sa.Index("agent_events_trip_time_idx", "trip_id", sa.text("occurred_at DESC")),
        sa.Index(
            "agent_events_disposition_idx",
            "disposition",
            postgresql_where=sa.text("disposition = 'pending'::event_disposition"),
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.user_id", ondelete="CASCADE")
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    kind: Mapped[EventKind] = mapped_column(_pg_enum(EventKind, "event_kind"))
    payload: Mapped[dict] = mapped_column(
        pg.JSONB,
        server_default=sa.text("'{}'::jsonb"),
        doc="transcript, changed-event delta, …",
    )
    disposition: Mapped[EventDisposition] = mapped_column(
        _pg_enum(EventDisposition, "event_disposition"),
        server_default=sa.text("'pending'::event_disposition"),
    )
    occurred_at: Mapped[datetime]
    received_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))
    # Declared last because migration 0031 adds it: ADD COLUMN appends
    # physically, and `alembic check` compares presence and type, not position.
    # Null for producer-written events, which have no client to retry them.
    idempotency_key: Mapped[uuid.UUID | None] = mapped_column(
        doc="client-generated; a retry lands on the event that already exists"
    )


class AgentRun(Base):
    """One agent workflow execution; context_snapshot is the exact model input."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        sa.Index("agent_runs_trip_idx", "trip_id", sa.text("started_at DESC")),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    trigger_event_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("agent_events.event_id")
    )
    kind: Mapped[RunKind] = mapped_column(_pg_enum(RunKind, "run_kind"))
    status: Mapped[RunStatus] = mapped_column(
        _pg_enum(RunStatus, "run_status"),
        server_default=sa.text("'running'::run_status"),
    )
    context_snapshot: Mapped[dict | None] = mapped_column(pg.JSONB)
    result: Mapped[dict | None] = mapped_column(pg.JSONB)
    model: Mapped[str | None] = mapped_column(doc="model id used")
    error: Mapped[str | None]
    started_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))
    finished_at: Mapped[datetime | None]


class Notification(Base):
    """Outbound notifications ("Your schedule changed", "Plan ready")."""

    __tablename__ = "notifications"
    __table_args__ = (
        sa.Index(
            "notifications_user_idx",
            "user_id",
            "status",
            sa.text("created_at DESC"),
        ),
    )

    notification_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.user_id", ondelete="CASCADE")
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("trips.trip_id", ondelete="CASCADE")
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("agent_runs.run_id"))
    kind: Mapped[str] = mapped_column(doc="'plan_ready','schedule_conflict',…")
    title: Mapped[str]
    body: Mapped[str | None]
    cta: Mapped[dict | None] = mapped_column(pg.JSONB, doc="{label, deep_link}")
    status: Mapped[NotificationStatus] = mapped_column(
        _pg_enum(NotificationStatus, "notification_status"),
        server_default=sa.text("'pending'::notification_status"),
    )
    created_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"))
    sent_at: Mapped[datetime | None]
    opened_at: Mapped[datetime | None]

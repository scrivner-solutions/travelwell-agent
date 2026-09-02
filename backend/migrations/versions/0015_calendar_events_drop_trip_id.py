"""calendar_events: drop trip_id, a link nothing wrote and one reader misread.

Sync never set it, by design and by test: which trip an event belongs to is
detection's judgement, and detection records that in `trip_evidence`. The only
writer was the demo seed. The only reader was the planner's context gather,
which filtered on it and so saw zero events for any calendar that had really
been synced, scheduling workouts over real meetings while the timeline, reading
by owner and date overlap, showed those same meetings on the next screen.

Both readers now share the overlap query in `services/calendar/overlap.py`, so
the column has no writer and no reader. It goes, rather than staying nullable,
because a column that looks like the place to record "this event's trip" is an
invitation to couple sync to detection again.

The index went with it; the remaining `(user_id, starts_at)` index serves the
overlap read.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0015"
# Subject to the merge-time rule: whatever is head when this lands, not what
# was head when it was written. The per-track number ranges keep filenames
# disjoint and say nothing about this line.
down_revision: str | None = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("calendar_events_trip_time_idx", table_name="calendar_events")
    op.drop_column("calendar_events", "trip_id")


def downgrade() -> None:
    op.add_column(
        "calendar_events",
        sa.Column(
            "trip_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("trips.trip_id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "calendar_events_trip_time_idx", "calendar_events", ["trip_id", "starts_at"]
    )

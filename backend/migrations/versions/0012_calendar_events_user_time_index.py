"""calendar_events index for the timeline's owner-and-overlap read

The timeline stopped filtering by trip_id and started filtering by user_id plus
a date overlap, which the existing (trip_id, starts_at) index does not serve.
That index stays: detection really does filter by trip, so this is an addition.

Revision ID: 0012
Revises: 0011
"""

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "calendar_events_user_time_idx", "calendar_events", ["user_id", "starts_at"]
    )


def downgrade() -> None:
    op.drop_index("calendar_events_user_time_idx", table_name="calendar_events")

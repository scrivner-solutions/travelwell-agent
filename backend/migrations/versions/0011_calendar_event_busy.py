"""calendar_events.busy: does this event block time?

Nullable on purpose. NULL means no sync has classified the row yet, which is
not the same as "does not block time", and every consumer asks `busy is not
false` so an unclassified event still blocks. A NOT NULL DEFAULT true would
have made "never synced" and "the provider said opaque" the same value.

The rule that writes it lives in app/services/calendar/busy.py and nowhere
else: the research (docs/CALENDAR_INTEGRATION.md section 4) closes by warning
that the busy rule eventually becomes a user preference.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendar_events", sa.Column("busy", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("calendar_events", "busy")

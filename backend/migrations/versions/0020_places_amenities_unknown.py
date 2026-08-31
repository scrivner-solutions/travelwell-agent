"""places.amenities: let NULL mean "the provider never told us".

The column was NOT NULL DEFAULT '{}', so a venue with no amenities and a venue
we know nothing about were the same row. Google supplies no amenities field at
all, so every row a live fetch writes would have read as "we asked, there are
none" -- which is the value a filter treats as known-bad.

Existing `{}` rows are left as `{}` rather than converted to NULL. They are
seed rows written by hand, where empty really is known-empty: nothing has ever
fetched from a provider, because `refresh_area()` is still called from nowhere.
The day that stops being true this backfill would be wrong, so it is stated
here rather than assumed.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
# Re-pointed from "0004" at merge time: the calendar track branched off the
# same parent, and two heads fail `alembic upgrade head`.
down_revision: str | None = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("places", "amenities", nullable=True, server_default=None)


def downgrade() -> None:
    # NULL cannot survive the round trip: going back means asserting that
    # everything unknown is empty, which is the conflation this removed.
    op.execute("UPDATE places SET amenities = '{}'::text[] WHERE amenities IS NULL")
    op.alter_column(
        "places",
        "amenities",
        nullable=False,
        server_default=sa.text("'{}'::text[]"),
    )

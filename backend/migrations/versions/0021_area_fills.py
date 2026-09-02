"""area_fills: area-level bookkeeping, so "nobody looked" stops looking like "empty".

`places.fetched_at` makes staleness a property of a row. That cannot answer the
question that costs money -- has anyone ever fetched *here* -- because an area
nobody has looked at and an area with genuinely nothing in it are the same
absence of rows. The cheap proxy, "is there a fresh row near this point", gets
the expensive case exactly wrong: a thin neighbourhood refetches on every
planning run, forever.

A row here records an *attempted* fetch and nothing else. A fetch the policy
declined leaves no row, because a row is a claim about the provider, not about
us. `outcome` is what earns the retry window: `ok` holds for the full TTL,
`error` for a short backoff so an outage cannot consume the freshness a good
fetch earns, and `unavailable` suppresses nothing at all -- an unusable provider
raises before a request leaves the process, so retrying is free, and a timer
would mean fixing credentials took effect only when someone deleted a row.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0021"
# Subject to the merge-time rule: whatever is head when this lands, not what was
# head when it was written. Track A's 0013 and track C's 0030 are both in flight
# off the same parent, and two heads fail `alembic upgrade head`.
down_revision: str | None = "0020"
branch_labels = None
depends_on = None

_OUTCOME = pg.ENUM(
    "ok", "error", "unavailable", name="area_fill_outcome", create_type=False
)


def upgrade() -> None:
    # Native enum created explicitly, matching 0001: the models declare
    # create_type=False so that SQLAlchemy never emits CREATE TYPE behind a
    # migration's back.
    op.execute("CREATE TYPE area_fill_outcome AS ENUM ('ok', 'error', 'unavailable')")
    op.create_table(
        "area_fills",
        sa.Column(
            "area_fill_id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("area_key", sa.Text(), nullable=False, unique=True),
        sa.Column("outcome", _OUTCOME, nullable=False),
        sa.Column(
            "result_count", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("area_fills")
    op.execute("DROP TYPE area_fill_outcome")

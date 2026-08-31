"""basemap_areas: real street geometry, so the Explore map is a map.

Until now the map drew our own data -- pins and a route -- on a plain tinted
ground, which reads as a diagram of connected dots rather than a map. The
missing layer is geography, and the assumption that geography means a paid tile
provider was simply wrong: OpenStreetMap publishes street centrelines, water
and parks as open vector data, no key and no billing account.

Geometry lands here in degrees rather than screen pixels. The map's scale is
computed from its contents, so it changes whenever a category chip hides the
furthest pin; a cached projection would be wrong one tap after it was written.

No outcome enum, unlike `area_fills`. That column exists there to stop an
outage consuming the freshness window a paid fetch earned. Nothing bills here,
so a failed attempt costs only the retry, and the cheapest correct behaviour is
to write no row and ask again next time.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0022"
# Subject to the merge-time rule: whatever is head when this lands, not what
# was head when it was written. The per-track number ranges keep filenames
# disjoint and say nothing about this line.
down_revision: str | None = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "basemap_areas",
        sa.Column(
            "basemap_area_id",
            pg.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("area_key", sa.Text(), nullable=False),
        sa.Column("roads_major", pg.JSONB(), nullable=False),
        sa.Column("roads_minor", pg.JSONB(), nullable=False),
        sa.Column("water", pg.JSONB(), nullable=False),
        sa.Column("parks", pg.JSONB(), nullable=False),
        sa.Column("buildings", pg.JSONB(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("basemap_area_id"),
        sa.UniqueConstraint("area_key"),
    )


def downgrade() -> None:
    op.drop_table("basemap_areas")

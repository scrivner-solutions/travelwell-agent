"""user_preferences.preferred_times: time-of-day preference slugs.

The profile screen's chip row includes "Mornings" and Slice 1 already ranks
options with matched_preferences=["Running", "Mornings"]; no column carried
that preference. Array like the other preference facets ({'mornings'}).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column(
            "preferred_times",
            pg.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "preferred_times")

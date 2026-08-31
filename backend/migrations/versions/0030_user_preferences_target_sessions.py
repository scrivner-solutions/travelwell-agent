"""user_preferences.target_sessions

Windows are capacity, not demand. Nothing in `user_preferences` said how much
the traveler actually wants, so the planner filled every window it could - and
an over-full plan passes every structural check identically to a well-judged
one, which is why this is a column rather than a prompt change.

It also gives the item bound a home outside the wire schema. `maxItems` is the
keyword Vertex refuses to compile at `PlanProposal`'s nesting depth, so the
ceiling moved to Verify, and Verify needs a number to read.

Nullable with no default on purpose: absent means "no stated target", which
`verify` reads as the `MAX_ITEMS` backstop rather than as zero.

Revision ID: 0030
Revises: 0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        # No `comment=`: prose lives in the model's `doc=`, which alembic does
        # not project into the database, so a comment here reads as drift.
        sa.Column("target_sessions", sa.SmallInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "target_sessions")

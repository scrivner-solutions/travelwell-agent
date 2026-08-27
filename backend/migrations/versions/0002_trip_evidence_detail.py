"""trip_evidence.detail: caption line under the evidence summary.

The design prototype renders evidence rows as a bold summary with a muted
caption below ('The Gwen' / '521 N Rush St · 3 nights'); one summary string
cannot carry both. Nullable - detection may not always have a second line.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trip_evidence", sa.Column("detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("trip_evidence", "detail")

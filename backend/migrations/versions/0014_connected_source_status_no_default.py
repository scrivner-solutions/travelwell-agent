"""connected_sources.status: drop the default that violated 0013's own CHECK.

With `DEFAULT 'connected'` and `CHECK (status <> 'connected' OR secret_ref IS
NOT NULL)`, a minimal `INSERT (user_id, kind)` failed the table's own
constraint. The error named neither column the caller had omitted, which is
what made it read as unrelated breakage rather than a missing argument.

Dropping the default is safe only because `status` is NOT NULL: the same
insert now fails naming `status`. Were it nullable this would be the wrong
fix -- `NULL <> 'connected' OR ...` evaluates to NULL, and a CHECK accepts
NULL, so a status-less row would pass every gate silently.

No backfill: existing rows already hold a value, and a default is consulted
only at insert time.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("connected_sources", "status", server_default=None)


def downgrade() -> None:
    op.alter_column(
        "connected_sources",
        "status",
        server_default=sa.text("'connected'::source_status"),
    )

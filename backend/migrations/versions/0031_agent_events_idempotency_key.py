"""agent_events.idempotency_key

docs/openapi.yaml requires an Idempotency-Key header on POST /events and its
description promises that "retries are safe". Accepting the header without a
uniqueness constraint would make that promise a comment: a client that retries
a dropped response would get a second event, and for `scheduled_activation`
a second event is a second paid run.

Unique per user rather than globally, because the key is client-generated and
two users may pick the same UUID. Nullable, and NULLs are distinct in Postgres,
so the sync job and the scheduler write rows without one and never collide.

Revision ID: 0031
Revises: 0030
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_events",
        # No comment=: the model says it with doc=, which is Python-only, and a
        # DB comment the ORM does not declare is drift.
        sa.Column("idempotency_key", sa.Uuid(), nullable=True),
    )
    op.create_unique_constraint(
        "agent_events_idempotency_uq", "agent_events", ["user_id", "idempotency_key"]
    )


def downgrade() -> None:
    op.drop_constraint("agent_events_idempotency_uq", "agent_events", type_="unique")
    op.drop_column("agent_events", "idempotency_key")

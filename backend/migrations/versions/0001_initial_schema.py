"""Initial schema: docs/schema.sql applied verbatim.

Hand-written per ADR-001 point 1: the schema's value is in the constraint
constructs autogenerate fumbles (CHECK constraints, the partial unique index
on plan_item_options, native enums). The SQL lives in
migrations/sql/0001_initial_schema.sql, a frozen copy of docs/schema.sql at
the time this revision was written. Migration files are immutable once
applied; scripts/check_schema_drift.sh keeps docs/schema.sql honest against
the migration chain in CI.
"""

from pathlib import Path

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def upgrade() -> None:
    op.execute((SQL_DIR / "0001_initial_schema.sql").read_text())


def downgrade() -> None:
    op.execute((SQL_DIR / "0001_initial_schema_down.sql").read_text())

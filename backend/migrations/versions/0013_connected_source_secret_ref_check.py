"""connected_sources: a `connected` grant must carry a token reference.

`status='connected'` with `secret_ref IS NULL` is a row that claims access
nothing can exercise. The application already writes the pair together --
the OAuth upsert sets both, disconnect clears both -- so this makes an
existing convention something the database enforces rather than trusts.

The UPDATE must run BEFORE the constraint. Rows predating this migration can
hold exactly the combination being forbidden, and a CHECK is validated against
existing data when it is added.

Autogenerate produced the constraint (alembic 1.19.1 has a check-constraint
plugin; the older claim that it emits none is wrong). It cannot produce the
backfill, because autogenerate diffs schema and never data.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
# Parented on the head that existed when this was written, not on 0012 where
# the 0010-0019 range would suggest. Per-track number ranges keep filenames
# disjoint and say nothing about down_revision. Re-point if another track's
# migration lands first; two heads fail `alembic upgrade head`.
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE connected_sources SET status = 'revoked'::source_status "
        "WHERE status = 'connected'::source_status AND secret_ref IS NULL"
    )
    op.create_check_constraint(
        "connected_sources_check",
        "connected_sources",
        "status <> 'connected'::source_status or secret_ref is not null",
    )


def downgrade() -> None:
    # The UPDATE is not reversed: nothing records which revoked rows were
    # tokenless-connected before, and restoring the claim would be a guess.
    op.drop_constraint("connected_sources_check", "connected_sources", type_="check")

"""login_codes: database-backed email sign-in codes.

The in-process code store breaks past one instance: the code is issued on one
Cloud Run instance and verified on another. One row per address; the code is
never stored, only its HMAC (app/api/login_codes.py).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_codes",
        sa.Column("email", pg.CITEXT(), primary_key=True),
        sa.Column("code_hmac", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts_left", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("login_codes")

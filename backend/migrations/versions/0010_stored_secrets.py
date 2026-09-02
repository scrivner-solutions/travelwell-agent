"""stored_secrets: long-lived secrets, encrypted at rest.

Backs the token store (app/services/tokens). A calendar grant needs a refresh
token that outlives the request that obtained it, and the decision was the
database encrypted at rest rather than one Secret Manager secret per user.

Only the ciphertext is here; the key is TOKEN_ENCRYPTION_KEY. Nothing outside
app/services/tokens reads this table -- callers hold `connected_sources.
secret_ref` and nothing else.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stored_secrets",
        sa.Column(
            "secret_id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "kind", name="stored_secrets_user_id_kind_key"),
    )


def downgrade() -> None:
    op.drop_table("stored_secrets")

"""Add revocable authentication sessions.

Revision ID: 20261102_0002
Revises: 20261102_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261102_0002"
down_revision: str | None = "20261102_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("login_id", sa.Uuid(), nullable=False),
        sa.Column("token_id", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["login_id"], ["logins.id"], name="fk_auth_sessions_login_id_logins", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.UniqueConstraint("token_id", name="uq_auth_sessions_token_id"),
    )
    op.create_index("ix_auth_sessions_login_id", "auth_sessions", ["login_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_login_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")

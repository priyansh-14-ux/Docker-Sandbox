"""Store hashed, rotating refresh tokens for authentication sessions.

Revision ID: 20261102_0005
Revises: 20261102_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261102_0005"
down_revision: str | None = "20261102_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("refresh_token_hash", sa.String(length=64)))
    op.add_column("auth_sessions", sa.Column("refresh_expires_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint(
        "uq_auth_sessions_refresh_token_hash", "auth_sessions", ["refresh_token_hash"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_auth_sessions_refresh_token_hash", "auth_sessions", type_="unique")
    op.drop_column("auth_sessions", "refresh_expires_at")
    op.drop_column("auth_sessions", "refresh_token_hash")

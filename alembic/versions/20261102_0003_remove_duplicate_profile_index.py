"""Remove the duplicate index on the unique profile login id.

Revision ID: 20261102_0003
Revises: 20261102_0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261102_0003"
down_revision: str | None = "20261102_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_profiles_login_id", table_name="profiles")


def downgrade() -> None:
    op.create_index("ix_profiles_login_id", "profiles", ["login_id"])

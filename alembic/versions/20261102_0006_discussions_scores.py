"""Add problem discussions and submission scores.

Revision ID: 20261102_0006
Revises: 20261102_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261102_0006"
down_revision: str | None = "20261102_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("score", sa.Numeric(precision=5, scale=2)))
    op.create_table(
        "problem_discussions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("author_profile_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(body) > 0 AND length(body) <= 4000",
            name="ck_problem_discussions_discussion_body_length",
        ),
        sa.ForeignKeyConstraint(
            ["author_profile_id"],
            ["profiles.id"],
            name="fk_problem_discussions_author_profile_id_profiles",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["problem_discussions.id"],
            name="fk_problem_discussions_parent_id_problem_discussions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"],
            ["problems.id"],
            name="fk_problem_discussions_problem_id_problems",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_discussions"),
    )
    op.create_index("ix_problem_discussions_problem_id", "problem_discussions", ["problem_id"])
    op.create_index(
        "ix_problem_discussions_author_profile_id", "problem_discussions", ["author_profile_id"]
    )
    op.create_index("ix_problem_discussions_parent_id", "problem_discussions", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_problem_discussions_parent_id", table_name="problem_discussions")
    op.drop_index("ix_problem_discussions_author_profile_id", table_name="problem_discussions")
    op.drop_index("ix_problem_discussions_problem_id", table_name="problem_discussions")
    op.drop_table("problem_discussions")
    op.drop_column("submissions", "score")

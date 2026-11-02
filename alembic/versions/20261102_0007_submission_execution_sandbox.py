"""Add submission execution sandbox tables and columns.

Revision ID: 20261102_0007
Revises: 20261102_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0007"
down_revision: str | None = "20261102_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 1. Add comparison_mode to problems
    op.add_column(
        "problems",
        sa.Column("comparison_mode", sa.String(length=32), nullable=False, server_default="ignore_whitespace"),
    )

    # 2. Add execution tracking columns to submissions
    op.add_column("submissions", sa.Column("verdict", sa.String(length=16), nullable=True))
    op.add_column("submissions", sa.Column("time_ms", sa.Integer(), nullable=True))
    op.add_column("submissions", sa.Column("memory_kb", sa.Integer(), nullable=True))
    op.add_column(
        "submissions",
        sa.Column("passed_test_cases", sa.Integer(), nullable=True, server_default="0"),
    )
    op.add_column(
        "submissions",
        sa.Column("total_test_cases", sa.Integer(), nullable=True, server_default="0"),
    )
    op.add_column("submissions", sa.Column("error_message", sa.Text(), nullable=True))
    op.alter_column("submissions", "course_enrollment_id", nullable=True)

    # 3. Create composite index on submissions
    op.create_index(
        "ix_submissions_student_problem_created",
        "submissions",
        ["student_profile_id", "problem_id", "created_at"],
    )

    # 4. Create submission_results table
    op.create_table(
        "submission_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("test_case_id", sa.Uuid(), nullable=True),
        sa.Column("test_number", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("time_ms", sa.Integer(), nullable=True),
        sa.Column("memory_kb", sa.Integer(), nullable=True),
        sa.Column("stdout", sa.Text(), nullable=True),
        sa.Column("stderr", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name="fk_submission_results_submission_id_submissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["test_case_id"],
            ["test_cases.id"],
            name="fk_submission_results_test_case_id_test_cases",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_submission_results"),
    )
    op.create_index(
        "ix_submission_results_submission_id", "submission_results", ["submission_id"]
    )
    op.create_index(
        "ix_submission_results_test_case_id", "submission_results", ["test_case_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_submission_results_test_case_id", table_name="submission_results")
    op.drop_index("ix_submission_results_submission_id", table_name="submission_results")
    op.drop_table("submission_results")

    op.drop_index("ix_submissions_student_problem_created", table_name="submissions")
    op.alter_column("submissions", "course_enrollment_id", nullable=False)
    op.drop_column("submissions", "error_message")
    op.drop_column("submissions", "total_test_cases")
    op.drop_column("submissions", "passed_test_cases")
    op.drop_column("submissions", "memory_kb")
    op.drop_column("submissions", "time_ms")
    op.drop_column("submissions", "verdict")
    op.drop_column("problems", "comparison_mode")

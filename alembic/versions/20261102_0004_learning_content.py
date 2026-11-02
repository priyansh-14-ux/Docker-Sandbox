"""Add course content and assignment submission tables.

Revision ID: 20261102_0004
Revises: 20261102_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261102_0004"
down_revision: str | None = "20261102_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "labs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("sort_order >= 0", name="ck_labs_nonnegative_lab_sort"),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name="fk_labs_course_id_courses", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_labs"),
    )
    op.create_index("ix_labs_course_id", "labs", ["course_id"])

    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lab_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("sort_order >= 0", name="ck_experiments_nonnegative_experiment_sort"),
        sa.ForeignKeyConstraint(
            ["lab_id"], ["labs.id"], name="fk_experiments_lab_id_labs", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_experiments"),
    )
    op.create_index("ix_experiments_lab_id", "experiments", ["lab_id"])

    op.create_table(
        "problems",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=16), nullable=False),
        sa.Column("time_limit_ms", sa.Integer(), nullable=False),
        sa.Column("memory_limit_mb", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("time_limit_ms > 0", name="ck_problems_positive_problem_time_limit"),
        sa.CheckConstraint("memory_limit_mb > 0", name="ck_problems_positive_problem_memory_limit"),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name="fk_problems_experiment_id_experiments",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problems"),
    )
    op.create_index("ix_problems_experiment_id", "problems", ["experiment_id"])

    op.create_table(
        "test_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("input_data", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=False),
        sa.Column("is_hidden", sa.Boolean(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("points > 0", name="ck_test_cases_positive_test_case_points"),
        sa.CheckConstraint("sort_order >= 0", name="ck_test_cases_nonnegative_test_case_sort"),
        sa.ForeignKeyConstraint(
            ["problem_id"],
            ["problems.id"],
            name="fk_test_cases_problem_id_problems",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_test_cases"),
    )
    op.create_index("ix_test_cases_problem_id", "test_cases", ["problem_id"])

    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_profile_id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("course_enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("source_code", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "octet_length(source_code) <= 65536", name="ck_submissions_submission_source_size"
        ),
        sa.ForeignKeyConstraint(
            ["course_enrollment_id"],
            ["course_enrollments.id"],
            name="fk_submissions_course_enrollment_id_course_enrollments",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"],
            ["problems.id"],
            name="fk_submissions_problem_id_problems",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id"],
            ["profiles.id"],
            name="fk_submissions_student_profile_id_profiles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_submissions"),
    )
    op.create_index("ix_submissions_student_profile_id", "submissions", ["student_profile_id"])
    op.create_index("ix_submissions_problem_id", "submissions", ["problem_id"])
    op.create_index("ix_submissions_course_enrollment_id", "submissions", ["course_enrollment_id"])


def downgrade() -> None:
    for table, column in (
        ("submissions", "course_enrollment_id"),
        ("submissions", "problem_id"),
        ("submissions", "student_profile_id"),
        ("test_cases", "problem_id"),
        ("problems", "experiment_id"),
        ("experiments", "lab_id"),
        ("labs", "course_id"),
    ):
        op.drop_index(f"ix_{table}_{column}", table_name=table)
    for table in ("submissions", "test_cases", "problems", "experiments", "labs"):
        op.drop_table(table)

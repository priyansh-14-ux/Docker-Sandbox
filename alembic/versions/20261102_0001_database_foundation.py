"""Create the identity and academic database foundation.

Revision ID: 20261102_0001
Revises:
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261102_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_departments"),
        sa.UniqueConstraint("code", name="uq_departments_code"),
    )
    op.create_table(
        "logins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("email = lower(email)", name="ck_logins_email_lowercase"),
        sa.PrimaryKeyConstraint("id", name="pk_logins"),
        sa.UniqueConstraint("email", name="uq_logins_email"),
    )
    op.create_table(
        "programs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("duration_semesters", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint("duration_semesters > 0", name="positive_duration_semesters"),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name="fk_programs_department_id_departments",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_programs"),
        sa.UniqueConstraint("department_id", "code", name="uq_programs_department_code"),
    )
    op.create_table(
        "academic_terms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("academic_year_start", sa.Integer(), nullable=False),
        sa.Column("academic_year_end", sa.Integer(), nullable=False),
        sa.Column("term_type", sa.String(length=16), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint(
            "academic_year_end = academic_year_start + 1", name="valid_academic_year"
        ),
        sa.CheckConstraint("starts_on < ends_on", name="valid_term_dates"),
        sa.PrimaryKeyConstraint("id", name="pk_academic_terms"),
        sa.UniqueConstraint("name", name="uq_academic_terms_name"),
    )
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("login_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name="fk_profiles_department_id_departments",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["login_id"], ["logins.id"], name="fk_profiles_login_id_logins", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name="fk_profiles_role_id_roles", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_profiles"),
        sa.UniqueConstraint("login_id", name="uq_profiles_login_id"),
    )
    op.create_table(
        "courses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=False),
        sa.Column("course_code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("credits", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name="fk_courses_department_id_departments",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_courses"),
        sa.UniqueConstraint("department_id", "course_code", name="uq_courses_department_code"),
    )
    op.create_table(
        "student_details",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("enrollment_number", sa.String(length=64), nullable=False),
        sa.Column("admission_year", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name="fk_student_details_profile_id_profiles",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name="fk_student_details_program_id_programs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_student_details"),
        sa.UniqueConstraint("enrollment_number", name="uq_student_details_enrollment_number"),
        sa.UniqueConstraint("profile_id", name="uq_student_details_profile_id"),
    )
    op.create_table(
        "student_term_enrollments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_profile_id", sa.Uuid(), nullable=False),
        sa.Column("academic_term_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("semester_number", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=32), nullable=True),
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
        sa.CheckConstraint("semester_number > 0", name="positive_student_semester"),
        sa.ForeignKeyConstraint(
            ["academic_term_id"],
            ["academic_terms.id"],
            name="fk_student_term_enrollments_academic_term_id_academic_terms",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name="fk_student_term_enrollments_program_id_programs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id"],
            ["profiles.id"],
            name="fk_student_term_enrollments_student_profile_id_profiles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_student_term_enrollments"),
        sa.UniqueConstraint(
            "student_profile_id",
            "academic_term_id",
            name="uq_student_term_enrollments_student_term",
        ),
    )
    op.create_table(
        "course_offerings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("academic_term_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("semester_number", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=32), nullable=True),
        sa.Column("offering_code", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
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
        sa.CheckConstraint("semester_number > 0", name="positive_offering_semester"),
        sa.ForeignKeyConstraint(
            ["academic_term_id"],
            ["academic_terms.id"],
            name="fk_course_offerings_academic_term_id_academic_terms",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name="fk_course_offerings_course_id_courses",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name="fk_course_offerings_program_id_programs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_course_offerings"),
        sa.UniqueConstraint("offering_code", name="uq_course_offerings_offering_code"),
        sa.UniqueConstraint(
            "course_id",
            "academic_term_id",
            "program_id",
            "semester_number",
            "section",
            name="uq_course_offerings_delivery",
        ),
    )
    op.create_table(
        "offering_faculty",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("offering_id", sa.Uuid(), nullable=False),
        sa.Column("faculty_profile_id", sa.Uuid(), nullable=False),
        sa.Column("assignment_role", sa.String(length=32), nullable=False),
        sa.Column("ended_at", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["faculty_profile_id"],
            ["profiles.id"],
            name="fk_offering_faculty_faculty_profile_id_profiles",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_offering_faculty_offering_id_course_offerings",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_offering_faculty"),
        sa.UniqueConstraint(
            "offering_id", "faculty_profile_id", name="uq_offering_faculty_assignment"
        ),
    )
    op.create_table(
        "course_enrollments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("offering_id", sa.Uuid(), nullable=False),
        sa.Column("student_profile_id", sa.Uuid(), nullable=False),
        sa.Column("enrollment_status", sa.String(length=16), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["offering_id"],
            ["course_offerings.id"],
            name="fk_course_enrollments_offering_id_course_offerings",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id"],
            ["profiles.id"],
            name="fk_course_enrollments_student_profile_id_profiles",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_course_enrollments"),
        sa.UniqueConstraint(
            "offering_id", "student_profile_id", name="uq_course_enrollments_offering_student"
        ),
    )

    for table, columns in {
        "profiles": ["login_id", "role_id", "department_id"],
        "programs": ["department_id"],
        "courses": ["department_id"],
        "student_term_enrollments": ["student_profile_id", "academic_term_id"],
        "course_offerings": ["course_id", "academic_term_id", "program_id"],
        "offering_faculty": ["offering_id", "faculty_profile_id"],
        "course_enrollments": ["offering_id", "student_profile_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])

    roles_table = sa.table(
        "roles",
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        roles_table,
        [
            {"name": "SUPER_ADMIN", "description": "Platform super administrator"},
            {"name": "INSTITUTE_ADMIN", "description": "Institution administrator"},
            {"name": "FACULTY", "description": "Faculty member"},
            {"name": "STUDENT", "description": "Student"},
        ],
    )


def downgrade() -> None:
    for table, columns in {
        "course_enrollments": ["offering_id", "student_profile_id"],
        "offering_faculty": ["offering_id", "faculty_profile_id"],
        "course_offerings": ["course_id", "academic_term_id", "program_id"],
        "student_term_enrollments": ["student_profile_id", "academic_term_id"],
        "courses": ["department_id"],
        "programs": ["department_id"],
        "profiles": ["login_id", "role_id", "department_id"],
    }.items():
        for column in columns:
            op.drop_index(f"ix_{table}_{column}", table_name=table)

    for table in (
        "course_enrollments",
        "offering_faculty",
        "course_offerings",
        "student_term_enrollments",
        "student_details",
        "courses",
        "profiles",
        "academic_terms",
        "programs",
        "logins",
        "departments",
        "roles",
    ):
        op.drop_table(table)

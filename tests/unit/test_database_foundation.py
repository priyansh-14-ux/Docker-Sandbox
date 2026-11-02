import medicode.models  # noqa: F401
from medicode.db.base import Base


def test_database_foundation_tables_are_registered() -> None:
    expected_tables = {
        "roles",
        "logins",
        "auth_sessions",
        "departments",
        "profiles",
        "programs",
        "academic_terms",
        "student_details",
        "student_term_enrollments",
        "courses",
        "course_offerings",
        "offering_faculty",
        "course_enrollments",
    }

    assert expected_tables.issubset(set(Base.metadata.tables))


def test_course_enrollment_has_unique_offering_student_constraint() -> None:
    table = Base.metadata.tables["course_enrollments"]
    constraint_names = {constraint.name for constraint in table.constraints}

    assert "uq_course_enrollments_offering_student" in constraint_names

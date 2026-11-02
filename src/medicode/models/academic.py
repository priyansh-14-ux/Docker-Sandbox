from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from medicode.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from medicode.models.identity import Department


class TermType(StrEnum):
    ODD = "ODD"
    EVEN = "EVEN"
    SUMMER = "SUMMER"


class OfferingStatus(StrEnum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class EnrollmentStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    DROPPED = "DROPPED"
    COMPLETED = "COMPLETED"


class Program(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "programs"
    __table_args__ = (
        UniqueConstraint("department_id", "code", name="uq_programs_department_code"),
        CheckConstraint("duration_semesters > 0", name="positive_duration_semesters"),
    )

    department_id: Mapped[UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_semesters: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    department: Mapped["Department"] = relationship(back_populates="programs")
    student_term_enrollments: Mapped[list["StudentTermEnrollment"]] = relationship(
        back_populates="program"
    )
    course_offerings: Mapped[list["CourseOffering"]] = relationship(back_populates="program")


class AcademicTerm(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "academic_terms"
    __table_args__ = (
        CheckConstraint("academic_year_end = academic_year_start + 1", name="valid_academic_year"),
        CheckConstraint("starts_on < ends_on", name="valid_term_dates"),
    )

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    academic_year_start: Mapped[int] = mapped_column(Integer, nullable=False)
    academic_year_end: Mapped[int] = mapped_column(Integer, nullable=False)
    term_type: Mapped[TermType] = mapped_column(String(16), nullable=False)
    starts_on: Mapped[date] = mapped_column(nullable=False)
    ends_on: Mapped[date] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    student_term_enrollments: Mapped[list["StudentTermEnrollment"]] = relationship(
        back_populates="academic_term"
    )
    course_offerings: Mapped[list["CourseOffering"]] = relationship(back_populates="academic_term")


class StudentDetail(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_details"

    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    enrollment_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    admission_year: Mapped[int] = mapped_column(Integer, nullable=False)
    program_id: Mapped[UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), nullable=False
    )
    program: Mapped[Program] = relationship()


class StudentTermEnrollment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_term_enrollments"
    __table_args__ = (
        UniqueConstraint(
            "student_profile_id",
            "academic_term_id",
            name="uq_student_term_enrollments_student_term",
        ),
        CheckConstraint("semester_number > 0", name="positive_student_semester"),
    )

    student_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    academic_term_id: Mapped[UUID] = mapped_column(
        ForeignKey("academic_terms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    program_id: Mapped[UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), nullable=False
    )
    semester_number: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str | None] = mapped_column(String(32))
    academic_term: Mapped[AcademicTerm] = relationship(back_populates="student_term_enrollments")
    program: Mapped[Program] = relationship(back_populates="student_term_enrollments")


class Course(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("department_id", "course_code", name="uq_courses_department_code"),
    )

    department_id: Mapped[UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_code: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    credits: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    department: Mapped["Department"] = relationship(back_populates="courses")
    offerings: Mapped[list["CourseOffering"]] = relationship(back_populates="course")


class CourseOffering(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "course_offerings"
    __table_args__ = (
        UniqueConstraint(
            "course_id",
            "academic_term_id",
            "program_id",
            "semester_number",
            "section",
            name="uq_course_offerings_delivery",
        ),
        CheckConstraint("semester_number > 0", name="positive_offering_semester"),
    )

    course_id: Mapped[UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    academic_term_id: Mapped[UUID] = mapped_column(
        ForeignKey("academic_terms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    program_id: Mapped[UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    semester_number: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str | None] = mapped_column(String(32))
    offering_code: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[OfferingStatus] = mapped_column(String(16), nullable=False)
    course: Mapped[Course] = relationship(back_populates="offerings")
    academic_term: Mapped[AcademicTerm] = relationship(back_populates="course_offerings")
    program: Mapped[Program] = relationship(back_populates="course_offerings")
    faculty_assignments: Mapped[list["OfferingFaculty"]] = relationship(back_populates="offering")
    student_enrollments: Mapped[list["CourseEnrollment"]] = relationship(back_populates="offering")


class OfferingFaculty(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offering_faculty"
    __table_args__ = (
        UniqueConstraint(
            "offering_id", "faculty_profile_id", name="uq_offering_faculty_assignment"
        ),
    )

    offering_id: Mapped[UUID] = mapped_column(
        ForeignKey("course_offerings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    faculty_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assignment_role: Mapped[str] = mapped_column(String(32), nullable=False, default="INSTRUCTOR")
    ended_at: Mapped[date | None]
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    offering: Mapped[CourseOffering] = relationship(back_populates="faculty_assignments")


class CourseEnrollment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "course_enrollments"
    __table_args__ = (
        UniqueConstraint(
            "offering_id", "student_profile_id", name="uq_course_enrollments_offering_student"
        ),
    )

    offering_id: Mapped[UUID] = mapped_column(
        ForeignKey("course_offerings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    enrollment_status: Mapped[EnrollmentStatus] = mapped_column(
        String(16), nullable=False, default=EnrollmentStatus.PENDING
    )
    offering: Mapped[CourseOffering] = relationship(back_populates="student_enrollments")

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from medicode.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from medicode.models.identity import Profile


class Lab(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "labs"
    __table_args__ = (CheckConstraint("sort_order >= 0", name="nonnegative_lab_sort"),)

    course_id: Mapped[UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_published: Mapped[bool] = mapped_column(nullable=False, default=False)
    experiments: Mapped[list["Experiment"]] = relationship(back_populates="lab")


class Experiment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiments"
    __table_args__ = (CheckConstraint("sort_order >= 0", name="nonnegative_experiment_sort"),)

    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_published: Mapped[bool] = mapped_column(nullable=False, default=False)
    lab: Mapped[Lab] = relationship(back_populates="experiments")
    problems: Mapped[list["Problem"]] = relationship(back_populates="experiment")


class Problem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "problems"
    __table_args__ = (
        CheckConstraint("time_limit_ms > 0", name="positive_problem_time_limit"),
        CheckConstraint("memory_limit_mb > 0", name="positive_problem_memory_limit"),
    )

    experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    time_limit_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=256)
    is_published: Mapped[bool] = mapped_column(nullable=False, default=False)
    experiment: Mapped[Experiment] = relationship(back_populates="problems")
    test_cases: Mapped[list["TestCase"]] = relationship(back_populates="problem")


class TestCase(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "test_cases"
    __table_args__ = (
        CheckConstraint("points > 0", name="positive_test_case_points"),
        CheckConstraint("sort_order >= 0", name="nonnegative_test_case_sort"),
    )

    problem_id: Mapped[UUID] = mapped_column(
        ForeignKey("problems.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    input_data: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(nullable=False, default=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    problem: Mapped[Problem] = relationship(back_populates="test_cases")


class Submission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint("octet_length(source_code) <= 65536", name="submission_source_size"),
    )

    student_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    problem_id: Mapped[UUID] = mapped_column(
        ForeignKey("problems.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_enrollment_id: Mapped[UUID] = mapped_column(
        ForeignKey("course_enrollments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="python")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="RECEIVED")
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    student_profile: Mapped["Profile"] = relationship()
    problem: Mapped[Problem] = relationship()


class ProblemDiscussion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "problem_discussions"
    __table_args__ = (
        CheckConstraint("length(body) > 0 AND length(body) <= 4000", name="discussion_body_length"),
    )

    problem_id: Mapped[UUID] = mapped_column(
        ForeignKey("problems.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    author_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("problem_discussions.id", ondelete="RESTRICT"), index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

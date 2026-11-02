from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CourseCreate(BaseModel):
    department_id: UUID
    course_code: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    credits: int | None = Field(default=None, ge=0, le=30)


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    credits: int | None = Field(default=None, ge=0, le=30)
    is_active: bool | None = None


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    department_id: UUID
    course_code: str
    title: str
    description: str | None
    credits: int | None
    is_active: bool
    created_at: datetime


class CourseOfferingCreate(BaseModel):
    academic_term_id: UUID
    program_id: UUID
    semester_number: int = Field(gt=0)
    section: str | None = Field(default=None, max_length=32)
    offering_code: str | None = Field(default=None, max_length=64)


class FacultyAssignmentCreate(BaseModel):
    faculty_profile_id: UUID
    assignment_role: str = Field(default="INSTRUCTOR", min_length=1, max_length=32)


class LabResponse(BaseModel):
    id: UUID
    course_id: UUID
    title: str
    description: str | None
    sort_order: int
    is_published: bool


class ExperimentResponse(BaseModel):
    id: UUID
    lab_id: UUID
    title: str
    description: str | None
    sort_order: int
    is_published: bool


class TestCaseResponse(BaseModel):
    id: UUID
    problem_id: UUID
    input_data: str
    expected_output: str
    is_hidden: bool
    points: int
    sort_order: int


class PublishUpdate(BaseModel):
    is_published: bool


class LabCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    sort_order: int = Field(default=0, ge=0)


class ExperimentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    sort_order: int = Field(default=0, ge=0)


class ProblemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1)
    difficulty: str = Field(default="MEDIUM", max_length=16)
    time_limit_ms: int = Field(default=2000, gt=0, le=60000)
    memory_limit_mb: int = Field(default=256, gt=0, le=2048)


class TestCaseCreate(BaseModel):
    input_data: str = Field(max_length=65536)
    expected_output: str = Field(max_length=65536)
    is_hidden: bool = True
    points: int = Field(default=1, gt=0)
    sort_order: int = Field(default=0, ge=0)

    @field_validator("input_data", "expected_output")
    @classmethod
    def inline_data_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 65536:
            raise ValueError("inline test data cannot exceed 64 KiB")
        return value


class VisibleTestCase(BaseModel):
    id: UUID
    input_data: str
    expected_output: str
    points: int
    is_hidden: bool


class ProblemResponse(BaseModel):
    id: UUID
    title: str
    statement: str
    difficulty: str
    time_limit_ms: int
    memory_limit_mb: int
    test_cases: list[VisibleTestCase]


class EnrollmentResponse(BaseModel):
    id: UUID
    offering_id: UUID
    student_profile_id: UUID
    enrollment_status: str

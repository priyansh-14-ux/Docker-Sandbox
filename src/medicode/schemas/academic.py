from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    code: str = Field(min_length=1, max_length=32)


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    code: str


class ProgramCreate(BaseModel):
    department_id: UUID
    name: str = Field(min_length=1, max_length=150)
    code: str = Field(min_length=1, max_length=32)
    duration_semesters: int = Field(gt=0, le=20)


class ProgramResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    department_id: UUID
    name: str
    code: str
    duration_semesters: int
    is_active: bool


class AcademicTermCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    academic_year_start: int = Field(ge=2000, le=2200)
    academic_year_end: int = Field(ge=2001, le=2201)
    term_type: str = Field(pattern="^(ODD|EVEN|SUMMER)$")
    starts_on: date
    ends_on: date

    @model_validator(mode="after")
    def validate_term(self) -> "AcademicTermCreate":
        if self.academic_year_end != self.academic_year_start + 1:
            raise ValueError("academic_year_end must follow academic_year_start by one year")
        if self.starts_on >= self.ends_on:
            raise ValueError("starts_on must be before ends_on")
        return self


class AcademicTermResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    academic_year_start: int
    academic_year_end: int
    term_type: str
    starts_on: date
    ends_on: date
    is_active: bool

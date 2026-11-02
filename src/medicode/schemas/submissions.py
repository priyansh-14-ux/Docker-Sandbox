from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class SupportedLanguage(StrEnum):
    PYTHON = "python"


class SubmissionCreate(BaseModel):
    problem_id: UUID
    source_code: str = Field(
        default="",
        description="Source code written by the student (max 64 KiB).",
    )
    code: str | None = Field(
        default=None,
        description="Alias for source_code to maintain backward compatibility.",
    )
    language: SupportedLanguage = Field(
        default=SupportedLanguage.PYTHON,
        description="Programming language used for execution.",
    )

    @model_validator(mode="before")
    @classmethod
    def resolve_code_field(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Accept either source_code or code
            code_val = data.get("source_code") or data.get("code")
            if not code_val or not str(code_val).strip():
                raise ValueError("source_code (or code) cannot be empty")
            if len(str(code_val).encode("utf-8")) > 65536:
                raise ValueError("source_code must not exceed 64 KiB when UTF-8 encoded")
            data["source_code"] = str(code_val)
        return data


class SubmissionQueuedResponse(BaseModel):
    submission_id: UUID = Field(description="Unique submission identifier.")
    status: str = Field(default="queued", description="Initial queue status.")
    message: str = Field(
        default="Submission queued for isolated sandbox execution.",
        description="User-friendly status message.",
    )


class TestCaseResultResponse(BaseModel):
    test_number: int = Field(description="Ordinal index of the test case.")
    verdict: str = Field(description="Verdict (e.g. AC, WA, TLE, MLE, RE, CE, OLE, IE).")
    time_ms: int | None = Field(default=None, description="Execution time in milliseconds.")
    memory_kb: int | None = Field(default=None, description="Memory used in kilobytes.")
    is_hidden: bool = Field(description="Whether this test case was hidden from the student.")
    stdout: str | None = Field(
        default=None,
        description="Standard output (only revealed for visible tests; null for hidden tests).",
    )
    stderr: str | None = Field(
        default=None,
        description="Standard error output (only revealed for visible tests; null for hidden tests).",
    )
    error_message: str | None = Field(
        default=None,
        description="Error or explanation message.",
    )


class SubmissionDetailResponse(BaseModel):
    id: UUID
    problem_id: UUID
    status: str
    verdict: str | None = None
    language: str
    score: Decimal | None = None
    time_ms: int | None = None
    memory_kb: int | None = None
    passed_test_cases: int | None = 0
    total_test_cases: int | None = 0
    error_message: str | None = None
    results: list[TestCaseResultResponse] = Field(default_factory=list)
    created_at: datetime


class SubmissionResponse(BaseModel):
    """Backward-compatible response model for existing endpoints."""
    id: UUID
    problem_id: UUID
    status: str
    language: str
    score: Decimal | None = None
    verdict: str | None = None
    time_ms: int | None = None
    memory_kb: int | None = None
    created_at: datetime


class RunCodeRequest(BaseModel):
    problem_id: UUID | None = Field(
        default=None,
        description="Problem ID to test against visible sample test cases.",
    )
    source_code: str = Field(
        default="",
        description="Python source code to execute.",
    )
    code: str | None = Field(default=None)
    language: SupportedLanguage = Field(default=SupportedLanguage.PYTHON)
    custom_input: str | None = Field(
        default=None,
        description="Optional custom stdin input to execute code against.",
    )

    @model_validator(mode="before")
    @classmethod
    def resolve_code_field(cls, data: Any) -> Any:
        if isinstance(data, dict):
            code_val = data.get("source_code") or data.get("code")
            if not code_val or not str(code_val).strip():
                raise ValueError("source_code (or code) cannot be empty")
            if len(str(code_val).encode("utf-8")) > 65536:
                raise ValueError("source_code must not exceed 64 KiB when UTF-8 encoded")
            data["source_code"] = str(code_val)
        return data


class RunCodeResponse(BaseModel):
    status: str
    verdict: str
    stdout: str | None = None
    stderr: str | None = None
    error_message: str | None = None
    time_ms: int | None = None
    memory_kb: int | None = None
    results: list[TestCaseResultResponse] = Field(default_factory=list)

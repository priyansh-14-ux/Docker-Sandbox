from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SubmissionCreate(BaseModel):
    problem_id: UUID
    code: str = Field(min_length=1, max_length=65536)
    language: str = Field(default="python", pattern="^python$", max_length=16)

    @field_validator("code")
    @classmethod
    def code_size_limit(cls, code: str) -> str:
        if len(code.encode("utf-8")) > 65536:
            raise ValueError("code must be no larger than 64 KiB when UTF-8 encoded")
        return code


class SubmissionResponse(BaseModel):
    id: UUID
    problem_id: UUID
    status: str
    language: str
    score: Decimal | None
    created_at: datetime

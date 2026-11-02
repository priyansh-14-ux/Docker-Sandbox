from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class LeaderboardEntry(BaseModel):
    rank: int
    student_profile_id: UUID
    student_name: str
    total_score: Decimal

from decimal import Decimal

from pydantic import BaseModel


class AdminStatsResponse(BaseModel):
    total_users: int
    active_users: int
    student_users: int
    faculty_users: int
    total_courses: int
    active_courses: int
    total_offerings: int
    total_labs: int
    total_problems: int
    total_submissions: int
    scored_submissions: int
    average_submission_score: Decimal | None

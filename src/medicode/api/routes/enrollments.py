from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from medicode.api.dependencies import require_roles
from medicode.db.session import get_db_session
from medicode.models.academic import (
    CourseEnrollment,
    CourseOffering,
    EnrollmentStatus,
    OfferingStatus,
)
from medicode.models.identity import Login, RoleName
from medicode.schemas.courses import EnrollmentResponse

router = APIRouter()


@router.post("/offerings/{offering_id}/enroll", response_model=EnrollmentResponse, status_code=201)
async def enroll_in_offering(
    offering_id: UUID,
    account: Annotated[Login, Depends(require_roles(RoleName.STUDENT))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EnrollmentResponse:
    if account.profile is None:
        raise HTTPException(status_code=400, detail="Student profile was not found")
    offering = await session.get(CourseOffering, offering_id)
    if offering is None:
        raise HTTPException(status_code=404, detail="Course offering not found")
    if offering.status not in (OfferingStatus.OPEN, OfferingStatus.ACTIVE):
        raise HTTPException(status_code=409, detail="This offering is not open for enrollment")
    existing = await session.scalar(
        select(CourseEnrollment).where(
            CourseEnrollment.offering_id == offering_id,
            CourseEnrollment.student_profile_id == account.profile.id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Already enrolled in this offering")
    enrollment = CourseEnrollment(
        offering_id=offering_id,
        student_profile_id=account.profile.id,
        enrollment_status=EnrollmentStatus.ACTIVE,
    )
    session.add(enrollment)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Already enrolled in this offering") from exc
    await session.refresh(enrollment)
    return EnrollmentResponse(
        id=enrollment.id,
        offering_id=enrollment.offering_id,
        student_profile_id=enrollment.student_profile_id,
        enrollment_status=str(enrollment.enrollment_status),
    )

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from medicode.models.academic import (
    CourseEnrollment,
    CourseOffering,
    EnrollmentStatus,
    OfferingFaculty,
)
from medicode.models.content import Experiment, Lab, Problem
from medicode.models.identity import Login, RoleName


async def student_has_course_access(
    session: AsyncSession, profile_id: UUID, course_id: UUID
) -> bool:
    enrollment = await session.scalar(
        select(CourseEnrollment.id)
        .join(CourseOffering, CourseOffering.id == CourseEnrollment.offering_id)
        .where(
            CourseOffering.course_id == course_id,
            CourseEnrollment.student_profile_id == profile_id,
            CourseEnrollment.enrollment_status == EnrollmentStatus.ACTIVE,
        )
    )
    return enrollment is not None


async def require_course_manager(account: Login, course_id: UUID, session: AsyncSession) -> None:
    if _role(account) in (RoleName.SUPER_ADMIN, RoleName.INSTITUTE_ADMIN):
        return
    if _role(account) != RoleName.FACULTY or account.profile is None:
        raise HTTPException(status_code=403, detail="Faculty assignment is required")
    assignment = await session.scalar(
        select(OfferingFaculty.id)
        .join(CourseOffering, CourseOffering.id == OfferingFaculty.offering_id)
        .where(
            CourseOffering.course_id == course_id,
            OfferingFaculty.faculty_profile_id == account.profile.id,
            OfferingFaculty.is_active.is_(True),
        )
    )
    if assignment is None:
        raise HTTPException(status_code=403, detail="Faculty assignment is required")


async def course_id_for_lab(session: AsyncSession, lab_id: UUID) -> UUID:
    course_id = await session.scalar(select(Lab.course_id).where(Lab.id == lab_id))
    if course_id is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    return course_id


async def course_id_for_problem(session: AsyncSession, problem: Problem) -> UUID:
    course_id = await session.scalar(
        select(Lab.course_id)
        .join(Experiment, Experiment.lab_id == Lab.id)
        .where(Experiment.id == problem.experiment_id)
    )
    if course_id is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return course_id


def _role(account: Login) -> RoleName | str | None:
    return account.profile.role.name if account.profile else None

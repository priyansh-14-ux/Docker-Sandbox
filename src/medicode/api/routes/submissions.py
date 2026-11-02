from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from medicode.api.dependencies import get_current_login, require_roles
from medicode.db.session import get_db_session
from medicode.models.academic import CourseEnrollment, CourseOffering, EnrollmentStatus
from medicode.models.content import Experiment, Lab, Problem, Submission
from medicode.models.identity import Login, RoleName
from medicode.schemas.submissions import SubmissionCreate, SubmissionResponse
from medicode.services.access import student_has_course_access

router = APIRouter()
ADMIN_ROLES = (RoleName.SUPER_ADMIN, RoleName.INSTITUTE_ADMIN)


@router.post("", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
async def upload_assignment(
    body: SubmissionCreate,
    account: Annotated[Login, Depends(require_roles(RoleName.STUDENT))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Submission:
    if account.profile is None:
        raise HTTPException(status_code=400, detail="Student profile was not found")
    problem = await session.get(Problem, body.problem_id)
    if problem is None or not problem.is_published:
        raise HTTPException(status_code=404, detail="Problem not found")

    experiment = await session.get(Experiment, problem.experiment_id)
    lab = await session.get(Lab, experiment.lab_id) if experiment else None
    if not experiment or not experiment.is_published or not lab or not lab.is_published:
        raise HTTPException(status_code=404, detail="Problem not found")
    if not await student_has_course_access(session, account.profile.id, lab.course_id):
        raise HTTPException(status_code=403, detail="Active course enrollment is required")

    enrollment_id = await session.scalar(
        select(CourseEnrollment.id)
        .join(CourseOffering, CourseOffering.id == CourseEnrollment.offering_id)
        .where(
            CourseOffering.course_id == lab.course_id,
            CourseEnrollment.student_profile_id == account.profile.id,
            CourseEnrollment.enrollment_status == EnrollmentStatus.ACTIVE,
        )
        .limit(1)
    )
    submission = Submission(
        student_profile_id=account.profile.id,
        problem_id=problem.id,
        course_enrollment_id=enrollment_id,
        source_code=body.code,
        language=body.language,
        status="RECEIVED",
    )
    session.add(submission)
    await session.commit()
    await session.refresh(submission)
    return submission


@router.get("/{submission_id}", response_model=SubmissionResponse)
async def get_submission(
    submission_id: UUID,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Submission:
    submission = await session.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    if _role(account) not in ADMIN_ROLES and (
        account.profile is None or submission.student_profile_id != account.profile.id
    ):
        raise HTTPException(status_code=403, detail="You may only view your own submissions")
    return submission


@router.get("", response_model=list[SubmissionResponse])
async def list_submissions(
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    problem_id: UUID | None = None,
    user_id: UUID | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[Submission]:
    if _role(account) == RoleName.STUDENT:
        if account.profile is None:
            return []
        target_id = account.profile.id
        if user_id is not None and user_id != target_id:
            raise HTTPException(status_code=403, detail="You may only view your own submissions")
    elif _role(account) in ADMIN_ROLES:
        target_id = user_id
    else:
        raise HTTPException(status_code=403, detail="Student or administrator access is required")

    statement = select(Submission).order_by(Submission.created_at.desc())
    if target_id is not None:
        statement = statement.where(Submission.student_profile_id == target_id)
    if problem_id is not None:
        statement = statement.where(Submission.problem_id == problem_id)
    rows = await session.scalars(statement.offset(offset).limit(limit))
    return list(rows)


def _role(account: Login) -> RoleName | str | None:
    return account.profile.role.name if account.profile else None

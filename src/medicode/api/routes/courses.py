from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from medicode.api.dependencies import get_current_login, require_roles
from medicode.db.session import get_db_session
from medicode.models.academic import (
    AcademicTerm,
    Course,
    CourseEnrollment,
    CourseOffering,
    OfferingFaculty,
    OfferingStatus,
    Program,
)
from medicode.models.content import Submission
from medicode.models.identity import Department, Login, Profile, Role, RoleName
from medicode.schemas.courses import (
    CourseCreate,
    CourseOfferingCreate,
    CourseResponse,
    CourseUpdate,
    FacultyAssignmentCreate,
)
from medicode.schemas.leaderboard import LeaderboardEntry
from medicode.services.access import require_course_manager, student_has_course_access

router = APIRouter()
ADMIN_ROLES = (RoleName.SUPER_ADMIN, RoleName.INSTITUTE_ADMIN)
CONTENT_ROLES = (*ADMIN_ROLES, RoleName.FACULTY)


@router.get("", response_model=list[CourseResponse])
async def list_courses(
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[Course]:
    return list(
        await session.scalars(
            select(Course).where(Course.is_active.is_(True)).order_by(Course.title)
        )
    )


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    body: CourseCreate,
    account: Annotated[Login, Depends(require_roles(*CONTENT_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Course:
    if await session.get(Department, body.department_id) is None:
        raise HTTPException(status_code=404, detail="Department not found")
    course = Course(**body.model_dump())
    session.add(course)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Course code already exists for this department"
        ) from exc
    await session.refresh(course)
    return course


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: UUID,
    _account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Course:
    course = await session.get(Course, course_id)
    if course is None or not course.is_active:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.get("/{course_id}/offerings")
async def list_course_offerings(
    course_id: UUID,
    _account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict[str, object]]:
    if await session.get(Course, course_id) is None:
        raise HTTPException(status_code=404, detail="Course not found")
    offerings = await session.scalars(
        select(CourseOffering)
        .where(
            CourseOffering.course_id == course_id,
            CourseOffering.status.in_((OfferingStatus.OPEN, OfferingStatus.ACTIVE)),
        )
        .order_by(CourseOffering.created_at.desc())
    )
    return [
        {
            "id": offering.id,
            "academic_term_id": offering.academic_term_id,
            "program_id": offering.program_id,
            "semester_number": offering.semester_number,
            "section": offering.section,
            "offering_code": offering.offering_code,
            "status": str(offering.status),
        }
        for offering in offerings
    ]


@router.get("/{course_id}/leaderboard", response_model=list[LeaderboardEntry])
async def get_course_leaderboard(
    course_id: UUID,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=50, ge=1, le=100),
) -> list[LeaderboardEntry]:
    course = await session.get(Course, course_id)
    if course is None or not course.is_active:
        raise HTTPException(status_code=404, detail="Course not found")
    role = _role(account)
    if role == RoleName.STUDENT:
        if account.profile is None or not await student_has_course_access(
            session, account.profile.id, course_id
        ):
            raise HTTPException(status_code=403, detail="Active course enrollment is required")
    else:
        await require_course_manager(account, course_id, session)

    best_scores = (
        select(
            Submission.student_profile_id.label("student_profile_id"),
            Submission.problem_id.label("problem_id"),
            func.max(Submission.score).label("best_score"),
        )
        .join(CourseEnrollment, CourseEnrollment.id == Submission.course_enrollment_id)
        .join(CourseOffering, CourseOffering.id == CourseEnrollment.offering_id)
        .where(CourseOffering.course_id == course_id, Submission.score.is_not(None))
        .group_by(Submission.student_profile_id, Submission.problem_id)
        .subquery()
    )
    student_totals = (
        select(
            best_scores.c.student_profile_id.label("profile_id"),
            func.sum(best_scores.c.best_score).label("total_score"),
        )
        .group_by(best_scores.c.student_profile_id)
        .subquery()
    )
    rows = await session.execute(
        select(Profile.id, Profile.full_name, student_totals.c.total_score)
        .join(student_totals, student_totals.c.profile_id == Profile.id)
        .order_by(student_totals.c.total_score.desc(), Profile.full_name)
        .limit(limit)
    )
    result: list[LeaderboardEntry] = []
    previous_score: Decimal | None = None
    current_rank = 0
    for index, row in enumerate(rows, start=1):
        score = Decimal(row.total_score)
        if score != previous_score:
            current_rank = index
            previous_score = score
        result.append(
            LeaderboardEntry(
                rank=current_rank,
                student_profile_id=row.id,
                student_name=row.full_name,
                total_score=score,
            )
        )
    return result


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: UUID,
    changes: CourseUpdate,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Course:
    course = await session.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    await require_course_manager(account, course.id, session)
    for key, value in changes.model_dump(exclude_unset=True).items():
        setattr(course, key, value)
    await session.commit()
    await session.refresh(course)
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_course(
    course_id: UUID,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    course = await session.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    await require_course_manager(account, course.id, session)
    course.is_active = False
    await session.commit()


@router.post("/{course_id}/offerings", status_code=status.HTTP_201_CREATED)
async def create_course_offering(
    course_id: UUID,
    body: CourseOfferingCreate,
    account: Annotated[Login, Depends(require_roles(*CONTENT_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str | UUID]:
    course = await session.get(Course, course_id)
    if course is None or not course.is_active:
        raise HTTPException(status_code=404, detail="Course not found")
    if (
        await session.get(AcademicTerm, body.academic_term_id) is None
        or await session.get(Program, body.program_id) is None
    ):
        raise HTTPException(status_code=404, detail="Academic term or program not found")
    offering = CourseOffering(
        course_id=course_id,
        **body.model_dump(),
        status=OfferingStatus.OPEN,
    )
    session.add(offering)
    if _role(account) == RoleName.FACULTY:
        if account.profile is None:
            raise HTTPException(status_code=400, detail="Faculty profile was not found")
        offering.faculty_assignments.append(
            OfferingFaculty(
                faculty_profile_id=account.profile.id,
                assignment_role="COORDINATOR",
                is_active=True,
            )
        )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Offering conflicts with an existing offering"
        ) from exc
    await session.refresh(offering)
    return {"id": offering.id, "course_id": course_id, "status": str(offering.status)}


@router.post("/offerings/{offering_id}/faculty", status_code=status.HTTP_201_CREATED)
async def assign_faculty(
    offering_id: UUID,
    body: FacultyAssignmentCreate,
    _admin: Annotated[Login, Depends(require_roles(*ADMIN_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, UUID | str]:
    offering = await session.get(CourseOffering, offering_id)
    if offering is None:
        raise HTTPException(status_code=404, detail="Course offering not found")
    is_faculty = await session.scalar(
        select(Profile.id)
        .join(Role, Role.id == Profile.role_id)
        .where(Profile.id == body.faculty_profile_id, Role.name == RoleName.FACULTY)
    )
    if is_faculty is None:
        raise HTTPException(status_code=404, detail="Faculty profile not found")
    assignment_role = body.assignment_role.strip().upper()
    if not assignment_role:
        raise HTTPException(status_code=422, detail="assignment_role cannot be empty")
    assignment = OfferingFaculty(
        offering_id=offering_id,
        faculty_profile_id=body.faculty_profile_id,
        assignment_role=assignment_role,
        is_active=True,
    )
    session.add(assignment)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Faculty is already assigned to this offering"
        ) from exc
    await session.refresh(assignment)
    return {
        "id": assignment.id,
        "offering_id": offering_id,
        "faculty_profile_id": body.faculty_profile_id,
        "assignment_role": assignment.assignment_role,
    }


def _role(account: Login) -> RoleName | str | None:
    return account.profile.role.name if account.profile else None

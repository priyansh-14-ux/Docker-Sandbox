from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from medicode.api.dependencies import require_roles
from medicode.db.session import get_db_session
from medicode.models.academic import AcademicTerm, Course, CourseOffering, Program, TermType
from medicode.models.content import Lab, Problem, Submission
from medicode.models.identity import Department, Login, Profile, Role, RoleName
from medicode.schemas.academic import (
    AcademicTermCreate,
    AcademicTermResponse,
    DepartmentCreate,
    DepartmentResponse,
    ProgramCreate,
    ProgramResponse,
)
from medicode.schemas.admin import AdminStatsResponse

router = APIRouter()
ADMIN_ROLES = (RoleName.SUPER_ADMIN, RoleName.INSTITUTE_ADMIN)


@router.get("/departments", response_model=list[DepartmentResponse])
async def list_departments(
    _admin: Annotated[Login, Depends(require_roles(*ADMIN_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[Department]:
    return list(await session.scalars(select(Department).order_by(Department.name)))


@router.post("/departments", response_model=DepartmentResponse, status_code=201)
async def create_department(
    body: DepartmentCreate,
    _admin: Annotated[Login, Depends(require_roles(*ADMIN_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Department:
    department = Department(name=body.name.strip(), code=body.code.strip().upper())
    session.add(department)
    return await commit_unique(session, department, "Department code already exists")


@router.get("/programs", response_model=list[ProgramResponse])
async def list_programs(
    _admin: Annotated[Login, Depends(require_roles(*ADMIN_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[Program]:
    return list(await session.scalars(select(Program).order_by(Program.name)))


@router.post("/programs", response_model=ProgramResponse, status_code=201)
async def create_program(
    body: ProgramCreate,
    _admin: Annotated[Login, Depends(require_roles(*ADMIN_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Program:
    if await session.get(Department, body.department_id) is None:
        raise HTTPException(status_code=404, detail="Department not found")
    data = body.model_dump()
    data["code"] = body.code.strip().upper()
    program = Program(**data)
    session.add(program)
    return await commit_unique(session, program, "Program code already exists for this department")


@router.get("/academic-terms", response_model=list[AcademicTermResponse])
async def list_academic_terms(
    _admin: Annotated[Login, Depends(require_roles(*ADMIN_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AcademicTerm]:
    return list(await session.scalars(select(AcademicTerm).order_by(AcademicTerm.starts_on.desc())))


@router.post("/academic-terms", response_model=AcademicTermResponse, status_code=201)
async def create_academic_term(
    body: AcademicTermCreate,
    _admin: Annotated[Login, Depends(require_roles(*ADMIN_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AcademicTerm:
    data = body.model_dump()
    data["term_type"] = TermType(body.term_type)
    term = AcademicTerm(**data, is_active=True)
    session.add(term)
    return await commit_unique(session, term, "Academic term name already exists")


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_stats(
    _admin: Annotated[Login, Depends(require_roles(*ADMIN_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminStatsResponse:
    total_users = await session.scalar(select(func.count(Login.id))) or 0
    active_users = (
        await session.scalar(select(func.count(Login.id)).where(Login.is_active.is_(True))) or 0
    )
    student_users = (
        await session.scalar(
            select(func.count(Login.id))
            .join(Profile, Profile.login_id == Login.id)
            .join(Role, Role.id == Profile.role_id)
            .where(Role.name == RoleName.STUDENT)
        )
        or 0
    )
    faculty_users = (
        await session.scalar(
            select(func.count(Login.id))
            .join(Profile, Profile.login_id == Login.id)
            .join(Role, Role.id == Profile.role_id)
            .where(Role.name == RoleName.FACULTY)
        )
        or 0
    )
    total_courses = await session.scalar(select(func.count(Course.id))) or 0
    active_courses = (
        await session.scalar(select(func.count(Course.id)).where(Course.is_active.is_(True))) or 0
    )
    total_offerings = await session.scalar(select(func.count(CourseOffering.id))) or 0
    total_labs = await session.scalar(select(func.count(Lab.id))) or 0
    total_problems = await session.scalar(select(func.count(Problem.id))) or 0
    total_submissions = await session.scalar(select(func.count(Submission.id))) or 0
    scored_submissions = (
        await session.scalar(select(func.count(Submission.id)).where(Submission.score.is_not(None)))
        or 0
    )
    average_score = await session.scalar(select(func.avg(Submission.score)))
    return AdminStatsResponse(
        total_users=total_users,
        active_users=active_users,
        student_users=student_users,
        faculty_users=faculty_users,
        total_courses=total_courses,
        active_courses=active_courses,
        total_offerings=total_offerings,
        total_labs=total_labs,
        total_problems=total_problems,
        total_submissions=total_submissions,
        scored_submissions=scored_submissions,
        average_submission_score=average_score,
    )


async def commit_unique(session: AsyncSession, row, error_detail: str):
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=error_detail) from exc
    await session.refresh(row)
    return row

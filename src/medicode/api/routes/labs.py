from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from medicode.api.dependencies import get_current_login
from medicode.db.session import get_db_session
from medicode.models.academic import Course
from medicode.models.content import Experiment, Lab, Problem, TestCase
from medicode.models.identity import Login, RoleName
from medicode.schemas.courses import (
    ExperimentCreate,
    ExperimentResponse,
    LabCreate,
    LabResponse,
    ProblemCreate,
    ProblemResponse,
    PublishUpdate,
    TestCaseCreate,
    TestCaseResponse,
    VisibleTestCase,
)
from medicode.services.access import (
    course_id_for_lab,
    course_id_for_problem,
    require_course_manager,
    student_has_course_access,
)

router = APIRouter()


@router.get("/{course_id}/labs", response_model=list[LabResponse])
async def list_course_labs(
    course_id: UUID,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[Lab]:
    if await session.get(Course, course_id) is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if _role(account) == RoleName.STUDENT:
        if account.profile is None or not await student_has_course_access(
            session, account.profile.id, course_id
        ):
            raise HTTPException(status_code=403, detail="Active course enrollment is required")
        published_only = True
    else:
        await require_course_manager(account, course_id, session)
        published_only = False
    statement = select(Lab).where(Lab.course_id == course_id).order_by(Lab.sort_order)
    if published_only:
        statement = statement.where(Lab.is_published.is_(True))
    return list(await session.scalars(statement))


@router.post("/{course_id}/labs", response_model=LabResponse, status_code=201)
async def create_lab(
    course_id: UUID,
    body: LabCreate,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Lab:
    if await session.get(Course, course_id) is None:
        raise HTTPException(status_code=404, detail="Course not found")
    await require_course_manager(account, course_id, session)
    lab = Lab(course_id=course_id, **body.model_dump())
    session.add(lab)
    await session.commit()
    await session.refresh(lab)
    return lab


@router.patch("/labs/{lab_id}/publication", response_model=LabResponse)
async def publish_lab(
    lab_id: UUID,
    body: PublishUpdate,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Lab:
    lab = await session.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    await require_course_manager(account, lab.course_id, session)
    lab.is_published = body.is_published
    await session.commit()
    await session.refresh(lab)
    return lab


@router.get("/labs/{lab_id}/experiments", response_model=list[ExperimentResponse])
async def list_lab_experiments(
    lab_id: UUID,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[Experiment]:
    lab = await session.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    if _role(account) == RoleName.STUDENT:
        if (
            not lab.is_published
            or account.profile is None
            or not await student_has_course_access(session, account.profile.id, lab.course_id)
        ):
            raise HTTPException(
                status_code=403, detail="Published content and active enrollment are required"
            )
        published_only = True
    else:
        await require_course_manager(account, lab.course_id, session)
        published_only = False
    statement = (
        select(Experiment).where(Experiment.lab_id == lab_id).order_by(Experiment.sort_order)
    )
    if published_only:
        statement = statement.where(Experiment.is_published.is_(True))
    return list(await session.scalars(statement))


@router.post("/labs/{lab_id}/experiments", response_model=ExperimentResponse, status_code=201)
async def create_experiment(
    lab_id: UUID,
    body: ExperimentCreate,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Experiment:
    lab = await session.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    await require_course_manager(account, lab.course_id, session)
    experiment = Experiment(lab_id=lab_id, **body.model_dump())
    session.add(experiment)
    await session.commit()
    await session.refresh(experiment)
    return experiment


@router.patch("/experiments/{experiment_id}/publication", response_model=ExperimentResponse)
async def publish_experiment(
    experiment_id: UUID,
    body: PublishUpdate,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Experiment:
    experiment = await session.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    await require_course_manager(
        account, await course_id_for_lab(session, experiment.lab_id), session
    )
    experiment.is_published = body.is_published
    await session.commit()
    await session.refresh(experiment)
    return experiment


@router.get("/experiments/{experiment_id}/problems")
async def list_experiment_problems(
    experiment_id: UUID,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict[str, object]]:
    experiment = await session.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    lab = await session.get(Lab, experiment.lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail="Lab not found")
    if _role(account) == RoleName.STUDENT:
        if (
            not experiment.is_published
            or not lab.is_published
            or account.profile is None
            or not await student_has_course_access(session, account.profile.id, lab.course_id)
        ):
            raise HTTPException(
                status_code=403, detail="Published content and active enrollment are required"
            )
        published_only = True
    else:
        await require_course_manager(account, lab.course_id, session)
        published_only = False
    statement = (
        select(Problem).where(Problem.experiment_id == experiment_id).order_by(Problem.created_at)
    )
    if published_only:
        statement = statement.where(Problem.is_published.is_(True))
    problems = await session.scalars(statement)
    return [
        {
            "id": problem.id,
            "title": problem.title,
            "difficulty": problem.difficulty,
            "statement": problem.statement,
        }
        for problem in problems
    ]


@router.post("/experiments/{experiment_id}/problems", status_code=201)
async def create_problem(
    experiment_id: UUID,
    body: ProblemCreate,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, UUID | str | int]:
    experiment = await session.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    course_id = await course_id_for_lab(session, experiment.lab_id)
    await require_course_manager(account, course_id, session)
    problem = Problem(experiment_id=experiment_id, **body.model_dump())
    session.add(problem)
    await session.commit()
    await session.refresh(problem)
    return {"id": problem.id, "title": problem.title, "difficulty": problem.difficulty}


@router.patch("/problems/{problem_id}/publication")
async def publish_problem(
    problem_id: UUID,
    body: PublishUpdate,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, UUID | bool]:
    problem = await session.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    await require_course_manager(account, await course_id_for_problem(session, problem), session)
    problem.is_published = body.is_published
    await session.commit()
    return {"id": problem.id, "is_published": problem.is_published}


@router.post("/problems/{problem_id}/test-cases", response_model=TestCaseResponse, status_code=201)
async def create_test_case(
    problem_id: UUID,
    body: TestCaseCreate,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TestCase:
    problem = await session.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    await require_course_manager(account, await course_id_for_problem(session, problem), session)
    test_case = TestCase(problem_id=problem_id, **body.model_dump())
    session.add(test_case)
    await session.commit()
    await session.refresh(test_case)
    return test_case


@router.get("/problems/{problem_id}", response_model=ProblemResponse)
async def get_problem(
    problem_id: UUID,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProblemResponse:
    problem = await session.get(Problem, problem_id)
    if problem is None or not problem.is_published:
        raise HTTPException(status_code=404, detail="Problem not found")
    experiment = await session.get(Experiment, problem.experiment_id)
    lab = await session.get(Lab, experiment.lab_id) if experiment else None
    if not experiment or not experiment.is_published or not lab or not lab.is_published:
        raise HTTPException(status_code=404, detail="Problem not found")

    role = _role(account)
    if role == RoleName.STUDENT:
        if account.profile is None or not await student_has_course_access(
            session, account.profile.id, lab.course_id
        ):
            raise HTTPException(status_code=403, detail="Active course enrollment is required")
        cases = await session.scalars(
            select(TestCase)
            .where(TestCase.problem_id == problem_id, TestCase.is_hidden.is_(False))
            .order_by(TestCase.sort_order)
        )
    elif role == RoleName.FACULTY:
        await require_course_manager(account, lab.course_id, session)
        cases = await session.scalars(
            select(TestCase).where(TestCase.problem_id == problem_id).order_by(TestCase.sort_order)
        )
    elif role in (RoleName.SUPER_ADMIN, RoleName.INSTITUTE_ADMIN):
        cases = await session.scalars(
            select(TestCase).where(TestCase.problem_id == problem_id).order_by(TestCase.sort_order)
        )
    else:
        raise HTTPException(status_code=403, detail="Problem access is not permitted")
    return ProblemResponse(
        id=problem.id,
        title=problem.title,
        statement=problem.statement,
        difficulty=problem.difficulty,
        time_limit_ms=problem.time_limit_ms,
        memory_limit_mb=problem.memory_limit_mb,
        test_cases=[
            VisibleTestCase(
                id=case.id,
                input_data=case.input_data,
                expected_output=case.expected_output,
                points=case.points,
                is_hidden=case.is_hidden,
            )
            for case in cases
        ],
    )


def _role(account: Login) -> RoleName | str | None:
    return account.profile.role.name if account.profile else None

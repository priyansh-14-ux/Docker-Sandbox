import asyncio
import json
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from medicode.api.dependencies import get_current_login, require_roles
from medicode.core.logging import get_logger, submission_id_ctx
from medicode.core.security import read_access_token
from medicode.db.session import AsyncSessionLocal, get_db_session
from medicode.models.academic import CourseEnrollment, CourseOffering, EnrollmentStatus
from medicode.models.content import Experiment, Lab, Problem, Submission, TestCase
from medicode.models.identity import AuthSession, Login, RoleName
from medicode.schemas.submissions import (
    RunCodeRequest,
    RunCodeResponse,
    SubmissionCreate,
    SubmissionDetailResponse,
    SubmissionQueuedResponse,
    SubmissionResponse,
    TestCaseResultResponse,
)
from medicode.services.access import student_has_course_access
from medicode.services.execution.base import ExecutionProvider
from medicode.services.execution.factory import get_execution_provider
from medicode.services.execution.models import ExecutionLimits, ExecutionRequest
from medicode.services.rate_limiter import rate_limit_runs, rate_limit_submissions
from medicode.services.verdict import (
    Verdict,
    map_execution_result_to_verdict,
    sanitize_output,
)
from medicode.workers.submission_worker import enqueue_submission

logger = get_logger(__name__)

router = APIRouter()
ADMIN_ROLES = (RoleName.SUPER_ADMIN, RoleName.INSTITUTE_ADMIN)


def _role(account: Login) -> RoleName | str | None:
    return account.profile.role.name if account.profile else None


@router.post(
    "",
    response_model=SubmissionQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit solution for judging",
    description="Saves the submission as queued, checks permissions and rate limits, and enqueues it for isolated sandbox judging.",
    dependencies=[Depends(rate_limit_submissions)],
)
async def create_submission(
    body: SubmissionCreate,
    account: Annotated[Login, Depends(require_roles(RoleName.STUDENT))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    background_tasks: BackgroundTasks,
) -> SubmissionQueuedResponse:
    if account.profile is None:
        raise HTTPException(status_code=400, detail="Student profile was not found")

    problem = await session.get(Problem, body.problem_id)
    if problem is None or not problem.is_published:
        raise HTTPException(status_code=404, detail="Problem not found")

    # Check course enrollment if problem is tied to a lab/experiment
    enrollment_id: UUID | None = None
    if problem.experiment_id:
        experiment = await session.get(Experiment, problem.experiment_id)
        if experiment is not None and isinstance(experiment, Experiment) and experiment.is_published:
            lab = await session.get(Lab, experiment.lab_id)
            if lab is not None and isinstance(lab, Lab) and lab.is_published:
                has_access = await student_has_course_access(session, account.profile.id, lab.course_id)
                if not has_access:
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
        id=uuid4(),
        student_profile_id=account.profile.id,
        problem_id=problem.id,
        course_enrollment_id=enrollment_id,
        source_code=body.source_code,
        language=body.language.value,
        status="QUEUED",
    )
    session.add(submission)
    await session.commit()
    await session.refresh(submission)

    submission_id_ctx.set(str(submission.id))
    logger.info("Created submission %s for problem %s", submission.id, problem.id)

    # Dispatch to background queue worker
    await enqueue_submission(submission.id, background_tasks=background_tasks)

    return SubmissionQueuedResponse(
        submission_id=submission.id,
        status="queued",
        message="Submission queued for isolated sandbox execution.",
    )


@router.get(
    "/{submission_id}",
    response_model=SubmissionDetailResponse,
    summary="Get submission result",
    description="Fetches submission status and per-test verdicts. Hidden test case inputs and outputs are masked for students.",
)
async def get_submission(
    submission_id: UUID,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubmissionDetailResponse:
    submission = await session.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(selectinload(Submission.results))
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    is_admin = _role(account) in ADMIN_ROLES
    if not is_admin and (account.profile is None or submission.student_profile_id != account.profile.id):
        raise HTTPException(status_code=403, detail="You may only view your own submissions")

    # Format per-test results with hidden-test data masking
    results_list: list[TestCaseResultResponse] = []
    for res in submission.results:
        # Never reveal stdout or stderr for hidden test cases
        show_details = (not res.is_hidden) or is_admin
        results_list.append(
            TestCaseResultResponse(
                test_number=res.test_number,
                verdict=res.verdict,
                time_ms=res.time_ms,
                memory_kb=res.memory_kb,
                is_hidden=res.is_hidden,
                stdout=res.stdout if show_details else None,
                stderr=res.stderr if show_details else None,
                error_message=res.error_message if show_details else None,
            )
        )

    return SubmissionDetailResponse(
        id=submission.id,
        problem_id=submission.problem_id,
        status=submission.status,
        verdict=submission.verdict,
        language=submission.language,
        score=submission.score,
        time_ms=submission.time_ms,
        memory_kb=submission.memory_kb,
        passed_test_cases=submission.passed_test_cases or 0,
        total_test_cases=submission.total_test_cases or 0,
        error_message=submission.error_message,
        results=results_list,
        created_at=submission.created_at,
    )


@router.post(
    "/run",
    response_model=RunCodeResponse,
    summary="Quick run against sample tests or custom input",
    description="Runs untrusted code synchronously against visible sample tests or custom stdin. Does not persist as a graded submission.",
    dependencies=[Depends(rate_limit_runs)],
)
async def run_code(
    body: RunCodeRequest,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    provider: Annotated[ExecutionProvider, Depends(get_execution_provider)],
) -> RunCodeResponse:
    requests: list[ExecutionRequest] = []
    expected_outputs: list[str | None] = []

    if body.custom_input is not None:
        # Run against custom user stdin
        requests.append(
            ExecutionRequest(
                source_code=body.source_code,
                stdin=body.custom_input,
                expected_output=None,
            )
        )
        expected_outputs.append(None)
    elif body.problem_id is not None:
        # Fetch problem's visible sample test cases only
        problem = await session.get(Problem, body.problem_id)
        if problem is None or not problem.is_published:
            raise HTTPException(status_code=404, detail="Problem not found")

        visible_tests = await session.scalars(
            select(TestCase)
            .where(TestCase.problem_id == body.problem_id, TestCase.is_hidden.is_(False))
            .order_by(TestCase.sort_order)
        )
        tests_list = list(visible_tests)
        if not tests_list:
            raise HTTPException(
                status_code=400,
                detail="This problem has no public sample test cases. Provide custom_input to run.",
            )

        for tc in tests_list:
            requests.append(
                ExecutionRequest(
                    source_code=body.source_code,
                    stdin=tc.input_data,
                    expected_output=tc.expected_output,
                )
            )
            expected_outputs.append(tc.expected_output)
    else:
        # Fallback run with empty input
        requests.append(ExecutionRequest(source_code=body.source_code, stdin="", expected_output=None))
        expected_outputs.append(None)

    # Execute via sandbox provider with safe limits
    limits = ExecutionLimits(
        cpu_time_limit_sec=1.0,
        wall_time_limit_sec=3.0,
        memory_limit_kb=128_000,
        enable_network=False,
    )
    exec_results = await provider.execute_batch(requests, limits)

    test_case_results: list[TestCaseResultResponse] = []
    first_failing_verdict: str | None = None
    all_passed = True
    max_time_ms = 0
    max_memory_kb = 0

    for idx, (res, exp) in enumerate(zip(exec_results, expected_outputs, strict=False), start=1):
        verdict, err = map_execution_result_to_verdict(res, exp, mode="ignore_whitespace")
        time_ms = int(res.time_sec * 1000) if res.time_sec is not None else None
        memory_kb = res.memory_kb

        if time_ms and time_ms > max_time_ms:
            max_time_ms = time_ms
        if memory_kb and memory_kb > max_memory_kb:
            max_memory_kb = memory_kb

        if verdict != Verdict.AC:
            all_passed = False
            if first_failing_verdict is None:
                first_failing_verdict = verdict.value

        test_case_results.append(
            TestCaseResultResponse(
                test_number=idx,
                verdict=verdict.value,
                time_ms=time_ms,
                memory_kb=memory_kb,
                is_hidden=False,
                stdout=sanitize_output(res.stdout),
                stderr=sanitize_output(res.stderr),
                error_message=err,
            )
        )

    overall_verdict = Verdict.AC.value if all_passed else (first_failing_verdict or Verdict.WA.value)
    primary_res = test_case_results[0] if test_case_results else None

    return RunCodeResponse(
        status="completed",
        verdict=overall_verdict,
        stdout=primary_res.stdout if primary_res else None,
        stderr=primary_res.stderr if primary_res else None,
        error_message=primary_res.error_message if primary_res else None,
        time_ms=max_time_ms or None,
        memory_kb=max_memory_kb or None,
        results=test_case_results,
    )


@router.get(
    "/{submission_id}/events",
    summary="Live SSE status stream for submission",
    description="Streams Server-Sent Events (SSE) indicating judging progress and final result.",
)
async def stream_submission_events(
    submission_id: UUID,
    request: Request,
    token: str | None = None,
) -> StreamingResponse:
    """Streams live Server-Sent Events (SSE) until submission finishes judging."""
    auth_header = request.headers.get("Authorization")
    raw_token = token
    if not raw_token and auth_header and auth_header.startswith("Bearer "):
        raw_token = auth_header.replace("Bearer ", "", 1).strip()

    if not raw_token:
        raise HTTPException(status_code=401, detail="Authentication token required for SSE stream")

    payload = read_access_token(raw_token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    async def event_generator():
        # Validate submission access once
        async with AsyncSessionLocal() as session:
            account = await session.scalar(
                select(Login)
                .join(AuthSession, AuthSession.login_id == Login.id)
                .where(
                    AuthSession.token_id == payload["jti"],
                    AuthSession.login_id == UUID(payload["sub"]),
                    AuthSession.revoked_at.is_(None),
                    Login.is_active.is_(True),
                )
                .options(selectinload(Login.profile).selectinload(Login.profile.property.mapper.class_.role))
            )
            if account is None:
                yield f"event: error\ndata: {json.dumps({'detail': 'Unauthorized'})}\n\n"
                return

        # Poll database status with short backoff until terminal state
        terminal_states = {"COMPLETED", "ERROR", "FAILED"}
        while True:
            if await request.is_disconnected():
                break

            async with AsyncSessionLocal() as session:
                sub = await session.get(Submission, submission_id)
                if sub is None:
                    yield f"event: error\ndata: {json.dumps({'detail': 'Submission not found'})}\n\n"
                    break

                event_data = {
                    "submission_id": str(sub.id),
                    "status": sub.status,
                    "verdict": sub.verdict,
                    "score": str(sub.score) if sub.score is not None else None,
                    "time_ms": sub.time_ms,
                    "memory_kb": sub.memory_kb,
                }
                yield f"event: update\ndata: {json.dumps(event_data)}\n\n"

                if sub.status.upper() in terminal_states:
                    yield f"event: done\ndata: {json.dumps(event_data)}\n\n"
                    break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("", response_model=list[SubmissionResponse], summary="List submissions")
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

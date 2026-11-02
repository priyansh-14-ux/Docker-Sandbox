from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from medicode.core.config import get_settings
from medicode.core.logging import get_logger, submission_id_ctx
from medicode.models.content import Problem, Submission, SubmissionResult, TestCase
from medicode.services.cache import (
    compute_cache_key,
    get_cached_submission_result,
    set_cached_submission_result,
)
from medicode.services.execution.base import ExecutionProvider
from medicode.services.execution.models import ExecutionLimits, ExecutionRequest, ExecutionResult
from medicode.services.rate_limiter import get_redis_client
from medicode.services.realtime import publish_submission_update
from medicode.services.verdict import (
    Verdict,
    aggregate_verdicts,
    map_execution_result_to_verdict,
    sanitize_output,
)

logger = get_logger(__name__)


async def judge_submission(
    session: AsyncSession,
    submission_id: UUID,
    provider: ExecutionProvider,
) -> Submission:
    """
    Executes and grades a submission against all associated test cases in an isolated sandbox.
    """
    submission_id_ctx.set(str(submission_id))
    logger.info("Starting judging for submission %s", submission_id)

    submission = await session.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(selectinload(Submission.problem).selectinload(Problem.test_cases))
    )

    if submission is None:
        logger.error("Submission %s not found for judging", submission_id)
        raise ValueError(f"Submission {submission_id} not found")

    problem = submission.problem
    if problem is None:
        logger.error("Submission %s problem not found", submission_id)
        submission.status = "ERROR"
        submission.verdict = Verdict.IE
        submission.error_message = "Associated problem not found"
        await session.commit()
        return submission

    # Set status to RUNNING
    submission.status = "RUNNING"
    await session.commit()
    await publish_submission_update(submission.id, "RUNNING")

    settings = get_settings()
    redis = get_redis_client()
    test_cases: list[TestCase] = sorted(problem.test_cases, key=lambda tc: tc.sort_order)

    # 1. Check Cache
    test_sig = ",".join(f"{tc.id}:{tc.sort_order}:{tc.points}" for tc in test_cases)
    cache_key = compute_cache_key(problem.id, submission.source_code, test_sig)

    if settings.cache_results_enabled and redis:
        cached = await get_cached_submission_result(redis, cache_key)
        if cached:
            logger.info("Cache hit for submission %s", submission_id)
            submission.verdict = cached["verdict"]
            submission.score = Decimal(str(cached["score"])) if cached.get("score") is not None else None
            submission.time_ms = cached.get("time_ms")
            submission.memory_kb = cached.get("memory_kb")
            submission.passed_test_cases = cached.get("passed_test_cases", 0)
            submission.total_test_cases = cached.get("total_test_cases", len(test_cases))
            submission.status = "COMPLETED"

            # Create cached results
            for r in cached.get("results", []):
                tc_result = SubmissionResult(
                    submission_id=submission.id,
                    test_case_id=UUID(r["test_case_id"]) if r.get("test_case_id") else None,
                    test_number=r["test_number"],
                    verdict=r["verdict"],
                    time_ms=r.get("time_ms"),
                    memory_kb=r.get("memory_kb"),
                    stdout=r.get("stdout"),
                    stderr=r.get("stderr"),
                    error_message=r.get("error_message"),
                    is_hidden=r.get("is_hidden", False),
                )
                session.add(tc_result)

            await session.commit()
            await publish_submission_update(submission.id, "COMPLETED", submission.score)
            return submission

    # 2. Build limits and requests
    cpu_limit = float(problem.time_limit_ms) / 1000.0 if problem.time_limit_ms else settings.default_cpu_time_limit_sec
    mem_limit = (problem.memory_limit_mb * 1024) if problem.memory_limit_mb else settings.default_memory_limit_kb

    limits = ExecutionLimits(
        cpu_time_limit_sec=cpu_limit,
        wall_time_limit_sec=max(cpu_limit * 2, settings.default_wall_time_limit_sec),
        memory_limit_kb=mem_limit,
        stack_limit_kb=settings.default_stack_limit_kb,
        max_processes_and_or_threads=settings.default_max_processes,
        max_file_size_kb=settings.default_max_file_size_kb,
        enable_network=settings.default_enable_network,
        number_of_runs=1,
    )

    requests = [
        ExecutionRequest(
            source_code=submission.source_code,
            stdin=tc.input_data,
            expected_output=tc.expected_output,
            language_id=settings.python_language_id,
        )
        for tc in test_cases
    ]

    try:
        # Execute batch via provider
        exec_results = await provider.execute_batch(requests, limits)

        # Retry once if any test resulted in Internal Error (IE / status 13)
        if any(r.status_id == 13 for r in exec_results):
            logger.warning("Internal Error returned from sandbox for submission %s, retrying once", submission_id)
            exec_results = await provider.execute_batch(requests, limits)

        # 3. Grade each test case
        comparison_mode = getattr(problem, "comparison_mode", "ignore_whitespace")
        test_verdicts_data: list[tuple[Verdict, int | None, int | None]] = []
        cached_results_data = []
        total_points = sum(tc.points for tc in test_cases)
        earned_points = 0

        for idx, (tc, exec_res) in enumerate(zip(test_cases, exec_results, strict=False), start=1):
            verdict, err_msg = map_execution_result_to_verdict(
                exec_res,
                tc.expected_output,
                mode=comparison_mode,
                memory_limit_kb=limits.memory_limit_kb,
            )

            time_ms = int(exec_res.time_sec * 1000) if exec_res.time_sec is not None else None
            memory_kb = exec_res.memory_kb

            if verdict == Verdict.AC:
                earned_points += tc.points

            test_verdicts_data.append((verdict, time_ms, memory_kb))

            # Truncate and sanitize outputs for storage
            clean_stdout = sanitize_output(exec_res.stdout, max_length=settings.max_output_length_chars)
            clean_stderr = sanitize_output(exec_res.stderr, max_length=settings.max_output_length_chars)

            db_result = SubmissionResult(
                submission_id=submission.id,
                test_case_id=tc.id,
                test_number=idx,
                verdict=verdict.value,
                time_ms=time_ms,
                memory_kb=memory_kb,
                stdout=clean_stdout,
                stderr=clean_stderr,
                error_message=err_msg,
                is_hidden=tc.is_hidden,
            )
            session.add(db_result)

            cached_results_data.append(
                {
                    "test_case_id": str(tc.id),
                    "test_number": idx,
                    "verdict": verdict.value,
                    "time_ms": time_ms,
                    "memory_kb": memory_kb,
                    "stdout": clean_stdout,
                    "stderr": clean_stderr,
                    "error_message": err_msg,
                    "is_hidden": tc.is_hidden,
                }
            )

        # 4. Compute overall verdict & score
        overall_v, passed_cnt, total_cnt, max_t, max_m = aggregate_verdicts(test_verdicts_data)
        final_score = Decimal(str(round((earned_points / total_points) * 100, 2))) if total_points > 0 else None

        submission.status = "COMPLETED"
        submission.verdict = overall_v.value
        submission.score = final_score
        submission.time_ms = max_t
        submission.memory_kb = max_m
        submission.passed_test_cases = passed_cnt
        submission.total_test_cases = total_cnt

        await session.commit()
        await session.refresh(submission)

        logger.info(
            "Completed judging submission %s: verdict=%s passed=%d/%d score=%s",
            submission_id,
            submission.verdict,
            passed_cnt,
            total_cnt,
            final_score,
        )

        # 5. Populate Cache
        if settings.cache_results_enabled and redis:
            cache_payload = {
                "verdict": overall_v.value,
                "score": str(final_score) if final_score is not None else None,
                "time_ms": max_t,
                "memory_kb": max_m,
                "passed_test_cases": passed_cnt,
                "total_test_cases": total_cnt,
                "results": cached_results_data,
            }
            await set_cached_submission_result(
                redis, cache_key, cache_payload, ttl_seconds=settings.cache_results_ttl_sec
            )

        await publish_submission_update(submission.id, "COMPLETED", final_score)
        return submission

    except Exception as exc:
        logger.exception("Judging failed with exception for submission %s", submission_id)
        submission.status = "ERROR"
        submission.verdict = Verdict.IE.value
        submission.error_message = sanitize_output(str(exc))
        await session.commit()
        await publish_submission_update(submission.id, "ERROR")
        return submission

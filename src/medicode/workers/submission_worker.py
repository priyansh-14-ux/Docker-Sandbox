import asyncio
from typing import Any
from uuid import UUID

import httpx
from arq.connections import ArqRedis, RedisSettings, create_pool
from fastapi import BackgroundTasks

from medicode.core.config import get_settings
from medicode.core.logging import configure_logging, get_logger, submission_id_ctx
from medicode.db.session import AsyncSessionLocal
from medicode.services.execution.factory import get_execution_provider
from medicode.services.execution.judge0 import Judge0Provider
from medicode.services.judging import judge_submission
from medicode.services.rate_limiter import set_global_redis

logger = get_logger(__name__)

_ARQ_REDIS_POOL: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis | None:
    """Returns or initializes the shared ARQ Redis connection pool."""
    global _ARQ_REDIS_POOL
    if _ARQ_REDIS_POOL is None:
        try:
            settings = get_settings()
            redis_settings = RedisSettings.from_dsn(settings.redis_url)
            _ARQ_REDIS_POOL = await create_pool(redis_settings)
            set_global_redis(_ARQ_REDIS_POOL)
        except Exception as exc:
            logger.warning("Could not connect to Redis ARQ pool: %s", str(exc))
            return None
    return _ARQ_REDIS_POOL


async def enqueue_submission(
    submission_id: UUID,
    background_tasks: BackgroundTasks | None = None,
) -> bool:
    """
    Enqueues a submission to the Redis ARQ worker queue.
    Falls back to FastAPI BackgroundTasks in dev/local mode if Redis is unavailable.
    """
    pool = await get_arq_pool()
    if pool is not None:
        try:
            await pool.enqueue_job("judge_submission_job", str(submission_id))
            logger.info("Submission %s enqueued to ARQ worker queue", submission_id)
            return True
        except Exception as exc:
            logger.warning("Failed to enqueue submission %s to Redis: %s", submission_id, str(exc))

    # Dev / Local fallback
    if background_tasks is not None:
        logger.info("Enqueuing submission %s via BackgroundTasks fallback", submission_id)
        background_tasks.add_task(_dev_mode_judge_runner, submission_id)
        return True

    logger.error("No worker queue or background task available for submission %s", submission_id)
    return False


async def _dev_mode_judge_runner(submission_id: UUID) -> None:
    """Background fallback runner for dev environments without Redis."""
    async with AsyncSessionLocal() as session:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
        try:
            settings = get_settings()
            provider = Judge0Provider(
                client=client,
                base_url=settings.judge0_url,
                auth_header=settings.judge0_auth_header,
                auth_token=settings.judge0_auth_token,
                poll_interval=settings.judge0_poll_interval_sec,
                poll_timeout=settings.judge0_poll_timeout_sec,
                default_language_id=settings.python_language_id,
            )
            await judge_submission(session, submission_id, provider)
        finally:
            await client.aclose()


# --- ARQ Worker Lifecycle and Job Definition ---


async def judge_submission_job(ctx: dict[str, Any], submission_id_str: str) -> str:
    """ARQ job executing untrusted code against the Judge0 sandbox."""
    submission_id = UUID(submission_id_str)
    submission_id_ctx.set(submission_id_str)
    logger.info("ARQ Worker picked up job for submission %s", submission_id)

    provider = ctx.get("provider")
    async with AsyncSessionLocal() as session:
        submission = await judge_submission(session, submission_id, provider)
        return f"Completed: {submission.verdict}"


async def startup(ctx: dict[str, Any]) -> None:
    """Initializes HTTP client and Judge0 execution provider on worker boot."""
    configure_logging()
    logger.info("Starting MediCode ARQ execution worker...")

    settings = get_settings()
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=5.0),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
    )
    ctx["client"] = client
    ctx["provider"] = get_execution_provider(client=client, settings=settings)
    logger.info("MediCode ARQ execution worker initialized successfully")


async def shutdown(ctx: dict[str, Any]) -> None:
    """Cleans up resources on worker exit."""
    logger.info("Shutting down MediCode ARQ worker...")
    client: httpx.AsyncClient | None = ctx.get("client")
    if client and not client.is_closed:
        await client.aclose()
    logger.info("MediCode ARQ worker shutdown complete")


class WorkerSettings:
    """ARQ Worker configuration class."""
    _settings = get_settings()
    functions = [judge_submission_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    max_jobs = _settings.arq_max_jobs
    queue_name = _settings.arq_queue_name


if __name__ == "__main__":
    from arq import run_worker
    run_worker(WorkerSettings)

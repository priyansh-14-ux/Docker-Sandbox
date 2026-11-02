from contextlib import asynccontextmanager
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from medicode.api.router import api_router
from medicode.api.routes.realtime import router as realtime_router
from medicode.core.config import get_settings
from medicode.core.logging import configure_logging, get_logger, request_id_ctx
from medicode.db.session import AsyncSessionLocal
from medicode.services.execution.factory import (
    get_execution_provider,
    set_global_http_client,
)
from medicode.services.rate_limiter import get_redis_client, set_global_redis

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Initializes shared async resources (HTTP connection pool, Redis, structured logging)
    and handles graceful termination.
    """
    settings = get_settings()
    configure_logging(level=10 if settings.debug else 20)
    logger.info("Initializing %s in %s environment...", settings.app_name, settings.app_env)

    # 1. Initialize shared httpx.AsyncClient with connection pooling and timeouts
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=5.0),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
    )
    set_global_http_client(http_client)

    # 2. Initialize Redis client for rate limiting and result caching
    redis_client: Redis | None = None
    try:
        redis_client = Redis.from_url(settings.redis_url, decode_responses=False)
        await redis_client.ping()
        set_global_redis(redis_client)
        logger.info("Connected to Redis at %s", settings.redis_url)
    except Exception as exc:
        logger.warning("Redis unavailable at startup (%s). Using local/in-memory fallback.", str(exc))
        set_global_redis(None)

    yield

    # Teardown
    logger.info("Shutting down %s resources...", settings.app_name)
    if redis_client is not None:
        try:
            await redis_client.aclose()
        except Exception:
            pass

    if not http_client.is_closed:
        await http_client.aclose()
    logger.info("MediCode shutdown completed cleanly.")


app = FastAPI(
    title="MediCode API",
    version="0.1.0",
    description="Backend API for the MediCode educational coding practice and assessment platform.",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_tracing_middleware(request: Request, call_next):
    """Assigns and propagates a unique Request ID for structured tracing across logs."""
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_ctx.set(req_id)
    start_time = time.monotonic()

    try:
        response: Response = await call_next(request)
        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
        return response
    finally:
        request_id_ctx.reset(token)


# --- Global Exception Handlers returning consistent JSON ---


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status_code": exc.status_code},
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": "Request payload validation failed",
            "errors": jsonable_encoder(exc.errors()),
            "status_code": 422,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server exception during request %s: %s", request.url.path, str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected internal server error occurred.",
            "error_code": "INTERNAL_SERVER_ERROR",
            "status_code": 500,
        },
    )


# --- Routers ---
app.include_router(api_router, prefix="/api")
app.include_router(realtime_router, prefix="/ws", tags=["realtime"])


@app.get("/", tags=["system"])
async def read_root() -> dict[str, str]:
    return {"message": "Welcome to MediCode API"}


@app.get("/health", tags=["system"], summary="Liveness check")
async def health_check() -> dict[str, str]:
    """Liveness probe indicating API server is running."""
    return {"status": "ok", "app": get_settings().app_name}


@app.get("/ready", tags=["system"], summary="Readiness check")
async def readiness_check() -> JSONResponse:
    """Readiness probe checking DB, Redis, and Sandbox provider reachability."""
    components: dict[str, bool] = {
        "database": False,
        "redis": False,
        "execution_sandbox": False,
    }

    # 1. Check PostgreSQL
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            components["database"] = True
    except Exception as exc:
        logger.warning("Readiness probe: Database check failed: %s", str(exc))

    # 2. Check Redis
    redis = get_redis_client()
    if redis is not None:
        try:
            await redis.ping()
            components["redis"] = True
        except Exception as exc:
            logger.warning("Readiness probe: Redis check failed: %s", str(exc))

    # 3. Check Execution Sandbox (Judge0)
    try:
        settings = get_settings()
        http_client = httpx.AsyncClient(timeout=3.0)
        try:
            provider = get_execution_provider(client=http_client, settings=settings)
            components["execution_sandbox"] = await provider.check_health()
        finally:
            await http_client.aclose()
    except Exception as exc:
        logger.warning("Readiness probe: Sandbox check failed: %s", str(exc))

    all_ready = components["database"] and components["redis"] and components["execution_sandbox"]
    status_code = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ready else "degraded",
            "components": components,
        },
    )

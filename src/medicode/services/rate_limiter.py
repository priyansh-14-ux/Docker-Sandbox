import time
from typing import Annotated

from fastapi import Depends, HTTPException, status
from redis.asyncio import Redis

from medicode.api.dependencies import get_current_login
from medicode.core.config import Settings, get_settings
from medicode.core.logging import get_logger
from medicode.models.identity import Login

logger = get_logger(__name__)

# Global Redis client holder
_GLOBAL_REDIS: Redis | None = None


def set_global_redis(redis_client: Redis | None) -> None:
    global _GLOBAL_REDIS
    _GLOBAL_REDIS = redis_client


def get_redis_client() -> Redis | None:
    global _GLOBAL_REDIS
    return _GLOBAL_REDIS


# In-memory fallback tracking when Redis is unavailable (e.g. in standalone unit tests)
_IN_MEMORY_RATE_STORE: dict[str, list[float]] = {}


class RateLimiter:
    """Sliding window rate limiter using Redis with an in-memory fallback."""

    def __init__(self, key_prefix: str, max_requests: int, window_seconds: int, min_interval_seconds: float = 0.0):
        self.key_prefix = key_prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.min_interval_seconds = min_interval_seconds

    async def check(self, user_id: str, redis: Redis | None) -> None:
        now = time.time()

        if redis is not None:
            try:
                burst_key = f"rl:{self.key_prefix}:burst:{user_id}"
                window_key = f"rl:{self.key_prefix}:win:{user_id}"

                # Check minimum interval between submissions (burst check)
                if self.min_interval_seconds > 0:
                    last_time = await redis.get(burst_key)
                    if last_time:
                        elapsed = now - float(last_time)
                        if elapsed < self.min_interval_seconds:
                            retry_after = int(self.min_interval_seconds - elapsed) + 1
                            raise HTTPException(
                                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail=f"Too many requests. Please wait {retry_after} second(s) before resubmitting.",
                                headers={"Retry-After": str(retry_after)},
                            )

                # Check sliding window count
                pipe = redis.pipeline()
                pipe.zremrangebyscore(window_key, 0, now - self.window_seconds)
                pipe.zadd(window_key, {str(now): now})
                pipe.zcard(window_key)
                pipe.expire(window_key, self.window_seconds + 5)
                if self.min_interval_seconds > 0:
                    pipe.set(burst_key, str(now), ex=int(self.min_interval_seconds) + 2)
                results = await pipe.execute()

                request_count = results[2]
                if request_count > self.max_requests:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Rate limit exceeded: maximum {self.max_requests} requests per {self.window_seconds} seconds.",
                        headers={"Retry-After": str(self.window_seconds)},
                    )
                return
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("Redis rate limiter error, using in-memory fallback: %s", str(exc))

        # In-memory fallback
        mem_key = f"{self.key_prefix}:{user_id}"
        timestamps = _IN_MEMORY_RATE_STORE.get(mem_key, [])
        timestamps = [t for t in timestamps if now - t < self.window_seconds]

        if self.min_interval_seconds > 0 and timestamps:
            if now - timestamps[-1] < self.min_interval_seconds:
                retry_after = int(self.min_interval_seconds - (now - timestamps[-1])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests. Please wait {retry_after} second(s) before resubmitting.",
                    headers={"Retry-After": str(retry_after)},
                )

        if len(timestamps) >= self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: maximum {self.max_requests} requests per {self.window_seconds} seconds.",
                headers={"Retry-After": str(self.window_seconds)},
            )

        timestamps.append(now)
        _IN_MEMORY_RATE_STORE[mem_key] = timestamps


async def rate_limit_submissions(
    account: Annotated[Login, Depends(get_current_login)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Dependency for standard submission rate limiting."""
    limiter = RateLimiter(
        key_prefix="submissions",
        max_requests=settings.rate_limit_submission_requests,
        window_seconds=settings.rate_limit_submission_window_sec,
        min_interval_seconds=settings.rate_limit_burst_window_sec,
    )
    user_id = str(account.id)
    await limiter.check(user_id, get_redis_client())


async def rate_limit_runs(
    account: Annotated[Login, Depends(get_current_login)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Dependency for quick run rate limiting."""
    limiter = RateLimiter(
        key_prefix="run",
        max_requests=settings.rate_limit_run_requests,
        window_seconds=settings.rate_limit_run_window_sec,
        min_interval_seconds=5.0,
    )
    user_id = str(account.id)
    await limiter.check(user_id, get_redis_client())

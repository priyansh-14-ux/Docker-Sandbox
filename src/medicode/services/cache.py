import hashlib
import json
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from medicode.core.logging import get_logger

logger = get_logger(__name__)


def compute_cache_key(problem_id: UUID, source_code: str, test_signature: str) -> str:
    """Computes a SHA256 hash key for submission idempotency and caching."""
    hasher = hashlib.sha256()
    hasher.update(str(problem_id).encode("utf-8"))
    hasher.update(b":")
    hasher.update(source_code.strip().encode("utf-8"))
    hasher.update(b":")
    hasher.update(test_signature.encode("utf-8"))
    return f"sub_cache:{hasher.hexdigest()}"


async def get_cached_submission_result(
    redis: Redis | None, key: str
) -> dict[str, Any] | None:
    """Retrieves cached judging results if present."""
    if redis is None:
        return None
    try:
        data = await redis.get(key)
        if data:
            return json.loads(data)
    except Exception as exc:
        logger.warning("Cache lookup failed: %s", str(exc))
    return None


async def set_cached_submission_result(
    redis: Redis | None, key: str, result_data: dict[str, Any], ttl_seconds: int = 3600
) -> None:
    """Stores judging results in Redis cache."""
    if redis is None:
        return
    try:
        await redis.set(key, json.dumps(result_data), ex=ttl_seconds)
    except Exception as exc:
        logger.warning("Cache write failed: %s", str(exc))

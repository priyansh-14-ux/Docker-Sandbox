import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text

from medicode.db.session import engine


async def publish_submission_update(
    submission_id: UUID, status: str, score: Decimal | None = None
) -> None:
    """Notify WebSocket listeners after a worker commits a submission result."""
    payload = json.dumps(
        {
            "submission_id": str(submission_id),
            "status": status,
            "score": str(score) if score is not None else None,
        }
    )
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT pg_notify('submission_updates', :payload)"), {"payload": payload}
        )

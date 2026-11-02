import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from medicode.core.config import get_settings
from medicode.core.security import read_access_token
from medicode.db.session import AsyncSessionLocal
from medicode.models.content import Submission
from medicode.models.identity import AuthSession, Login, Profile, RoleName

router = APIRouter()
ADMIN_ROLES = (RoleName.SUPER_ADMIN, RoleName.INSTITUTE_ADMIN)


@router.websocket("/submissions/{submission_id}")
async def submission_updates(websocket: WebSocket, submission_id: UUID) -> None:
    await websocket.accept()
    listener: asyncpg.Connection | None = None
    receive_task: asyncio.Task | None = None
    notification_task: asyncio.Task | None = None
    try:
        auth_message = await websocket.receive_json()
        access_token = auth_message.get("access_token") if isinstance(auth_message, dict) else None
        payload = read_access_token(access_token) if isinstance(access_token, str) else None
        if payload is None:
            await websocket.close(code=4401, reason="Authentication required")
            return

        async with AsyncSessionLocal() as session:
            account = await session.scalar(
                select(Login)
                .join(AuthSession, AuthSession.login_id == Login.id)
                .where(
                    AuthSession.token_id == payload["jti"],
                    AuthSession.login_id == UUID(payload["sub"]),
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > datetime.now(UTC),
                    Login.is_active.is_(True),
                )
                .options(selectinload(Login.profile).selectinload(Profile.role))
            )
            if account is None:
                await websocket.close(code=4401, reason="Session is not active")
                return
            submission = await session.get(Submission, submission_id)
            if submission is None:
                await websocket.close(code=4404, reason="Submission not found")
                return
            role = account.profile.role.name if account.profile else None
            if role not in ADMIN_ROLES and (
                account.profile is None or submission.student_profile_id != account.profile.id
            ):
                await websocket.close(code=4403, reason="Submission access denied")
                return
            initial = {
                "type": "submission_status",
                "submission_id": str(submission.id),
                "status": submission.status,
                "score": str(submission.score) if submission.score is not None else None,
                "created_at": submission.created_at.isoformat(),
            }

        await websocket.send_json(initial)
        dsn = get_settings().async_database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        listener = await asyncpg.connect(dsn=dsn)
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)

        def on_notification(
            _conn: asyncpg.Connection, _pid: int, _channel: str, message: str
        ) -> None:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                pass

        await listener.add_listener("submission_updates", on_notification)
        while True:
            receive_task = asyncio.create_task(websocket.receive_text())
            notification_task = asyncio.create_task(queue.get())
            done, pending = await asyncio.wait(
                (receive_task, notification_task), return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if receive_task in done:
                message = receive_task.result()
                if message == "close":
                    break
                if message == "ping":
                    await websocket.send_json({"type": "pong"})
            if notification_task in done:
                try:
                    event = json.loads(notification_task.result())
                except (json.JSONDecodeError, TypeError):
                    continue
                if event.get("submission_id") == str(submission_id):
                    await websocket.send_json({"type": "submission_update", **event})
    except WebSocketDisconnect:
        pass
    finally:
        for task in (receive_task, notification_task):
            if task is not None and not task.done():
                task.cancel()
        if listener is not None and not listener.is_closed():
            await listener.close()

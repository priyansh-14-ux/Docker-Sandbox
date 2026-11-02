from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from medicode.core.security import read_access_token
from medicode.db.session import get_db_session
from medicode.models.identity import AuthSession, Login, Profile, RoleName

bearer = HTTPBearer(auto_error=False)


async def get_current_login(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Login:
    payload = read_access_token(credentials.credentials) if credentials else None
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    current_time = datetime.now(UTC)
    login = await session.scalar(
        select(Login)
        .join(AuthSession, AuthSession.login_id == Login.id)
        .where(
            AuthSession.token_id == payload["jti"],
            AuthSession.login_id == UUID(payload["sub"]),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > current_time,
            Login.is_active.is_(True),
        )
        .options(selectinload(Login.profile).selectinload(Profile.role))
    )
    if login is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is not active",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return login


def require_roles(*allowed_roles: RoleName) -> Callable:
    async def role_guard(
        account: Annotated[Login, Depends(get_current_login)],
    ) -> Login:
        role = account.profile.role.name if account.profile else None
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return account

    return role_guard

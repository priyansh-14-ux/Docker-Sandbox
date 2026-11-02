from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from medicode.api.dependencies import bearer, get_current_login
from medicode.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    new_token_id,
    read_access_token,
    refresh_token_expiry,
    token_expiry,
    verify_password,
)
from medicode.db.session import get_db_session
from medicode.models.identity import AuthSession, Login, Profile, Role, RoleName
from medicode.schemas.accounts import RegisterRequest, UserResponse

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: datetime
    refresh_expires_at: datetime


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=40, max_length=128)


def _user_response(account: Login) -> UserResponse:
    return UserResponse(
        id=account.id,
        email=account.email,
        is_active=account.is_active,
        full_name=account.profile.full_name if account.profile else None,
        role=str(account.profile.role.name) if account.profile else None,
        created_at=account.created_at,
        last_login_at=account.last_login_at,
    )


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest, session: Annotated[AsyncSession, Depends(get_db_session)]
) -> LoginResponse:
    email = str(body.email).lower()
    existing = await session.scalar(select(Login.id).where(Login.email == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
        )

    student_role = await session.scalar(select(Role).where(Role.name == RoleName.STUDENT))
    if student_role is None:
        raise HTTPException(status_code=500, detail="Student role is not configured")
    account = Login(
        email=email,
        password_hash=hash_password(body.password),
        profile=Profile(full_name=body.full_name.strip(), role=student_role),
    )
    if not account.profile.full_name:
        raise HTTPException(status_code=422, detail="full_name cannot be empty")
    session.add(account)
    expires_at = token_expiry()
    token_id = new_token_id()
    refresh_token = new_refresh_token()
    refresh_expires_at = refresh_token_expiry()
    session.add(
        AuthSession(
            login=account,
            token_id=token_id,
            expires_at=expires_at,
            refresh_token_hash=hash_refresh_token(refresh_token),
            refresh_expires_at=refresh_expires_at,
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
        ) from exc
    return LoginResponse(
        access_token=create_access_token(account.id, token_id, expires_at),
        refresh_token=refresh_token,
        expires_at=expires_at,
        refresh_expires_at=refresh_expires_at,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest, session: Annotated[AsyncSession, Depends(get_db_session)]
) -> LoginResponse:
    email = str(body.email).lower()
    account = await session.scalar(select(Login).where(Login.email == email))
    if (
        not account
        or not account.is_active
        or not verify_password(body.password, account.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    expires_at = token_expiry()
    token_id = new_token_id()
    refresh_token = new_refresh_token()
    refresh_expires_at = refresh_token_expiry()
    session.add(
        AuthSession(
            login_id=account.id,
            token_id=token_id,
            expires_at=expires_at,
            refresh_token_hash=hash_refresh_token(refresh_token),
            refresh_expires_at=refresh_expires_at,
        )
    )
    account.last_login_at = datetime.now(UTC)
    await session.commit()
    return LoginResponse(
        access_token=create_access_token(account.id, token_id, expires_at),
        refresh_token=refresh_token,
        expires_at=expires_at,
        refresh_expires_at=refresh_expires_at,
    )


@router.get("/me", response_model=UserResponse)
async def read_authenticated_user(
    account: Annotated[Login, Depends(get_current_login)],
) -> UserResponse:
    return _user_response(account)


@router.post("/refresh", response_model=LoginResponse)
async def refresh_session(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LoginResponse:
    now = datetime.now(UTC)
    auth_session = await session.scalar(
        select(AuthSession)
        .where(
            AuthSession.refresh_token_hash == hash_refresh_token(body.refresh_token),
            AuthSession.revoked_at.is_(None),
            AuthSession.refresh_expires_at > now,
        )
        .with_for_update()
    )
    if auth_session is None:
        raise HTTPException(status_code=401, detail="Refresh token is invalid or expired")
    account = await session.get(Login, auth_session.login_id)
    if account is None or not account.is_active:
        auth_session.revoked_at = now
        await session.commit()
        raise HTTPException(status_code=401, detail="Account is not active")

    access_expires_at = token_expiry()
    refresh_expires_at = refresh_token_expiry()
    token_id = new_token_id()
    refresh_token = new_refresh_token()
    auth_session.token_id = token_id
    auth_session.expires_at = access_expires_at
    auth_session.refresh_token_hash = hash_refresh_token(refresh_token)
    auth_session.refresh_expires_at = refresh_expires_at
    await session.commit()
    return LoginResponse(
        access_token=create_access_token(account.id, token_id, access_expires_at),
        refresh_token=refresh_token,
        expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    payload = read_access_token(credentials.credentials) if credentials else None
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    auth_session = await session.scalar(
        select(AuthSession).where(
            AuthSession.token_id == payload["jti"],
            AuthSession.login_id == UUID(payload["sub"]),
        )
    )
    now = datetime.now(UTC)
    if not auth_session or auth_session.revoked_at or auth_session.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is not active"
        )
    auth_session.revoked_at = now
    auth_session.refresh_token_hash = None
    await session.commit()

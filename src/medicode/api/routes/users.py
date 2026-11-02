from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from medicode.api.dependencies import get_current_login, require_roles
from medicode.core.security import hash_password
from medicode.db.session import get_db_session
from medicode.models.identity import Login, Profile, Role, RoleName
from medicode.schemas.accounts import ProfileUpdate, UserProvisionRequest, UserResponse

router = APIRouter()
ADMIN_ROLES = (RoleName.SUPER_ADMIN, RoleName.INSTITUTE_ADMIN)


def serialize_user(account: Login) -> UserResponse:
    return UserResponse(
        id=account.id,
        email=account.email,
        is_active=account.is_active,
        full_name=account.profile.full_name if account.profile else None,
        role=str(account.profile.role.name) if account.profile else None,
        created_at=account.created_at,
        last_login_at=account.last_login_at,
    )


@router.get("", response_model=list[UserResponse])
async def list_users(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _admin: Annotated[Login, Depends(require_roles(*ADMIN_ROLES))],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[UserResponse]:
    accounts = await session.scalars(
        select(Login)
        .options(selectinload(Login.profile).selectinload(Profile.role))
        .order_by(Login.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [serialize_user(account) for account in accounts]


@router.post("", response_model=UserResponse, status_code=201)
async def provision_user(
    body: UserProvisionRequest,
    _admin: Annotated[Login, Depends(require_roles(*ADMIN_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    email = str(body.email).lower()
    existing = await session.scalar(select(Login.id).where(Login.email == email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")
    role = await session.scalar(select(Role).where(Role.name == RoleName(body.role)))
    if role is None:
        raise HTTPException(status_code=500, detail="Requested role is not configured")
    account = Login(
        email=email,
        password_hash=hash_password(body.password),
        profile=Profile(full_name=body.full_name.strip(), role=role),
    )
    if not account.profile.full_name:
        raise HTTPException(status_code=422, detail="full_name cannot be empty")
    session.add(account)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered") from exc
    return serialize_user(account)


@router.get("/me", response_model=UserResponse)
async def read_current_user(
    account: Annotated[Login, Depends(get_current_login)],
) -> UserResponse:
    return serialize_user(account)


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    changes: ProfileUpdate,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    return await update_profile(account, changes, session)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    if user_id != account.id and _role(account) not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="You may only view your own account")
    target = await session.scalar(
        select(Login)
        .where(Login.id == user_id)
        .options(selectinload(Login.profile).selectinload(Profile.role))
    )
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    return serialize_user(target)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    changes: ProfileUpdate,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    if user_id != account.id and _role(account) not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="You may only update your own profile")
    target = await session.scalar(
        select(Login)
        .where(Login.id == user_id)
        .options(selectinload(Login.profile).selectinload(Profile.role))
    )
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    return await update_profile(target, changes, session)


async def update_profile(
    account: Login, changes: ProfileUpdate, session: AsyncSession
) -> UserResponse:
    if account.profile is None:
        raise HTTPException(status_code=404, detail="User profile was not found")
    if "full_name" in changes.model_fields_set:
        if changes.full_name is None or not changes.full_name.strip():
            raise HTTPException(status_code=422, detail="full_name cannot be empty")
        account.profile.full_name = changes.full_name.strip()
    if "phone" in changes.model_fields_set:
        account.profile.phone = changes.phone
    await session.commit()
    return serialize_user(account)


def _role(account: Login) -> RoleName | str | None:
    return account.profile.role.name if account.profile else None

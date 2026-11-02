import asyncio
from getpass import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from medicode.core.security import hash_password
from medicode.db.session import AsyncSessionLocal
from medicode.models.identity import Login, Profile, Role, RoleName


async def main() -> None:
    raw_email = input("Admin email: ").strip().lower()
    try:
        email = str(TypeAdapter(EmailStr).validate_python(raw_email)).lower()
    except ValidationError as exc:
        raise SystemExit("Enter a valid email address") from exc
    full_name = input("Admin full name: ").strip()
    if not full_name:
        raise SystemExit("Full name is required")
    password = getpass("Admin password (minimum 8 characters): ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters")

    async with AsyncSessionLocal() as session:
        existing = await session.scalar(select(Login.id).where(Login.email == email))
        if existing is not None:
            raise SystemExit("An account with this email already exists")
        role = await session.scalar(select(Role).where(Role.name == RoleName.SUPER_ADMIN))
        if role is None:
            raise SystemExit("SUPER_ADMIN role seed is missing; apply database migrations first")
        account = Login(
            email=email,
            password_hash=hash_password(password),
            profile=Profile(full_name=full_name, role=role),
        )
        session.add(account)
        await session.commit()
    print(f"Created administrator account for {email}")


if __name__ == "__main__":
    asyncio.run(main())

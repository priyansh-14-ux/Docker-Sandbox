import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from medicode.core.config import get_settings

_PBKDF2_ITERATIONS = 310_000
_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    if encoded.startswith("$argon2"):
        try:
            return _password_hasher.verify(encoded, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    try:
        algorithm, rounds, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt), int(rounds))
        return hmac.compare_digest(actual, _unb64(expected))
    except (ValueError, TypeError):
        return False


def create_access_token(login_id: UUID, token_id: str, expires_at: datetime) -> str:
    payload = {
        "sub": str(login_id),
        "jti": token_id,
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, get_settings().auth_secret_key, algorithm="HS256")


def read_access_token(token: str) -> dict[str, str | int] | None:
    try:
        payload = jwt.decode(
            token,
            get_settings().auth_secret_key,
            algorithms=["HS256"],
            options={"require": ["sub", "jti", "exp"]},
        )
        UUID(payload["sub"])
        if not isinstance(payload["jti"], str):
            return None
        return payload
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
        return None


def token_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=get_settings().auth_token_expire_minutes)


def new_token_id() -> str:
    return secrets.token_urlsafe(32)


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=get_settings().auth_refresh_token_expire_days)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

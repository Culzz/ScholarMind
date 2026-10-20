"""Authentication and authorisation primitives.

- Passwords are hashed with Argon2id (passlib's Argon2 backend).
- Access tokens are short-lived JWTs; refresh tokens are long-lived and rotated.
- Roles are carried in the token and enforced by FastAPI dependencies.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError

ALGORITHM = "HS256"


class Role(str, Enum):
    STUDENT = "student"
    ADMIN = "admin"
    RESEARCHER = "researcher"


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    from argon2 import PasswordHasher

    hasher = PasswordHasher()
    return hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash; never raises on malformed hashes."""
    from argon2.exceptions import VerificationError, VerifyMismatchError
    from argon2 import PasswordHasher

    hasher = PasswordHasher()
    try:
        return hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, Exception):
        return False


def _encode(subject: str, role: Role, token_type: str, secret: str, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role.value,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def create_access_token(*, subject: str, role: Role, settings: Settings) -> str:
    return _encode(subject, role, "access", settings.jwt_secret, timedelta(minutes=settings.jwt_access_minutes))


def create_refresh_token(*, subject: str, role: Role, settings: Settings) -> str:
    return _encode(subject, role, "refresh", settings.jwt_refresh_secret, timedelta(days=settings.jwt_refresh_days))


def decode_token(token: str, *, secret: str, expected_type: str = "access") -> dict[str, Any]:
    """Decode and validate a token, raising :class:`UnauthorizedError` on failure."""
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Your session has expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid authentication token.", code="invalid_token") from exc
    if payload.get("type") != expected_type:
        raise UnauthorizedError("Invalid token type.", code="invalid_token_type")
    return payload


def hash_token(token: str) -> str:
    """Deterministic hash of a token, used for refresh-token rotation storage."""
    return hmac.new(b"scholarmind-refresh", token.encode("utf-8"), hashlib.sha256).hexdigest()


bearer_scheme = HTTPBearer(auto_error=False)


async def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Resolve the authenticated user from the bearer token."""
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Authentication is required.")
    payload = decode_token(credentials.credentials, secret=settings.jwt_secret)
    request.state.user_id = payload.get("sub")
    request.state.user_role = payload.get("role")
    return payload


async def current_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    """Require the admin role."""
    if user.get("role") != Role.ADMIN.value:
        raise ForbiddenError("This action requires an administrator account.")
    return user


async def current_researcher(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    """Require the researcher or admin role."""
    if user.get("role") not in (Role.RESEARCHER.value, Role.ADMIN.value):
        raise ForbiddenError("This action requires a researcher account.")
    return user

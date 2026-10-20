"""Authentication endpoints.

Access tokens are short-lived JWTs returned to the client. The refresh token
is set as an httpOnly cookie so it cannot be read by JavaScript, and it is
rotated on every refresh.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, UnauthorizedError
from app.core.security import (
    Role,
    create_access_token,
    create_refresh_token,
    current_user,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "scholarmind_refresh"


class RegisterRequest(BaseModel):
    """Create a student account."""

    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=10, max_length=200)
    full_name: str | None = Field(default=None, max_length=200)
    country_iso3: str | None = Field(default=None, max_length=3)


class LoginRequest(BaseModel):
    """Exchange credentials for tokens."""

    email: str
    password: str


class TokenResponse(BaseModel):
    """The access token and who it belongs to."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict[str, Any]


def _set_refresh_cookie(response: Response, token: str, settings: Any) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.jwt_refresh_days * 24 * 3600,
        path="/api/v1/auth",
    )


def _user_payload(user_id: str, email: str, role: str, full_name: str | None) -> dict[str, Any]:
    return {"id": user_id, "email": email, "role": role, "full_name": full_name}


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: RegisterRequest, response: Response, session: Session = Depends(get_db)) -> TokenResponse:
    """Create a student account and return an access token."""
    settings = get_settings()
    email = payload.email.strip().lower()

    existing = session.execute(
        text("SELECT id::text FROM users WHERE email = :email"), {"email": email}
    ).first()
    if existing:
        raise ConflictError("An account with that email already exists.")

    role = Role.ADMIN.value if email in settings.admin_emails else Role.STUDENT.value

    user_id = session.execute(
        text(
            """
            INSERT INTO users (id, email, password_hash, full_name, role, country_iso3)
            VALUES (gen_random_uuid(), :email, :password_hash, :full_name, :role, :country)
            RETURNING id::text, email::text, role, full_name
            """
        ),
        {
            "email": email,
            "password_hash": hash_password(payload.password),
            "full_name": payload.full_name,
            "role": role,
            "country": (payload.country_iso3 or "").upper() or None,
        },
    ).first()

    session.execute(
        text("INSERT INTO student_profiles (id, user_id, nationality_country_iso3) VALUES (gen_random_uuid(), :user, :country)"),
        {"user": user_id[0], "country": (payload.country_iso3 or "").upper() or None},
    )
    session.commit()

    access_token = create_access_token(subject=user_id[0], role=Role(role), settings=settings)
    refresh_token = create_refresh_token(subject=user_id[0], role=Role(role), settings=settings)
    _set_refresh_cookie(response, refresh_token, settings)

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_minutes * 60,
        user=_user_payload(user_id[0], user_id[1], user_id[2], user_id[3]),
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response, session: Session = Depends(get_db)) -> TokenResponse:
    """Exchange credentials for an access token."""
    settings = get_settings()
    row = session.execute(
        text(
            """
            SELECT id::text, email::text, password_hash, role, full_name, is_active
            FROM users WHERE email = :email
            """
        ),
        {"email": payload.email.strip().lower()},
    ).fetchone()

    if not row or not verify_password(payload.password, row[2]) or not row[5]:
        raise UnauthorizedError("Email or password is incorrect.", code="invalid_credentials")

    role = Role(row[3])
    access_token = create_access_token(subject=row[0], role=role, settings=settings)
    refresh_token = create_refresh_token(subject=row[0], role=role, settings=settings)
    _set_refresh_cookie(response, refresh_token, settings)

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_minutes * 60,
        user=_user_payload(row[0], row[1], row[3], row[4]),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(response: Response, session: Session = Depends(get_db)) -> TokenResponse:
    """Rotate the refresh cookie and issue a new access token."""
    settings = get_settings()
    token = response.cookies.get(REFRESH_COOKIE) or ""
    if not token:
        raise UnauthorizedError("No refresh token was supplied.", code="missing_refresh_token")

    payload = decode_token(token, secret=settings.jwt_refresh_secret, expected_type="refresh")
    row = session.execute(
        text("SELECT id::text, email::text, role, full_name, is_active FROM users WHERE id::text = :id"),
        {"id": payload.get("sub")},
    ).first()
    if not row or not row[4]:
        raise UnauthorizedError("This account is no longer active.")

    role = Role(row[2])
    access_token = create_access_token(subject=row[0], role=role, settings=settings)
    refresh_token = create_refresh_token(subject=row[0], role=role, settings=settings)
    _set_refresh_cookie(response, refresh_token, settings)

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_minutes * 60,
        user=_user_payload(row[0], row[1], row[2], row[3]),
    )


@router.post("/logout", status_code=204)
async def logout(response: Response) -> Response:
    """Clear the refresh cookie."""
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    return Response(status_code=204)


@router.get("/me")
async def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    """The authenticated user's profile summary."""
    return {
        "id": user.get("sub"),
        "role": user.get("role"),
        "issued_at": user.get("iat"),
    }

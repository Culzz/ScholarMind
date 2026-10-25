"""Authentication endpoints.

Access tokens are short-lived JWTs returned to the client. The refresh token is
set as an httpOnly cookie and is rotated on every refresh.

Rotation is enforced server-side: every issued refresh token is stored as a
hash with a ``family_id``. Using a token that has already been rotated revokes
the whole family, which turns a stolen token into a session-wide alarm instead
of a silent second session.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.csrf import require_same_origin
from app.core.errors import ConflictError, UnauthorizedError
from app.core.rate_limit import rate_limit
from app.core.security import (
    Role,
    create_access_token,
    create_refresh_token,
    current_user,
    decode_token,
    hash_password,
    hash_token,
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


def _request_metadata(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    host = request.client.host if request.client else None
    return (user_agent[:400] if user_agent else None, host)


def _store_refresh_token(
    session: Session,
    *,
    token: str,
    user_id: str,
    family_id: uuid.UUID,
    settings: Any,
    request: Request,
) -> str:
    """Persist the hash of a freshly issued refresh token and return its row id."""
    user_agent, ip_address = _request_metadata(request)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_days)
    row = session.execute(
        text(
            """
            INSERT INTO refresh_tokens
                (id, user_id, token_hash, family_id, expires_at, user_agent, ip_address)
            VALUES (gen_random_uuid(), CAST(:user_id AS uuid), :token_hash,
                    CAST(:family_id AS uuid), :expires_at, :user_agent, :ip_address)
            RETURNING id::text
            """
        ),
        {
            "user_id": user_id,
            "token_hash": hash_token(token),
            "family_id": str(family_id),
            "expires_at": expires_at,
            "user_agent": user_agent,
            "ip_address": ip_address,
        },
    ).first()
    return row[0]


def _issue_session(
    session: Session,
    request: Request,
    response: Response,
    *,
    user_id: str,
    role: Role,
    settings: Any,
    family_id: uuid.UUID | None = None,
) -> tuple[str, str]:
    """Issue an access token and a stored refresh token.

    Returns ``(access_token, refresh_row_id)`` so the caller can link a rotated
    token to its replacement in the same transaction.
    """
    refresh_token = create_refresh_token(subject=user_id, role=role, settings=settings)
    row_id = _store_refresh_token(
        session,
        token=refresh_token,
        user_id=user_id,
        family_id=family_id or uuid.uuid4(),
        settings=settings,
        request=request,
    )
    _set_refresh_cookie(response, refresh_token, settings)
    return create_access_token(subject=user_id, role=role, settings=settings), row_id


def _revoke_family(session: Session, family_id: str) -> None:
    session.execute(
        text(
            """
            UPDATE refresh_tokens SET revoked_at = now()
            WHERE family_id = CAST(:family_id AS uuid) AND revoked_at IS NULL
            """
        ),
        {"family_id": family_id},
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=201,
    dependencies=[Depends(rate_limit("auth_register", setting="rate_limit_auth_per_min"))],
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> TokenResponse:
    """Create a student account and return an access token."""
    settings = get_settings()
    email = payload.email.strip().lower()

    existing = session.execute(
        text("SELECT id::text FROM users WHERE email = :email"), {"email": email}
    ).first()
    if existing:
        raise ConflictError("An account with that email already exists.")

    # Public registration always creates a student. Administrators are
    # provisioned with `python -m app.cli create-admin`.
    role = Role.STUDENT

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
            "role": role.value,
            "country": (payload.country_iso3 or "").upper() or None,
        },
    ).first()

    session.execute(
        text("INSERT INTO student_profiles (id, user_id, nationality_country_iso3) VALUES (gen_random_uuid(), :user, :country)"),
        {"user": user_id[0], "country": (payload.country_iso3 or "").upper() or None},
    )

    access_token, _ = _issue_session(
        session,
        request,
        response,
        user_id=user_id[0],
        role=role,
        settings=settings,
    )
    session.commit()

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_minutes * 60,
        user=_user_payload(user_id[0], user_id[1], user_id[2], user_id[3]),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("auth_login", setting="rate_limit_auth_per_min"))],
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> TokenResponse:
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
    access_token, _ = _issue_session(
        session, request, response, user_id=row[0], role=role, settings=settings
    )
    session.commit()

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_minutes * 60,
        user=_user_payload(row[0], row[1], row[3], row[4]),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[
        Depends(require_same_origin),
        Depends(rate_limit("auth_refresh", setting="rate_limit_auth_per_min")),
    ],
)
async def refresh(
    request: Request, response: Response, session: Session = Depends(get_db)
) -> TokenResponse:
    """Rotate the refresh cookie and issue a new access token."""
    settings = get_settings()
    token = request.cookies.get(REFRESH_COOKIE) or ""
    if not token:
        raise UnauthorizedError("No refresh token was supplied.", code="missing_refresh_token")

    payload = decode_token(token, secret=settings.jwt_refresh_secret, expected_type="refresh")

    stored = session.execute(
        text(
            """
            SELECT id::text, user_id::text, family_id::text, revoked_at, expires_at
            FROM refresh_tokens WHERE token_hash = :token_hash
            """
        ),
        {"token_hash": hash_token(token)},
    ).first()

    if stored is None:
        raise UnauthorizedError(
            "This session is no longer valid. Please sign in again.",
            code="refresh_token_unknown",
        )

    token_id, user_id, family_id, revoked_at, expires_at = stored
    now = datetime.now(timezone.utc)

    if revoked_at is not None:
        # A rotated or revoked token was presented again: assume it leaked and
        # end every session in the family.
        _revoke_family(session, family_id)
        session.commit()
        raise UnauthorizedError(
            "This session was already used and has been revoked. Please sign in again.",
            code="refresh_token_reused",
        )

    if expires_at <= now:
        session.execute(
            text("UPDATE refresh_tokens SET revoked_at = now() WHERE id = CAST(:id AS uuid)"),
            {"id": token_id},
        )
        session.commit()
        raise UnauthorizedError("Your session has expired.", code="token_expired")

    user = session.execute(
        text("SELECT id::text, email::text, role, full_name, is_active FROM users WHERE id::text = :id"),
        {"id": user_id},
    ).first()
    if not user or not user[4]:
        raise UnauthorizedError("This account is no longer active.")

    role = Role(user[2])
    access_token, new_row_id = _issue_session(
        session,
        request,
        response,
        user_id=user[0],
        role=role,
        settings=settings,
        family_id=uuid.UUID(family_id),
    )

    session.execute(
        text(
            """
            UPDATE refresh_tokens
            SET revoked_at = now(), replaced_by = CAST(:new_id AS uuid)
            WHERE id = CAST(:id AS uuid)
            """
        ),
        {"id": token_id, "new_id": new_row_id},
    )
    session.commit()

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_minutes * 60,
        user=_user_payload(user[0], user[1], user[2], user[3]),
    )


@router.post("/logout", status_code=204, dependencies=[Depends(require_same_origin)])
async def logout(request: Request, response: Response, session: Session = Depends(get_db)) -> Response:
    """Revoke the presented refresh token and clear the cookie."""
    token = request.cookies.get(REFRESH_COOKIE) or ""
    if token:
        row = session.execute(
            text("SELECT id::text, family_id::text FROM refresh_tokens WHERE token_hash = :hash"),
            {"hash": hash_token(token)},
        ).first()
        if row:
            _revoke_family(session, row[1])
            session.commit()
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

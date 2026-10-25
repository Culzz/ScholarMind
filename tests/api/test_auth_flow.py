"""Refresh-cookie rotation, reuse detection and origin checks.

These tests need a database (CI provides one; locally set ``DATABASE_URL``).
They are skipped when Postgres is unreachable so the rest of the unit suite can
run anywhere.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app


def _database_available() -> bool:
    if not os.getenv("DATABASE_URL"):
        return False
    try:
        from app.db.session import get_engine

        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _database_available(), reason="needs a reachable PostgreSQL database"
)


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def account(client: TestClient):
    email = f"auth-{uuid.uuid4().hex[:12]}@example.test"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a long enough password", "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    yield {"email": email, "response": response}
    from app.db.session import get_engine

    with get_engine().begin() as connection:
        connection.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})


def _cookie(client: TestClient) -> str:
    value = client.cookies.get("scholarmind_refresh")
    assert value, "the refresh cookie was not set"
    return value


def test_registration_always_creates_a_student(client: TestClient) -> None:
    email = f"register-{uuid.uuid4().hex[:12]}@example.test"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "a long enough password",
            "role": "admin",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["user"]["role"] == "student"

    from app.db.session import get_engine

    with get_engine().begin() as connection:
        connection.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})


def test_refresh_rotates_the_cookie(client: TestClient, account) -> None:
    first = _cookie(client)

    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]
    second = _cookie(client)
    assert second != first


def test_reusing_a_rotated_token_revokes_the_family(client: TestClient, account) -> None:
    first = _cookie(client)
    assert client.post("/api/v1/auth/refresh").status_code == 200
    second = _cookie(client)

    # An attacker replaying the old cookie is rejected...
    client.cookies.set("scholarmind_refresh", first, path="/api/v1/auth")
    replay = client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "refresh_token_reused"

    # ...and the legitimate session is revoked with it.
    client.cookies.set("scholarmind_refresh", second, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_from_a_foreign_origin_is_rejected(client: TestClient, account) -> None:
    response = client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_origin_rejected"


def test_logout_revokes_the_presented_token(client: TestClient, account) -> None:
    cookie = _cookie(client)

    assert client.post("/api/v1/auth/logout").status_code == 204

    client.cookies.set("scholarmind_refresh", cookie, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401

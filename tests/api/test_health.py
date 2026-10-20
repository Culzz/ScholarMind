"""Smoke tests for the API surface.

These run without a database: the health endpoint reports dependency status but
must not fail when Postgres or Redis are unreachable, and the error envelope must
always be well formed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def test_health_endpoint_shape(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code in (200, 503)
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert "db" in body and "redis" in body and "worker" in body


def test_ready_endpoint_shape(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code in (200, 503)
    assert response.json()["status"] in ("ready", "not_ready")


def test_unknown_route_returns_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "not_found"


def test_request_id_header_is_returned(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.headers.get("X-Request-ID")
    assert response.headers.get("X-Response-Time-ms")

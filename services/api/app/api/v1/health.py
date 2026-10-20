"""Operational health endpoints.

``/health`` reports liveness plus dependency status. It never reveals connection
strings, credentials, or internal error details — only a coarse status per dependency.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine

router = APIRouter(tags=["health"])


def _check_database() -> dict[str, Any]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:  # pragma: no cover - depends on environment
        return {"status": "error", "error": type(exc).__name__}


def _check_redis() -> dict[str, Any]:
    settings = get_settings()
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.ping()
        return {"status": "ok"}
    except Exception as exc:  # pragma: no cover - depends on environment
        return {"status": "error", "error": type(exc).__name__}


def _check_worker() -> dict[str, Any]:
    """The worker publishes a heartbeat key; freshness of that key is the signal."""
    settings = get_settings()
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        ttl = client.ttl("scholarmind:worker:heartbeat")
        if ttl is None or ttl < 0:
            return {"status": "unknown", "detail": "no heartbeat recorded"}
        return {"status": "ok", "heartbeat_ttl_s": ttl}
    except Exception as exc:  # pragma: no cover - depends on environment
        return {"status": "error", "error": type(exc).__name__}


@router.get("/health")
async def health(response: Response) -> dict[str, Any]:
    """Liveness probe with dependency status."""
    db = _check_database()
    redis_status = _check_redis()
    worker = _check_worker()
    healthy = db.get("status") == "ok"
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if healthy else "degraded",
        "version": "1.0.0",
        "environment": get_settings().app_env,
        "db": db,
        "redis": redis_status,
        "worker": worker,
    }


@router.get("/health/ready")
async def ready(response: Response) -> dict[str, Any]:
    """Readiness probe: requires the database to be reachable."""
    db = _check_database()
    ready_now = db.get("status") == "ok"
    if not ready_now:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready_now else "not_ready", "db": db}

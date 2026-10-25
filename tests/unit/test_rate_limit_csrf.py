"""The in-process rate limiter and the cookie CSRF check."""

from __future__ import annotations

import asyncio

import pytest
from starlette.requests import Request

from app.core.config import get_settings
from app.core.csrf import require_same_origin
from app.core.errors import ForbiddenError, RateLimitError
from app.core.rate_limit import SlidingWindowLimiter, limiter_for, reset_rate_limits


def _request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/refresh",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
            "client": ("203.0.113.5", 12345),
        }
    )


def test_limiter_allows_up_to_the_limit_then_refuses() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)

    assert limiter.allow("client", now=100.0)
    assert limiter.allow("client", now=101.0)
    assert not limiter.allow("client", now=102.0)


def test_limiter_window_rolls_forward() -> None:
    limiter = SlidingWindowLimiter(limit=1, window_seconds=10)

    assert limiter.allow("client", now=100.0)
    assert not limiter.allow("client", now=105.0)
    assert limiter.allow("client", now=111.0)


def test_limits_are_per_key() -> None:
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)

    assert limiter.allow("first", now=100.0)
    assert limiter.allow("second", now=100.0)


def test_named_limiters_are_shared_and_resettable() -> None:
    first = limiter_for("test-scope", 1, 60)
    second = limiter_for("test-scope", 1, 60)

    assert first is second
    assert first.allow("client", now=1.0)
    reset_rate_limits()
    assert first.allow("client", now=1.0)


def test_limiter_rejects_a_non_positive_limit() -> None:
    with pytest.raises(ValueError):
        SlidingWindowLimiter(limit=0, window_seconds=60)


def test_csrf_rejects_a_foreign_origin() -> None:
    with pytest.raises(ForbiddenError):
        asyncio.run(require_same_origin(_request({"origin": "https://evil.example"}), get_settings()))


def test_csrf_allows_an_absent_origin() -> None:
    # A native client sends no Origin; only a browser attaches the cookie
    # automatically, and it sends Origin on cross-origin writes.
    asyncio.run(require_same_origin(_request({}), get_settings()))


def test_csrf_allows_a_configured_origin() -> None:
    origin = get_settings().cors_origins[0]

    asyncio.run(require_same_origin(_request({"origin": origin}), get_settings()))


def test_rate_limit_error_maps_to_429() -> None:
    error = RateLimitError("slow down")

    assert error.status_code == 429

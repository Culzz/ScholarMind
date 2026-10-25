"""Request rate limiting.

Limits are defined in settings and enforced here. The limiter is in-process: it
protects a single API instance and is deliberately simple. When the API runs
behind several instances the counters must move to Redis; that is recorded in
docs/SECURITY.md rather than silently assumed to work.

Keys combine the scope with the client address, so one noisy client cannot
consume another client's budget.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.errors import RateLimitError


class SlidingWindowLimiter:
    """Counts events per key inside a rolling window."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(current)
            return True

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


_limiters: dict[tuple[str, int, float], SlidingWindowLimiter] = {}


def limiter_for(name: str, limit: int, window_seconds: float) -> SlidingWindowLimiter:
    key = (name, limit, window_seconds)
    limiter = _limiters.get(key)
    if limiter is None:
        limiter = SlidingWindowLimiter(limit, window_seconds)
        _limiters[key] = limiter
    return limiter


def reset_rate_limits() -> None:
    """Clear every counter. Used by the test suite between cases."""
    for limiter in _limiters.values():
        limiter.reset()


def client_key(request: Request) -> str:
    """The budget a request is charged to."""
    host = request.client.host if request.client else "unknown"
    user_id = getattr(request.state, "user_id", None)
    return f"{user_id or host}"


def rate_limit(
    name: str,
    *,
    setting: str,
    window_seconds: float = 60,
) -> Callable[..., None]:
    """A dependency enforcing ``settings.<setting>`` requests per window."""

    async def dependency(request: Request, settings: Settings = Depends(get_settings)) -> None:
        limit = int(getattr(settings, setting))
        limiter = limiter_for(name, limit, window_seconds)
        if not limiter.allow(f"{name}:{client_key(request)}"):
            raise RateLimitError(
                "Too many requests. Please slow down and try again shortly.",
                code="rate_limited",
                detail={"scope": name, "limit": limit, "window_seconds": int(window_seconds)},
            )

    return dependency

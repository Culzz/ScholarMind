"""CSRF protection for cookie-authenticated endpoints.

The refresh token is carried in an httpOnly cookie, so a cross-site form post
would be sent with the cookie attached. Two defences are used together:

* cookies are set with ``SameSite=Lax``, which no longer sends them on most
  cross-site requests;
* state-changing cookie endpoints reject a request whose ``Origin`` header is
  not in the configured allow-list.

A request without an ``Origin`` header (a native client, curl, or a same-origin
fetch that omits it) is allowed: the browser is the only client that sends the
cookie automatically, and it always sends ``Origin`` on cross-origin writes.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError


async def require_same_origin(
    request: Request, settings: Settings = Depends(get_settings)
) -> None:
    """Reject cross-origin writes that arrive with a refresh cookie."""
    origin = request.headers.get("origin")
    if not origin:
        return
    if origin not in settings.cors_origins:
        raise ForbiddenError(
            "This request came from an origin that is not allowed to use the session cookie.",
            code="csrf_origin_rejected",
        )

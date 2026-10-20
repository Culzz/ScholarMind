"""Error envelope and exception handlers.

Every error returned by the API uses one shape so the frontend can rely on it:

    {
      "error": {
        "code": "not_found",
        "message": "Scholarship not found.",
        "detail": {...},
        "request_id": "..."
      }
    }
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

REQUEST_ID_HEADER = "X-Request-ID"


class ApiError(Exception):
    """Base class for domain errors that map to an HTTP response."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"

    def __init__(self, message: str, *, detail: Any = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
        if code:
            self.code = code


class NotFoundError(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(ApiError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class UnauthorizedError(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class RateLimitError(ApiError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_payload(request: Request, *, code: str, message: str, detail: Any = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "detail": detail,
            "request_id": _request_id(request),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers for domain, HTTP and validation errors."""

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(request, code=exc.code, message=exc.message, detail=exc.detail),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            429: "rate_limited",
        }.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(request, code=code, message=str(exc.detail), detail=None),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_payload(
                request,
                code="validation_error",
                message="The request payload is invalid.",
                detail=exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Never leak internals to the client; the request id ties the user-facing
        # message to the server-side traceback.
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload(
                request,
                code="internal_error",
                message="An unexpected error occurred.",
                detail=None,
            ),
        )

"""FastAPI application factory."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import REQUEST_ID_HEADER, register_exception_handlers

API_DESCRIPTION = """
ScholarMind API — scholarship discovery, eligibility intelligence, and application planning.

Facts are served from structured records with provenance; every material claim is traceable
to an official source, a snapshot version, and a check timestamp.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_secrets()
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description=API_DESCRIPTION,
        version="1.0.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """Attach a request id and timing to every request."""
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        return response

    @app.get("/", include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse({"name": settings.app_name, "docs": "/docs"})

    register_exception_handlers(app)

    from app.api.v1 import router as v1_router

    app.include_router(v1_router, prefix=settings.api_base_path)

    return app


app = create_app()

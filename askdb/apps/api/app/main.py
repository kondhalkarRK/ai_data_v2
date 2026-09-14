"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_v1_router
from app.api.routes import system
from app.auth.rate_limit import FixedWindowRateLimiter
from app.core.config import Settings, get_settings
from app.core.context import current_request_id
from app.core.exceptions import NqlError, RateLimitedError
from app.db.session import DatabaseRegistry
from app.observability.logging import configure_logging
from app.observability.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.schemas.common import ErrorBody, ErrorResponse
from app.semantic.service import SemanticService

logger = logging.getLogger(__name__)

DESCRIPTION = """
Governed natural-language analytics over PostgreSQL.

Numerical answers are always computed in SQL against the analytics databases. Retrieved
documents and web pages may add narrative context, and every such claim carries a
citation. The semantic YAML packs are the only source of truth for entities, metrics and
relationships.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings

    registry = DatabaseRegistry(settings)
    await registry.start()
    app.state.databases = registry
    app.state.login_limiter = FixedWindowRateLimiter(
        limit=settings.rate_limit_login_per_minute, window_seconds=60
    )

    logger.info(
        "api started",
        extra={
            "environment": settings.environment.value,
            "default_industry": settings.default_industry.value,
        },
    )
    try:
        yield
    finally:
        await registry.stop()
        logger.info("api stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level, json_output=resolved.is_production)

    app = FastAPI(
        title="Ask DB API",
        version=system.SERVICE_VERSION,
        description=DESCRIPTION,
        lifespan=lifespan,
        # The interactive docs are useful in development and are an unnecessary surface
        # in production.
        docs_url=None if resolved.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if resolved.is_production else "/openapi.json",
    )
    app.state.settings = resolved
    # Pure file-backed service; safe to create before lifespan and therefore available
    # to ASGI test transports that intentionally skip external database startup.
    app.state.semantic_service = SemanticService(resolved)

    # Middleware runs in reverse registration order, so security headers are applied
    # last and therefore end up on every response, including error responses.
    app.add_middleware(SecurityHeadersMiddleware, settings=resolved)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["content-type", "authorization", resolved.csrf_header_name, "x-industry"],
        expose_headers=["x-request-id", "server-timing"],
        max_age=600,
    )
    if resolved.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=resolved.trusted_hosts)
    app.add_middleware(RequestContextMiddleware, settings=resolved)

    app.include_router(system.router)
    app.include_router(api_v1_router)

    _register_exception_handlers(app)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NqlError)
    async def handle_nql_error(request: Request, exc: NqlError) -> JSONResponse:
        # Client errors are expected traffic; server errors are not and get a stack trace.
        if exc.status_code >= 500:
            logger.exception("application error", extra={"code": exc.code})
        else:
            logger.info(
                "handled error", extra={"code": exc.code, "status": exc.status_code}
            )

        headers = {}
        if isinstance(exc, RateLimitedError):
            headers["Retry-After"] = str(exc.retry_after_seconds)

        body = ErrorResponse(
            error=ErrorBody(
                code=exc.code,
                message=exc.message,
                request_id=current_request_id(),
                details=exc.details,
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(by_alias=True),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        # Field names and constraints are safe to return; submitted values are not, so
        # only the location and the rule are echoed.
        problems = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ())[1:]),
                "problem": error.get("msg", "invalid value"),
            }
            for error in exc.errors()
        ]
        body = ErrorResponse(
            error=ErrorBody(
                code="validation_failed",
                message="The request payload is invalid.",
                request_id=current_request_id(),
                details={"problems": problems},
            )
        )
        return JSONResponse(status_code=422, content=body.model_dump(by_alias=True))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Logged in full, returned as a generic message with a correlating request id.
        logger.exception("unhandled exception", extra={"error_type": type(exc).__name__})
        body = ErrorResponse(
            error=ErrorBody(
                code="internal_error",
                message="An unexpected error occurred. Quote the request id when reporting it.",
                request_id=current_request_id(),
            )
        )
        return JSONResponse(status_code=500, content=body.model_dump(by_alias=True))


app = create_app()

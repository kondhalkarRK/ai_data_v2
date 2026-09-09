"""HTTP middleware: request context, access logging and security headers."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import Industry, Settings
from app.core.context import RequestContext, set_request_context

logger = logging.getLogger("nql.access")

REQUEST_ID_HEADER = "x-request-id"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Establishes the per-request context and logs the outcome.

    The request id is echoed back so a user-visible error can be traced to exactly one
    log line.
    """

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]

        industry = self._settings.default_industry
        header_industry = request.headers.get("x-industry")
        if header_industry:
            try:
                industry = Industry(header_industry.strip().lower())
            except ValueError:
                # An unknown industry header is ignored rather than rejected here; the
                # route dependency validates it properly where it matters.
                logger.debug("ignoring unknown x-industry header", extra={"value": header_industry})

        context = RequestContext(request_id=request_id, industry=industry)
        set_request_context(context)
        request.state.context = context

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.exception(
                "request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                },
            )
            raise

        duration_ms = int((time.perf_counter() - started) * 1000)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["Server-Timing"] = f"app;dur={duration_ms}"

        # Health probes are frequent and uninteresting at info level.
        level = logging.DEBUG if request.url.path in {"/health", "/ready"} else logging.INFO
        logger.log(
            level,
            "request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "request_id": request_id,
                "user_id": str(context.user_id) if context.user_id else None,
            },
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Applies response security headers (spec section 20)."""

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings
        # The API serves JSON and SSE only, never HTML or scripts, so the strictest
        # possible policy is correct here. The frontend sets its own policy.
        self._csp = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Content-Security-Policy", self._csp)
        headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        )
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        # Authenticated API responses must never be cached by an intermediary.
        headers.setdefault("Cache-Control", "no-store")
        if self._settings.cookie_secure:
            headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response

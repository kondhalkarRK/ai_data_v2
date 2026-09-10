"""Route dependencies: sessions, the current user, CSRF and role checks."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import read_access_token, read_csrf_cookie
from app.auth.rate_limit import FixedWindowRateLimiter, client_ip
from app.auth.service import AuthService, RequestFingerprint
from app.auth.tokens import constant_time_equals, decode_access_token
from app.core.config import Industry, Settings, get_settings
from app.core.context import RequestContext
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    CsrfError,
    DependencyUnavailableError,
    ValidationError,
)
from app.db.session import DatabaseRegistry
from app.models.enums import Role
from app.models.user import User
from app.semantic.service import SemanticService

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def _bypass_user(session: AsyncSession) -> User:
    """TEMPORARY: pick the first active admin (else any active user) when AUTH_BYPASS=true."""
    admin = await session.scalar(
        select(User)
        .where(User.is_active.is_(True), User.role == Role.ADMIN)
        .order_by(User.created_at.asc())
        .limit(1)
    )
    if admin is not None:
        return admin
    any_user = await session.scalar(
        select(User).where(User.is_active.is_(True)).order_by(User.created_at.asc()).limit(1)
    )
    if any_user is None:
        raise AuthenticationError(
            "AUTH_BYPASS is on but no active user exists. Run scripts/create_admin.py first."
        )
    return any_user


def get_app_settings() -> Settings:
    return get_settings()


def get_registry(request: Request) -> DatabaseRegistry:
    registry: DatabaseRegistry | None = getattr(request.app.state, "databases", None)
    if registry is None:
        raise DependencyUnavailableError("The database registry is not initialised.")
    return registry


def get_semantic_service(request: Request) -> SemanticService:
    service: SemanticService | None = getattr(
        request.app.state, "semantic_service", None
    )
    if service is None:
        raise DependencyUnavailableError("The semantic service is not initialised.")
    return service


def get_login_limiter(request: Request) -> FixedWindowRateLimiter:
    limiter: FixedWindowRateLimiter | None = getattr(request.app.state, "login_limiter", None)
    if limiter is None:
        raise DependencyUnavailableError("The rate limiter is not initialised.")
    return limiter


async def get_app_session(
    registry: Annotated[DatabaseRegistry, Depends(get_registry)],
) -> AsyncIterator[AsyncSession]:
    async with registry.app_session() as session:
        yield session


def get_request_context(request: Request) -> RequestContext:
    context: RequestContext | None = getattr(request.state, "context", None)
    if context is None:
        raise DependencyUnavailableError("The request context middleware did not run.")
    return context


def get_fingerprint(request: Request) -> RequestFingerprint:
    return RequestFingerprint(
        request_id=get_request_context(request).request_id,
        ip_address=client_ip(
            request.headers.get("x-forwarded-for"),
            request.client.host if request.client else None,
        ),
        user_agent=request.headers.get("user-agent"),
    )


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    limiter: Annotated[FixedWindowRateLimiter, Depends(get_login_limiter)],
) -> AuthService:
    return AuthService(session=session, settings=settings, login_limiter=limiter)


async def verify_csrf(
    request: Request, settings: Annotated[Settings, Depends(get_app_settings)]
) -> None:
    """Double-submit CSRF check for cookie-authenticated mutations.

    Skipped for safe methods and for bearer-token callers, which are not subject to
    ambient cookie authority and therefore cannot be CSRF'd.
    """
    if settings.auth_bypass and not settings.is_production:
        return

    if request.method in SAFE_METHODS:
        return

    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return

    cookie_token = read_csrf_cookie(request)
    header_token = request.headers.get(settings.csrf_header_name)
    if not cookie_token or not header_token:
        raise CsrfError("Missing CSRF token.")
    if not constant_time_equals(cookie_token, header_token):
        raise CsrfError("CSRF token mismatch.")


async def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
    session: Annotated[AsyncSession, Depends(get_app_session)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> User:
    # TEMPORARY local testing: skip JWT and impersonate the first admin.
    if settings.auth_bypass and not settings.is_production:
        user = await _bypass_user(session)
        context.user_id = user.id
        context.role = user.role
        context.email = user.email
        return user

    token = read_access_token(request)
    if not token:
        raise AuthenticationError

    claims = decode_access_token(settings, token)

    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active:
        # The token is valid but the account no longer is. Treated as unauthenticated so
        # the client clears its session rather than retrying.
        raise AuthenticationError("This account is no longer active.")

    context.user_id = user.id
    context.role = user.role
    context.email = user.email
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(
    minimum: Role,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Dependency factory enforcing a minimum role.

    ``admin`` satisfies ``analyst``, and ``analyst`` satisfies ``viewer``.
    """

    async def _check(user: CurrentUser) -> User:
        if not user.role.at_least(minimum):
            raise AuthorizationError(
                f"This action requires the '{minimum.value}' role or higher."
            )
        return user

    return _check


RequireViewer = Annotated[User, Depends(require_role(Role.VIEWER))]
RequireAnalyst = Annotated[User, Depends(require_role(Role.ANALYST))]
RequireAdmin = Annotated[User, Depends(require_role(Role.ADMIN))]


def resolve_industry(
    request: Request,
    user: CurrentUser,
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> Industry:
    """Determine which analytics industry this request targets.

    Precedence: explicit ``industry`` query parameter, then the ``X-Industry`` header,
    then the user's saved default.
    """
    raw = request.query_params.get("industry") or request.headers.get("x-industry")
    if raw:
        try:
            industry = Industry(raw.strip().lower())
        except ValueError as exc:
            valid = ", ".join(member.value for member in Industry)
            raise ValidationError(
                f"Unknown industry '{raw}'. Expected one of: {valid}."
            ) from exc
    else:
        industry = user.default_industry

    context.industry = industry
    return industry


ActiveIndustry = Annotated[Industry, Depends(resolve_industry)]

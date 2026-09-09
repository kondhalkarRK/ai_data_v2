"""Cookie handling for the browser session.

The access and refresh tokens are HttpOnly so client JavaScript cannot read them, which
removes the XSS token-theft path that ``localStorage`` would open. The CSRF token is
deliberately readable, because the frontend has to echo it back in a header.
"""

from __future__ import annotations

from typing import Final

from fastapi import Request, Response

from app.core.config import Settings

ACCESS_COOKIE: Final = "nql_access"
REFRESH_COOKIE: Final = "nql_refresh"
CSRF_COOKIE: Final = "nql_csrf"

# The refresh cookie is only ever sent to the endpoints that consume it, so a request to
# any other route cannot leak it.
REFRESH_COOKIE_PATH: Final = "/api/v1/auth"


def set_session_cookies(
    response: Response,
    settings: Settings,
    *,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
) -> None:
    # Spelled out per call rather than splatted from a dict: Starlette's ``samesite`` is
    # a Literal, and a dict of mixed value types erases that back to ``str``.
    domain = settings.cookie_domain or None
    secure = settings.cookie_secure
    samesite = settings.cookie_samesite
    refresh_max_age = settings.jwt_refresh_ttl_days * 24 * 60 * 60

    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.jwt_access_ttl_minutes * 60,
        httponly=True,
        path="/",
        domain=domain,
        secure=secure,
        samesite=samesite,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        path=REFRESH_COOKIE_PATH,
        domain=domain,
        secure=secure,
        samesite=samesite,
    )
    # Readable by design: the frontend echoes this value back in a header so the server
    # can compare the two halves of the double-submit pair.
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=refresh_max_age,
        httponly=False,
        path="/",
        domain=domain,
        secure=secure,
        samesite=samesite,
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    domain = settings.cookie_domain or None
    response.delete_cookie(ACCESS_COOKIE, path="/", domain=domain)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, domain=domain)
    response.delete_cookie(CSRF_COOKIE, path="/", domain=domain)


def read_access_token(request: Request) -> str | None:
    """Read the access token from the cookie, or from a bearer header.

    The header path exists for non-browser clients such as scripts and integration tests,
    which have no cookie jar and no CSRF exposure.
    """
    cookie_value = request.cookies.get(ACCESS_COOKIE)
    if cookie_value:
        return cookie_value

    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def read_refresh_token(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE)


def read_csrf_cookie(request: Request) -> str | None:
    return request.cookies.get(CSRF_COOKIE)

"""Adversarial regressions for the ASVS-aligned application hardening.

These tests provide evidence for specific controls, not Level 2 certification.
"""

from __future__ import annotations

import logging
import sys

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.cookies import ACCESS_COOKIE, REFRESH_COOKIE
from app.auth.passwords import hash_password
from app.auth.rate_limit import FixedWindowRateLimiter, client_ip
from app.core.config import Industry, Settings
from app.main import create_app
from app.models.enums import Role
from app.observability.logging import JsonFormatter, RedactedTextFormatter
from app.repositories.users import UserRepository

EMAIL = "security@example.com"
PASSWORD = "Vh7!kRq2$mTx9pLw"


async def seed_and_login(client, session_factory):
    async with session_factory() as session:
        await UserRepository(session).create(
            email=EMAIL, full_name="Security User", password_hash=hash_password(PASSWORD),
            role=Role.ADMIN, default_industry=Industry.AUTOMOTIVE,
        )
        await session.commit()
    response = await client.post(
        "/api/v1/auth/login", json={"username": EMAIL, "password": PASSWORD},
    )
    assert response.status_code == 200
    return client.cookies.get(ACCESS_COOKIE), response.json()["csrfToken"]


@pytest.mark.parametrize("all_sessions", [False, True])
async def test_logout_immediately_blocks_captured_access_token(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], all_sessions: bool,
):
    token, csrf = await seed_and_login(client, session_factory)
    assert (await client.post(
        "/api/v1/auth/logout", json={"allSessions": all_sessions},
        headers={"x-csrf-token": csrf},
    )).status_code == 204
    client.cookies.clear()
    assert (await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )).status_code == 401


async def test_bearer_only_logout_revokes_current_family(client, session_factory):
    token, _ = await seed_and_login(client, session_factory)
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.post(
        "/api/v1/auth/logout", json={"allSessions": False}, headers=headers,
    )).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_rotation_preserves_access_but_reuse_ends_it(client, session_factory):
    token, _ = await seed_and_login(client, session_factory)
    old_refresh = client.cookies.get(REFRESH_COOKIE)
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200
    client.cookies.delete(ACCESS_COOKIE)
    assert (await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )).status_code == 200
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, old_refresh, path="/api/v1/auth")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    assert (await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )).status_code == 401


async def test_password_change_revokes_other_captured_access(client, session_factory):
    first, _ = await seed_and_login(client, session_factory)
    second = await client.post(
        "/api/v1/auth/login", json={"username": EMAIL, "password": PASSWORD},
    )
    response = await client.post(
        "/api/v1/auth/me/password",
        json={"currentPassword": PASSWORD, "newPassword": "Another-Strong-Passphrase-92!"},
        headers={"x-csrf-token": second.json()["csrfToken"]},
    )
    assert response.status_code == 204
    client.cookies.clear()
    assert (await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {first}"},
    )).status_code == 401


async def test_bearer_header_does_not_bypass_cookie_csrf(client, session_factory):
    token, _ = await seed_and_login(client, session_factory)
    for bearer in ["invalid-token", token]:
        response = await client.post(
            "/api/v1/auth/logout", json={"allSessions": False},
            headers={"Authorization": f"Bearer {bearer}"},
        )
        assert response.status_code == 403
    assert (await client.get("/api/v1/auth/me")).status_code == 200


@pytest.mark.parametrize("path", ["login", "refresh", "logout"])
async def test_untrusted_browser_origin_is_rejected_before_auth(client, path):
    response = await client.post(
        f"/api/v1/auth/{path}", json={}, headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "no-store"


async def test_allowed_browser_origin_can_login(client, session_factory):
    await seed_and_login(client, session_factory)
    response = await client.post(
        "/api/v1/auth/login", json={"username": EMAIL, "password": PASSWORD},
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200


async def test_cross_site_fetch_without_origin_is_rejected(client):
    assert (await client.post(
        "/api/v1/auth/refresh", headers={"Sec-Fetch-Site": "cross-site"},
    )).status_code == 403


async def test_forwarding_header_cannot_rotate_login_throttle_identity(client):
    statuses = []
    for i in range(6):
        response = await client.post(
            "/api/v1/auth/login", json={"username": f"unknown{i}", "password": PASSWORD},
            headers={"X-Forwarded-For": f"203.0.113.{i + 1}"},
        )
        statuses.append(response.status_code)
    assert statuses == [401] * 5 + [429]
    assert client_ip("203.0.113.4", "127.0.0.1") == "127.0.0.1"


async def test_authenticated_api_budget_returns_retry_after(client, session_factory):
    await seed_and_login(client, session_factory)
    client._transport.app.state.api_limiter = FixedWindowRateLimiter(limit=1)
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


async def test_headers_cover_host_rejection_and_request_id_is_bounded(client):
    response = await client.get("/health", headers={"Host": "attacker.example"})
    assert response.status_code == 400
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    response = await client.get("/health", headers={"X-Request-ID": "bad value " * 100})
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) <= 64
    assert " " not in request_id


async def test_unexpected_errors_are_generic_and_uncacheable(settings):
    app = create_app(settings)

    @app.get("/test-error")
    async def error():
        raise RuntimeError("password=do-not-expose-this")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://testserver",
    ) as http:
        response = await http.get("/test-error")
    assert response.status_code == 500
    assert "do-not-expose-this" not in response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize("formatter", [JsonFormatter(), RedactedTextFormatter()])
def test_exception_tracebacks_are_redacted(formatter):
    try:
        raise RuntimeError("password=secret-traceback-value")
    except RuntimeError:
        record = logging.LogRecord("test", logging.ERROR, __file__, 1, "Failed", (), sys.exc_info())
    result = formatter.format(record)
    assert "secret-traceback-value" not in result
    assert "[redacted]" in result


def production_settings(**changes):
    return Settings(_env_file=None, **({
        "environment": "production", "jwt_secret_key": "production-test-only-secret-64-chars-xxxx",
        "cookie_secure": True, "auth_bypass": False, "ssl_verify": True,
        "cors_allowed_origins": ["https://soci.example"], "trusted_hosts": ["soci.example"],
    } | changes))


@pytest.mark.parametrize("changes", [
    {"ssl_verify": False, "ssl_cert_file": ""}, {"trusted_hosts": []},
    {"trusted_hosts": ["*"]}, {"cors_allowed_origins": ["http://soci.example"]},
    {"auth_bypass": True}, {"cookie_secure": False},
])
def test_insecure_production_configuration_fails_closed(changes):
    with pytest.raises(ValidationError):
        production_settings(**changes)


async def test_production_hides_docs_and_sets_hsts():
    app = create_app(production_settings())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://soci.example",
    ) as http:
        response = await http.get("/docs")
    assert response.status_code == 404
    assert "includeSubDomains" in response.headers["Strict-Transport-Security"]

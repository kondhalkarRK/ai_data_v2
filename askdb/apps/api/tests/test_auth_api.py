"""End-to-end authentication tests over the HTTP surface."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE
from app.auth.passwords import hash_password
from app.core.config import Industry
from app.models.enums import Role
from app.repositories.users import UserRepository

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Vh7!kRq2$mTx9pLw"


async def _seed_admin(
    session_factory: async_sessionmaker[AsyncSession], *, is_active: bool = True
) -> None:
    async with session_factory() as session:
        repo = UserRepository(session)
        user = await repo.create(
            email=ADMIN_EMAIL,
            full_name="Test Admin",
            password_hash=hash_password(ADMIN_PASSWORD),
            role=Role.ADMIN,
            default_industry=Industry.INSURANCE,
        )
        if not is_active:
            await repo.set_active(user, is_active=False)
        await session.commit()


async def _login(client: AsyncClient, password: str = ADMIN_PASSWORD):
    return await client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": password}
    )


async def test_health_is_public(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "nql-insight-api"
    # Liveness must not disclose dependency detail.
    assert "dependencies" not in body


async def test_security_headers_present(client: AsyncClient) -> None:
    headers = (await client.get("/health")).headers

    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "content-security-policy" in headers
    assert headers["cache-control"] == "no-store"
    assert "x-request-id" in headers


async def test_login_sets_httponly_cookies(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_admin(session_factory)

    response = await _login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == ADMIN_EMAIL
    assert body["user"]["role"] == "admin"
    # No token may appear in the response body.
    assert "accessToken" not in body
    assert "refreshToken" not in body

    set_cookie = " ".join(response.headers.get_list("set-cookie")).lower()
    assert f"{ACCESS_COOKIE}=" in set_cookie
    assert f"{REFRESH_COOKIE}=" in set_cookie
    assert "httponly" in set_cookie
    # The CSRF cookie must be readable by the frontend, so it is the one without HttpOnly.
    assert CSRF_COOKIE in client.cookies


async def test_login_with_wrong_password_is_generic(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_admin(session_factory)

    response = await _login(client, password="Definitely-Wrong-1!")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_unknown_email_returns_the_same_error(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Definitely-Wrong-1!"},
    )

    assert response.status_code == 401
    # Identical to the wrong-password case, so the endpoint cannot enumerate accounts.
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_disabled_account_cannot_sign_in(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_admin(session_factory, is_active=False)

    response = await _login(client)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "account_locked"


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_me_returns_profile_after_login(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_admin(session_factory)
    await _login(client)

    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == ADMIN_EMAIL


async def test_refresh_rotates_the_token(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_admin(session_factory)
    await _login(client)
    original_refresh = client.cookies.get(REFRESH_COOKIE)

    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    assert client.cookies.get(REFRESH_COOKIE) != original_refresh


async def test_reusing_a_rotated_refresh_token_revokes_the_family(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_admin(session_factory)
    await _login(client)
    stolen = client.cookies.get(REFRESH_COOKIE)

    # Legitimate rotation.
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200

    # An attacker replays the token captured before rotation. The jar is cleared first so
    # the replayed value is the only refresh cookie on the request.
    successor = client.cookies.get(REFRESH_COOKIE)
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, stolen)
    replay = await client.post("/api/v1/auth/refresh")

    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "token_reuse_detected"

    # The whole family is now dead, so even the legitimate successor stops working.
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, successor)
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_logout_requires_csrf_header(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_admin(session_factory)
    await _login(client)

    without_header = await client.post("/api/v1/auth/logout", json={"allSessions": False})

    assert without_header.status_code == 403
    assert without_header.json()["error"]["code"] == "csrf_failed"


async def test_logout_clears_the_session(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_admin(session_factory)
    login = await _login(client)
    csrf = login.json()["csrfToken"]

    response = await client.post(
        "/api/v1/auth/logout",
        json={"allSessions": False},
        headers={"x-csrf-token": csrf},
    )

    assert response.status_code == 204
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_login_is_rate_limited(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_admin(session_factory)

    statuses = [
        (await _login(client, password="Wrong-Password-9!")).status_code for _ in range(7)
    ]

    assert 429 in statuses
    # The configured limit is 5 per minute, so the sixth attempt onwards is throttled.
    assert statuses[:5] == [401] * 5


async def test_rate_limited_response_carries_retry_after(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_admin(session_factory)
    for _ in range(6):
        response = await _login(client, password="Wrong-Password-9!")

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


@pytest.mark.parametrize("path", ["/api/v1/auth/me", "/api/v1/auth/users"])
async def test_protected_routes_reject_anonymous(client: AsyncClient, path: str) -> None:
    assert (await client.get(path)).status_code == 401


async def test_viewer_cannot_list_users(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        await UserRepository(session).create(
            email="viewer@example.com",
            full_name="Read Only",
            password_hash=hash_password(ADMIN_PASSWORD),
            role=Role.VIEWER,
            default_industry=Industry.AUTOMOTIVE,
        )
        await session.commit()

    await client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@example.com", "password": ADMIN_PASSWORD},
    )

    response = await client.get("/api/v1/auth/users")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_validation_error_does_not_echo_the_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"email": "not-an-email", "password": "s3cret-value"}
    )

    assert response.status_code == 422
    assert "s3cret-value" not in response.text

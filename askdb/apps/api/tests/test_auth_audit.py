"""The security trail must survive the error response it describes.

A failed login and a detected token reuse both end in an exception, and the request-scoped
session rolls back when a handler raises. Without an explicit commit the audit row and the
family revocation would be discarded — which is exactly backwards, since those are the
records an incident investigation depends on.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.cookies import REFRESH_COOKIE
from app.auth.passwords import hash_password
from app.core.config import Industry
from app.models.audit import AuthAuditEvent
from app.models.enums import AuthEventType, Role
from app.models.refresh_token import RefreshToken
from app.repositories.users import UserRepository

EMAIL = "auditee@example.com"
PASSWORD = "Vh7!kRq2$mTx9pLw"


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await UserRepository(session).create(
            email=EMAIL,
            full_name="Audit Subject",
            password_hash=hash_password(PASSWORD),
            role=Role.ANALYST,
            default_industry=Industry.INSURANCE,
        )
        await session.commit()


async def _events(
    session_factory: async_sessionmaker[AsyncSession], event_type: AuthEventType
) -> list[AuthAuditEvent]:
    async with session_factory() as session:
        stmt = select(AuthAuditEvent).where(AuthAuditEvent.event_type == event_type)
        return list((await session.execute(stmt)).scalars())


async def test_failed_login_is_recorded(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed(session_factory)

    await client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": "Wrong-Password-1!"}
    )

    events = await _events(session_factory, AuthEventType.LOGIN_FAILED)
    assert len(events) == 1
    assert events[0].succeeded is False
    assert events[0].email_attempted == EMAIL
    assert events[0].reason == "bad_credentials"


async def test_successful_login_is_recorded(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed(session_factory)

    await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})

    events = await _events(session_factory, AuthEventType.LOGIN_SUCCEEDED)
    assert len(events) == 1
    assert events[0].succeeded is True


async def test_login_for_unknown_email_is_recorded_without_a_user(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "Wrong-Password-1!"},
    )

    events = await _events(session_factory, AuthEventType.LOGIN_FAILED)
    assert len(events) == 1
    # No account exists, but the probe is still visible.
    assert events[0].user_id is None
    assert events[0].email_attempted == "ghost@example.com"


async def test_audit_never_stores_the_submitted_password(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed(session_factory)
    secret = "Nobody-Should-See-This-1!"

    await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": secret})

    async with session_factory() as session:
        rows = list((await session.execute(select(AuthAuditEvent))).scalars())

    for row in rows:
        assert secret not in str(row.metadata_json)
        assert secret != row.reason


async def test_token_reuse_revocation_is_durable(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed(session_factory)
    await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    stolen = client.cookies.get(REFRESH_COOKIE)

    await client.post("/api/v1/auth/refresh")

    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, stolen)
    await client.post("/api/v1/auth/refresh")

    async with session_factory() as session:
        tokens = list((await session.execute(select(RefreshToken))).scalars())

    assert len(tokens) == 2
    # The revocation was committed even though the request ended in a 401.
    assert all(token.revoked_at is not None for token in tokens)
    assert all(token.revoked_reason == "reuse_detected" for token in tokens)

    events = await _events(session_factory, AuthEventType.TOKEN_REUSE_DETECTED)
    assert len(events) == 1

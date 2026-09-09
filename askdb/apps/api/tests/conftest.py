"""Test fixtures.

Tests run against SQLite by default so the suite needs no external services. Anything
that depends on PostgreSQL-specific behaviour is marked and skipped unless
``TEST_DATABASE_URL`` points at a real database.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-long-enough-for-tests-xx")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("RATE_LIMIT_LOGIN_PER_MINUTE", "5")
# Empty means host-only cookies, which is what the ASGI test host needs: a cookie scoped
# to "localhost" would never be stored for requests to "testserver".
os.environ.setdefault("COOKIE_DOMAIN", "")

from app.api.deps import get_app_session, get_registry
from app.auth.rate_limit import FixedWindowRateLimiter
from app.core.config import Settings, get_settings
from app.main import create_app
from app.models import Base

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture(scope="session")
def settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
        await session.commit()


@pytest.fixture
async def client(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> AsyncIterator[AsyncClient]:
    """An HTTP client bound to the app, with the database swapped for SQLite."""
    app = create_app(settings)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    class _StubRegistry:
        """Stands in for DatabaseRegistry so lifespan startup is not required."""

        async def check_app_database(self) -> tuple[bool, str]:
            return True, "ok"

        async def check_analytics_database(self, industry: object) -> tuple[bool, str]:
            return False, "not_configured_in_tests"

    app.dependency_overrides[get_app_session] = _session_override
    app.dependency_overrides[get_registry] = _StubRegistry
    app.state.login_limiter = FixedWindowRateLimiter(
        limit=settings.rate_limit_login_per_minute, window_seconds=60
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client

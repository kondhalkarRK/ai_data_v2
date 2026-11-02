"""Phase 0: ASK_ME_RAG_ENABLED gates document mutations and exposes capabilities."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_app_session, get_registry
from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE
from app.auth.passwords import hash_password
from app.auth.rate_limit import FixedWindowRateLimiter
from app.core.config import Industry, Settings, get_settings
from app.core.exceptions import RagDisabledError
from app.main import create_app
from app.models.enums import Role
from app.rag.feature import rag_enabled, require_rag_mutations
from app.repositories.users import UserRepository
from app.schemas.auth import user_profile

ADMIN_EMAIL = "rag-flag-admin@example.com"
ADMIN_PASSWORD = "Vh7!kRq2$mTx9pLw"


async def _seed_admin(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.create(
            email=ADMIN_EMAIL,
            full_name="RAG Flag Admin",
            password_hash=hash_password(ADMIN_PASSWORD),
            role=Role.ADMIN,
            default_industry=Industry.INSURANCE,
        )
        await session.commit()


def _client_for_settings(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> AsyncClient:
    app = create_app(settings)

    async def _session_override():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    class _StubRegistry:
        async def check_app_database(self) -> tuple[bool, str]:
            return True, "ok"

        async def check_analytics_database(self, industry: object) -> tuple[bool, str]:
            return False, "not_configured_in_tests"

    app.dependency_overrides[get_app_session] = _session_override
    app.dependency_overrides[get_registry] = _StubRegistry
    app.state.login_limiter = FixedWindowRateLimiter(
        limit=settings.rate_limit_login_per_minute, window_seconds=60
    )
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@pytest.fixture
def rag_off_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"ask_me_rag_enabled": False})


@pytest.fixture
def rag_on_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"ask_me_rag_enabled": True})


def test_rag_enabled_reflects_settings(rag_off_settings: Settings, rag_on_settings: Settings) -> None:
    assert rag_enabled(rag_off_settings) is False
    assert rag_enabled(rag_on_settings) is True


def test_require_rag_mutations_raises_when_disabled(rag_off_settings: Settings) -> None:
    with pytest.raises(RagDisabledError) as exc:
        require_rag_mutations(rag_off_settings)
    assert exc.value.code == "rag_disabled"
    assert exc.value.status_code == 403


def test_user_profile_capabilities(rag_off_settings: Settings, rag_on_settings: Settings) -> None:
    from datetime import UTC, datetime

    from app.models.user import User

    user = User(
        id=__import__("uuid").uuid4(),
        username="u",
        email="u@example.com",
        full_name="U",
        role=Role.USER,
        default_industry=Industry.INSURANCE,
        is_active=True,
        must_change_password=False,
        password_hash="x",
        created_at=datetime.now(UTC),
    )
    assert user_profile(user, settings=rag_off_settings).capabilities.rag_enabled is False
    assert user_profile(user, settings=rag_on_settings).capabilities.rag_enabled is True


@pytest.mark.asyncio
async def test_mutating_document_routes_return_rag_disabled_when_flag_off(
    rag_off_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_admin(session_factory)
    async with _client_for_settings(rag_off_settings, session_factory) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert login.status_code == 200
        csrf = login.cookies.get(CSRF_COOKIE)
        headers = {
            "x-csrf-token": csrf or "",
            "x-industry": "insurance",
            "cookie": login.headers.get("set-cookie", ""),
        }
        # Authenticated cookie jar is on client
        for path, method in (
            ("/api/v1/documents/reindex", "post"),
            ("/api/v1/documents/doc-1", "delete"),
        ):
            response = await client.request(method, path, headers={"x-industry": "insurance"})
            assert response.status_code == 403, path
            body = response.json()
            assert body["error"]["code"] == "rag_disabled"

        files = {"file": ("note.txt", b"hello", "text/plain")}
        upload = await client.post(
            "/api/v1/documents",
            files=files,
            data={"title": "note"},
            headers={"x-industry": "insurance"},
        )
        assert upload.status_code == 403
        assert upload.json()["error"]["code"] == "rag_disabled"


@pytest.mark.asyncio
async def test_list_and_search_documents_allowed_when_flag_off(
    rag_off_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_admin(session_factory)
    async with _client_for_settings(rag_off_settings, session_factory) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert login.status_code == 200
        list_resp = await client.get("/api/v1/documents", headers={"x-industry": "insurance"})
        assert list_resp.status_code == 200
        search_resp = await client.post(
            "/api/v1/documents/search",
            json={"query": "policy"},
            headers={"x-industry": "insurance"},
        )
        assert search_resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_me_includes_rag_capability(
    rag_on_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_admin(session_factory)
    async with _client_for_settings(rag_on_settings, session_factory) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert login.status_code == 200
        assert login.json()["user"]["capabilities"]["ragEnabled"] is True
        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["capabilities"]["ragEnabled"] is True

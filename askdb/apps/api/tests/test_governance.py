"""Simple ADMIN / USER governance: username login, audit, quotas and the Admin Center."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.cookies import CSRF_COOKIE, REFRESH_COOKIE
from app.auth.passwords import hash_password
from app.core.config import Industry
from app.core.exceptions import QuotaExceededError
from app.models.activity import LlmUsage
from app.models.enums import ExecutionMode, Role
from app.models.governance import AdminAudit, LoginAudit
from app.models.user import User
from app.repositories.users import UserRepository
from app.services.governance.llm_config import set_active_llm
from app.services.governance.quota import enforce_quota, week_start, weekly_usage
from app.services.governance.usage import (
    execution_mode,
    governance_overview,
    llm_usage_overview,
    record_question_usage,
)

PASSWORD = "Vh7!kRq2$mTx9pLw"


@pytest.fixture(autouse=True)
def _reset_llm() -> Iterator[None]:
    set_active_llm(None)
    yield
    set_active_llm(None)


async def _seed(
    session_factory: async_sessionmaker[AsyncSession], username: str, role: Role
) -> User:
    async with session_factory() as session:
        user = await UserRepository(session).create(
            username=username,
            email=f"{username}@askdb.local",
            full_name=username.title(),
            password_hash=hash_password(PASSWORD),
            role=role,
            default_industry=Industry.AUTOMOTIVE,
        )
        await session.commit()
        return user


async def _login(client: AsyncClient, username: str, *, remember_me: bool = True):
    return await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PASSWORD, "rememberMe": remember_me},
    )


def _csrf(client: AsyncClient) -> dict[str, str]:
    return {"x-csrf-token": client.cookies.get(CSRF_COOKIE) or ""}


async def test_limits_follow_the_role(session_factory: async_sessionmaker[AsyncSession]) -> None:
    admin = await _seed(session_factory, "admin", Role.ADMIN)
    user = await _seed(session_factory, "user1", Role.USER)

    assert admin.weekly_token_limit is None and admin.weekly_call_limit is None
    assert user.weekly_token_limit == 60_000 and user.weekly_call_limit == 50


async def test_username_login_is_audited(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed(session_factory, "user1", Role.USER)

    assert (await _login(client, "nobody")).status_code == 401
    response = await _login(client, "USER1")
    assert response.status_code == 200
    profile = response.json()["user"]
    assert profile["username"] == "user1"
    assert profile["role"] == "user"
    assert profile["weeklyTokenLimit"] == 60_000

    logout = await client.post(
        "/api/v1/auth/logout", json={"allSessions": False}, headers=_csrf(client)
    )
    assert logout.status_code == 204

    async with session_factory() as session:
        statuses = sorted(
            (await session.execute(select(LoginAudit.status))).scalars().all()
        )
        actions = set((await session.execute(select(AdminAudit.action))).scalars().all())
    assert statuses == ["FAILED", "LOGOUT"]
    assert {"User Login", "User Logout", "Login Failed"} <= actions


async def test_remember_me_off_issues_browser_session_cookies(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed(session_factory, "user1", Role.USER)

    response = await _login(client, "user1", remember_me=False)

    refresh_cookie = next(
        c for c in response.headers.get_list("set-cookie") if c.startswith(f"{REFRESH_COOKIE}=")
    ).lower()
    assert "max-age" not in refresh_cookie and "expires" not in refresh_cookie
    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    again = next(
        c for c in refreshed.headers.get_list("set-cookie") if c.startswith(f"{REFRESH_COOKIE}=")
    ).lower()
    assert "max-age" not in again


async def test_user_cannot_reach_admin_center(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed(session_factory, "user1", Role.USER)
    await _login(client, "user1")

    for path in ("/api/v1/admin/llm", "/api/v1/admin/governance", "/api/v1/admin/audit"):
        response = await client.get(path)
        assert response.status_code == 403, path
    assert (await client.get("/api/v1/auth/me/usage")).status_code == 200


async def test_admin_changes_llm_and_it_is_audited(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed(session_factory, "admin", Role.ADMIN)
    await _login(client, "admin")

    current = await client.get("/api/v1/admin/llm")
    assert current.status_code == 200
    assert {p["id"] for p in current.json()["providers"]} == {
        "openai",
        "claude",
        "gemini",
        "azure_openai",
        "ollama",
    }

    response = await client.put(
        "/api/v1/admin/llm",
        json={"provider": "ollama", "model": "llama3.1", "temperature": 0.2, "maxTokens": 900},
        headers=_csrf(client),
    )
    assert response.status_code == 200, response.text
    assert response.json()["current"]["provider"] == "ollama"
    assert response.json()["current"]["maxTokens"] == 900

    audit = await client.get("/api/v1/admin/audit", params={"category": "llm"})
    actions = {item["action"] for item in audit.json()["items"]}
    assert {"Changed LLM Provider", "Changed LLM Model", "Changed Max Tokens"} <= actions


async def test_weekly_quota_is_enforced(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await _seed(session_factory, "user1", Role.USER)
    admin = await _seed(session_factory, "admin", Role.ADMIN)

    async with session_factory() as session:
        await enforce_quota(session, user)
        session.add(
            LlmUsage(
                user_id=user.id,
                question="big",
                model_name="gpt-4.1-mini",
                execution_mode="LLM",
                prompt_tokens=59_000,
                completion_tokens=1_000,
                total_tokens=60_000,
                response_time_ms=900,
                created_at=datetime.now(UTC),
            )
        )
        session.add(
            LlmUsage(
                user_id=admin.id,
                question="admin",
                model_name="gpt-4.1-mini",
                execution_mode="LLM",
                prompt_tokens=90_000,
                completion_tokens=0,
                total_tokens=90_000,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

        usage = await weekly_usage(session, user)
        assert usage.tokens_used == 60_000 and usage.tokens_remaining == 0
        with pytest.raises(QuotaExceededError) as caught:
            await enforce_quota(session, user)
        assert caught.value.status_code == 429
        assert caught.value.details["tokenLimit"] == 60_000

        # Administrators are unlimited.
        await enforce_quota(session, admin)


async def test_call_limit_counts_questions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await _seed(session_factory, "user1", Role.USER)
    async with session_factory() as session:
        for _ in range(50):
            await record_question_usage(
                session,
                user_id=user.id,
                question="Total sales",
                industry="automotive",
                mode=ExecutionMode.SCHEMA,
                model_name="none",
                prompt_tokens=0,
                completion_tokens=0,
                response_time_ms=120,
                query_history_id=None,
            )
        await session.commit()
        with pytest.raises(QuotaExceededError):
            await enforce_quota(session, user)

        overview = await governance_overview(session, days=7)
        assert overview["kpis"]["totalQuestions"] == 50
        assert overview["kpis"]["schemaQueries"] == 50
        assert overview["kpis"]["avgResponseMs"] == 120
        assert overview["byUser"][0]["user"] == "user1"

        usage = await llm_usage_overview(session, days=7)
        row = next(item for item in usage["users"] if item["user"] == "user1")
        assert row["calls"] == 50 and row["tokens"] == 0 and row["weekCalls"] == 50


def test_execution_mode_rules() -> None:
    assert execution_mode(cache_hit=True, llm_used=True, path="semantic_llm") is ExecutionMode.CACHE
    assert execution_mode(cache_hit=False, llm_used=False, path="compiled") is ExecutionMode.SCHEMA
    assert execution_mode(cache_hit=False, llm_used=True, path="semantic_llm") is ExecutionMode.LLM
    assert execution_mode(cache_hit=False, llm_used=True, path="compiled") is ExecutionMode.HYBRID


def test_week_starts_monday_utc() -> None:
    start = week_start(datetime(2026, 10, 1, 15, 30, tzinfo=UTC))  # a Thursday
    assert start == datetime(2026, 9, 28, tzinfo=UTC)

"""Per-question usage recording and the admin governance / LLM usage aggregates."""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import LlmUsage
from app.models.enums import ExecutionMode
from app.models.governance import AdminAudit
from app.models.user import User, weekly_limits
from app.services.governance.audit import AUDIT_CATEGORIES
from app.services.governance.quota import week_start

# Dashboards aggregate in Python; a PoC window stays well under this.
MAX_ROWS = 20_000
MODES = [mode.value for mode in ExecutionMode]


def execution_mode(*, cache_hit: bool, llm_used: bool, path: str | None) -> ExecutionMode:
    if cache_hit:
        return ExecutionMode.CACHE
    if not llm_used:
        return ExecutionMode.SCHEMA
    if path == "semantic_llm":
        return ExecutionMode.LLM
    return ExecutionMode.HYBRID


async def record_question_usage(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    question: str,
    industry: str,
    mode: ExecutionMode,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    response_time_ms: int,
    query_history_id: uuid.UUID | None,
) -> None:
    total = prompt_tokens + completion_tokens
    session.add(
        LlmUsage(
            user_id=user_id,
            question=question[:4000],
            model_name=model_name[:120],
            execution_mode=mode.value,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            response_time_ms=response_time_ms,
            industry=industry,
            query_history_id=query_history_id,
            estimated_cost_usd=total * 0.000002,
            purpose="chat",
        )
    )
    await session.flush()


async def _rows(session: AsyncSession, days: int) -> list[LlmUsage]:
    since = datetime.now(UTC) - timedelta(days=days)
    result = await session.execute(
        select(LlmUsage)
        .where(LlmUsage.created_at >= since)
        .order_by(LlmUsage.created_at.desc())
        .limit(MAX_ROWS)
    )
    return list(result.scalars())


async def _users(session: AsyncSession) -> dict[uuid.UUID, User]:
    return {user.id: user for user in (await session.execute(select(User))).scalars()}


def _name(users: dict[uuid.UUID, User], user_id: uuid.UUID | None) -> str:
    user = users.get(user_id) if user_id else None
    return user.username if user else "unknown"


def _avg(values: list[int]) -> int | None:
    return round(sum(values) / len(values)) if values else None


def _day(value: datetime) -> str:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC).date().isoformat()


async def governance_overview(session: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    """Hybrid AI Governance: how questions were answered."""
    rows = await _rows(session, days)
    users = await _users(session)
    by_mode = Counter(row.execution_mode for row in rows)

    today = datetime.now(UTC).date()
    trend: dict[str, Counter[str]] = {
        (today - timedelta(days=offset)).isoformat(): Counter()
        for offset in range(days - 1, -1, -1)
    }
    per_user: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        day = _day(row.created_at)
        if day in trend:
            trend[day][row.execution_mode] += 1
        per_user[_name(users, row.user_id)][row.execution_mode] += 1

    return {
        "days": days,
        "kpis": {
            "totalQuestions": len(rows),
            "schemaQueries": by_mode["SCHEMA"],
            "llmQueries": by_mode["LLM"],
            "hybridQueries": by_mode["HYBRID"],
            "cachedQueries": by_mode["CACHE"],
            "avgResponseMs": _avg(
                [r.response_time_ms for r in rows if r.response_time_ms is not None]
            ),
        },
        "distribution": [{"mode": mode, "count": by_mode[mode]} for mode in MODES],
        "dailyTrend": [
            {"date": day, **{mode: counts[mode] for mode in MODES}} for day, counts in trend.items()
        ],
        "byUser": sorted(
            (
                {
                    "user": name,
                    "total": sum(counts.values()),
                    **{mode: counts[mode] for mode in MODES},
                }
                for name, counts in per_user.items()
            ),
            key=lambda item: -int(item["total"]),
        )[:10],
        "recent": [
            {
                "id": str(row.id),
                "user": _name(users, row.user_id),
                "question": row.question,
                "mode": row.execution_mode,
                "responseMs": row.response_time_ms,
                "createdAt": row.created_at.isoformat(),
            }
            for row in rows[:50]
        ],
    }


async def llm_usage_overview(session: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    """LLM Usage Monitoring: calls, tokens and response time for every user."""
    rows = await _rows(session, days)
    users = await _users(session)
    since_week = week_start()
    llm_rows = [row for row in rows if row.total_tokens > 0]
    models = Counter(row.model_name for row in llm_rows)

    stats: dict[uuid.UUID | None, dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "llmCalls": 0,
            "tokens": 0,
            "times": [],
            "weekTokens": 0,
            "weekCalls": 0,
        }
    )
    for row in rows:
        bucket = stats[row.user_id]
        bucket["calls"] += 1
        bucket["tokens"] += row.total_tokens
        if row.total_tokens > 0:
            bucket["llmCalls"] += 1
        if row.response_time_ms is not None:
            bucket["times"].append(row.response_time_ms)
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
        if created >= since_week:
            bucket["weekTokens"] += row.total_tokens
            bucket["weekCalls"] += 1

    table = []
    for user in users.values():
        bucket = stats.get(user.id) or stats.default_factory()
        token_limit, call_limit = weekly_limits(
            user.role, user.weekly_token_limit, user.weekly_call_limit
        )
        table.append(
            {
                "userId": str(user.id),
                "user": user.username,
                "role": user.role.value,
                "calls": bucket["calls"],
                "llmCalls": bucket["llmCalls"],
                "tokens": bucket["tokens"],
                "avgResponseMs": _avg(bucket["times"]),
                "weekTokens": bucket["weekTokens"],
                "weekCalls": bucket["weekCalls"],
                "tokenLimit": token_limit,
                "callLimit": call_limit,
            }
        )
    table.sort(key=lambda item: (-int(item["tokens"]), -int(item["calls"]), str(item["user"])))

    return {
        "days": days,
        "kpis": {
            "totalLlmCalls": len(llm_rows),
            "totalTokens": sum(row.total_tokens for row in rows),
            "mostUsedModel": models.most_common(1)[0][0] if models else None,
            "activeUsers": sum(1 for item in table if item["calls"]),
        },
        "topUsers": [item for item in table if item["tokens"] or item["calls"]][:5],
        "users": table,
        "models": [{"model": model, "calls": count} for model, count in models.most_common()],
    }


async def audit_log(
    session: AsyncSession, *, category: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    stmt = select(AdminAudit).order_by(AdminAudit.created_at.desc()).limit(min(limit, 500))
    if category and category in AUDIT_CATEGORIES:
        stmt = stmt.where(AdminAudit.action.in_(AUDIT_CATEGORIES[category]))
    rows = list((await session.execute(stmt)).scalars())
    users = await _users(session)
    return [
        {
            "id": str(row.id),
            "user": _name(users, row.user_id) if row.user_id else None,
            "action": row.action,
            "details": row.action_details,
            "createdAt": row.created_at.isoformat(),
        }
        for row in rows
    ]


async def audit_counts(session: AsyncSession, *, days: int = 30) -> dict[str, int]:
    since = datetime.now(UTC) - timedelta(days=days)
    actions = Counter(
        (
            await session.execute(select(AdminAudit.action).where(AdminAudit.created_at >= since))
        ).scalars()
    )
    return {key: sum(actions[a] for a in names) for key, names in AUDIT_CATEGORIES.items()}

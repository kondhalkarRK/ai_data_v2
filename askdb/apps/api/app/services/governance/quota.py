"""Weekly AI quotas for every role (users 60k tokens / 50 calls, admins 60k / 100).

Usage is summed from ``llm_usage`` since Monday 00:00 UTC, so the allowance resets every
week on its own; there is no reset job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import QuotaExceededError
from app.models.activity import LlmUsage
from app.models.user import User, weekly_limits


def week_start(now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    monday = current - timedelta(days=current.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass(frozen=True, slots=True)
class WeeklyUsage:
    tokens_used: int
    calls_used: int
    token_limit: int | None
    call_limit: int | None
    week_start: datetime

    @property
    def resets_at(self) -> datetime:
        return self.week_start + timedelta(days=7)

    @property
    def tokens_remaining(self) -> int | None:
        return None if self.token_limit is None else max(self.token_limit - self.tokens_used, 0)

    @property
    def calls_remaining(self) -> int | None:
        return None if self.call_limit is None else max(self.call_limit - self.calls_used, 0)

    @property
    def exhausted(self) -> bool:
        return self.tokens_remaining == 0 or self.calls_remaining == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "tokenLimit": self.token_limit,
            "tokensUsed": self.tokens_used,
            "tokensRemaining": self.tokens_remaining,
            "callLimit": self.call_limit,
            "callsUsed": self.calls_used,
            "callsRemaining": self.calls_remaining,
            "unlimited": self.token_limit is None and self.call_limit is None,
            "weekStart": self.week_start.isoformat(),
            "resetsAt": self.resets_at.isoformat(),
        }


async def weekly_usage(
    session: AsyncSession, user: User, *, now: datetime | None = None
) -> WeeklyUsage:
    start = week_start(now)
    tokens, calls = (
        await session.execute(
            select(
                func.coalesce(func.sum(LlmUsage.total_tokens), 0), func.count(LlmUsage.id)
            ).where(LlmUsage.user_id == user.id, LlmUsage.created_at >= start)
        )
    ).one()
    token_limit, call_limit = weekly_limits(
        user.role, user.weekly_token_limit, user.weekly_call_limit
    )
    return WeeklyUsage(
        tokens_used=int(tokens),
        calls_used=int(calls),
        token_limit=token_limit,
        call_limit=call_limit,
        week_start=start,
    )


async def enforce_quota(session: AsyncSession, user: User) -> WeeklyUsage:
    """Raise ``QuotaExceededError`` when the user has no tokens or calls left this week."""
    usage = await weekly_usage(session, user)
    if usage.exhausted:
        raise QuotaExceededError(details=usage.to_dict())
    return usage

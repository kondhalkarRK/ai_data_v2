"""Persistence for rule settings, custom monitors, run history and score snapshots.

Uses the application database when its tables exist; otherwise keeps state in process
memory so the Trust Center still works (history then resets on restart, and the response
says so).
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Industry
from app.core.exceptions import DependencyUnavailableError
from app.models.reliability import DqRuleRun, DqRuleSetting, DqScoreSnapshot
from app.services.reliability.model import RuleResult, RunHistory

logger = logging.getLogger(__name__)

StorageMode = Literal["database", "memory"]
HISTORY_DAYS = 120
_RECENT_RATES = 14


@dataclass(slots=True)
class Setting:
    rule_id: str
    custom: bool
    definition: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class RunRow:
    rule_id: str
    ran_at: datetime
    status: str
    pass_rate: float | None


@dataclass(slots=True)
class Snapshot:
    ran_at: datetime
    score: float | None
    dimensions: dict[str, Any]
    rules_passing: int
    rules_failing: int


@dataclass(slots=True)
class _Memory:
    settings: dict[str, Setting] = field(default_factory=dict)
    runs: list[RunRow] = field(default_factory=list)
    snapshots: list[Snapshot] = field(default_factory=list)


_MEMORY: dict[str, _Memory] = defaultdict(_Memory)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _store_problem(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        isinstance(exc, ProgrammingError | DBAPIError | DependencyUnavailableError | OSError)
        or "does not exist" in text
        or "no such table" in text
    )


def summarise_history(rows: list[RunRow]) -> dict[str, RunHistory]:
    """Per rule: last failure, start of the current failing streak and recent pass rates."""
    by_rule: dict[str, list[RunRow]] = defaultdict(list)
    for row in rows:
        by_rule[row.rule_id].append(row)
    out: dict[str, RunHistory] = {}
    for rule_id, items in by_rule.items():
        items.sort(key=lambda r: r.ran_at)
        history = RunHistory(runs=len(items))
        failures = [r.ran_at for r in items if r.status == "failing"]
        history.last_failure_at = failures[-1] if failures else None
        streak_start = None
        for row in reversed(items):
            if row.status != "failing":
                break
            streak_start = row.ran_at
        history.failing_since = streak_start
        history.recent_pass_rates = [r.pass_rate for r in items if r.pass_rate is not None][
            -_RECENT_RATES:
        ]
        out[rule_id] = history
    return out


class ReliabilityStore:
    def __init__(self, session: AsyncSession | None, industry: Industry) -> None:
        self._session = session
        self._industry = industry.value
        self.mode: StorageMode = "database" if session is not None else "memory"

    @property
    def _memory(self) -> _Memory:
        return _MEMORY[self._industry]

    async def _fallback(self, exc: BaseException) -> None:
        if not _store_problem(exc):
            raise exc
        logger.info("reliability store unavailable, using process memory: %s", type(exc).__name__)
        self.mode = "memory"
        if self._session is not None:
            try:
                await self._session.rollback()
            except Exception:
                logger.debug("reliability store rollback failed", exc_info=True)

    # ------------------------------------------------------------------ settings

    async def settings(self) -> dict[str, Setting]:
        if self.mode == "database" and self._session is not None:
            try:
                rows = (
                    await self._session.execute(
                        select(DqRuleSetting).where(DqRuleSetting.industry == self._industry)
                    )
                ).scalars()
                return {
                    row.rule_id: Setting(
                        rule_id=row.rule_id,
                        custom=row.custom,
                        definition=dict(row.definition or {}),
                        overrides=dict(row.overrides or {}),
                        created_by=row.created_by,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                    )
                    for row in rows
                }
            except Exception as exc:
                await self._fallback(exc)
        return dict(self._memory.settings)

    async def save_setting(self, setting: Setting) -> None:
        now = datetime.now(UTC)
        setting.updated_at = now
        setting.created_at = setting.created_at or now
        if self.mode == "database" and self._session is not None:
            try:
                row = (
                    await self._session.execute(
                        select(DqRuleSetting).where(
                            DqRuleSetting.industry == self._industry,
                            DqRuleSetting.rule_id == setting.rule_id,
                        )
                    )
                ).scalar_one_or_none()
                if row is None:
                    row = DqRuleSetting(
                        industry=self._industry,
                        rule_id=setting.rule_id,
                        created_by=setting.created_by,
                    )
                    self._session.add(row)
                row.custom = setting.custom
                row.definition = dict(setting.definition)
                row.overrides = dict(setting.overrides)
                row.updated_at = now
                await self._session.flush()
                return
            except Exception as exc:
                await self._fallback(exc)
        self._memory.settings[setting.rule_id] = setting

    async def delete_setting(self, rule_id: str) -> None:
        if self.mode == "database" and self._session is not None:
            try:
                await self._session.execute(
                    delete(DqRuleSetting).where(
                        DqRuleSetting.industry == self._industry, DqRuleSetting.rule_id == rule_id
                    )
                )
                await self._session.flush()
                return
            except Exception as exc:
                await self._fallback(exc)
        self._memory.settings.pop(rule_id, None)

    # ------------------------------------------------------------------ runs

    async def record_run(
        self,
        *,
        ran_at: datetime,
        results: dict[str, RuleResult],
        score: float | None,
        dimensions: dict[str, Any],
        datasets: dict[str, Any],
        duration_ms: int,
        triggered_by: str | None,
    ) -> None:
        passing = sum(1 for r in results.values() if r.status == "passing")
        failing = sum(1 for r in results.values() if r.status == "failing")
        if self.mode == "database" and self._session is not None:
            try:
                run_id = uuid.uuid4()
                self._session.add(
                    DqScoreSnapshot(
                        id=run_id,
                        industry=self._industry,
                        ran_at=ran_at,
                        score=score,
                        dimensions=dimensions,
                        datasets=datasets,
                        rules_total=len(results),
                        rules_passing=passing,
                        rules_failing=failing,
                        duration_ms=duration_ms,
                        triggered_by=triggered_by,
                    )
                )
                for result in results.values():
                    self._session.add(
                        DqRuleRun(
                            industry=self._industry,
                            run_id=run_id,
                            rule_id=result.rule_id,
                            ran_at=ran_at,
                            status=result.status,
                            total=result.total,
                            failed=result.failed,
                            pass_rate=result.pass_rate,
                            score=result.score,
                            value_at_risk=result.value_at_risk,
                        )
                    )
                cutoff = ran_at - timedelta(days=HISTORY_DAYS)
                await self._session.execute(
                    delete(DqRuleRun).where(
                        DqRuleRun.industry == self._industry, DqRuleRun.ran_at < cutoff
                    )
                )
                await self._session.flush()
                return
            except Exception as exc:
                await self._fallback(exc)
        memory = self._memory
        memory.snapshots.append(Snapshot(ran_at, score, dimensions, passing, failing))
        memory.runs.extend(
            RunRow(r.rule_id, ran_at, r.status, r.pass_rate) for r in results.values()
        )
        cutoff = ran_at - timedelta(days=HISTORY_DAYS)
        memory.runs = [r for r in memory.runs if r.ran_at >= cutoff][-20_000:]
        memory.snapshots = [s for s in memory.snapshots if s.ran_at >= cutoff][-2_000:]

    async def history(self, *, now: datetime) -> dict[str, RunHistory]:
        since = now - timedelta(days=HISTORY_DAYS)
        if self.mode == "database" and self._session is not None:
            try:
                rows = (
                    await self._session.execute(
                        select(
                            DqRuleRun.rule_id,
                            DqRuleRun.ran_at,
                            DqRuleRun.status,
                            DqRuleRun.pass_rate,
                        )
                        .where(DqRuleRun.industry == self._industry, DqRuleRun.ran_at >= since)
                        .order_by(DqRuleRun.ran_at.desc())
                        .limit(20_000)
                    )
                ).all()
                return summarise_history([RunRow(r[0], _aware(r[1]), r[2], r[3]) for r in rows])
            except Exception as exc:
                await self._fallback(exc)
        return summarise_history([r for r in self._memory.runs if r.ran_at >= since])

    async def snapshots(self, *, now: datetime, days: int = 90) -> list[Snapshot]:
        since = now - timedelta(days=days)
        if self.mode == "database" and self._session is not None:
            try:
                rows = (
                    await self._session.execute(
                        select(DqScoreSnapshot)
                        .where(
                            DqScoreSnapshot.industry == self._industry,
                            DqScoreSnapshot.ran_at >= since,
                        )
                        .order_by(DqScoreSnapshot.ran_at)
                        .limit(5_000)
                    )
                ).scalars()
                return [
                    Snapshot(
                        _aware(r.ran_at),
                        r.score,
                        dict(r.dimensions or {}),
                        r.rules_passing,
                        r.rules_failing,
                    )
                    for r in rows
                ]
            except Exception as exc:
                await self._fallback(exc)
        return [s for s in self._memory.snapshots if s.ran_at >= since]

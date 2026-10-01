"""Executes data-quality rules as set-based, read-only SQL against an analytics database."""

# ruff: noqa: S608

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.services.reliability.model import DatasetSpec, RuleResult, RuleSpec, RuleStatus

logger = logging.getLogger(__name__)

ROW_KINDS = frozenset({"row_check", "not_null", "range", "allowed_values", "pattern"})
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
_QUALIFIED = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")
TREND_DAYS = 90
STATEMENT_TIMEOUT_MS = 30_000
SAMPLE_LIMIT = 5


class RuleDefinitionError(ValueError):
    """A rule references an unknown dataset or an unsafe identifier."""


def ident(name: str | None) -> str:
    if not name or not _IDENT.match(name):
        raise RuleDefinitionError(f"Invalid column name: {name!r}")
    return name


def qualified(name: str) -> str:
    if not _QUALIFIED.match(name):
        raise RuleDefinitionError(f"Invalid table name: {name!r}")
    return name


@dataclass(slots=True)
class _Compiled:
    rule: RuleSpec
    condition: str
    scope: str
    params: dict[str, Any]
    expanding: tuple[str, ...]


def compile_condition(rule: RuleSpec, index: int) -> _Compiled:
    """The 'valid row' predicate for a row-level rule, with its bind parameters."""
    params: dict[str, Any] = {}
    expanding: tuple[str, ...] = ()
    if rule.kind == "row_check":
        if not rule.condition:
            raise RuleDefinitionError(f"{rule.id}: row_check needs a condition")
        condition = rule.condition
    elif rule.kind == "not_null":
        columns = rule.columns or ((rule.column,) if rule.column else ())
        if not columns:
            raise RuleDefinitionError(f"{rule.id}: not_null needs a column")
        condition = " AND ".join(
            f"NULLIF(btrim(t.{ident(c)}::text), '') IS NOT NULL" for c in columns
        )
    elif rule.kind == "range":
        column = f"t.{ident(rule.column)}"
        parts = []
        if rule.min_value is not None:
            params[f"lo_{index}"] = rule.min_value
            parts.append(f"{column} >= :lo_{index}")
        if rule.max_value is not None:
            params[f"hi_{index}"] = rule.max_value
            parts.append(f"{column} <= :hi_{index}")
        if not parts:
            raise RuleDefinitionError(f"{rule.id}: range needs a minimum or maximum")
        condition = f"({column} IS NULL OR ({' AND '.join(parts)}))"
    elif rule.kind == "allowed_values":
        if not rule.allowed:
            raise RuleDefinitionError(f"{rule.id}: allowed_values needs values")
        column = f"t.{ident(rule.column)}"
        params[f"vals_{index}"] = list(rule.allowed)
        expanding = (f"vals_{index}",)
        condition = f"({column} IS NULL OR {column}::text IN :vals_{index})"
    elif rule.kind == "pattern":
        if not rule.pattern:
            raise RuleDefinitionError(f"{rule.id}: pattern needs a regular expression")
        column = f"t.{ident(rule.column)}"
        params[f"re_{index}"] = rule.pattern
        condition = f"({column} IS NULL OR {column}::text ~ :re_{index})"
    else:
        raise RuleDefinitionError(f"{rule.id}: {rule.kind} is not a row-level rule")
    return _Compiled(rule, condition, rule.scope or "TRUE", params, expanding)


def _statement(sql: str, params: dict[str, Any], expanding: tuple[str, ...]) -> Any:
    statement = text(sql)
    if expanding:
        statement = statement.bindparams(*(bindparam(name, expanding=True) for name in expanding))
    return statement


def _num(value: Any) -> float:
    return float(value) if value is not None else 0.0


def period_end(value: date | datetime, cadence: str) -> datetime:
    """When the period a business date stands for is complete."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    start = datetime(value.year, value.month, value.day, tzinfo=UTC)
    if cadence == "monthly":
        year, month = (value.year + 1, 1) if value.month == 12 else (value.year, value.month + 1)
        return datetime(year, month, 1, tzinfo=UTC)
    return start + timedelta(days=1)


def freshness_score(lag_hours: float, max_age_hours: float) -> float:
    """100 within the SLA, falling linearly to 0 at three times the SLA."""
    if lag_hours <= max_age_hours:
        return 100.0
    over = (lag_hours - max_age_hours) / max_age_hours
    return round(max(0.0, 100.0 - 50.0 * over), 1)


def finish_population(
    rule: RuleSpec, total: int, failed: int, value_at_risk: float | None
) -> RuleResult:
    if total <= 0:
        return RuleResult(rule.id, "no_data", observed=f"No {rule.unit} to check")
    failed = max(0, min(failed, total))
    pass_rate = round(100.0 * (1 - failed / total), 3)
    status: RuleStatus = "passing" if pass_rate + 1e-9 >= rule.threshold else "failing"
    observed = (
        f"All {total:,} {rule.unit} passed"
        if failed == 0
        else f"{failed:,} of {total:,} {rule.unit} failed"
    )
    return RuleResult(
        rule.id,
        status,
        total=total,
        failed=failed,
        pass_rate=pass_rate,
        score=pass_rate,
        observed=observed,
        value_at_risk=value_at_risk if failed else None,
    )


def _hours(value: float) -> str:
    if value < 48:
        return f"{value:.0f} h"
    return f"{value / 24:.1f} days"


class RuleEngine:
    def __init__(
        self,
        connection: AsyncConnection,
        datasets: dict[str, DatasetSpec],
        *,
        now: datetime | None = None,
    ) -> None:
        self._connection = connection
        self._datasets = datasets
        self._now = now or datetime.now(UTC)

    def dataset(self, name: str) -> DatasetSpec:
        spec = self._datasets.get(name)
        if spec is None:
            raise RuleDefinitionError(f"Unknown dataset: {name}")
        qualified(spec.physical)
        return spec

    async def run(self, rules: list[RuleSpec]) -> dict[str, RuleResult]:
        await self._set_timeout()
        results: dict[str, RuleResult] = {}
        row_rules: dict[str, list[RuleSpec]] = defaultdict(list)
        for rule in rules:
            if rule.kind in ROW_KINDS:
                row_rules[rule.dataset].append(rule)
        for dataset, group in row_rules.items():
            results.update(await self._row_group(dataset, group))
        for rule in rules:
            if rule.kind in ROW_KINDS:
                continue
            started = time.perf_counter()
            try:
                result = await self._single(rule)
            except Exception as exc:
                result = self._error(rule, exc)
            result.duration_ms = int((time.perf_counter() - started) * 1000)
            if rule.trend_sql and result.status in {"passing", "failing"}:
                result.trend = await self._trend(rule)
            results[rule.id] = result
        return results

    async def latest_dates(self) -> dict[str, date | datetime | None]:
        """Most recent business date per dated dataset."""
        out: dict[str, date | datetime | None] = {}
        for spec in self._datasets.values():
            if not spec.date_column:
                continue
            try:
                column = ident(spec.date_column)
                rows = await self._fetch(
                    f"SELECT MAX(t.{column}) FROM {qualified(spec.physical)} t"
                )
                out[spec.name] = rows[0][0]
            except Exception:
                logger.debug("reliability: latest date failed for %s", spec.name, exc_info=True)
                out[spec.name] = None
        return out

    async def row_estimates(self, schema: str) -> dict[str, int]:
        """Approximate row counts from the planner statistics, keyed by ``schema.table``."""
        try:
            async with self._connection.begin_nested():
                rows = (
                    await self._connection.execute(
                        text(
                            "SELECT n.nspname || '.' || c.relname, "
                            "GREATEST(c.reltuples, 0)::bigint FROM pg_class c "
                            "JOIN pg_namespace n ON n.oid = c.relnamespace "
                            "WHERE n.nspname = :schema AND c.relkind IN ('r', 'm', 'p', 'v')"
                        ),
                        {"schema": schema},
                    )
                ).all()
        except Exception:
            logger.debug("reliability: row estimates unavailable", exc_info=True)
            return {}
        return {str(name): int(count or 0) for name, count in rows}

    # ------------------------------------------------------------------ internals

    async def _set_timeout(self) -> None:
        try:
            await self._connection.execute(
                text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
            )
        except Exception:
            logger.debug("reliability: statement_timeout not applied", exc_info=True)

    async def _fetch(
        self, sql: str, params: dict[str, Any] | None = None, expanding: tuple[str, ...] = ()
    ) -> list[Any]:
        async with self._connection.begin_nested():
            result = await self._connection.execute(
                _statement(sql, params or {}, expanding), params or {}
            )
            return list(result.all())

    def _error(self, rule: RuleSpec, exc: BaseException) -> RuleResult:
        logger.warning("reliability: rule %s could not run: %s", rule.id, exc.__class__.__name__)
        message = str(exc).splitlines()[0][:300] if str(exc) else exc.__class__.__name__
        return RuleResult(rule.id, "error", observed="Check could not run", error=message)

    async def _row_group(self, dataset: str, rules: list[RuleSpec]) -> dict[str, RuleResult]:
        out: dict[str, RuleResult] = {}
        try:
            spec = self.dataset(dataset)
        except RuleDefinitionError as exc:
            return {rule.id: self._error(rule, exc) for rule in rules}
        compiled: list[_Compiled] = []
        for index, rule in enumerate(rules):
            try:
                compiled.append(compile_condition(rule, index))
            except RuleDefinitionError as exc:
                out[rule.id] = self._error(rule, exc)
        if not compiled:
            return out
        value = f"t.{ident(spec.value_column)}" if spec.value_column else None
        params: dict[str, Any] = {}
        expanding: list[str] = []
        selects: list[str] = []
        for index, item in enumerate(compiled):
            params.update(item.params)
            expanding.extend(item.expanding)
            fail = f"({item.scope}) AND NOT COALESCE(({item.condition}), FALSE)"
            selects.append(f"COUNT(*) FILTER (WHERE {item.scope}) AS t{index}")
            selects.append(f"COUNT(*) FILTER (WHERE {fail}) AS f{index}")
            selects.append(
                f"SUM({value}) FILTER (WHERE {fail}) AS v{index}" if value else f"NULL AS v{index}"
            )
        started = time.perf_counter()
        try:
            row = (
                await self._fetch(
                    f"SELECT {', '.join(selects)} FROM {spec.physical} t", params, tuple(expanding)
                )
            )[0]
        except Exception as exc:
            for item in compiled:
                out[item.rule.id] = self._error(item.rule, exc)
            return out
        elapsed = int((time.perf_counter() - started) * 1000)
        for index, item in enumerate(compiled):
            result = finish_population(
                item.rule,
                int(row[index * 3] or 0),
                int(row[index * 3 + 1] or 0),
                _num(row[index * 3 + 2]) if row[index * 3 + 2] is not None else None,
            )
            result.duration_ms = elapsed
            if result.status == "failing" and spec.key_column:
                result.samples = await self._row_samples(spec, item)
            out[item.rule.id] = result
        if spec.cadence == "daily" and spec.date_column:
            await self._row_trend(spec, compiled, params, tuple(expanding), out)
        return out

    async def _row_samples(self, spec: DatasetSpec, item: _Compiled) -> list[str]:
        key = ident(spec.key_column)
        try:
            rows = await self._fetch(
                f"SELECT t.{key}::text FROM {spec.physical} t "
                f"WHERE ({item.scope}) AND NOT COALESCE(({item.condition}), FALSE) "
                f"LIMIT {SAMPLE_LIMIT}",
                item.params,
                item.expanding,
            )
        except Exception:
            logger.debug("reliability: samples failed for %s", item.rule.id, exc_info=True)
            return []
        return [f"{key} {r[0]}" for r in rows]

    async def _row_trend(
        self,
        spec: DatasetSpec,
        compiled: list[_Compiled],
        params: dict[str, Any],
        expanding: tuple[str, ...],
        out: dict[str, RuleResult],
    ) -> None:
        column = ident(spec.date_column)
        selects = []
        for index, item in enumerate(compiled):
            fail = f"({item.scope}) AND NOT COALESCE(({item.condition}), FALSE)"
            selects.append(f"COUNT(*) FILTER (WHERE {item.scope}) AS t{index}")
            selects.append(f"COUNT(*) FILTER (WHERE {fail}) AS f{index}")
        sql = (
            f"SELECT t.{column}::date AS period, {', '.join(selects)} FROM {spec.physical} t "
            f"WHERE t.{column} > (SELECT MAX({column}) FROM {spec.physical}) - {TREND_DAYS} "
            "GROUP BY 1"
        )
        try:
            rows = await self._fetch(sql, params, expanding)
        except Exception:
            logger.debug("reliability: row trend failed for %s", spec.name, exc_info=True)
            return
        for index, item in enumerate(compiled):
            result = out.get(item.rule.id)
            if result is None or result.status not in {"passing", "failing"}:
                continue
            result.trend = {
                r[0]: (int(r[1 + index * 2] or 0), int(r[2 + index * 2] or 0)) for r in rows
            }

    async def _single(self, rule: RuleSpec) -> RuleResult:
        if rule.kind == "metric":
            return await self._metric(rule)
        if rule.kind == "unique":
            return await self._unique(rule)
        if rule.kind == "reference":
            return await self._reference(rule)
        if rule.kind == "freshness":
            return await self._freshness(rule)
        raise RuleDefinitionError(f"{rule.id}: unsupported kind {rule.kind}")

    async def _metric(self, rule: RuleSpec) -> RuleResult:
        if not rule.sql:
            raise RuleDefinitionError(f"{rule.id}: metric needs SQL")
        row = (await self._fetch(rule.sql))[0]
        value = _num(row[2]) if len(row) > 2 and row[2] is not None else None
        result = finish_population(rule, int(row[0] or 0), int(row[1] or 0), value)
        if result.status == "failing" and rule.sample_sql:
            try:
                result.samples = [str(r[0]) for r in await self._fetch(rule.sample_sql)][
                    :SAMPLE_LIMIT
                ]
            except Exception:
                logger.debug("reliability: samples failed for %s", rule.id, exc_info=True)
        return result

    async def _unique(self, rule: RuleSpec) -> RuleResult:
        spec = self.dataset(rule.dataset)
        columns = [
            f"t.{ident(c)}" for c in (rule.columns or ((rule.column,) if rule.column else ()))
        ]
        if not columns:
            raise RuleDefinitionError(f"{rule.id}: unique needs columns")
        keys = ", ".join(columns)
        where = " AND ".join(
            [f"({rule.scope})" if rule.scope else "TRUE"] + [f"{c} IS NOT NULL" for c in columns]
        )
        groups = f"SELECT COUNT(*) AS n FROM {spec.physical} t WHERE {where} GROUP BY {keys}"
        row = (
            await self._fetch(
                "SELECT COALESCE(SUM(n), 0), COALESCE(SUM(n - 1) FILTER (WHERE n > 1), 0) "
                f"FROM ({groups}) g"
            )
        )[0]
        result = finish_population(rule, int(row[0] or 0), int(row[1] or 0), None)
        if result.status == "failing":
            label = " || ' / ' || ".join(f"COALESCE({c}::text, '')" for c in columns)
            try:
                rows = await self._fetch(
                    f"SELECT {label} || ' (x' || COUNT(*)::text || ')' FROM {spec.physical} t "
                    f"WHERE {where} GROUP BY {keys} HAVING COUNT(*) > 1 LIMIT {SAMPLE_LIMIT}"
                )
                result.samples = [str(r[0]) for r in rows]
            except Exception:
                logger.debug("reliability: samples failed for %s", rule.id, exc_info=True)
        return result

    async def _reference(self, rule: RuleSpec) -> RuleResult:
        child = self.dataset(rule.dataset)
        parent = self.dataset(rule.ref_dataset or "")
        column, ref = ident(rule.column), ident(rule.ref_column)
        value = f"t.{ident(child.value_column)}" if child.value_column else "NULL::numeric"
        orphan = f"t.{column} IS NOT NULL AND r.{ref} IS NULL"
        join = f"FROM {child.physical} t LEFT JOIN {parent.physical} r ON r.{ref} = t.{column}"
        row = (
            await self._fetch(
                f"SELECT COUNT(*), COUNT(*) FILTER (WHERE {orphan}), "
                f"SUM({value}) FILTER (WHERE {orphan}) {join}"
            )
        )[0]
        result = finish_population(
            rule, int(row[0] or 0), int(row[1] or 0), _num(row[2]) if row[2] is not None else None
        )
        if result.status == "failing":
            try:
                rows = await self._fetch(
                    f"SELECT DISTINCT t.{column}::text {join} WHERE {orphan} LIMIT {SAMPLE_LIMIT}"
                )
                result.samples = [f"{column} {r[0]}" for r in rows]
            except Exception:
                logger.debug("reliability: samples failed for %s", rule.id, exc_info=True)
        return result

    async def _freshness(self, rule: RuleSpec) -> RuleResult:
        spec = self.dataset(rule.dataset)
        column = ident(rule.column or spec.date_column)
        max_age = rule.max_age_hours or spec.sla_hours or 24.0
        latest = (await self._fetch(f"SELECT MAX(t.{column}) FROM {spec.physical} t"))[0][0]
        if latest is None:
            return RuleResult(rule.id, "no_data", observed="No records loaded yet")
        if not isinstance(latest, date):
            raise RuleDefinitionError(f"{rule.id}: {column} is not a date column")
        cadence = spec.cadence if spec.cadence != "static" else "daily"
        lag = max(0.0, (self._now - period_end(latest, cadence)).total_seconds() / 3600.0)
        on_time = lag <= max_age
        shown = latest.date() if isinstance(latest, datetime) else latest
        return RuleResult(
            rule.id,
            "passing" if on_time else "failing",
            total=1,
            failed=0 if on_time else 1,
            pass_rate=100.0 if on_time else 0.0,
            score=freshness_score(lag, max_age),
            observed=f"Latest data {shown:%d %b %Y}, {_hours(lag)} old (SLA {_hours(max_age)})",
            lag_hours=round(lag, 1),
            last_value=latest,
        )

    async def _trend(self, rule: RuleSpec) -> dict[date, tuple[int, int]]:
        try:
            rows = await self._fetch(rule.trend_sql or "")
        except Exception:
            logger.debug("reliability: trend failed for %s", rule.id, exc_info=True)
            return {}
        out: dict[date, tuple[int, int]] = {}
        for period, total, failed in rows:
            day = period.date() if isinstance(period, datetime) else period
            out[day] = (int(total or 0), int(failed or 0))
        return out

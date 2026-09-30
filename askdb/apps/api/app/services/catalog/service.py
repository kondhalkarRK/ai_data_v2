"""Entity Catalog: the metadata layer that keeps AI Chat, the glossary and the graph current.

A refresh reads warehouse metadata and distinct values, records what is new or changed,
then swaps the live value dictionary and drops the semantic/graph/result caches so every
consumer sees the new values without a restart. Refreshes run on startup, on data-load
completion, on demand, and as a targeted lookup when a question names an unknown value;
never on every query.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.config import Industry
from app.models.catalog import CatalogChange, CatalogColumn, CatalogRefresh, CatalogValue
from app.semantic.service import SemanticService
from app.services.catalog import config as catalog_config
from app.services.catalog.config import CatalogConfig, CatalogDomain, build_catalog_config
from app.services.catalog.drift import (
    IMPACT,
    SCHEMA_KINDS,
    ColumnInfo,
    DetectedChange,
    diff_schema,
    diff_values,
)
from app.services.catalog.introspect import CatalogObservation, lookup_values, observe
from app.services.catalog.readiness import ValueReadiness, assess_value
from app.services.chat.entity_resolver import (
    _DOMAIN_PRIORITY,
    EntityResolver,
    load_chat_vocabulary,
    normalize,
)
from app.services.chat.query_cache import QUERY_CACHE
from app.services.chat.value_dictionary import (
    ValueDictionarySnapshot,
    build_snapshot,
    cached_value_dictionary,
    replace_value_dictionary,
    resolver_for,
)

logger = logging.getLogger(__name__)

Scope = Literal["catalog", "values", "semantic_cache"]
Trigger = Literal["startup", "data_load", "manual", "unknown_entity"]

NEW_VALUE_DAYS = 7
DRIFT_WINDOW_DAYS = 30
LOOKUP_COOLDOWN_SECONDS = 600
_STATUS_ORDER = ("needs_review", "low_confidence", "missing_synonyms", "ai_ready")

_LOCKS: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_LOOKUPS: dict[tuple[str, str], float] = {}

Observer = Callable[..., Awaitable[CatalogObservation]]
Lookup = Callable[..., Awaitable[list[tuple[str, str, int]]]]


class CatalogBusyError(RuntimeError):
    """A refresh for this industry is already running."""


def utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    value = _aware(value)
    return value.isoformat() if value else None


@dataclass(slots=True)
class AssessedValue:
    value: str
    frequency: int
    is_new: bool
    first_seen_at: datetime | None
    first_seen_load: str | None
    active: bool
    readiness: ValueReadiness
    aliases: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EntityView:
    domain: CatalogDomain
    data_type: str | None
    distinct: int
    last_updated: datetime | None
    values: list[AssessedValue]
    error: str | None = None

    @property
    def new_values(self) -> list[AssessedValue]:
        return [v for v in self.values if v.is_new and v.active]

    @property
    def readiness_counts(self) -> dict[str, int]:
        counts = dict.fromkeys(_STATUS_ORDER, 0)
        for value in self.values:
            if value.active:
                counts[value.readiness.status] += 1
        return counts

    @property
    def status(self) -> str:
        if not self.domain.ai_known:
            return "needs_review"
        counts = self.readiness_counts
        if not any(counts.values()):
            return "needs_review"
        # Entity-level: flag review only when new arrivals need it; otherwise report
        # the dominant state so one odd value does not mark a whole column.
        if any(v.readiness.status == "needs_review" for v in self.new_values):
            return "needs_review"
        total = sum(counts.values())
        for status in ("needs_review", "low_confidence", "missing_synonyms"):
            if counts[status] / total >= 0.2:
                return status
        return "ai_ready"


class EntityCatalogService:
    def __init__(
        self,
        session: AsyncSession,
        semantic: SemanticService,
        industry: Industry,
        *,
        analytics: AsyncConnection | None = None,
        observer: Observer = observe,
        lookup: Lookup = lookup_values,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.session = session
        self.semantic = semantic
        self.industry = industry
        self.analytics = analytics
        self._observe = observer
        self._lookup = lookup
        self._now = clock

    # ------------------------------------------------------------------ config
    async def _pack(self) -> Any:
        return await self.semantic.get_pack(self.industry)

    async def config(self) -> CatalogConfig:
        return build_catalog_config(self.industry, await self._pack())

    # ----------------------------------------------------------------- queries
    async def latest_refresh(self, *, completed: bool = False) -> CatalogRefresh | None:
        statement = select(CatalogRefresh).where(CatalogRefresh.industry == self.industry.value)
        if completed:
            statement = statement.where(CatalogRefresh.status == "completed")
        statement = statement.order_by(CatalogRefresh.started_at.desc()).limit(1)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def _latest_with_domains(self) -> CatalogRefresh | None:
        statement = (
            select(CatalogRefresh)
            .where(
                CatalogRefresh.industry == self.industry.value,
                CatalogRefresh.status == "completed",
                CatalogRefresh.scope.in_(("catalog", "values")),
            )
            .order_by(CatalogRefresh.started_at.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def _values(self, domain_key: str | None = None) -> list[CatalogValue]:
        statement = select(CatalogValue).where(CatalogValue.industry == self.industry.value)
        if domain_key is not None:
            statement = statement.where(CatalogValue.domain_key == domain_key)
        return list((await self.session.execute(statement)).scalars())

    async def _columns(self) -> list[CatalogColumn]:
        statement = select(CatalogColumn).where(CatalogColumn.industry == self.industry.value)
        return list((await self.session.execute(statement)).scalars())

    # ----------------------------------------------------------------- refresh
    async def refresh(
        self,
        *,
        scope: Scope = "catalog",
        trigger: Trigger = "manual",
        load_id: str | None = None,
        requested_by: str | None = None,
    ) -> CatalogRefresh:
        lock = _LOCKS[self.industry.value]
        if lock.locked():
            raise CatalogBusyError(self.industry.value)
        async with lock:
            return await self._refresh(scope, trigger, load_id, requested_by)

    async def _refresh(
        self, scope: Scope, trigger: Trigger, load_id: str | None, requested_by: str | None
    ) -> CatalogRefresh:
        now = self._now()
        previous = await self.latest_refresh(completed=True)
        run = CatalogRefresh(
            id=uuid.uuid4(),
            industry=self.industry.value,
            scope=scope,
            trigger=trigger,
            status="running",
            version=previous.version if previous else 0,
            load_id=(load_id or f"{trigger}-{now:%Y%m%d%H%M%S}")[:80],
            requested_by=requested_by,
            started_at=now,
            stats={},
        )
        self.session.add(run)
        await self.session.flush()
        try:
            async with self.session.begin_nested():
                if scope == "semantic_cache":
                    await self._rebuild_caches(reload_pack=True)
                    self._carry_forward(run, previous)
                else:
                    await self._observe_and_record(run, previous, include_schema=scope == "catalog")
            run.status = "completed"
        except Exception as exc:
            logger.warning("catalog refresh failed for %s", self.industry.value, exc_info=True)
            run.status = "failed"
            run.error = _friendly_error(exc)
            self._carry_forward(run, previous)
        run.finished_at = self._now()
        await self.session.flush()
        # A rolled-back savepoint expires what it touched; reload before callers read it.
        await self.session.refresh(run)
        return run

    @staticmethod
    def _carry_forward(run: CatalogRefresh, previous: CatalogRefresh | None) -> None:
        """Keep the last good figures on the summary cards (never read ``run`` here)."""
        if previous is None:
            return
        run.rows_processed = previous.rows_processed
        run.entity_count = previous.entity_count
        run.ai_coverage = previous.ai_coverage
        run.stats = dict(previous.stats or {})

    async def _observe_and_record(
        self, run: CatalogRefresh, previous: CatalogRefresh | None, *, include_schema: bool
    ) -> None:
        if self.analytics is None:
            raise RuntimeError("warehouse unavailable")
        config = await self.config()
        observation = await self._observe(self.analytics, config, include_schema=include_schema)
        base = await self._latest_with_domains()
        previous_domains: dict[str, Any] = (
            dict((base.stats or {}).get("domains", {})) if base else {}
        )

        changes: list[DetectedChange] = []
        new_total = 0
        retired = 0
        stored = await self._values()
        by_domain: dict[str, dict[str, CatalogValue]] = defaultdict(dict)
        for row in stored:
            by_domain[row.domain_key][row.value] = row

        domain_stats: dict[str, Any] = {}
        for domain in config.domains:
            seen = observation.domains.get(domain.key)
            if seen is None:
                continue
            prior = previous_domains.get(domain.key) or {}
            if seen.error:
                domain_stats[domain.key] = {**prior, "error": seen.error}
                continue
            existing = by_domain.get(domain.key, {})
            first_time = not existing
            fresh: list[str] = []
            observed = set()
            for value, frequency in seen.values:
                observed.add(value)
                known = existing.get(value)
                if known is None:
                    self.session.add(
                        CatalogValue(
                            industry=self.industry.value,
                            domain_key=domain.key,
                            value=value[:500],
                            frequency=frequency,
                            first_seen_at=run.started_at,
                            first_seen_load=run.load_id,
                            last_seen_at=run.started_at,
                            baseline=first_time,
                            active=True,
                        )
                    )
                    if not first_time:
                        fresh.append(value)
                else:
                    known.frequency = frequency
                    known.last_seen_at = run.started_at
                    known.active = True
            if seen.complete:
                for value, known in existing.items():
                    if value not in observed and known.active:
                        known.active = False
                        retired += 1
            new_total += len(fresh)
            prior_distinct = prior.get("distinct")
            changes.extend(
                diff_values(
                    domain.key,
                    domain.label,
                    previous_distinct=None if prior_distinct is None else int(prior_distinct),
                    current_distinct=seen.distinct,
                    new_values=fresh,
                )
            )
            domain_stats[domain.key] = {
                "distinct": seen.distinct,
                "observed": len(seen.values),
                "dataType": seen.data_type or prior.get("dataType"),
                "updatedAt": _iso(run.started_at),
            }
        for key, prior in previous_domains.items():
            domain_stats.setdefault(key, prior)

        if observation.columns is not None:
            changes.extend(await self._record_schema(run, config, observation.columns))

        for change in changes:
            self.session.add(_change_row(self.industry, run, change))

        coverage = _coverage(config, domain_stats)
        prior_stats = (previous.stats or {}) if previous else {}
        run.stats = {
            "domains": domain_stats,
            "factRows": observation.fact_rows or prior_stats.get("factRows", {}),
            "retiredValues": retired,
            "schemaChecked": observation.columns is not None
            or bool(prior_stats.get("schemaChecked")),
        }
        run.rows_processed = observation.rows_processed or (
            previous.rows_processed if previous else None
        )
        run.entity_count = len(config.domains)
        run.new_value_count = new_total
        run.change_count = len(changes)
        run.ai_coverage = coverage
        content_changed = previous is None or bool(changes) or retired > 0
        run.version = (previous.version if previous else 0) + (1 if content_changed else 0)
        await self.session.flush()
        await self._rebuild_caches(reload_pack=False)

    async def _record_schema(
        self, run: CatalogRefresh, config: CatalogConfig, current: dict[tuple[str, str], ColumnInfo]
    ) -> list[DetectedChange]:
        rows = await self._columns()
        live = {(r.table_name, r.column_name): r for r in rows if r.removed_at is None}
        previous = (
            {
                key: ColumnInfo(r.table_name, r.column_name, r.data_type, r.ordinal)
                for key, r in live.items()
            }
            if rows
            else None
        )
        last_seen = {key: _iso(r.last_seen_at) or "" for key, r in live.items()}
        detected = diff_schema(
            previous,
            current,
            references=config.references,
            table_groups=config.table_groups,
            last_seen=last_seen,
        )
        # "Used by the semantic layer but absent" repeats every refresh until fixed;
        # record it once per column.
        open_missing = set(
            (
                await self.session.execute(
                    select(CatalogChange.table_name, CatalogChange.column_name).where(
                        CatalogChange.industry == self.industry.value,
                        CatalogChange.kind == "missing_in_database",
                    )
                )
            ).all()
        )
        detected = [
            c
            for c in detected
            if not (c.kind == "missing_in_database" and (c.table, c.column) in open_missing)
        ]

        by_key = {(r.table_name, r.column_name): r for r in rows}
        for key, info in current.items():
            row = by_key.get(key)
            if row is None:
                self.session.add(
                    CatalogColumn(
                        industry=self.industry.value,
                        table_name=info.table,
                        column_name=info.column,
                        data_type=info.data_type[:60],
                        ordinal=info.ordinal,
                        first_seen_at=run.started_at,
                        last_seen_at=run.started_at,
                    )
                )
            else:
                row.data_type = info.data_type[:60]
                row.ordinal = info.ordinal
                row.last_seen_at = run.started_at
                row.removed_at = None
        visible = {table.split(".", 1)[0] for table, _ in current}
        for key, row in live.items():
            if key not in current and row.table_name.split(".", 1)[0] in visible:
                row.removed_at = run.started_at
        return detected

    async def _rebuild_caches(self, *, reload_pack: bool) -> None:
        """Push catalog values into AI Chat and drop derived caches (graph, glossary, results)."""
        if reload_pack:
            catalog_config._read_yaml.cache_clear()
            load_chat_vocabulary.cache_clear()
        self.semantic.invalidate(self.industry)
        QUERY_CACHE.clear()
        snapshot = await self.dictionary_snapshot()
        if snapshot is not None:
            replace_value_dictionary(snapshot)

    async def dictionary_snapshot(self) -> ValueDictionarySnapshot | None:
        """The AI value dictionary rebuilt from catalog values (top N per domain)."""
        config = await self.config()
        rows = [r for r in await self._values() if r.active]
        if not rows:
            return None
        grouped: dict[str, list[CatalogValue]] = defaultdict(list)
        for row in rows:
            grouped[row.domain_key].append(row)
        current = cached_value_dictionary(self.industry)
        selected: dict[tuple[str, str], tuple[str, str, int]] = {}

        def pick(column: str, value: str, frequency: int) -> None:
            selected.setdefault((column.casefold(), value.casefold()), (column, value, frequency))

        for domain in config.domains:
            if not domain.ai_known:
                continue
            catalogued = grouped.get(domain.key, [])
            if not any(r.baseline for r in catalogued) and current is not None:
                # Never captured by a full refresh: keep what AI Chat already knows.
                column = domain.qualified_column.casefold()
                for value in current.values:
                    if value.column.casefold() == column:
                        pick(value.column, value.value, value.frequency)
            ranked = sorted(catalogued, key=lambda r: (-r.frequency, r.value))
            for r in ranked[: domain.max_values]:
                pick(domain.qualified_column, r.value, int(r.frequency))
            # Values found by the targeted lookup stay resolvable even past the cap.
            for r in catalogued:
                if r.first_seen_load.startswith("lookup-"):
                    pick(domain.qualified_column, r.value, int(r.frequency))
        return build_snapshot(self.industry, selected.values(), pack=await self._pack())

    # ---------------------------------------------------- unknown-entity lookup
    async def targeted_lookup(self, terms: Iterable[str]) -> list[tuple[str, str]]:
        """Look up names the dictionary does not know; add any found and refresh AI Chat.

        Throttled per term so a repeated unknown word never turns into a query storm.
        """
        if self.analytics is None:
            return []
        now = time.monotonic()
        wanted = []
        for term in dict.fromkeys(t.strip().lower() for t in terms if t and t.strip()):
            key = (self.industry.value, term)
            if now - _LOOKUPS.get(key, -LOOKUP_COOLDOWN_SECONDS) < LOOKUP_COOLDOWN_SECONDS:
                continue
            _LOOKUPS[key] = now
            wanted.append(term)
        if not wanted:
            return []
        config = await self.config()
        found = await self._lookup(self.analytics, config, wanted[:3])
        if not found:
            return []
        existing = {(r.domain_key, r.value) for r in await self._values()}
        started = self._now()
        run = CatalogRefresh(
            id=uuid.uuid4(),
            industry=self.industry.value,
            scope="values",
            trigger="unknown_entity",
            status="completed",
            load_id=f"lookup-{started:%Y%m%d%H%M%S}",
            started_at=started,
            finished_at=started,
            stats={"terms": wanted},
        )
        previous = await self.latest_refresh(completed=True)
        self._carry_forward(run, previous)
        run.stats = {**run.stats, "terms": wanted}
        run.version = (previous.version if previous else 0) + 1
        added: list[tuple[str, str]] = []
        for domain_key, value, frequency in found:
            if (domain_key, value) in existing:
                continue
            existing.add((domain_key, value))
            self.session.add(
                CatalogValue(
                    industry=self.industry.value,
                    domain_key=domain_key,
                    value=value[:500],
                    frequency=frequency,
                    first_seen_at=started,
                    first_seen_load=run.load_id,
                    last_seen_at=started,
                    baseline=False,
                    active=True,
                )
            )
            added.append((domain_key, value))
        by_domain: dict[str, list[str]] = defaultdict(list)
        for domain_key, value in added:
            by_domain[domain_key].append(value)
        for domain_key, values in by_domain.items():
            domain = config.domain(domain_key)
            change = DetectedChange(
                kind="new_values",
                severity="medium",
                summary=(
                    f"Found {', '.join(values[:5])} in {domain.label if domain else domain_key} "
                    "while answering a question"
                ),
                domain_key=domain_key,
                detail={"values": values, "count": len(values), "trigger": "unknown_entity"},
                impact=IMPACT["new_values"],
            )
            self.session.add(_change_row(self.industry, run, change))
        run.new_value_count = len(added)
        run.change_count = len(by_domain)
        self.session.add(run)
        await self.session.flush()
        # The dictionary must know about the value even if it was already catalogued
        # past the cap; rebuilding covers both.
        snapshot = await self.dictionary_snapshot()
        if snapshot is not None:
            replace_value_dictionary(snapshot)
        QUERY_CACHE.clear()
        return [(domain_key, value) for domain_key, value, _ in found]

    # ------------------------------------------------------------- read models
    async def entity_views(self, *, domain_key: str | None = None) -> list[EntityView]:
        config = await self.config()
        base = await self._latest_with_domains()
        domain_stats: dict[str, Any] = dict((base.stats or {}).get("domains", {})) if base else {}
        grouped: dict[str, list[CatalogValue]] = defaultdict(list)
        for row in await self._values():
            grouped[row.domain_key].append(row)

        pack = await self._pack()
        # What AI Chat is actually using right now; the catalog-built one if not loaded yet.
        snapshot = cached_value_dictionary(self.industry) or await self.dictionary_snapshot()
        resolver: EntityResolver | None = resolver_for(snapshot, pack) if snapshot else None
        phrases = resolver.phrases_by_value() if resolver else {}
        in_dictionary = {
            (v.column.casefold(), v.value.casefold()) for v in (snapshot.values if snapshot else ())
        }
        # Same normalized name in more than one AI-known column -> ambiguity / shadowing.
        owners: dict[str, list[CatalogDomain]] = defaultdict(list)
        for domain in config.domains:
            if domain.ai_known:
                for row in grouped.get(domain.key, []):
                    if row.active:
                        owners[normalize(row.value)].append(domain)
        cutoff = self._now() - timedelta(days=NEW_VALUE_DAYS)

        views: list[EntityView] = []
        for domain in config.domains:
            if domain_key is not None and domain.key != domain_key:
                continue
            stats = domain_stats.get(domain.key) or {}
            assessed: list[AssessedValue] = []
            for row in sorted(grouped.get(domain.key, []), key=lambda r: (-r.frequency, r.value)):
                first_seen = _aware(row.first_seen_at)
                is_new = not row.baseline and first_seen is not None and first_seen >= cutoff
                key = (domain.qualified_column.casefold(), row.value.casefold())
                forms = phrases.get(key, {})
                others = [d for d in owners.get(normalize(row.value), []) if d.key != domain.key]
                mine = _DOMAIN_PRIORITY.get(domain.column, 10)
                shadow = next(
                    (d.label for d in others if _DOMAIN_PRIORITY.get(d.column, 10) < mine), None
                )
                readiness = assess_value(
                    row.value,
                    domain_key=domain.key,
                    domain_ai_known=domain.ai_known,
                    in_dictionary=key in in_dictionary,
                    is_new=is_new,
                    phrases=forms,
                    shadowed_by=shadow,
                    ambiguous_with=[d.label for d in others] if not shadow else None,
                    generic_word=bool(resolver and resolver.is_generic_value(key[0], row.value)),
                    max_values=domain.max_values,
                )
                own = normalize(row.value)
                aliases = [
                    phrase
                    for method in ("synonym", "alias")
                    for phrase in forms.get(method, [])
                    if phrase != own
                ]
                assessed.append(
                    AssessedValue(
                        value=row.value,
                        frequency=int(row.frequency),
                        is_new=is_new,
                        first_seen_at=first_seen,
                        first_seen_load=row.first_seen_load,
                        active=row.active,
                        readiness=readiness,
                        aliases=aliases,
                    )
                )
            updated = stats.get("updatedAt")
            views.append(
                EntityView(
                    domain=domain,
                    data_type=stats.get("dataType"),
                    distinct=int(stats.get("distinct") or sum(1 for a in assessed if a.active)),
                    last_updated=datetime.fromisoformat(updated) if updated else None,
                    values=assessed,
                    error=stats.get("error"),
                )
            )
        return views

    async def changes(self, *, limit: int = 200) -> list[CatalogChange]:
        statement = (
            select(CatalogChange)
            .where(CatalogChange.industry == self.industry.value)
            .order_by(CatalogChange.detected_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars())

    async def summary(self) -> dict[str, Any]:
        latest = await self.latest_refresh()
        completed = await self.latest_refresh(completed=True)
        views = await self.entity_views()
        since = self._now() - timedelta(days=DRIFT_WINDOW_DAYS)
        schema_rows = [
            c
            for c in await self.changes(limit=500)
            if c.kind in SCHEMA_KINDS and (_aware(c.detected_at) or since) >= since
        ]
        schema_checked = bool(((completed.stats or {}) if completed else {}).get("schemaChecked"))
        if not schema_checked:
            drift = {"status": "not_checked", "label": "Not checked yet", "count": 0}
        elif not schema_rows:
            drift = {"status": "stable", "label": "Stable", "count": 0}
        else:
            high = any(c.severity == "high" for c in schema_rows)
            drift = {
                "status": "action_required" if high else "changes_detected",
                "label": "Action required" if high else "Changes detected",
                "count": len(schema_rows),
            }
        readiness = dict.fromkeys(_STATUS_ORDER, 0)
        for view in views:
            readiness[view.status] += 1
        return {
            "industry": self.industry.value,
            "lastRefresh": refresh_dict(latest),
            "lastCompleted": refresh_dict(completed),
            "catalogVersion": completed.version if completed else 0,
            "rowsProcessed": completed.rows_processed if completed else None,
            "lastLoadId": completed.load_id if completed else None,
            "totalEntities": len(views),
            "totalValues": sum(v.distinct for v in views),
            "newValues": sum(len(v.new_values) for v in views),
            "schemaDrift": drift,
            "aiCoverage": completed.ai_coverage if completed else None,
            "entityReadiness": readiness,
        }


def _coverage(config: CatalogConfig, domain_stats: dict[str, Any]) -> float | None:
    total = 0
    known = 0
    for domain in config.domains:
        distinct = int((domain_stats.get(domain.key) or {}).get("distinct") or 0)
        total += distinct
        if domain.ai_known:
            known += min(distinct, domain.max_values)
    return round(known / total, 4) if total else None


def _change_row(industry: Industry, run: CatalogRefresh, change: DetectedChange) -> CatalogChange:
    return CatalogChange(
        industry=industry.value,
        refresh_id=run.id,
        kind=change.kind,
        severity=change.severity,
        summary=change.summary[:500],
        table_name=change.table,
        column_name=change.column,
        domain_key=change.domain_key,
        confidence=change.confidence,
        detail=change.detail,
        impact=change.impact,
        detected_at=run.started_at,
    )


def refresh_dict(run: CatalogRefresh | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "id": str(run.id),
        "scope": run.scope,
        "trigger": run.trigger,
        "status": run.status,
        "version": run.version,
        "loadId": run.load_id,
        "startedAt": _iso(run.started_at),
        "finishedAt": _iso(run.finished_at),
        "rowsProcessed": run.rows_processed,
        "newValueCount": run.new_value_count,
        "changeCount": run.change_count,
        "error": run.error,
    }


def _friendly_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "warehouse unavailable" in text or "connect" in text or "timeout" in text:
        return "The data warehouse could not be reached. The previous catalog is still in use."
    return "The refresh could not finish. The previous catalog is still in use."

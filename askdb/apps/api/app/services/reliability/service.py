"""Data Reliability Center: runs rules, scores trust and assembles the executive view."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.config import Industry
from app.models.catalog import CatalogValue
from app.schemas.reliability import (
    AlertItem,
    BulkMonitorRequest,
    BusinessImpact,
    Capability,
    CatalogColumn,
    CatalogDataset,
    CreateMonitorRequest,
    DataReliabilityResponse,
    DatasetTrust,
    DimensionCard,
    DriftEvent,
    EntityChanges,
    EntityGroup,
    EntityValueOut,
    FreshnessRow,
    ImpactItem,
    InsightItem,
    Methodology,
    MethodologyDimension,
    MonitorCatalog,
    MonitorMutationResult,
    ReliabilityHero,
    RuleRow,
    SchemaDrift,
    SummaryStatement,
    TrendEvent,
    TrendPointOut,
    TrustBand,
    TrustSummary,
    TrustTrend,
    UpdateMonitorRequest,
)
from app.semantic.service import SemanticService
from app.services.catalog.drift import SCHEMA_KINDS
from app.services.catalog.service import EntityCatalogService
from app.services.reliability.defaults import default_datasets, default_rules
from app.services.reliability.engine import RuleEngine, period_end
from app.services.reliability.model import (
    DIMENSION_INFO,
    DIMENSIONS,
    SEVERITY_WEIGHT,
    TRUST_BANDS,
    DatasetSpec,
    Dimension,
    RuleResult,
    RuleSpec,
    RuleStatus,
    RunHistory,
    band_for,
)
from app.services.reliability.scoring import (
    dataset_score,
    dimension_scores,
    effective_weights,
    format_hours,
    format_inr,
    impact_text,
    overall_score,
    quality_drops,
    record_date_trend,
    window_delta,
)
from app.services.reliability.store import ReliabilityStore, Setting, Snapshot

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 15 * 60
ENTITY_WINDOW_DAYS = 30
_RECORD_UNITS = frozenset(
    {
        "records",
        "orders",
        "claims",
        "policies",
        "policy-months",
        "car lines",
        "dealers",
        "salespeople",
        "target rows",
    }
)
_ENTITY_GROUPS = {
    "make": "Brands",
    "model": "Models",
    "dealer_name": "Dealers",
    "city": "Cities",
    "state": "States",
    "region": "Zones",
    "product_name": "Products",
    "line_of_business": "Lines of business",
    "agent_name": "Agents",
}
_DEFAULT_SLA = {"daily": 36.0, "monthly": 24.0 * 45}
_ERROR_IMPACT = "This check could not run, so the score leaves it out until it runs again."


@dataclass(slots=True)
class RunOutcome:
    ran_at: datetime
    results: dict[str, RuleResult]
    latest: dict[str, date | datetime | None] = field(default_factory=dict)
    estimates: dict[str, int] = field(default_factory=dict)
    duration_ms: int = 0
    rule_ran_at: dict[str, datetime] = field(default_factory=dict)


_CACHE: dict[str, tuple[float, RunOutcome]] = {}
_LOCKS: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def clear_reliability_cache(industry: str | None = None) -> None:
    if industry is None:
        _CACHE.clear()
    else:
        _CACHE.pop(industry, None)


_SNAPSHOTS: dict[str, dict[str, Any]] = {}


def shared_snapshot(industry: str) -> dict[str, Any] | None:
    """Latest trust score for Chat and Executive Intelligence, once a run has happened."""
    return _SNAPSHOTS.get(industry)


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:48] or "monitor"


def rescore(rule: RuleSpec, result: RuleResult) -> RuleResult:
    """Re-derive pass/fail when only the threshold changed since the run."""
    if rule.kind == "freshness" or result.status not in {"passing", "failing"}:
        return result
    if result.pass_rate is None:
        return result
    status: RuleStatus = "passing" if result.pass_rate + 1e-9 >= rule.threshold else "failing"
    return result if status == result.status else replace(result, status=status)


class DataReliabilityService:
    def __init__(
        self,
        *,
        connection: AsyncConnection | None,
        semantic: SemanticService,
        industry: Industry,
        app_session: AsyncSession | None = None,
    ) -> None:
        self._connection = connection
        self._semantic = semantic
        self._industry = industry
        self._session = app_session
        self._store = ReliabilityStore(app_session, industry)

    # ------------------------------------------------------------------ registry

    async def datasets(self) -> dict[str, DatasetSpec]:
        out = {spec.name: spec for spec in default_datasets(self._industry)}
        try:
            pack = await self._semantic.get_pack(self._industry)
        except Exception:
            logger.debug("reliability: semantic pack unavailable", exc_info=True)
            return out
        for name, table in pack.model.tables.items():
            if name not in out:
                out[name] = DatasetSpec(
                    name,
                    table.physical_name,
                    table.display_name,
                    "fact" if table.type == "fact" else "dimension",
                    table.display_name,
                    key_column=table.primary_key,
                )
        return out

    async def _columns(self, datasets: dict[str, DatasetSpec]) -> dict[str, list[CatalogColumn]]:
        out: dict[str, list[CatalogColumn]] = {}
        tables: dict[str, Any] = {}
        try:
            tables = dict((await self._semantic.get_pack(self._industry)).model.tables)
        except Exception:
            logger.debug("reliability: semantic pack unavailable", exc_info=True)
        for name, spec in datasets.items():
            table = tables.get(name)
            if table is not None:
                out[name] = [
                    CatalogColumn(name=col, label=meta.display_name, type=meta.type)
                    for col, meta in table.columns.items()
                ]
            else:
                out[name] = [
                    CatalogColumn(name=col, label=col.replace("_", " ").title(), type="unknown")
                    for col in spec.columns
                ]
        return out

    async def rules(self) -> list[RuleSpec]:
        settings = await self._store.settings()
        rules: list[RuleSpec] = []
        for rule in default_rules(self._industry):
            setting = settings.get(rule.id)
            rules.append(rule.with_overrides(setting.overrides) if setting else rule)
        for setting in settings.values():
            if not setting.custom:
                continue
            try:
                rule = _custom_rule(setting)
            except (KeyError, TypeError, ValueError):
                logger.warning("reliability: skipping invalid custom monitor %s", setting.rule_id)
                continue
            rules.append(rule.with_overrides(setting.overrides))
        return rules

    # ------------------------------------------------------------------ running

    async def _run(
        self,
        rules: list[RuleSpec],
        datasets: dict[str, DatasetSpec],
        *,
        refresh: bool,
        user: str | None,
    ) -> tuple[RunOutcome, bool]:
        key = self._industry.value
        async with _LOCKS[key]:
            entry = _CACHE.get(key)
            enabled = [r for r in rules if r.enabled]
            if entry and not refresh and entry[0] > time.time():
                outcome = entry[1]
                missing = [r for r in enabled if r.id not in outcome.results]
                if missing and self._connection is not None:
                    now = datetime.now(UTC)
                    engine = RuleEngine(self._connection, datasets, now=now)
                    outcome.results.update(await engine.run(missing))
                    outcome.rule_ran_at.update({r.id: now for r in missing})
                return outcome, False
            if self._connection is None:
                raise RuntimeError("Analytics database unavailable")
            started = time.perf_counter()
            now = datetime.now(UTC)
            engine = RuleEngine(self._connection, datasets, now=now)
            results = await engine.run(enabled)
            latest = await engine.latest_dates()
            schema = next(iter(datasets.values())).physical.split(".", 1)[0]
            estimates = await engine.row_estimates(schema)
            outcome = RunOutcome(
                ran_at=now,
                results=results,
                latest=latest,
                estimates=estimates,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            _CACHE[key] = (time.time() + CACHE_TTL_SECONDS, outcome)
            await self._persist(rules, outcome, datasets, user)
            return outcome, True

    async def _persist(
        self,
        rules: list[RuleSpec],
        outcome: RunOutcome,
        datasets: dict[str, DatasetSpec],
        user: str | None,
    ) -> None:
        dims = dimension_scores(rules, outcome.results)
        score = overall_score(dims)
        by_dataset = defaultdict(list)
        for rule in rules:
            by_dataset[rule.dataset].append(rule)
        dataset_scores = {
            name: dataset_score(items, outcome.results)
            for name, items in by_dataset.items()
            if name in datasets
        }
        _SNAPSHOTS[self._industry.value] = _snapshot_payload(score, dims, outcome)
        try:
            await self._store.record_run(
                ran_at=outcome.ran_at,
                results=dict(outcome.results),
                score=score,
                dimensions={k: d.score for k, d in dims.items()},
                datasets=dataset_scores,
                duration_ms=outcome.duration_ms,
                triggered_by=user,
            )
        except Exception:
            logger.warning("reliability: run history not saved", exc_info=True)

    # ------------------------------------------------------------------ center

    async def center(
        self, *, refresh: bool = False, user: str | None = None
    ) -> DataReliabilityResponse:
        datasets = await self.datasets()
        rules = await self.rules()
        try:
            outcome, _fresh = await self._run(rules, datasets, refresh=refresh, user=user)
        except Exception:
            logger.warning("reliability: rules could not run", exc_info=True)
            outcome = RunOutcome(ran_at=datetime.now(UTC), results={})
        results = {
            rule.id: rescore(rule, outcome.results[rule.id])
            for rule in rules
            if rule.enabled and rule.id in outcome.results
        }
        history = await self._store.history(now=datetime.now(UTC))
        snapshots = await self._store.snapshots(now=datetime.now(UTC))
        drift = await self._schema_drift()
        entities = await self._entities()
        columns = await self._columns(datasets)
        return build_response(
            industry=self._industry,
            rules=rules,
            results=results,
            outcome=outcome,
            datasets=datasets,
            history=history,
            snapshots=snapshots,
            drift=drift,
            entities=entities,
            columns=columns,
            storage=self._store.mode,
        )

    async def _schema_drift(self) -> SchemaDrift:
        if self._session is None:
            return SchemaDrift(status="unavailable", label="Entity Catalog unavailable")
        try:
            catalog = EntityCatalogService(self._session, self._semantic, self._industry)
            completed = await catalog.latest_refresh(completed=True)
            changes = [c for c in await catalog.changes(limit=300) if c.kind in SCHEMA_KINDS]
        except Exception:
            await _rollback(self._session)
            logger.debug("reliability: schema drift unavailable", exc_info=True)
            return SchemaDrift(status="unavailable", label="Entity Catalog not set up")
        events = [
            DriftEvent(
                id=str(c.id),
                kind=c.kind,
                severity=c.severity,
                summary=c.summary,
                table=c.table_name,
                column=c.column_name,
                detected_at=_iso(c.detected_at),
                impact={str(k): str(v) for k, v in (c.impact or {}).items()},
            )
            for c in changes
        ]
        checked = bool(((completed.stats or {}) if completed else {}).get("schemaChecked"))
        cutoff = datetime.now(UTC) - timedelta(days=30)
        recent = [
            e for e in events if e.detected_at and datetime.fromisoformat(e.detected_at) >= cutoff
        ]
        if not checked and not events:
            return SchemaDrift(status="not_checked", label="Not checked yet", events=[])
        if recent:
            return SchemaDrift(
                status="drift", label=f"{len(recent)} change(s) in 30 days", events=events
            )
        return SchemaDrift(status="stable", label="Stable", events=events)

    async def _entities(self) -> EntityChanges:
        if self._session is None:
            return EntityChanges(available=False)
        try:
            catalog = EntityCatalogService(self._session, self._semantic, self._industry)
            config = await catalog.config()
            completed = await catalog.latest_refresh(completed=True)
            cutoff = datetime.now(UTC) - timedelta(days=ENTITY_WINDOW_DAYS)
            rows = (
                await self._session.execute(
                    select(CatalogValue)
                    .where(
                        CatalogValue.industry == self._industry.value,
                        CatalogValue.baseline.is_(False),
                        CatalogValue.active.is_(True),
                        CatalogValue.first_seen_at >= cutoff,
                    )
                    .order_by(CatalogValue.first_seen_at.desc())
                    .limit(400)
                )
            ).scalars()
            values = list(rows)
        except Exception:
            await _rollback(self._session)
            logger.debug("reliability: entity changes unavailable", exc_info=True)
            return EntityChanges(available=False)
        labels = {d.key: d.label for d in config.domains}
        grouped: dict[str, list[CatalogValue]] = defaultdict(list)
        for row in values:
            grouped[row.domain_key].append(row)
        groups = [
            EntityGroup(
                key=key,
                label=_ENTITY_GROUPS.get(key, labels.get(key, key.replace("_", " ").title())),
                count=len(items),
                values=[
                    EntityValueOut(value=v.value, domain=key, first_seen_at=_iso(v.first_seen_at))
                    for v in items[:12]
                ],
            )
            for key, items in grouped.items()
        ]
        groups.sort(key=lambda g: -g.count)
        return EntityChanges(
            available=True,
            total=len(values),
            last_refresh_at=_iso(completed.finished_at or completed.started_at)
            if completed
            else None,
            groups=groups,
        )

    # ------------------------------------------------------------------ monitors

    async def create_monitor(
        self, body: CreateMonitorRequest, user: str | None
    ) -> MonitorMutationResult:
        datasets = await self.datasets()
        columns = await self._columns(datasets)
        definition = validate_monitor(body, datasets, columns)
        rule_id = f"custom.{_slug(body.name)}-{uuid.uuid4().hex[:6]}"
        definition["id"] = rule_id
        await self._store.save_setting(
            Setting(rule_id=rule_id, custom=True, definition=definition, created_by=user)
        )
        return MonitorMutationResult(ok=True, updated=[rule_id], storage=self._store.mode)

    async def update_monitor(
        self, rule_id: str, body: UpdateMonitorRequest, user: str | None
    ) -> MonitorMutationResult:
        changes = body.model_dump(exclude_none=True)
        return await self._apply({rule_id: changes}, user)

    async def bulk(self, body: BulkMonitorRequest, user: str | None) -> MonitorMutationResult:
        rules = {r.id: r for r in await self.rules()}
        plan: dict[str, dict[str, Any]] = {}
        skipped: list[str] = []
        for rule_id in dict.fromkeys(body.rule_ids):
            rule = rules.get(rule_id)
            if rule is None:
                skipped.append(rule_id)
                continue
            change = bulk_change(rule, body)
            if change is None:
                skipped.append(rule_id)
            else:
                plan[rule_id] = change
        result = await self._apply(plan, user)
        result.skipped.extend(skipped)
        return result

    async def delete_monitor(self, rule_id: str) -> MonitorMutationResult:
        settings = await self._store.settings()
        setting = settings.get(rule_id)
        if setting is None or not setting.custom:
            return MonitorMutationResult(
                ok=False,
                skipped=[rule_id],
                storage=self._store.mode,
                message="Only custom monitors can be deleted; disable built-in rules instead.",
            )
        await self._store.delete_setting(rule_id)
        _drop_result(self._industry.value, rule_id)
        return MonitorMutationResult(ok=True, updated=[rule_id], storage=self._store.mode)

    async def _apply(
        self, plan: dict[str, dict[str, Any]], user: str | None
    ) -> MonitorMutationResult:
        if not plan:
            return MonitorMutationResult(
                ok=False, storage=self._store.mode, message="Nothing to change."
            )
        settings = await self._store.settings()
        known = {r.id for r in default_rules(self._industry)} | {
            k for k, s in settings.items() if s.custom
        }
        updated: list[str] = []
        skipped: list[str] = []
        for rule_id, change in plan.items():
            if rule_id not in known:
                skipped.append(rule_id)
                continue
            setting = settings.get(rule_id) or Setting(
                rule_id=rule_id, custom=False, created_by=user
            )
            setting.overrides = {**setting.overrides, **change}
            await self._store.save_setting(setting)
            updated.append(rule_id)
        return MonitorMutationResult(
            ok=bool(updated), updated=updated, skipped=skipped, storage=self._store.mode
        )


async def _rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception:
        logger.debug("reliability: rollback failed", exc_info=True)


def _drop_result(industry: str, rule_id: str) -> None:
    entry = _CACHE.get(industry)
    if entry:
        entry[1].results.pop(rule_id, None)


def _snapshot_payload(
    score: float | None, dims: dict[Dimension, Any], outcome: RunOutcome
) -> dict[str, Any]:
    weights = effective_weights(dims)
    band_key, band_label = band_for(score)
    return {
        "score": score,
        "label": band_label,
        "band": band_key,
        "components": [
            {
                "id": key,
                "label": DIMENSION_INFO[key].label,
                "score": d.score,
                "weight": round(weights.get(key, 0.0) / 100, 4),
                "contribution": round((d.score or 0.0) * weights.get(key, 0.0) / 100, 2),
            }
            for key, d in dims.items()
            if d.score is not None
        ],
        "formulaNote": (
            "Weighted blend of Accuracy, Completeness, Consistency, Timeliness, Validity and "
            "Uniqueness; each dimension is the severity-weighted pass rate of its rules."
        ),
        "activeIncidents": sum(1 for r in outcome.results.values() if r.status == "failing"),
        "computedAt": outcome.ran_at.isoformat(),
    }


# --------------------------------------------------------------------------- monitors


def _custom_rule(setting: Setting) -> RuleSpec:
    d = setting.definition
    return RuleSpec(
        id=setting.rule_id,
        name=str(d["name"]),
        dimension=d["dimension"],
        dataset=str(d["dataset"]),
        severity=d["severity"],
        kind=d["kind"],
        description=str(d.get("description") or ""),
        owner=str(d.get("owner") or "Data Engineering"),
        threshold=float(d.get("threshold", 100)),
        tags=tuple(d.get("tags") or ()),
        impact=str(d.get("impact") or ""),
        assets=tuple(d.get("assets") or ()),
        unit=str(d.get("unit") or "records"),
        custom=True,
        column=d.get("column"),
        columns=tuple(d.get("columns") or ()),
        ref_dataset=d.get("ref_dataset"),
        ref_column=d.get("ref_column"),
        min_value=d.get("min_value"),
        max_value=d.get("max_value"),
        allowed=tuple(str(v) for v in d.get("allowed") or ()),
        pattern=d.get("pattern"),
        max_age_hours=d.get("max_age_hours"),
        created_by=setting.created_by,
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )


class MonitorValidationError(ValueError):
    pass


def validate_monitor(
    body: CreateMonitorRequest,
    datasets: dict[str, DatasetSpec],
    columns: dict[str, list[CatalogColumn]],
) -> dict[str, Any]:
    """Check a monitor against the dataset registry; returns a storable definition."""
    spec = datasets.get(body.dataset)
    if spec is None:
        raise MonitorValidationError(f"Unknown dataset '{body.dataset}'.")
    known = {c.name: c for c in columns.get(body.dataset, [])}

    def column(name: str | None, *, dataset: str = body.dataset) -> str:
        pool = known if dataset == body.dataset else {c.name: c for c in columns.get(dataset, [])}
        if not name or name not in pool:
            raise MonitorValidationError(f"Choose a column that exists in {dataset}.")
        return name

    definition: dict[str, Any] = {
        "name": body.name.strip(),
        "description": (body.description or "").strip(),
        "dimension": body.dimension,
        "dataset": body.dataset,
        "severity": body.severity,
        "kind": body.kind,
        "threshold": body.threshold,
        "owner": body.owner.strip(),
        "tags": body.tags,
        "assets": list(spec.assets),
        "unit": "records",
    }
    if body.kind == "not_null":
        definition["columns"] = [column(c) for c in (body.columns or [body.column or ""])]
        definition["impact"] = (
            "{failed} records in " + spec.display_name + " are missing required values."
        )
    elif body.kind == "unique":
        definition["columns"] = [column(c) for c in (body.columns or [body.column or ""])]
        definition["impact"] = (
            "{failed} duplicate records in " + spec.display_name + "; totals may be double counted."
        )
    elif body.kind == "range":
        if body.min_value is None and body.max_value is None:
            raise MonitorValidationError("Give a minimum, a maximum or both.")
        if (
            body.min_value is not None
            and body.max_value is not None
            and body.min_value > body.max_value
        ):
            raise MonitorValidationError("The minimum must not exceed the maximum.")
        definition.update(
            column=column(body.column), min_value=body.min_value, max_value=body.max_value
        )
        definition["impact"] = (
            "{failed} records in " + spec.display_name + " fall outside the expected range."
        )
    elif body.kind == "allowed_values":
        allowed = [v.strip() for v in body.allowed or [] if v.strip()]
        if not allowed:
            raise MonitorValidationError("List at least one allowed value.")
        definition.update(column=column(body.column), allowed=allowed[:200])
        definition["impact"] = (
            "{failed} records in " + spec.display_name + " carry unexpected values."
        )
    elif body.kind == "pattern":
        if not body.pattern:
            raise MonitorValidationError("Give a regular expression.")
        try:
            re.compile(body.pattern)
        except re.error as exc:
            raise MonitorValidationError(f"Invalid regular expression: {exc}") from exc
        definition.update(column=column(body.column), pattern=body.pattern)
        definition["impact"] = "{failed} records in " + spec.display_name + " are badly formatted."
    elif body.kind == "freshness":
        name = column(body.column or spec.date_column)
        kind = known[name].type.lower()
        if kind not in {"date", "timestamp", "datetime", "unknown"}:
            raise MonitorValidationError("Freshness needs a date or timestamp column.")
        if not body.max_age_hours:
            raise MonitorValidationError("Give the maximum age in hours.")
        definition.update(column=name, max_age_hours=body.max_age_hours, unit="dataset")
        definition["impact"] = spec.display_name + " is {lag} behind its {sla} SLA."
    elif body.kind == "reference":
        if not body.ref_dataset or body.ref_dataset not in datasets:
            raise MonitorValidationError("Choose the dataset being referenced.")
        definition.update(
            column=column(body.column),
            ref_dataset=body.ref_dataset,
            ref_column=column(body.ref_column, dataset=body.ref_dataset),
        )
        definition["impact"] = (
            "{failed} records in "
            + spec.display_name
            + " point to missing "
            + datasets[body.ref_dataset].display_name
            + " entries."
        )
    return definition


def bulk_change(rule: RuleSpec, body: BulkMonitorRequest) -> dict[str, Any] | None:
    action, value = body.action, (body.value or "").strip()
    if action == "assign_dimension":
        return {"dimension": value} if value in DIMENSIONS else None
    if action == "set_severity":
        return {"severity": value} if value in SEVERITY_WEIGHT else None
    if action == "assign_owner":
        return {"owner": value[:120]} if value else None
    if action == "add_tags":
        tags = body.tags or ([value.lower()] if value else [])
        return {"tags": list(dict.fromkeys([*rule.tags, *tags]))[:12]} if tags else None
    if action == "remove_tags":
        drop = set(body.tags or ([value.lower()] if value else []))
        return {"tags": [t for t in rule.tags if t not in drop]} if drop else None
    return {"enabled": action == "enable"}


# --------------------------------------------------------------------------- response


def build_response(
    *,
    industry: Industry,
    rules: list[RuleSpec],
    results: dict[str, RuleResult],
    outcome: RunOutcome,
    datasets: dict[str, DatasetSpec],
    history: dict[str, RunHistory],
    snapshots: list[Snapshot],
    drift: SchemaDrift,
    entities: EntityChanges,
    columns: dict[str, list[CatalogColumn]],
    storage: str,
) -> DataReliabilityResponse:
    dims = dimension_scores(rules, results)
    score = overall_score(dims)
    weights = effective_weights(dims)
    band_key, band_label = band_for(score)
    enabled = [r for r in rules if r.enabled]
    passing = [r for r in enabled if results.get(r.id) and results[r.id].status == "passing"]
    failing = [r for r in enabled if results.get(r.id) and results[r.id].status == "failing"]
    errored = [r for r in enabled if results.get(r.id) and results[r.id].status == "error"]

    trend_end = _trend_end(outcome, datasets)
    points = record_date_trend(rules, results, end=trend_end) if trend_end else []
    delta = window_delta([p.score for p in points])

    by_dataset: dict[str, list[RuleSpec]] = defaultdict(list)
    for rule in rules:
        by_dataset[rule.dataset].append(rule)
    monitored = [
        name
        for name, items in by_dataset.items()
        if any(results.get(r.id) and results[r.id].status in {"passing", "failing"} for r in items)
    ]
    records_checked = sum(
        max(
            (results[r.id].total for r in items if r.id in results and r.unit in _RECORD_UNITS),
            default=0,
        )
        for items in by_dataset.values()
    )
    critical = [r for r in failing if r.severity == "critical"]
    available = bool(results) and score is not None
    if available:
        reason = None
    elif (
        results
        and all(r.status in {"no_data", "error"} for r in results.values())
        and any(r.status == "no_data" for r in results.values())
    ):
        reason = "The monitored tables have no rows yet. Load data to start measuring trust."
    else:
        reason = "No data-quality rules could run. Check the analytics database connection."

    hero = ReliabilityHero(
        available=available,
        unavailable_reason=reason,
        score=score,
        band=band_key,
        band_label=band_label,
        delta_7d=delta,
        rules_total=len(rules),
        rules_active=len(enabled),
        rules_passing=len(passing),
        rules_failing=len(failing),
        rules_errored=len(errored),
        critical_issues=len(critical),
        datasets_monitored=len(monitored),
        records_checked=records_checked,
    )

    rows = [_rule_row(r, results.get(r.id), datasets, history.get(r.id), outcome) for r in rules]
    alerts = _alerts(rules, results, datasets, history, outcome)
    freshness = _freshness(rules, results, datasets, outcome)
    dataset_rows = _datasets(by_dataset, results, datasets, outcome)
    impact = _impact(failing, results)

    return DataReliabilityResponse(
        industry=industry.value,
        computed_at=outcome.ran_at.isoformat(),
        data_as_of=_iso(_data_as_of(outcome, datasets)),
        storage="database" if storage == "database" else "memory",
        run_duration_ms=outcome.duration_ms,
        hero=hero,
        summary=_summary(hero, freshness, drift, entities),
        dimensions=_dimension_cards(dims, weights, rules, results, history, points),
        trend=_trend(points, failing, history, drift, snapshots, rules, trend_end),
        rules=rows,
        alerts=alerts,
        impact=impact,
        datasets=dataset_rows,
        freshness=freshness,
        schema_drift=drift,
        entities=entities,
        methodology=_methodology(dims, weights),
        insights=_insights(dims, rules, results, delta, freshness, drift, entities),
        catalog=MonitorCatalog(
            datasets=[
                CatalogDataset(name=name, label=spec.display_name, columns=columns.get(name, []))
                for name, spec in datasets.items()
            ],
            owners=sorted({r.owner for r in rules}),
            tags=sorted({t for r in rules for t in r.tags}),
        ),
        capabilities=_capabilities(),
    )


def _trend_end(outcome: RunOutcome, datasets: dict[str, DatasetSpec]) -> date | None:
    days = [
        v.date() if isinstance(v, datetime) else v
        for name, v in outcome.latest.items()
        if v is not None and datasets.get(name) and datasets[name].cadence == "daily"
    ]
    return max(days) if days else None


def _data_as_of(outcome: RunOutcome, datasets: dict[str, DatasetSpec]) -> date | datetime | None:
    facts = [
        v
        for name, v in outcome.latest.items()
        if v is not None and datasets.get(name) and datasets[name].kind == "fact"
    ]
    return (
        max(
            facts,
            key=lambda v: (
                v if isinstance(v, datetime) else datetime(v.year, v.month, v.day, tzinfo=UTC)
            ),
        )
        if facts
        else None
    )


def _sparkline(result: RuleResult | None, history: RunHistory | None) -> list[float]:
    if result and result.trend and not all(k.day == 1 for k in result.trend):
        days = sorted(result.trend)[-14:]
        return [
            round(100.0 * (1 - min(f, t) / t), 2) if t else 100.0
            for t, f in (result.trend[d] for d in days)
        ]
    return [round(v, 2) for v in (history.recent_pass_rates if history else [])]


def _rule_row(
    rule: RuleSpec,
    result: RuleResult | None,
    datasets: dict[str, DatasetSpec],
    history: RunHistory | None,
    outcome: RunOutcome,
) -> RuleRow:
    spec = datasets.get(rule.dataset)
    status = "disabled" if not rule.enabled else (result.status if result else "no_data")
    failing = result is not None and result.status == "failing"
    return RuleRow(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        dimension=rule.dimension,
        dataset=rule.dataset,
        dataset_label=spec.display_name if spec else rule.dataset,
        severity=rule.severity,
        kind=rule.kind,
        threshold=rule.threshold,
        unit=rule.unit,
        status=status,
        pass_rate=result.pass_rate if result else None,
        score=result.score if result else None,
        total=result.total if result else 0,
        failed=result.failed if result else 0,
        observed=(result.observed if result else "Not run yet") if rule.enabled else "Disabled",
        value_at_risk=result.value_at_risk if result else None,
        last_run_at=(
            outcome.rule_ran_at.get(rule.id, outcome.ran_at).isoformat() if result else None
        ),
        last_failure_at=_iso(history.last_failure_at) if history else None,
        failing_since=_iso(history.failing_since) if history and failing else None,
        owner=rule.owner,
        tags=list(rule.tags),
        enabled=rule.enabled,
        custom=rule.custom,
        impact=impact_text(rule, result) if failing and result else None,
        assets=list(rule.assets),
        samples=result.samples if result else [],
        sparkline=_sparkline(result, history),
        duration_ms=result.duration_ms if result else 0,
    )


def _alerts(
    rules: list[RuleSpec],
    results: dict[str, RuleResult],
    datasets: dict[str, DatasetSpec],
    history: dict[str, RunHistory],
    outcome: RunOutcome,
) -> list[AlertItem]:
    alerts: list[AlertItem] = []
    for rule in rules:
        result = results.get(rule.id)
        if not rule.enabled or result is None or result.status not in {"failing", "error"}:
            continue
        spec = datasets.get(rule.dataset)
        past = history.get(rule.id)
        is_error = result.status == "error"
        alerts.append(
            AlertItem(
                id=f"alert:{rule.id}",
                rule_id=rule.id,
                severity=rule.severity,
                kind="error" if is_error else "rule",
                title=rule.name,
                dataset=rule.dataset,
                dataset_label=spec.display_name if spec else rule.dataset,
                dimension=rule.dimension,
                failed_records=0 if is_error else result.failed,
                unit=rule.unit,
                impact=_ERROR_IMPACT if is_error else impact_text(rule, result),
                value_at_risk=None if is_error else result.value_at_risk,
                detected_at=_iso(
                    (past.failing_since if past and not is_error else None) or outcome.ran_at
                ),
                assets=list(rule.assets),
            )
        )
    alerts.sort(
        key=lambda a: (-SEVERITY_WEIGHT[a.severity], a.kind == "error", -(a.failed_records or 0))
    )
    return alerts


def _impact(failing: list[RuleSpec], results: dict[str, RuleResult]) -> BusinessImpact:
    if not failing:
        return BusinessImpact(
            headline="No business impact detected: every monitored KPI rests on passing checks.",
        )
    by_asset: dict[str, list[RuleSpec]] = defaultdict(list)
    for rule in failing:
        for asset in rule.assets or ("Downstream reports",):
            by_asset[asset].append(rule)
    items = [
        ImpactItem(
            asset=asset,
            severity=max((r.severity for r in members), key=lambda s: SEVERITY_WEIGHT[s]),
            statements=[impact_text(r, results[r.id]) for r in members][:4],
            rule_ids=[r.id for r in members],
        )
        for asset, members in by_asset.items()
    ]
    items.sort(key=lambda i: (-SEVERITY_WEIGHT[i.severity], -len(i.rule_ids)))
    records = sum(results[r.id].failed for r in failing if r.unit in _RECORD_UNITS)
    value = sum(results[r.id].value_at_risk or 0.0 for r in failing) or None
    checks = f"{len(failing)} failing check{'s' if len(failing) != 1 else ''}"
    views = f"{len(items)} business view{'s' if len(items) != 1 else ''}"
    parts = [f"{checks} touch {views}"]
    if records:
        parts.append(f"{records:,} records affected")
    if value:
        parts.append(f"{format_inr(value)} of value in scope")
    return BusinessImpact(
        headline="; ".join(parts) + ".",
        records_affected=records,
        value_at_risk=value,
        items=items,
    )


def _freshness(
    rules: list[RuleSpec],
    results: dict[str, RuleResult],
    datasets: dict[str, DatasetSpec],
    outcome: RunOutcome,
) -> list[FreshnessRow]:
    rule_for = {r.dataset: r for r in rules if r.kind == "freshness" and r.enabled}
    rows: list[FreshnessRow] = []
    for name, spec in datasets.items():
        if not spec.date_column or spec.cadence == "static":
            continue
        rule = rule_for.get(name)
        sla = (rule.max_age_hours if rule else None) or spec.sla_hours or _DEFAULT_SLA[spec.cadence]
        latest = outcome.latest.get(name)
        if latest is None:
            rows.append(
                FreshnessRow(
                    dataset=name,
                    label=spec.display_name,
                    cadence=spec.cadence,
                    rule_id=rule.id if rule else None,
                    sla_hours=sla,
                    status="unknown",
                )
            )
            continue
        end = period_end(latest, spec.cadence)
        lag = (outcome.ran_at - end).total_seconds() / 3600.0
        delay = max(0.0, lag - sla)
        status = "on_time" if lag <= sla else "delayed" if lag <= 2 * sla else "stale"
        rows.append(
            FreshnessRow(
                dataset=name,
                label=spec.display_name,
                cadence=spec.cadence,
                rule_id=rule.id if rule else None,
                last_refresh=_iso(latest),
                expected_by=(end + timedelta(hours=sla)).isoformat(),
                sla_hours=sla,
                lag_hours=round(lag, 1),
                delay_hours=round(delay, 1),
                status=status,
            )
        )
    order = {"stale": 0, "delayed": 1, "unknown": 2, "on_time": 3}
    rows.sort(key=lambda r: (order[r.status], -(r.lag_hours or 0)))
    return rows


def _datasets(
    by_dataset: dict[str, list[RuleSpec]],
    results: dict[str, RuleResult],
    datasets: dict[str, DatasetSpec],
    outcome: RunOutcome,
) -> list[DatasetTrust]:
    rows: list[DatasetTrust] = []
    for name, spec in datasets.items():
        items = [r for r in by_dataset.get(name, []) if r.enabled]
        score = dataset_score(items, results)
        failing = [r for r in items if results.get(r.id) and results[r.id].status == "failing"]
        worst = max(
            failing,
            key=lambda r: (SEVERITY_WEIGHT[r.severity], -(results[r.id].score or 0)),
            default=None,
        )
        if not items:
            continue
        rows.append(
            DatasetTrust(
                name=name,
                label=spec.display_name,
                kind=spec.kind,
                domain=spec.domain,
                score=score,
                band=band_for(score)[0],
                rules=len(items),
                passing=sum(
                    1 for r in items if results.get(r.id) and results[r.id].status == "passing"
                ),
                failing=len(failing),
                rows=outcome.estimates.get(spec.physical),
                last_refresh=_iso(outcome.latest.get(name)),
                top_issue=worst.name if worst else None,
                assets=list(spec.assets),
            )
        )
    ranked = sorted(
        (r for r in rows if r.score is not None), key=lambda r: (-(r.score or 0), r.label)
    )
    for index, row in enumerate(ranked, start=1):
        row.rank = index
    return ranked + [r for r in rows if r.score is None]


def _dimension_cards(
    dims: dict[Dimension, Any],
    weights: dict[Dimension, float],
    rules: list[RuleSpec],
    results: dict[str, RuleResult],
    history: dict[str, RunHistory],
    points: list[Any],
) -> list[DimensionCard]:
    cards: list[DimensionCard] = []
    for key in DIMENSIONS:
        d = dims[key]
        info = DIMENSION_INFO[key]
        series = [p.dimensions.get(key) for p in points]
        members = [r for r in rules if r.dimension == key and r.enabled]
        failing = [r for r in members if results.get(r.id) and results[r.id].status == "failing"]
        worst = max(failing, key=lambda r: SEVERITY_WEIGHT[r.severity], default=None)
        failures: list[datetime] = [
            when
            for r in members
            if r.id in history and (when := history[r.id].last_failure_at) is not None
        ]
        cards.append(
            DimensionCard(
                key=key,
                label=info.label,
                question=info.question,
                weight=info.weight,
                effective_weight=weights.get(key),
                score=d.score,
                band=band_for(d.score)[0],
                rules=d.rules,
                passing=d.passing,
                failing=d.failing,
                errored=d.errored,
                delta_7d=window_delta(series),
                sparkline=[round(v, 2) if v is not None else None for v in series[-30:]],
                last_failure_at=_iso(max(failures)) if failures else None,
                top_issue=f"{worst.name}: {results[worst.id].observed}" if worst else None,
            )
        )
    return cards


def _trend(
    points: list[Any],
    failing: list[RuleSpec],
    history: dict[str, RunHistory],
    drift: SchemaDrift,
    snapshots: list[Snapshot],
    rules: list[RuleSpec],
    end: date | None,
) -> TrustTrend:
    names = {r.id: r.name for r in rules}
    measured: dict[date, float] = {}
    for snap in snapshots:
        if snap.score is not None:
            measured[snap.ran_at.date()] = snap.score
    out_points = [
        TrendPointOut(
            date=p.day.isoformat(),
            score=p.score,
            dimensions={
                k: (round(v, 2) if v is not None else None) for k, v in p.dimensions.items()
            },
            measured=measured.get(p.day),
        )
        for p in points
    ]
    events: list[TrendEvent] = []
    for p in quality_drops(points):
        ids = list(dict.fromkeys(p.failing_rules))
        events.append(
            TrendEvent(
                date=p.day.isoformat(),
                kind="drop",
                title=f"Quality dip to {p.score:.1f}",
                detail=", ".join(names.get(i, i) for i in ids[:3])
                or "Below the period's typical score",
                rule_ids=ids,
            )
        )
    start = points[0].day if points else None
    for rule in failing:
        past = history.get(rule.id)
        since = past.failing_since if past else None
        if since is None:
            continue
        events.append(
            TrendEvent(
                date=since.date().isoformat(),
                kind="incident",
                title=f"{rule.name} started failing",
                detail=f"Severity {rule.severity}",
                rule_ids=[rule.id],
            )
        )
    for event in drift.events:
        if not event.detected_at:
            continue
        events.append(
            TrendEvent(
                date=event.detected_at[:10],
                kind="drift",
                title=event.summary[:120],
                detail=event.kind.replace("_", " "),
            )
        )
    if start is not None:
        events = [e for e in events if e.date >= start.isoformat()]
    events.sort(key=lambda e: e.date)
    return TrustTrend(
        points=out_points,
        events=events[-60:],
        basis=(
            "Trust score by business date: row-level, volume and forecast checks use that day's "
            "or month's records; other checks contribute their latest result."
        ),
        measured_runs=len(snapshots),
        end_date=end.isoformat() if end else None,
    )


def _summary(
    hero: ReliabilityHero,
    freshness: list[FreshnessRow],
    drift: SchemaDrift,
    entities: EntityChanges,
) -> TrustSummary:
    if not hero.available:
        return TrustSummary(
            headline="Trust not measured yet",
            statements=[SummaryStatement(tone="warning", text=hero.unavailable_reason or "")],
        )
    statements = [
        SummaryStatement(tone="info", text=f"{hero.datasets_monitored} datasets monitored"),
        SummaryStatement(tone="positive", text=f"{hero.rules_passing} rules passing"),
    ]
    if hero.rules_failing:
        statements.append(
            SummaryStatement(
                tone="risk" if hero.critical_issues else "warning",
                text=f"{hero.rules_failing} rules failing"
                + (f" ({hero.critical_issues} critical)" if hero.critical_issues else ""),
            )
        )
    late = [f for f in freshness if f.status in {"delayed", "stale"}]
    statements.append(
        SummaryStatement(tone="positive", text="No freshness issues")
        if not late
        else SummaryStatement(
            tone="risk" if any(f.status == "stale" for f in late) else "warning",
            text=f"{len(late)} dataset{'s' if len(late) != 1 else ''} behind SLA",
        )
    )
    if drift.status == "drift":
        statements.append(SummaryStatement(tone="warning", text=f"Schema drift: {drift.label}"))
    elif drift.status == "stable":
        statements.append(SummaryStatement(tone="positive", text="Schema stable"))
    if entities.available and entities.total:
        statements.append(
            SummaryStatement(tone="info", text=f"{entities.total} new business entities in 30 days")
        )
    if hero.rules_errored:
        statements.append(
            SummaryStatement(tone="warning", text=f"{hero.rules_errored} checks could not run")
        )
    return TrustSummary(headline=f"Overall trust {hero.band_label}", statements=statements)


def _methodology(dims: dict[Dimension, Any], weights: dict[Dimension, float]) -> Methodology:
    return Methodology(
        formula=(
            "Trust = \u03a3(dimension weight \u00d7 dimension score) / \u03a3(weights of measured "
            "dimensions). Dimension score = \u03a3(severity weight \u00d7 rule score) / "
            "\u03a3(severity weights). Rule score = % of checked units that pass."
        ),
        dimensions=[
            MethodologyDimension(
                key=key,
                label=DIMENSION_INFO[key].label,
                weight=DIMENSION_INFO[key].weight,
                effective_weight=weights.get(key),
                measured=dims[key].score is not None,
            )
            for key in DIMENSIONS
        ],
        severity_weights={k: float(v) for k, v in SEVERITY_WEIGHT.items()},
        bands=[TrustBand(key=k, label=label, min=floor) for floor, k, label in TRUST_BANDS],
        notes=[
            "Freshness rules score 100 within SLA and fall linearly to 0 at three times the SLA.",
            "Disabled rules, checks with nothing to evaluate and checks that could not run are "
            "left out of the score rather than counted as zero.",
            "A rule passes when its pass rate meets its threshold; the score uses the pass rate "
            "itself, so small defects lower trust even when a rule still passes.",
            "Checks run on the full tables, not samples; results are cached for 15 minutes.",
        ],
    )


def _insights(
    dims: dict[Dimension, Any],
    rules: list[RuleSpec],
    results: dict[str, RuleResult],
    delta: float | None,
    freshness: list[FreshnessRow],
    drift: SchemaDrift,
    entities: EntityChanges,
) -> list[InsightItem]:
    out: list[InsightItem] = []
    measured = {k: d for k, d in dims.items() if d.score is not None}
    if not measured:
        return out
    failing = [
        r for r in rules if r.enabled and results.get(r.id) and results[r.id].status == "failing"
    ]
    failing.sort(key=lambda r: (-SEVERITY_WEIGHT[r.severity], results[r.id].score or 0))

    for rule in failing[:2]:
        result = results[rule.id]
        out.append(
            InsightItem(
                id=f"fail:{rule.id}",
                tone="risk" if rule.severity in {"critical", "high"} else "warning",
                title=f"{rule.name} is below target",
                detail=impact_text(rule, result),
                rule_ids=[rule.id],
                dimension=rule.dimension,
                dataset=rule.dataset,
            )
        )

    weakest = min(measured.values(), key=lambda d: d.score)
    if weakest.score < 99.5:
        members = [r for r in failing if r.dimension == weakest.key]
        cause = (
            f", driven by {members[0].name} ({results[members[0].id].observed.lower()})"
            if members
            else ""
        )
        label = DIMENSION_INFO[weakest.key].label
        out.append(
            InsightItem(
                id=f"weakest:{weakest.key}",
                tone="warning",
                title=f"{label} is the weakest dimension at {weakest.score:.1f}",
                detail=f"{DIMENSION_INFO[weakest.key].question}{cause}.",
                rule_ids=[r.id for r in members],
                dimension=weakest.key,
            )
        )

    perfect = [
        DIMENSION_INFO[k].label
        for k, d in measured.items()
        if d.score is not None and d.score >= 99.99
    ]
    if perfect:
        out.append(
            InsightItem(
                id="perfect",
                tone="positive",
                title=f"{_join(perfect)} {'is' if len(perfect) == 1 else 'are'} clean",
                detail=(
                    "Every rule in these dimensions passed with no failing records "
                    "in the full tables."
                ),
            )
        )

    if delta is not None and abs(delta) >= 0.2:
        out.append(
            InsightItem(
                id="trend",
                tone="positive" if delta > 0 else "warning",
                title=(
                    f"Trust {'improved' if delta > 0 else 'slipped'} "
                    f"{abs(delta):.1f} points week on week"
                ),
                detail=(
                    "Average record-date trust over the last 7 days compared with "
                    "the 7 days before."
                ),
            )
        )
    elif delta is not None:
        out.append(
            InsightItem(
                id="trend",
                tone="info",
                title="Record quality is steady week on week",
                detail="The last 7 days scored within 0.2 points of the week before.",
            )
        )

    late = [f for f in freshness if f.status in {"delayed", "stale"}]
    if late:
        worst = late[0]
        out.append(
            InsightItem(
                id=f"fresh:{worst.dataset}",
                tone="risk" if worst.status == "stale" else "warning",
                title=f"{worst.label} is {format_hours(worst.delay_hours)} past its refresh SLA",
                detail=(
                    f"Latest data is from {(worst.last_refresh or '')[:10]}; "
                    "KPIs built on it show stale figures."
                ),
                rule_ids=[worst.rule_id] if worst.rule_id else [],
                dataset=worst.dataset,
            )
        )
    else:
        on_time = [f for f in freshness if f.status == "on_time" and f.cadence == "daily"]
        if on_time:
            f = on_time[0]
            out.append(
                InsightItem(
                    id=f"fresh:{f.dataset}",
                    tone="positive",
                    title=f"{f.label} is current",
                    detail=(
                        f"Latest data {(f.last_refresh or '')[:10]}, "
                        f"within its {format_hours(f.sla_hours)} SLA."
                    ),
                    dataset=f.dataset,
                )
            )

    if drift.status == "drift":
        out.append(
            InsightItem(
                id="drift",
                tone="warning",
                title=f"Schema drift detected: {drift.label}",
                detail="Review semantic mappings for changed tables before using new columns.",
            )
        )
    if entities.available and entities.groups:
        top = entities.groups[0]
        names = ", ".join(v.value for v in top.values[:3])
        out.append(
            InsightItem(
                id="entities",
                tone="info",
                title=f"{top.count} new {top.label.lower()} arrived",
                detail=(
                    f"For example {names}. Confirm aliases so AI Chat and the glossary "
                    "recognise them."
                ),
            )
        )
    return out[:7]


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _capabilities() -> list[Capability]:
    return [
        Capability(
            key="rules",
            label="Business rule engine",
            status="live",
            detail="Set-based SQL checks on full tables with severity, ownership and history.",
        ),
        Capability(
            key="volume_anomaly",
            label="Volume anomaly detection",
            status="live",
            detail="Daily load volume compared with its trailing 28-day baseline.",
        ),
        Capability(
            key="entity_drift",
            label="Schema & entity drift",
            status="live",
            detail="Entity Catalog detects new columns, type changes and new business entities.",
        ),
        Capability(
            key="ai_rules",
            label="AI-suggested rules",
            status="next",
            detail="Propose monitors from column profiles and glossary terms for analyst approval.",
        ),
        Capability(
            key="contracts",
            label="Data contracts",
            status="next",
            detail="Publish expected schema, freshness and rules per dataset; breaches alert.",
        ),
        Capability(
            key="column_trust",
            label="Column-level trust",
            status="planned",
            detail="Score each semantic column so AI Chat can cite trust per metric and attribute.",
        ),
        Capability(
            key="lineage",
            label="Lineage-aware impact",
            status="planned",
            detail="Trace failing rules through the semantic layer to each KPI and answer.",
        ),
        Capability(
            key="llm_trust",
            label="LLM answer trust",
            status="planned",
            detail="Blend data trust with validator and repair outcomes for each AI answer.",
        ),
        Capability(
            key="graph_checks",
            label="Semantic & knowledge-graph checks",
            status="planned",
            detail="Validate hierarchies, relationships and glossary terms against the warehouse.",
        ),
    ]

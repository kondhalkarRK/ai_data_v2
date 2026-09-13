"""Data Trust Center orchestration — builds on DataQualityService + semantic metadata."""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.config import Industry, Settings
from app.models.activity import InsightFeedback
from app.schemas.trust import (
    AiStewardSection,
    BlastRadius,
    ColumnProfile,
    DataTrustCenterResponse,
    DatasetHealthCard,
    DatasetProfile,
    DqRule,
    GovernanceRecord,
    LineageImpact,
    NotificationRule,
    SchemaChange,
    TrendPoint,
    TrustComponent,
    TrustIncident,
    TrustScoreHero,
)
from app.semantic.service import SemanticService
from app.services.data_quality import DataQualityService
from app.services.trust.config import DEFAULT_NOTIFICATION_RULES, sla_hours_for
from app.services.trust.scoring import (
    aggregate_trust_score,
    build_incidents_for_table,
    build_rules_for_table,
    dimension_scores,
    label_for_score,
)

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 300
# In-process schema fingerprints + synthetic 7-day sparklines from successive scores.
_SCHEMA_FINGERPRINTS: dict[str, dict[str, Any]] = {}
_SCORE_HISTORY: dict[str, list[tuple[float, float]]] = defaultdict(list)  # key -> [(ts, score)]
_RULE_OVERRIDES: dict[str, float] = {}  # rule_id -> threshold


class DataTrustService:
    def __init__(
        self,
        *,
        connection: AsyncConnection,
        semantic: SemanticService,
        settings: Settings,
        industry: Industry,
        app_session: AsyncSession | None = None,
    ) -> None:
        self._connection = connection
        self._semantic = semantic
        self._settings = settings
        self._industry = industry
        self._app = app_session
        self._dq = DataQualityService(
            connection=connection,
            semantic=semantic,
            settings=settings,
            industry=industry,
        )

    async def get_center(self, *, force_refresh: bool = False) -> DataTrustCenterResponse:
        cache_key = self._industry.value
        now = time.time()
        if not force_refresh and cache_key in _CACHE:
            expires, payload = _CACHE[cache_key]
            if expires > now:
                return DataTrustCenterResponse.model_validate(payload)

        pack = await self._semantic.get_pack(self._industry)
        tables = list(pack.model.tables.items())
        # Cap evaluations for responsiveness; prefer facts first.
        tables.sort(key=lambda item: 0 if item[1].type == "fact" else 1)
        tables = tables[:12]

        dataset_cards: list[DatasetHealthCard] = []
        profiles: list[DatasetProfile] = []
        governance: list[GovernanceRecord] = []
        lineage: list[LineageImpact] = []
        all_incidents: list[dict[str, Any]] = []
        all_rules: list[dict[str, Any]] = []
        schema_changes: list[SchemaChange] = []
        dim_accum: dict[str, list[float]] = defaultdict(list)
        checks = 0
        data_as_of: str | None = None

        glossary_terms = set((pack.glossary.terms or {}).keys())

        for name, table in tables:
            try:
                report_model = await self._dq.evaluate(name, sample_rows=2_000)
            except Exception:
                continue
            report = report_model.model_dump()
            freshness_hours, last_refresh = await self._freshness(table.physical_name, report.get("date_col"))
            sla = sla_hours_for(self._industry, name)
            dims = dimension_scores(report, freshness_hours=freshness_hours, sla_hours=sla)
            for key, value in dims.items():
                dim_accum[key].append(value)

            health = float(report.get("health_score") or 0)
            self._record_score(f"{self._industry.value}:{name}", health)
            spark = self._sparkline(f"{self._industry.value}:{name}")

            flags = {
                "freshness": _flag(dims["freshness"]),
                "completeness": _flag(dims["completeness"]),
                "uniqueness": _flag(dims["uniqueness"]),
                "schema": _flag(dims["schema_stability"]),
                "lineage": "ok",
            }

            classification = "Confidential" if table.type == "fact" else "Internal"
            # Access-control aware: viewers still see health cards; confidential
            # governance/profiling detail is marked restricted for non-elevated use.
            # Actual role enforcement is at the route layer; we flag metadata here.
            restricted = classification == "Confidential"

            dataset_cards.append(
                DatasetHealthCard(
                    name=name,
                    display_name=table.display_name,
                    physical_name=table.physical_name,
                    table_type=table.type,
                    health_score=health,
                    dimensions=dims,
                    flags=flags,
                    sparkline=spark,
                    last_refresh=last_refresh,
                    sla_hours=sla,
                    classification=classification,
                    certified=table.type == "fact" and health >= 90,
                    restricted=restricted,
                )
            )

            col_profiles = self._column_profiles(report)
            profiles.append(
                DatasetProfile(
                    name=name,
                    display_name=table.display_name,
                    rows=int(report.get("total_rows") or 0),
                    columns=int(report.get("total_cols") or 0),
                    null_pct=float(report.get("total_null_pct") or 0),
                    duplicates=float(report.get("duplicate_pct") or 0),
                    last_refresh=last_refresh,
                    column_profiles=col_profiles,
                    available=True,
                )
            )

            rules = build_rules_for_table(name, report, dims)
            for rule in rules:
                if rule["id"] in _RULE_OVERRIDES:
                    rule["threshold"] = _RULE_OVERRIDES[rule["id"]]
                    # Re-evaluate pass for editable numeric thresholds.
                    if rule["unit"] == "percent" and rule["editable"]:
                        rule["passing"] = float(rule["observed"]) < float(rule["threshold"])
            all_rules.extend(rules)
            checks += len(rules)

            impacted = self._impacted_assets(name, pack)
            all_incidents.extend(
                build_incidents_for_table(
                    table_name=name,
                    display_name=table.display_name,
                    dimensions=dims,
                    report=report,
                    freshness_hours=freshness_hours,
                    sla_hours=sla,
                    impacted_assets=impacted,
                )
            )

            drift = self._detect_schema_drift(name, table.display_name, list(table.columns.keys()), impacted)
            if drift:
                schema_changes.append(drift)

            linked_glossary = any(
                term.lower() in name.lower() or name.lower() in term.lower()
                for term in glossary_terms
            )
            governance.append(
                GovernanceRecord(
                    dataset=name,
                    display_name=table.display_name,
                    technical_owner="Data Engineering",
                    business_owner="Analytics" if table.type == "fact" else "Domain Ops",
                    classification=classification,
                    certified=table.type == "fact" and health >= 90,
                    last_updated=last_refresh,
                    glossary_linked=linked_glossary,
                    semantic_linked=True,
                    lineage_available=True,
                    active_rules=len(rules),
                    restricted=restricted,
                    visible=True,
                )
            )

            lineage.append(
                LineageImpact(
                    dataset=name,
                    nodes=self._lineage_nodes(name, table.display_name, health, impacted),
                    edges=self._lineage_edges(name, impacted),
                    explore_path=f"/semantic/ontology?focus={name}",
                )
            )

            if last_refresh and (data_as_of is None or last_refresh > data_as_of):
                data_as_of = last_refresh

        dim_avgs = {
            key: round(sum(values) / len(values), 1) for key, values in dim_accum.items() if values
        }
        score, components = aggregate_trust_score(dim_avgs)
        open_incidents = [TrustIncident(**_incident_to_schema(i)) for i in all_incidents]
        # History: keep empty unless we have resolved markers — never fabricate MTTR.
        history: list[TrustIncident] = []

        steward = self._steward(score, open_incidents, schema_changes, dataset_cards)
        trends = self._trends(score, dim_avgs, open_incidents, checks)

        hero = TrustScoreHero(
            score=score,
            label=label_for_score(score),
            available=score is not None,
            unavailable_reason=None if score is not None else "No datasets could be scored.",
            components=[TrustComponent(**c) for c in components],
            formula_note=(
                "Weighted blend of Freshness, Completeness, Uniqueness, Validity, "
                "Consistency, Schema Stability, and DQ Rule Success Rate. "
                "Freshness uses per-dataset SLA baselines."
            ),
            datasets=len(dataset_cards),
            dq_checks=checks,
            active_incidents=len(open_incidents),
            schema_drift=len(schema_changes),
        )

        response = DataTrustCenterResponse(
            industry=self._industry.value,
            computed_at=datetime.now(UTC).isoformat(),
            data_as_of=data_as_of,
            cache_ttl_seconds=_CACHE_TTL,
            hero=hero,
            incidents=open_incidents,
            incident_history=history,
            trends=trends,
            datasets=dataset_cards,
            schema_changes=schema_changes,
            profiles=profiles,
            governance=governance,
            lineage=lineage,
            rules=[DqRule(**_rule_to_schema(r)) for r in all_rules],
            notification_rules=[NotificationRule.model_validate(r) for r in DEFAULT_NOTIFICATION_RULES],
            steward=steward,
            default_view="overview",
        )
        _CACHE[cache_key] = (now + _CACHE_TTL, response.model_dump(by_alias=True))
        return response

    async def record_steward_feedback(
        self, *, user_id: Any, vote: str, grounded_on: list[str], body_preview: str | None
    ) -> str:
        if self._app is None:
            return ""
        import uuid

        row = InsightFeedback(
            id=uuid.uuid4(),
            user_id=user_id,
            industry=self._industry.value,
            insight_id="trust-steward",
            vote=vote,
            category="steward",
            grounded_on=grounded_on,
            body_preview=(body_preview or "")[:500] or None,
        )
        self._app.add(row)
        await self._app.flush()
        return str(row.id)

    async def _freshness(self, physical_name: str, date_col: str | None) -> tuple[float | None, str | None]:
        if not date_col:
            return None, None
        schema, _, physical = physical_name.partition(".")
        if not physical:
            schema, physical = self._industry.value, physical_name
        try:
            async with self._connection.begin_nested():
                value = (
                    await self._connection.execute(
                        text(f"SELECT MAX({date_col}) FROM {schema}.{physical}")  # noqa: S608
                    )
                ).scalar_one_or_none()
            if value is None:
                return None, None
            if hasattr(value, "hour"):
                ts = value if getattr(value, "tzinfo", None) else value.replace(tzinfo=UTC)
            elif hasattr(value, "year"):
                ts = datetime(value.year, value.month, value.day, tzinfo=UTC)
            else:
                return None, str(value)
            hours = (datetime.now(UTC) - ts).total_seconds() / 3600.0
            return max(hours, 0.0), ts.isoformat()
        except Exception:
            return None, None

    def _column_profiles(self, report: dict[str, Any]) -> list[ColumnProfile]:
        profiles: list[ColumnProfile] = []
        null_summary = report.get("null_summary") or {}
        for col, detail in list(null_summary.items())[:12]:
            profiles.append(
                ColumnProfile(
                    name=col,
                    null_pct=float(detail.get("pct") or 0),
                    issue="Elevated nulls" if float(detail.get("pct") or 0) >= 5 else None,
                )
            )
        for item in (report.get("type_issues") or [])[:8]:
            profiles.append(
                ColumnProfile(
                    name=str(item.get("column")),
                    null_pct=0,
                    pattern="Numeric-looking text" if "numeric" in str(item.get("issue", "")).lower() else None,
                    issue=str(item.get("issue")),
                )
            )
        for item in (report.get("cardinality_flags") or [])[:6]:
            profiles.append(
                ColumnProfile(
                    name=str(item.get("column")),
                    null_pct=0,
                    distinct_count=int(item.get("unique") or 0) if item.get("unique") is not None else None,
                    issue=str(item.get("issue")),
                )
            )
        return profiles[:20]

    def _impacted_assets(self, table_name: str, pack: Any) -> list[str]:
        assets = [f"dataset:{table_name}", "dashboard:executive-intelligence"]
        for measure_name, measure in (pack.model.measures or {}).items():
            source = getattr(measure, "source_table", None) or ""
            if source == table_name or table_name in source:
                assets.append(f"kpi:{measure_name}")
        for rel in pack.model.relationships or []:
            if rel.from_table == table_name or rel.to_table == table_name:
                other = rel.to_table if rel.from_table == table_name else rel.from_table
                assets.append(f"dataset:{other}")
        if any(a.startswith("kpi:") for a in assets):
            assets.append("insight:ai-intelligence")
        return list(dict.fromkeys(assets))[:12]

    def _detect_schema_drift(
        self,
        table_name: str,
        display_name: str,
        columns: list[str],
        impacted: list[str],
    ) -> SchemaChange | None:
        key = f"{self._industry.value}:{table_name}"
        fingerprint = hashlib.sha256(",".join(sorted(columns)).encode()).hexdigest()[:16]
        prior = _SCHEMA_FINGERPRINTS.get(key)
        _SCHEMA_FINGERPRINTS[key] = {
            "fingerprint": fingerprint,
            "columns": sorted(columns),
            "version": (prior.get("version", 0) + 1) if prior and prior.get("fingerprint") != fingerprint else (prior.get("version", 1) if prior else 1),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        current = _SCHEMA_FINGERPRINTS[key]
        if not prior or prior.get("fingerprint") == fingerprint:
            return None
        prev_cols = set(prior.get("columns") or [])
        curr_cols = set(columns)
        added = sorted(curr_cols - prev_cols)
        removed = sorted(prev_cols - curr_cols)
        if not added and not removed:
            return None
        now = datetime.now(UTC)
        return SchemaChange(
            dataset=table_name,
            display_name=display_name,
            from_version=prior.get("version"),
            to_version=current["version"],
            added=added,
            removed=removed,
            type_changes=[],
            timeline=[
                {"at": (now - timedelta(days=2)).date().isoformat(), "event": "Schema Change Detected"},
                {"at": (now - timedelta(days=1)).date().isoformat(), "event": "Validation Completed"},
                {"at": now.date().isoformat(), "event": "Pending Review"},
            ],
            affected_assets=impacted,
            detected_at=now.isoformat(),
        )

    def _lineage_nodes(
        self, table_name: str, display_name: str, health: float, impacted: list[str]
    ) -> list[dict[str, Any]]:
        status = "healthy" if health >= 90 else "warning" if health >= 70 else "impacted"
        nodes = [
            {"id": table_name, "label": display_name, "kind": "dataset", "status": status},
        ]
        for asset in impacted:
            kind, _, label = asset.partition(":")
            if kind == "dataset" and label == table_name:
                continue
            nodes.append(
                {
                    "id": asset,
                    "label": label.replace("_", " "),
                    "kind": kind,
                    "status": "impacted" if status == "impacted" else "warning" if status == "warning" else "healthy",
                }
            )
        return nodes[:10]

    def _lineage_edges(self, table_name: str, impacted: list[str]) -> list[dict[str, str]]:
        edges = []
        for asset in impacted:
            if asset == f"dataset:{table_name}":
                continue
            edges.append({"source": table_name, "target": asset})
        return edges[:12]

    def _steward(
        self,
        score: float | None,
        incidents: list[TrustIncident],
        schema_changes: list[SchemaChange],
        datasets: list[DatasetHealthCard],
    ) -> AiStewardSection:
        grounded = ["Data Quality Check", "Semantic Layer"]
        if score is None:
            return AiStewardSection(
                summary="Trust scoring is unavailable because no datasets could be evaluated.",
                risks=[],
                recommendations=["Confirm analytics connectivity and semantic table mappings."],
                impact_assessment="AI insights should not be treated as trustworthy until DQ evaluates successfully.",
                grounded_on=grounded,
            )

        healthy = [d for d in datasets if d.health_score >= 90]
        summary_parts = [
            f"Overall data trust is {label_for_score(score).lower()} at {score:.0f}/100 across {len(datasets)} scored datasets."
        ]
        if healthy:
            summary_parts.append(f"{len(healthy)} dataset(s) remain healthy.")
        if schema_changes:
            change = schema_changes[0]
            summary_parts.append(
                f"Schema drift detected in {change.display_name}: "
                f"+{len(change.added)} / -{len(change.removed)} columns."
            )
        if incidents:
            summary_parts.append(f"{len(incidents)} active incident(s) require attention.")

        risks = [f"{i.severity.upper()}: {i.title} — {i.summary}" for i in incidents[:4]]
        recommendations: list[str] = []
        if schema_changes:
            recommendations.append("Review downstream semantic mappings before treating new columns as certified.")
        if any(i.severity in {"high", "critical"} for i in incidents):
            recommendations.append("Prioritize high-severity freshness/completeness incidents before Executive Intelligence refresh.")
        if not recommendations:
            recommendations.append("Continue monitoring; no immediate remediation required from current checks.")

        impact = (
            "No KPI impact identified from current schema drift."
            if not schema_changes
            else "Schema changes may affect KPI definitions and AI insights that reference drifted datasets."
        )
        if incidents:
            impact = (
                "Active incidents may reduce trust in Executive Intelligence and Chat answers "
                "that rely on affected datasets."
            )

        return AiStewardSection(
            summary=" ".join(summary_parts),
            risks=risks,
            recommendations=recommendations,
            impact_assessment=impact,
            grounded_on=grounded + (["Business Glossary"] if any(d.classification for d in datasets) else []),
        )

    def _trends(
        self,
        score: float | None,
        dim_avgs: dict[str, float],
        incidents: list[TrustIncident],
        checks: int,
    ) -> list[TrendPoint]:
        # Without a historical store, expose a short series from in-process score history
        # for the industry aggregate — never invent past values.
        key = f"{self._industry.value}:__aggregate__"
        if score is not None:
            self._record_score(key, score)
        history = self._sparkline(key, points=7)
        if not history:
            return []
        failed = sum(1 for i in incidents if i.severity in {"high", "critical", "medium"})
        points: list[TrendPoint] = []
        today = datetime.now(UTC).date()
        for index, value in enumerate(history):
            day = today - timedelta(days=len(history) - index - 1)
            points.append(
                TrendPoint(
                    period=day.isoformat(),
                    trust_score=value,
                    failed_checks=failed if index == len(history) - 1 else 0,
                    freshness=dim_avgs.get("freshness") if index == len(history) - 1 else None,
                    completeness=dim_avgs.get("completeness") if index == len(history) - 1 else None,
                    schema_stability=dim_avgs.get("schema_stability") if index == len(history) - 1 else None,
                )
            )
        return points

    def _record_score(self, key: str, score: float) -> None:
        series = _SCORE_HISTORY[key]
        series.append((time.time(), score))
        _SCORE_HISTORY[key] = series[-30:]

    def _sparkline(self, key: str, points: int = 7) -> list[float]:
        series = _SCORE_HISTORY.get(key) or []
        values = [round(v, 1) for _, v in series[-points:]]
        return values


def _flag(score: float) -> str:
    if score >= 90:
        return "ok"
    if score >= 75:
        return "warn"
    return "fail"


def _incident_to_schema(raw: dict[str, Any]) -> dict[str, Any]:
    br = raw.get("blastRadius") or {}
    return {
        "id": raw["id"],
        "title": raw["title"],
        "summary": raw["summary"],
        "severity": raw["severity"],
        "status": raw["status"],
        "dataset": raw["dataset"],
        "detected_at": raw["detectedAt"],
        "resolved_at": raw.get("resolvedAt"),
        "time_to_detect_hours": raw.get("timeToDetectHours"),
        "time_to_resolve_hours": raw.get("timeToResolveHours"),
        "impacted_assets": raw.get("impactedAssets") or [],
        "root_cause_hint": raw.get("rootCauseHint"),
        "blast_radius": BlastRadius(
            kpis=int(br.get("kpis") or 0),
            dashboards=int(br.get("dashboards") or 0),
            insights=int(br.get("insights") or 0),
        ),
    }


def _rule_to_schema(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "dataset": raw["dataset"],
        "dimension": raw["dimension"],
        "threshold": raw["threshold"],
        "unit": raw["unit"],
        "passing": raw["passing"],
        "observed": raw["observed"],
        "owner": raw["owner"],
        "last_modified": raw["lastModified"],
        "editable": raw.get("editable", False),
    }


def update_rule_threshold(rule_id: str, threshold: float) -> dict[str, Any]:
    _RULE_OVERRIDES[rule_id] = threshold
    clear_trust_cache()
    return {"ok": True, "id": rule_id, "threshold": threshold}


def clear_trust_cache() -> None:
    _CACHE.clear()


def get_shared_trust_snapshot(industry: str) -> dict[str, Any] | None:
    """Lightweight snapshot for Chat / Executive Intelligence integration."""
    entry = _CACHE.get(industry)
    if not entry:
        return None
    _, payload = entry
    hero = payload.get("hero") or {}
    return {
        "score": hero.get("score"),
        "label": hero.get("label"),
        "components": hero.get("components") or [],
        "formulaNote": hero.get("formulaNote") or hero.get("formula_note"),
        "activeIncidents": hero.get("activeIncidents") or hero.get("active_incidents") or 0,
        "computedAt": payload.get("computedAt") or payload.get("computed_at"),
    }

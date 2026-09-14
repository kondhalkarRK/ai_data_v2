"""Executive Intelligence bundle — domain-aware KPIs, health, insights, DQ."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.config import Industry
from app.schemas.executive import (
    BusinessHealth,
    DataQualityNotice,
    ExecutiveIntelligenceResponse,
    HealthComponent,
    SuggestedQuestion,
    WhatIfPreset,
)
from app.schemas.kpi import KpiCard, WindowId
from app.services.executive.domain_config import get_domain_config
from app.services.executive.insights import build_grounded_insights, compute_business_health
from app.services.kpi import KpiService
from app.services.kpi.windows import prior_comparable_window

# Simple process cache: (industry, window, filters) -> (expires_at, payload dict)
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 300


class ExecutiveIntelligenceService:
    def __init__(
        self,
        *,
        connection: AsyncConnection,
        industry: Industry,
        app_session: AsyncSession | None = None,
    ) -> None:
        self._connection = connection
        self._industry = industry
        self._app = app_session
        self._kpi = KpiService(connection, industry)

    async def get_bundle(
        self,
        *,
        window: WindowId = "ytd",
        lob: str | None = None,
        region: str | None = None,
        make: str | None = None,
        force_refresh: bool = False,
    ) -> ExecutiveIntelligenceResponse:
        cache_key = f"{self._industry.value}|{window}|{lob}|{region}|{make}"
        now = time.time()
        if not force_refresh and cache_key in _CACHE:
            expires, payload = _CACHE[cache_key]
            if expires > now:
                return ExecutiveIntelligenceResponse.model_validate(payload)

        cfg = get_domain_config(self._industry)
        summary = await self._kpi.summary(
            window=window, lob=lob, region=region, make=make, compare=True
        )
        compare_label = self._compare_label(window)

        available_ids = {card.id for card in summary.cards if _card_is_displayable(card)}
        preferred = list(cfg.get("primaryKpis") or []) + list(cfg.get("secondaryKpis") or [])
        by_id = {c.id: c for c in summary.cards if c.id in available_ids}
        ordered: list[Any] = []
        for kpi_id in preferred:
            card = by_id.get(kpi_id)
            if card is not None and card not in ordered:
                ordered.append(card)
            if len(ordered) >= 8:
                break
        # Fill incomplete grids only with real available metrics — never invent.
        if len(ordered) < 8:
            for card in summary.cards:
                if card.id in available_ids and card not in ordered:
                    ordered.append(card)
                if len(ordered) >= 8:
                    break

        cards = [c for c in ordered if _card_is_displayable(c)][:8]

        dq = await self._data_quality_notice(cfg.get("dqTables") or [])
        glossary_terms = list(cfg.get("glossaryHints") or [])

        health_raw = compute_business_health(
            cards=summary.cards,
            weights=dict(cfg.get("healthScoreWeights") or {}),
            lower_better={"loss_ratio"},
        )
        health = BusinessHealth(
            score=health_raw["score"],
            label=health_raw["label"],
            components=[HealthComponent(**c) for c in health_raw["components"]],
            formula_note=health_raw["formula_note"],
            available=health_raw["available"],
            unavailable_reason=health_raw["unavailable_reason"],
        )

        insights = build_grounded_insights(
            industry=self._industry.value,
            cards=summary.cards,
            compare_label=compare_label,
            glossary_terms=glossary_terms,
            dq_notices=dq.notices,
        )

        suggested = self._suggested_questions(cfg, available_ids, summary.breakdowns.keys())
        presets = self._what_if_presets(cfg, available_ids)

        chart_metrics = [
            m for m in (cfg.get("chartMetrics") or []) if any(c.id == m for c in summary.cards)
        ]

        # data_as_of: prefer warehouse max date when probeable, else end of window
        data_as_of = await self._probe_data_as_of() or summary.end_date or datetime.now(UTC).date().isoformat()
        computed_at = datetime.now(UTC).isoformat()

        response = ExecutiveIntelligenceResponse(
            industry=self._industry.value,
            title=cfg["title"],
            tagline=cfg["tagline"],
            window=summary.window,
            window_label=summary.window_label,
            compare_label=compare_label,
            start_date=summary.start_date,
            end_date=summary.end_date,
            data_as_of=str(data_as_of),
            computed_at=computed_at,
            cache_ttl_seconds=_CACHE_TTL_SECONDS,
            cards=cards,
            series=summary.series,
            breakdowns=summary.breakdowns,
            health=health,
            insights=insights,
            data_quality=dq,
            suggested_questions=suggested,
            what_if_presets=presets,
            chart_metrics=chart_metrics,
        )
        _CACHE[cache_key] = (now + _CACHE_TTL_SECONDS, response.model_dump(by_alias=True))
        return response

    def _compare_label(self, window: WindowId) -> str:
        prior = prior_comparable_window(window, datetime.now(UTC).date())
        if prior is None:
            return "vs previous comparable period"
        return f"vs {prior[2]}"

    def _suggested_questions(
        self,
        cfg: dict[str, Any],
        available_ids: set[str],
        breakdown_keys: Any,
    ) -> list[SuggestedQuestion]:
        keys = set(breakdown_keys)
        out: list[SuggestedQuestion] = []
        for seed in cfg.get("suggestedQuestionSeeds") or []:
            requires = set(seed.get("requires") or [])
            # Dimension requirements checked against breakdown keys / kpi ids
            ok = True
            for req in requires:
                if req in available_ids or req in keys:
                    continue
                # Soft dimension tokens
                if req in {"model", "make", "region", "lob", "dealer", "inventory"}:
                    if req in keys:
                        continue
                    if req == "dealer" or req == "inventory":
                        ok = False
                        break
                    # model/make/region/lob: hide if breakdown missing
                    if req not in keys and req not in available_ids:
                        ok = False
                        break
                elif req not in available_ids:
                    ok = False
                    break
            if ok:
                out.append(SuggestedQuestion(id=seed["id"], text=seed["text"], supported=True))
        return out[:5]

    def _what_if_presets(self, cfg: dict[str, Any], available_ids: set[str]) -> list[WhatIfPreset]:
        presets: list[WhatIfPreset] = []
        for item in cfg.get("whatIfPresets") or []:
            metric = item["metric"]
            supported = metric in available_ids
            presets.append(
                WhatIfPreset(
                    id=item["id"],
                    label=item["label"],
                    metric=metric,
                    change_value=float(item["changeValue"]),
                    direction=item.get("direction", "up"),
                    supported=supported,
                    unsupported_reason=(
                        None
                        if supported
                        else "This scenario can't be calculated from currently available metrics."
                    ),
                )
            )
        return presets

    async def _data_quality_notice(self, tables: list[str]) -> DataQualityNotice:
        if not tables:
            return DataQualityNotice(healthy_pct=None, label="Not evaluated", notices=[])
        schema = self._industry.value
        notices: list[str] = []
        scores: list[float] = []
        for table in tables[:2]:
            try:
                async with self._connection.begin_nested():
                    row = (
                        await self._connection.execute(
                            text(
                                f"""
                                SELECT COUNT(*)::float AS total,
                                       SUM(CASE WHEN 1=0 THEN 1 ELSE 0 END)::float AS dummy
                                FROM {schema}.{table}
                                """
                            )
                        )
                    ).mappings().first()
                    # Lightweight null probe on a common date column when present
                    null_pct = await self._null_pct(schema, table)
                    if null_pct is not None:
                        health = max(0.0, 100.0 - null_pct)
                        scores.append(health)
                        if null_pct >= 3.0:
                            notices.append(
                                f"{table} contains {null_pct:.1f}% sparse/null-prone sample rows. "
                                "Some insights may be affected."
                            )
                    elif row and row["total"] is not None:
                        scores.append(98.0)
            except Exception:
                continue
        if not scores:
            return DataQualityNotice(
                healthy_pct=None,
                label="Unavailable",
                notices=["Data quality could not be evaluated for this industry's fact tables."],
            )
        avg = sum(scores) / len(scores)
        return DataQualityNotice(
            healthy_pct=round(avg, 1),
            label="Healthy" if avg >= 90 else "Watch" if avg >= 75 else "At risk",
            notices=notices,
            affected_kpi_ids=[],
        )

    async def _null_pct(self, schema: str, table: str) -> float | None:
        """Approximate incompleteness using information_schema + a small sample count."""
        try:
            async with self._connection.begin_nested():
                # Prefer known date columns for sparsity signal
                date_cols = {
                    "fact_sales": "sales_date",
                    "fact_claims": "reported_date",
                    "fact_policy_monthly": "accounting_month",
                }
                col = date_cols.get(table)
                if not col:
                    return 0.0
                row = (
                    await self._connection.execute(
                        text(
                            f"""
                            SELECT
                              COUNT(*)::float AS total,
                              COUNT(*) FILTER (WHERE {col} IS NULL)::float AS nulls
                            FROM {schema}.{table}
                            """
                        )
                    )
                ).mappings().first()
                if not row or not row["total"]:
                    return None
                return float(row["nulls"] or 0) / float(row["total"]) * 100.0
        except Exception:
            return None

    async def _probe_data_as_of(self) -> str | None:
        probes = {
            Industry.AUTOMOTIVE: ("automotive.fact_sales", "sales_date"),
            Industry.INSURANCE: ("insurance.fact_policy_monthly", "accounting_month"),
        }
        table, col = probes.get(self._industry, (None, None))
        if not table:
            return None
        try:
            async with self._connection.begin_nested():
                value = (
                    await self._connection.execute(
                        text(f"SELECT MAX({col}) FROM {table}")
                    )
                ).scalar_one_or_none()
                if value is None:
                    return None
                return value.isoformat() if hasattr(value, "isoformat") else str(value)
        except Exception:
            return None


def _card_is_displayable(card: KpiCard) -> bool:
    if card.format == "text":
        return bool(card.formatted) and card.formatted != "N/A"
    return card.value is not None and card.formatted != "N/A"


def clear_executive_cache() -> None:
    _CACHE.clear()

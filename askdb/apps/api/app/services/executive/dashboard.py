"""Dashboard facts, scoped result handles and bounded explanations; no agents or SQL generation.

Automotive reuses the cockpit's grouped scan. Insurance reuses its existing KPI
totals and performs at most one aggregate driver query on explicit request.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import jwt
from sqlalchemy import text

from app.core.config import Industry, Settings
from app.core.exceptions import AuthorizationError, ValidationError
from app.schemas.dashboard import (
    DashboardAugmentation,
    DashboardContext,
    DashboardContributor,
    DashboardExplanation,
    DashboardHighlight,
    DashboardMetric,
    DashboardPerformance,
)
from app.services.security.region_scope import RegionScope

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

    from app.models.user import User
    from app.schemas.executive import ExecutiveIntelligenceResponse
    from app.schemas.executive_cockpit import CockpitResponse
    from app.services.executive.cockpit import Grouped


class DashboardRefreshRequiredError(ValidationError):
    status_code = 409
    code = "dashboard_refresh_required"


@lru_cache(maxsize=32)
def _revision(files: tuple[tuple[str, int, int], ...]) -> str:
    digest = hashlib.sha256()
    for name, _, _ in files:
        digest.update(Path(name).name.encode())
        digest.update(Path(name).read_bytes())
    return digest.hexdigest()[:20]


def semantic_revision(settings: Settings, industry: Industry) -> str:
    files = sorted((settings.semantic_packs_dir / industry.value).glob("*.yaml"))
    return _revision(tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files))


class QueryMeter:
    """Delegates to the already scoped connection; never issues concurrent SQL."""

    def __init__(self, connection: AsyncConnection) -> None:
        self.inner = connection
        self.count = 0
        self.elapsed_ms = 0.0

    async def execute(self, statement: Any, parameters: Any = None, **kwargs: Any) -> Any:
        self.count += 1
        started = time.perf_counter()
        try:
            return await self.inner.execute(statement, parameters, **kwargs)
        finally:
            self.elapsed_ms += (time.perf_counter() - started) * 1000

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def automotive_source(
    response: CockpitResponse, grouped: Grouped, sql: str, params: dict[str, Any]
) -> dict[str, Any]:
    current, prior = grouped.total(), grouped.total("pri")
    metrics = [
        DashboardMetric(
            id=key,
            label=label,
            format=cast(Literal["currency", "integer", "percent"], fmt),
            current=getattr(current, key),
            prior=getattr(prior, key),
            definition=definition,
            dimensions=["zone", "make", "model"],
        )
        for key, label, fmt, definition in [
            ("revenue", "Revenue", "currency", "SUM(automotive.fact_sales.total_sales)"),
            ("units", "Units sold", "integer", "SUM(automotive.fact_sales.order_qty)"),
            ("orders", "Orders", "integer", "COUNT(*) of automotive.fact_sales rows"),
        ]
    ]
    drivers: dict[str, list[DashboardContributor]] = {}
    for metric in metrics:
        for dimension in metric.dimensions:
            cur, pri = grouped.get(dimension), grouped.get(dimension, "pri")
            rows = []
            for key in cur.keys() | pri.keys():
                a, b = cur.get(key), pri.get(key)
                av = float(getattr(a, metric.id)) if a else 0.0
                bv = float(getattr(b, metric.id)) if b else 0.0
                bindings = (
                    {"make": str(key[0]), "model": str(key[1])}
                    if dimension == "model"
                    else {dimension: str(key[0])}
                )
                rows.append(
                    DashboardContributor(
                        label=" · ".join(map(str, key)),
                        current=av,
                        prior=bv,
                        change=av - bv,
                        filters=bindings,
                    )
                )
            drivers[f"{metric.id}:{dimension}"] = residual_rows(rows, metric.current, metric.prior)
    return {
        "metrics": metrics,
        "drivers": drivers,
        "sql": sql,
        "params": {k: v.isoformat() if isinstance(v, date) else v for k, v in params.items()},
        "tables": ["automotive.fact_sales", "automotive.dim_carline", "automotive.dim_region"],
    }


def insurance_source(response: ExecutiveIntelligenceResponse) -> dict[str, Any]:
    source = response._dashboard_source
    prior = {c.id: c for c in source.get("prior_cards", [])}
    cards = {c.id: c for c in source.get("cards", response.cards)}
    metrics = []
    for key in ("written_premium", "earned_premium", "claim_count", "loss_ratio"):
        card = cards.get(key)
        if card is None:
            continue
        before = prior.get(key)
        metrics.append(
            DashboardMetric(
                id=key,
                label=card.label,
                format=card.format,
                current=card.value,
                prior=before.value if before else None,
                definition=card.formula or key,
                dimensions=["components"] if key == "loss_ratio" else ["region", "lob"],
            )
        )
    return {
        "metrics": metrics,
        "drivers": {},
        "params": {},
        "prior_start": source.get("prior_start"),
        "prior_end": source.get("prior_end"),
        "ratio": {
            "current_claims": cards["claims_incurred"].value
            if cards.get("claims_incurred")
            else None,
            "prior_claims": prior["claims_incurred"].value
            if prior.get("claims_incurred")
            else None,
            "current_premium": cards["earned_premium"].value
            if cards.get("earned_premium")
            else None,
            "prior_premium": prior["earned_premium"].value if prior.get("earned_premium") else None,
        },
        "tables": [
            "insurance.fact_policy_monthly",
            "insurance.fact_claims",
            "insurance.dim_product",
            "insurance.dim_region",
        ],
    }


def finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def residual_rows(
    rows: list[DashboardContributor], current: float | None, prior: float | None, limit: int = 8
) -> list[DashboardContributor]:
    """Rank by absolute movement, retaining exits and a reconciled residual."""
    ranked = sorted(rows, key=lambda r: (-abs(r.change), r.label))[:limit]
    if current is None or prior is None:
        return ranked
    a, b = current - sum(r.current for r in ranked), prior - sum(r.prior for r in ranked)
    if (
        len(rows) > limit
        or abs(a) > max(1e-7, abs(current) * 1e-10)
        or abs(b) > max(1e-7, abs(prior) * 1e-10)
    ):
        ranked.append(
            DashboardContributor(
                label="Other contributors", current=a, prior=b, change=a - b, residual=True
            )
        )
    return ranked


def format_value(value: float | None, fmt: str) -> str:
    from app.services.kpi.windows import format_currency, format_number, format_percent

    if not finite(value):
        return "Unavailable"
    return {"currency": format_currency, "percent": format_percent}.get(fmt, format_number)(value)


def movement(metric: DashboardMetric) -> str:
    current, prior = metric.current, metric.prior
    if not finite(current):
        return f"{metric.label} is unavailable for this selection."
    if not finite(prior):
        return (
            f"{metric.label} is {format_value(current, metric.format)}; "
            "no comparable prior value is available."
        )
    assert current is not None and prior is not None
    delta = current - prior
    if math.isclose(delta, 0, abs_tol=1e-9):
        return f"{metric.label} is unchanged at {format_value(current, metric.format)}."
    direction = "increased" if delta > 0 else "decreased"
    if metric.format == "percent":
        change = f"{abs(delta) * 100:.2f} percentage points"
    elif abs(prior) < 1e-12:
        change = (
            f"{format_value(abs(delta), metric.format)} from a zero baseline; "
            "a percentage change is undefined"
        )
    else:
        change = f"{abs(delta / prior) * 100:.1f}%"
    return f"{metric.label} {direction} by {change} to {format_value(current, metric.format)}."


def ratio_contributors(values: dict[str, float | None]) -> list[DashboardContributor]:
    c1, c0 = values.get("current_claims"), values.get("prior_claims")
    e1, e0 = values.get("current_premium"), values.get("prior_premium")
    if not all(finite(v) for v in (c1, c0, e1, e0)) or not e1 or not e0:
        return []
    assert c1 is not None and c0 is not None and e1 is not None and e0 is not None
    # Symmetric two-factor decomposition: contributions sum exactly to C1/E1-C0/E0.
    claims_effect = (c1 - c0) * (1 / e0 + 1 / e1) / 2
    premium_effect = (c1 + c0) * (1 / e1 - 1 / e0) / 2
    return [
        DashboardContributor(
            label="Claims incurred effect", current=c1, prior=c0, change=claims_effect
        ),
        DashboardContributor(
            label="Earned premium effect", current=e1, prior=e0, change=premium_effect
        ),
    ]


@dataclass
class Snapshot:
    owner: str
    scope: str
    role: str
    source: dict[str, Any]
    context: DashboardContext
    expires: float
    metrics: list[DashboardMetric]
    caveats: list[str]
    explanations: dict[str, DashboardExplanation] = field(default_factory=dict)


class SnapshotStore:
    """Bounded process-local result handles; worker restart/eviction asks for refresh."""

    def __init__(self, max_entries: int = 256, ttl: int = 600) -> None:
        self.entries: dict[str, Snapshot] = {}
        self.max_entries, self.ttl = max_entries, ttl

    def put(self, snapshot: Snapshot) -> str:
        now = time.time()
        for key in [key for key, item in self.entries.items() if item.expires <= now]:
            del self.entries[key]
        if len(self.entries) >= self.max_entries:
            del self.entries[next(iter(self.entries))]
        key = secrets.token_urlsafe(24)
        self.entries[key] = snapshot
        return key


SNAPSHOTS = SnapshotStore()


def register_dashboard(
    response: CockpitResponse | ExecutiveIntelligenceResponse,
    *,
    settings: Settings,
    industry: Industry,
    user: User,
    scope: RegionScope,
    meter: QueryMeter,
    started: float,
    filters: dict[str, str],
    revision: str,
) -> DashboardAugmentation:
    from app.schemas.executive_cockpit import CockpitResponse

    if isinstance(response, CockpitResponse):
        p = response.period
        source = response._dashboard_source
        context = DashboardContext(
            result_id="",
            industry=industry.value,
            semantic_revision=revision,
            period_label=p.label,
            compare_label=p.prior_label,
            start=p.start,
            end=p.end,
            prior_start=p.prior_start,
            prior_end=p.prior_end,
            filters=filters,
            data_as_of=p.data_as_of,
            computed_at=response.computed_at,
        )
        caveats = [
            "Comparisons use the same selected span in the prior year; an "
            "incomplete period is not a full-period forecast."
        ]
    else:
        source = insurance_source(response)
        context = DashboardContext(
            result_id="",
            industry=industry.value,
            semantic_revision=revision,
            period_label=response.window_label,
            compare_label=response.compare_label,
            start=response.start_date,
            end=response.end_date,
            prior_start=source.get("prior_start"),
            prior_end=source.get("prior_end"),
            filters=filters,
            data_as_of=response.data_as_of,
            computed_at=response.computed_at,
        )
        caveats = list(response.data_quality.notices)
        caveats.append(
            "Policy premiums use accounting_month; claims use reported_date. "
            "Displayed periods follow the existing KPI definitions."
        )
    if context.start and context.end and context.prior_start and context.prior_end:
        current_days = (date.fromisoformat(context.end) - date.fromisoformat(context.start)).days
        prior_days = (
            date.fromisoformat(context.prior_end) - date.fromisoformat(context.prior_start)
        ).days
        if current_days != prior_days:
            caveats.append(
                "The existing comparison windows have different day counts. "
                "Interpret changes with care; the dashboard formulas have not "
                "been changed."
            )
    caveats.append(
        "Results describe contributions, not proven causes. Data-as-of is"
        " a watermark, not a transactional snapshot."
    )
    metrics = [m.model_copy(deep=True) for m in source.get("metrics", [])]
    for metric in metrics:
        if not finite(metric.current) or not finite(metric.prior) or not context.prior_start:
            metric.supported = False
            metric.unavailable_reason = (
                "A current and comparable prior value are required. Choose a "
                "supported comparison window."
            )
    context.result_id = hashlib.sha256(
        json.dumps(
            {
                "context": context.model_dump(),
                "scope": scope.cache_key(),
                "owner": str(user.id),
                "role": user.role.value,
                "values": [m.model_dump() for m in metrics],
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:24]
    expires = time.time() + SNAPSHOTS.ttl
    snapshot = Snapshot(
        str(user.id), scope.cache_key(), user.role.value, source, context, expires, metrics, caveats
    )
    key = SNAPSHOTS.put(snapshot)
    token = jwt.encode(
        {
            "aud": "ask-me-dashboard",
            "sub": str(user.id),
            "sid": key,
            "exp": int(expires),
            "type": "dashboard-result",
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    highlights = []
    # Curate domain-relevant metrics; do not compare absolute changes across unlike units.
    preferred = {"written_premium", "claim_count", "loss_ratio"}
    selected = [m for m in metrics if industry is Industry.AUTOMOTIVE or m.id in preferred]
    for metric in selected[:3]:
        a, b = metric.current, metric.prior
        delta = a - b if a is not None and b is not None else 0
        better = delta < 0 if metric.id == "loss_ratio" else delta > 0
        body = movement(metric)
        rows = source.get("drivers", {}).get(f"{metric.id}:{metric.dimensions[0]}", [])
        top = next((row for row in rows if not row.residual and abs(row.change) > 1e-9), None)
        if top is not None:
            body += (
                f" Largest displayed regional contribution: {top.label} "
                f"({format_value(top.change, metric.format)})."
            )
        highlights.append(
            DashboardHighlight(
                metric_id=metric.id,
                title=metric.label,
                body=body,
                tone="neutral"
                if not metric.supported or delta == 0
                else "positive"
                if better
                else "negative",
            )
        )
    return DashboardAugmentation(
        snapshot_token=token,
        context=context,
        metrics=metrics,
        highlights=highlights,
        caveats=caveats,
        performance=DashboardPerformance(
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            query_count=meter.count,
            warehouse_ms=round(meter.elapsed_ms, 2),
            cache_hit=meter.count == 0,
        ),
    )


def resolve_snapshot(
    token: str,
    *,
    settings: Settings,
    user: User,
    industry: Industry,
    scope: RegionScope,
) -> Snapshot:
    if not settings.ask_me_augmented_dashboard_enabled:
        raise AuthorizationError("Augmented dashboards are disabled.")
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience="ask-me-dashboard",
            options={"require": ["sub", "sid", "exp", "type"]},
        )
    except jwt.InvalidTokenError as exc:
        raise DashboardRefreshRequiredError(
            "This dashboard result expired. Refresh the board to continue."
        ) from exc
    item = SNAPSHOTS.entries.get(claims["sid"])
    if claims["sub"] != str(user.id) or claims["type"] != "dashboard-result":
        raise AuthorizationError("This dashboard result belongs to a different session.")
    if item is None or item.expires <= time.time():
        raise DashboardRefreshRequiredError(
            "This dashboard result is no longer available. Refresh the board."
        )
    if (
        item.owner != str(user.id)
        or item.scope != scope.cache_key()
        or item.role != user.role.value
        or item.context.industry != industry.value
    ):
        raise AuthorizationError("The dashboard access scope has changed. Refresh the board.")
    if item.context.semantic_revision != semantic_revision(settings, industry):
        raise DashboardRefreshRequiredError(
            "The semantic definitions changed. Refresh the board before asking again."
        )
    return item


def select_metric(snapshot: Snapshot, metric_id: str) -> DashboardMetric:
    found = next((m for m in snapshot.metrics if m.id == metric_id), None)
    if found is None:
        raise ValidationError("That metric is not part of this dashboard result.")
    return found.model_copy(deep=True)


async def explain_dashboard(
    snapshot: Snapshot,
    metric_id: str,
    dimension: str | None,
    connection: AsyncConnection,
    settings: Settings,
    scope: RegionScope,
) -> DashboardExplanation:
    started = time.perf_counter()
    metric = select_metric(snapshot, metric_id)
    dimension = dimension or (metric.dimensions[0] if metric.dimensions else "")
    if dimension not in metric.dimensions:
        raise ValidationError("This breakdown is not supported for the selected metric.")
    key = f"{metric.id}:{dimension}"
    cached = snapshot.explanations.get(key)
    if cached is not None:
        return cached.model_copy(update={"query_count": 0, "elapsed_ms": 0.0}, deep=True)
    evidence = DashboardExplanation(
        context=snapshot.context,
        metric=metric,
        dimension=dimension,
        narrative=movement(metric),
        caveats=list(snapshot.caveats),
        source_tables=snapshot.source.get("tables", []),
    )
    if not metric.supported:
        evidence.caveats.insert(0, metric.unavailable_reason or "Comparison unavailable.")
        return evidence
    if snapshot.context.industry == Industry.AUTOMOTIVE.value:
        evidence.contributors = snapshot.source.get("drivers", {}).get(key, [])
        evidence.sql = scope.apply_sql(snapshot.source.get("sql", ""), Industry.AUTOMOTIVE)
        evidence.sql_parameters = snapshot.source.get("params", {})
    elif metric.id == "loss_ratio":
        from app.services.kpi.insurance import INSURANCE_SUMMARY_SQL

        evidence.contributors = ratio_contributors(snapshot.source.get("ratio", {}))
        evidence.caveats.append(
            "Symmetric two-factor decomposition of claims incurred / earned "
            "premium. Effects are percentage-point contributions, not segment"
            " loss ratios."
        )
        evidence.sql = scope.apply_sql(INSURANCE_SUMMARY_SQL, Industry.INSURANCE)
        evidence.sql_parameters = {
            "start_date": snapshot.context.start,
            "end_date": snapshot.context.end,
            "lob": snapshot.context.filters.get("lob"),
            "region": snapshot.context.filters.get("region"),
        }
        evidence.prior_sql_parameters = {
            **evidence.sql_parameters,
            "start_date": snapshot.context.prior_start,
            "end_date": snapshot.context.prior_end,
        }
        if not evidence.contributors:
            evidence.caveats.insert(
                0,
                "Loss-ratio decomposition requires nonzero earned premium and "
                "claims totals in both periods.",
            )
    else:
        await insurance_drivers(evidence, snapshot, connection, settings, scope)
    a, b = evidence.metric.current, evidence.metric.prior
    evidence.reconciled = (
        bool(evidence.contributors)
        and a is not None
        and b is not None
        and math.isclose(
            sum(row.change for row in evidence.contributors),
            a - b,
            rel_tol=1e-8,
            abs_tol=1e-6,
        )
    )
    if evidence.contributors:
        top = max(
            (r for r in evidence.contributors if not r.residual),
            key=lambda r: abs(r.change),
            default=None,
        )
        if top is not None:
            amount = (
                f"{top.change * 100:+.2f} percentage points"
                if metric.format == "percent"
                else format_value(top.change, metric.format)
            )
            evidence.narrative += (
                f" {top.label} has the largest displayed absolute contribution ({amount}). "
                "This is an arithmetic contribution, not proof of causality."
            )
    evidence.suggested_questions = [
        f"Explain {metric.label} by {dim}" for dim in metric.dimensions if dim != dimension
    ] + [f"What is {metric.label}?"]
    evidence.elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    if not evidence.evidence_changed:
        snapshot.explanations[key] = evidence.model_copy(deep=True)
    return evidence


async def insurance_drivers(
    evidence: DashboardExplanation,
    snapshot: Snapshot,
    connection: AsyncConnection,
    settings: Settings,
    scope: RegionScope,
) -> None:
    """One fixed-identifier aggregate query, including whole-result window totals."""
    ctx, metric = snapshot.context, evidence.metric
    label = (
        "COALESCE(r.region_name, 'Unknown')"
        if evidence.dimension == "region"
        else "pr.line_of_business"
    )
    is_claim = metric.id == "claim_count"
    table, alias, day = (
        ("fact_claims", "c", "reported_date")
        if is_claim
        else ("fact_policy_monthly", "pm", "accounting_month")
    )
    value = "COUNT(DISTINCT c.claim_id)::float" if is_claim else f"SUM(pm.{metric.id})::float"
    params = {
        "cs": ctx.start,
        "ce": ctx.end,
        "ps": ctx.prior_start,
        "pe": ctx.prior_end,
        "lob": ctx.filters.get("lob"),
        "region": ctx.filters.get("region"),
    }
    sql = f"""
        WITH parts AS (
            SELECT {label} AS label,
                   CASE WHEN {alias}.{day} BETWEEN CAST(:cs AS date) AND CAST(:ce AS date)
                        THEN 'cur' ELSE 'pri' END AS period,
                   {value} AS value
            FROM insurance.{table} {alias}
            JOIN insurance.dim_product pr ON pr.product_id = {alias}.product_id
            LEFT JOIN insurance.dim_region r ON r.region_id = {alias}.region_id
            WHERE (({alias}.{day} BETWEEN CAST(:cs AS date) AND CAST(:ce AS date))
                OR ({alias}.{day} BETWEEN CAST(:ps AS date) AND CAST(:pe AS date)))
              AND (CAST(:lob AS text) IS NULL OR pr.line_of_business = CAST(:lob AS text))
              AND (CAST(:region AS text) IS NULL OR r.region_name = CAST(:region AS text))
            GROUP BY 1, 2
        ), compared AS (
            SELECT label, COALESCE(SUM(value) FILTER (WHERE period = 'cur'), 0) AS current,
                   COALESCE(SUM(value) FILTER (WHERE period = 'pri'), 0) AS prior
            FROM parts GROUP BY label
        )
        SELECT label, current, prior, SUM(current) OVER () AS total_current,
               SUM(prior) OVER () AS total_prior
        FROM compared ORDER BY ABS(current - prior) DESC, label LIMIT 9
    """  # noqa: S608 -- all identifiers selected from the server metric/dimension whitelist
    await connection.execute(
        text(f"SET LOCAL statement_timeout = {settings.nlq_sql_timeout_seconds * 1000}")
    )
    result = await connection.execute(text(sql), params)
    data = list(result.mappings().all())
    evidence.evidence_computed_at = datetime.now(UTC).isoformat()
    evidence.caveats.append(
        "Driver rows were queried on demand. Matching totals do not prove an unchanged "
        "underlying distribution; the query is not a historical database snapshot."
    )
    evidence.query_count = 2  # timeout configuration + one aggregate SELECT
    evidence.sql = scope.apply_sql(sql, Industry.INSURANCE)
    evidence.sql_parameters = dict(params)
    if not data:
        evidence.caveats.insert(
            0, "No driver rows were returned. Refresh the dashboard if the data changed."
        )
        return
    current, prior = float(data[0]["total_current"]), float(data[0]["total_prior"])
    evidence.evidence_changed = not (
        math.isclose(current, metric.current or 0, rel_tol=1e-8, abs_tol=1e-6)
        and math.isclose(prior, metric.prior or 0, rel_tol=1e-8, abs_tol=1e-6)
    )
    if evidence.evidence_changed:
        evidence.caveats.insert(
            0,
            "The warehouse totals changed since this board was loaded. This "
            "explanation uses newer totals; refresh the board to align it.",
        )
        evidence.metric = metric.model_copy(update={"current": current, "prior": prior})
        evidence.narrative = movement(evidence.metric)
    rows = [
        DashboardContributor(
            label=str(r["label"]),
            current=float(r["current"]),
            prior=float(r["prior"]),
            change=float(r["current"]) - float(r["prior"]),
            filters={evidence.dimension: str(r["label"])} if r["label"] != "Unknown" else {},
        )
        for r in data
    ]
    evidence.contributors = residual_rows(rows, current, prior)


def question_intent(
    question: str,
    snapshot: Snapshot,
    metric_id: str,
    dimension: str | None,
) -> tuple[str, str | None, str]:
    """Deterministic interpretation first; no rewriting of periods/access filters."""
    q = question.casefold()
    if re.search(r"\b(last month|last year|next year|q[1-4]|20\d\d|north|south|east|west)\b", q):
        return metric_id, dimension, "scope"
    aliases = {
        "revenue": r"revenue|sales value",
        "units": r"units|volume",
        "orders": r"orders",
        "written_premium": r"written premium|gross premium|\bpremium\b",
        "earned_premium": r"earned premium",
        "claim_count": r"claim count|number of claims|\bclaims\b",
        "loss_ratio": r"loss ratio|loss-rate",
    }
    # Specific matches override generic premium/claims wording.
    for key in (
        "revenue",
        "units",
        "orders",
        "written_premium",
        "claim_count",
        "earned_premium",
        "loss_ratio",
    ):
        if any(m.id == key for m in snapshot.metrics) and re.search(aliases[key], q):
            metric_id = key
    if dimension not in select_metric(snapshot, metric_id).dimensions:
        dimension = None
    for dim, pattern in {
        "zone": r"region|zone",
        "region": r"region|zone",
        "make": r"brand|make",
        "model": r"\bmodels?\b",
        "lob": r"line of business|\blob\b|\bproducts?\b",
        "components": r"numerator|denominator|components",
    }.items():
        if re.search(pattern, q):
            if dim in select_metric(snapshot, metric_id).dimensions:
                dimension = dim
            elif dim not in {"zone", "region"}:
                return metric_id, dimension, "unsupported"
    if re.search(r"\b(what is|define|definition|meaning)\b", q):
        return metric_id, dimension, "definition"
    if re.search(
        "explain|why|contribut|driver|change|grew|growth|fell|fall|declin"
        "|increas|decreas|compare|how|what|which|by |and ",
        q,
    ):
        return metric_id, dimension, "explain"
    return metric_id, dimension, "unknown"

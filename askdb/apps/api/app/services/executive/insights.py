"""Derive grounded AI insight cards from live KPIs — never invent numbers."""

from __future__ import annotations

from typing import Any

from app.schemas.executive import AiInsightCard
from app.schemas.kpi import KpiCard


def _card_map(cards: list[KpiCard]) -> dict[str, KpiCard]:
    return {card.id: card for card in cards}


def build_grounded_insights(
    *,
    industry: str,
    cards: list[KpiCard],
    compare_label: str,
    glossary_terms: list[str],
    dq_notices: list[str],
) -> list[AiInsightCard]:
    by_id = _card_map(cards)
    insights: list[AiInsightCard] = []
    grounded_base = ["Semantic Layer", "KPI Definition"]
    if glossary_terms:
        grounded_base.append("Business Glossary")
    if dq_notices:
        grounded_base.append("Data Quality Check")

    def add(
        *,
        insight_id: str,
        category: str,
        title: str,
        body: str,
        metric_ids: list[str],
    ) -> None:
        # Only emit if every referenced metric exists with a real value (or text KPI).
        for mid in metric_ids:
            card = by_id.get(mid)
            if card is None:
                return
            if card.format != "text" and card.value is None:
                return
        insights.append(
            AiInsightCard(
                id=insight_id,
                category=category,  # type: ignore[arg-type]
                title=title,
                body=body,
                grounded_on=list(grounded_base),
                metric_ids=metric_ids,
                explore_focus=metric_ids,
            )
        )

    if industry == "automotive":
        revenue = by_id.get("revenue")
        units = by_id.get("units_sold")
        aov = by_id.get("avg_order_value")
        top_model = by_id.get("top_model")

        if revenue and revenue.delta is not None:
            direction = "increased" if revenue.delta >= 0 else "declined"
            body = (
                f"Revenue {direction} {(abs(revenue.delta) * 100):.1f}% {compare_label} "
                f"to {revenue.formatted}."
            )
            if units and units.delta is not None:
                body += (
                    f" Units sold moved {(units.delta * 100):+.1f}% over the same window."
                )
            if top_model:
                body += f" Volume leadership is concentrated in {top_model.formatted}."
            category = "opportunity" if revenue.delta >= 0 else "risk"
            add(
                insight_id="auto-revenue-trend",
                category=category,
                title="Revenue movement",
                body=body,
                metric_ids=["revenue"]
                + (["units_sold"] if units and units.delta is not None else [])
                + (["top_model"] if top_model else []),
            )

        if aov and aov.delta is not None and units and units.delta is not None:
            if aov.delta > 0.02 and units.delta < 0:
                add(
                    insight_id="auto-mix-shift",
                    category="insight",
                    title="Price/mix vs volume",
                    body=(
                        f"Average order value rose {(aov.delta * 100):.1f}% {compare_label} "
                        f"while units moved {(units.delta * 100):+.1f}%. "
                        "Investigate mix and discounting before treating revenue as pure volume growth."
                    ),
                    metric_ids=["avg_order_value", "units_sold"],
                )

        if revenue and revenue.delta is not None and revenue.delta < -0.05:
            add(
                insight_id="auto-rec-focus-models",
                category="recommendation",
                title="Focus on leading models",
                body=(
                    "Revenue is down more than 5% versus the comparison window. "
                    "Ask which models and regions drove the decline before changing targets."
                ),
                metric_ids=["revenue"],
            )

    elif industry == "insurance":
        gwp = by_id.get("written_premium")
        loss = by_id.get("loss_ratio")
        renewal = by_id.get("renewal_rate")
        claims = by_id.get("claim_count")

        if gwp and gwp.delta is not None and loss and loss.value is not None:
            body = (
                f"Gross written premium is {gwp.formatted} "
                f"({(gwp.delta * 100):+.1f}% {compare_label}). "
                f"Loss ratio sits at {loss.formatted}."
            )
            if loss.delta is not None and loss.delta > 0.02:
                add(
                    insight_id="ins-underwriting-pressure",
                    category="risk",
                    title="Underwriting pressure",
                    body=(
                        body
                        + f" Loss ratio worsened by {(loss.delta * 100):.1f} percentage points "
                        f"{compare_label}, indicating pressure on underwriting profitability."
                    ),
                    metric_ids=["written_premium", "loss_ratio"],
                )
            elif gwp.delta > 0:
                add(
                    insight_id="ins-premium-growth",
                    category="opportunity",
                    title="Premium growth",
                    body=body + " Growth is present; monitor claims severity alongside acquisition.",
                    metric_ids=["written_premium", "loss_ratio"],
                )

        if renewal and renewal.value is not None:
            body = f"Renewal rate is {renewal.formatted}"
            if renewal.delta is not None:
                body += f" ({(renewal.delta * 100):+.1f}% {compare_label})."
            else:
                body += "."
            add(
                insight_id="ins-renewal",
                category="insight",
                title="Retention signal",
                body=body,
                metric_ids=["renewal_rate"],
            )

        if claims and claims.delta is not None and claims.delta > 0.05:
            add(
                insight_id="ins-claims-volume",
                category="risk",
                title="Claims volume rising",
                body=(
                    f"Claim count moved {(claims.delta * 100):+.1f}% {compare_label} "
                    f"to {claims.formatted}. Review frequency by region and product line."
                ),
                metric_ids=["claim_count"],
            )

        if loss and loss.value is not None and loss.value > 0.75:
            add(
                insight_id="ins-rec-loss",
                category="recommendation",
                title="Review high loss-ratio segments",
                body=(
                    f"Loss ratio at {loss.formatted} warrants a segment-level review. "
                    "Ask which LOBs and regions contribute most before changing rates."
                ),
                metric_ids=["loss_ratio"],
            )

    if dq_notices and insights:
        # Attach a recommendation only when DQ actually flagged something and we have
        # at least one grounded insight to hang the notice on.
        first_metrics = insights[0].metric_ids[:1]
        if first_metrics:
            insights.append(
                AiInsightCard(
                    id="dq-caution",
                    category="recommendation",
                    title="Treat insights with DQ context",
                    body=dq_notices[0],
                    grounded_on=list(grounded_base),
                    metric_ids=first_metrics,
                    explore_focus=first_metrics,
                )
            )

    return insights[:6]


def compute_business_health(
    *,
    cards: list[KpiCard],
    weights: dict[str, float],
    lower_better: set[str] | None = None,
) -> dict[str, Any]:
    lower_better = lower_better or {"loss_ratio"}
    by_id = _card_map(cards)
    components = []
    usable_weight = 0.0
    score_acc = 0.0

    for kpi_id, weight in weights.items():
        card = by_id.get(kpi_id)
        if card is None or card.value is None or card.format == "text":
            continue
        # Normalize contribution using delta when present, else mid score from value presence.
        if card.delta is not None:
            # Map delta (-20%..+20%) roughly into 0..100
            raw = 50 + max(-20.0, min(20.0, card.delta * 100)) * 2.5
        else:
            raw = 60.0
        if kpi_id in lower_better:
            # For loss ratio, positive delta is worse.
            if card.delta is not None:
                raw = 50 - max(-20.0, min(20.0, card.delta * 100)) * 2.5
            elif card.format == "percent" and card.value is not None:
                raw = max(0.0, min(100.0, (1.0 - card.value) * 100))
        raw = max(0.0, min(100.0, raw))
        contribution = raw * weight
        usable_weight += weight
        score_acc += contribution
        components.append(
            {
                "kpi_id": kpi_id,
                "label": card.label,
                "value": card.value,
                "formatted": card.formatted,
                "weight": weight,
                "contribution": round(contribution, 2),
                "direction": "lower_better" if kpi_id in lower_better else "higher_better",
            }
        )

    if usable_weight <= 0 or not components:
        return {
            "score": None,
            "label": "Unavailable",
            "components": [],
            "formula_note": "Business Health requires weighted KPIs with live values.",
            "available": False,
            "unavailable_reason": "Not enough live KPIs to compute a domain health score.",
        }

    # Renormalize if some weighted KPIs were missing.
    score = score_acc / usable_weight
    return {
        "score": round(score, 1),
        "label": "Strong" if score >= 70 else "Watch" if score >= 45 else "At risk",
        "components": components,
        "formula_note": (
            "Weighted blend of domain KPIs using configured healthScoreWeights. "
            "Missing KPIs are dropped and weights renormalized — not a black-box grade."
        ),
        "available": True,
        "unavailable_reason": None,
    }

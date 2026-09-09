"""Insurance KPI SQL — ported from legacy ``insurance_kpi_engine``."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.schemas.kpi import KpiCard, KpiSeriesPoint, NamedValue
from app.services.kpi.windows import format_currency, format_number, format_percent


async def fetch_insurance_summary(
    connection: AsyncConnection,
    *,
    start: date | None,
    end: date | None,
    lob: str | None,
    region: str | None,
) -> list[KpiCard]:
    sql = text(
        """
        SELECT
            :end_date AS data_through,
            p.written_premium,
            p.earned_premium,
            c.claims_incurred,
            c.claims_paid,
            c.claim_count,
            c.claims_incurred / NULLIF(p.earned_premium, 0) AS loss_ratio,
            c.claims_incurred / NULLIF(c.claim_count, 0) AS average_severity,
            c.approval_rate,
            c.avg_settlement_days,
            p.renewed::numeric / NULLIF(p.due_for_renewal, 0) AS renewal_rate
        FROM (
            SELECT
                COUNT(DISTINCT c.claim_id) AS claim_count,
                SUM(c.paid_amount) AS claims_paid,
                SUM(c.incurred_amount) AS claims_incurred,
                AVG(c.approved_flag::int) AS approval_rate,
                AVG(c.settlement_date - c.reported_date)
                    FILTER (WHERE c.settlement_date IS NOT NULL) AS avg_settlement_days
            FROM insurance.fact_claims c
            JOIN insurance.dim_product pr ON pr.product_id = c.product_id
            LEFT JOIN insurance.dim_region r ON r.region_id = c.region_id
            WHERE (:start_date IS NULL OR c.reported_date >= :start_date)
              AND (:end_date IS NULL OR c.reported_date <= :end_date)
              AND (:lob IS NULL OR pr.line_of_business = :lob)
              AND (:region IS NULL OR r.region_name = :region)
        ) c
        CROSS JOIN (
            SELECT
                SUM(pm.written_premium) AS written_premium,
                SUM(pm.earned_premium) AS earned_premium,
                COUNT(*) FILTER (WHERE pm.due_for_renewal_flag) AS due_for_renewal,
                COUNT(*) FILTER (WHERE pm.renewed_flag) AS renewed
            FROM insurance.fact_policy_monthly pm
            JOIN insurance.dim_product pr ON pr.product_id = pm.product_id
            LEFT JOIN insurance.dim_region r ON r.region_id = pm.region_id
            WHERE (:start_date IS NULL OR pm.accounting_month >= :start_date)
              AND (:end_date IS NULL OR pm.accounting_month <= :end_date)
              AND (:lob IS NULL OR pr.line_of_business = :lob)
              AND (:region IS NULL OR r.region_name = :region)
        ) p
        """
    )
    params = {
        "start_date": start,
        "end_date": end,
        "lob": lob,
        "region": region,
    }
    row = (await connection.execute(sql, params)).mappings().first()
    if row is None:
        return []

    def f(key: str) -> float | None:
        value = row.get(key)
        return float(value) if value is not None else None

    return [
        KpiCard(
            id="written_premium",
            label="Gross Written Premium",
            value=f("written_premium"),
            formatted=format_currency(f("written_premium")),
            format="currency",
            formula="SUM(written_premium)",
        ),
        KpiCard(
            id="earned_premium",
            label="Earned Premium",
            value=f("earned_premium"),
            formatted=format_currency(f("earned_premium")),
            format="currency",
            formula="SUM(earned_premium)",
        ),
        KpiCard(
            id="claims_incurred",
            label="Claims Incurred",
            value=f("claims_incurred"),
            formatted=format_currency(f("claims_incurred")),
            format="currency",
            formula="SUM(incurred_amount)",
        ),
        KpiCard(
            id="claims_paid",
            label="Claims Paid",
            value=f("claims_paid"),
            formatted=format_currency(f("claims_paid")),
            format="currency",
            formula="SUM(paid_amount)",
        ),
        KpiCard(
            id="claim_count",
            label="Claim Count",
            value=f("claim_count"),
            formatted=format_number(f("claim_count")),
            format="integer",
            formula="COUNT(DISTINCT claim_id)",
        ),
        KpiCard(
            id="loss_ratio",
            label="Loss Ratio",
            value=f("loss_ratio"),
            formatted=format_percent(f("loss_ratio")),
            format="percent",
            formula="incurred ÷ earned",
        ),
        KpiCard(
            id="average_severity",
            label="Average Severity",
            value=f("average_severity"),
            formatted=format_currency(f("average_severity")),
            format="currency",
            formula="incurred ÷ claim count",
        ),
        KpiCard(
            id="approval_rate",
            label="Approval Rate",
            value=f("approval_rate"),
            formatted=format_percent(f("approval_rate")),
            format="percent",
            formula="AVG(approved_flag)",
        ),
        KpiCard(
            id="avg_settlement_days",
            label="Avg Settlement Days",
            value=f("avg_settlement_days"),
            formatted=format_number(f("avg_settlement_days"), digits=1),
            format="number",
            formula="AVG(settlement - reported)",
        ),
        KpiCard(
            id="renewal_rate",
            label="Renewal Rate",
            value=f("renewal_rate"),
            formatted=format_percent(f("renewal_rate")),
            format="percent",
            formula="renewed ÷ due_for_renewal",
        ),
    ]


async def fetch_insurance_series(
    connection: AsyncConnection,
    *,
    start: date | None,
    end: date | None,
    lob: str | None,
    region: str | None,
) -> list[KpiSeriesPoint]:
    sql = text(
        """
        WITH premium AS (
            SELECT pm.accounting_month,
                   SUM(pm.earned_premium) AS earned_premium
            FROM insurance.fact_policy_monthly pm
            JOIN insurance.dim_product pr ON pr.product_id = pm.product_id
            LEFT JOIN insurance.dim_region r ON r.region_id = pm.region_id
            WHERE (:start_date IS NULL OR pm.accounting_month >= :start_date)
              AND (:end_date IS NULL OR pm.accounting_month <= :end_date)
              AND (:lob IS NULL OR pr.line_of_business = :lob)
              AND (:region IS NULL OR r.region_name = :region)
            GROUP BY 1
        ),
        claims AS (
            SELECT date_trunc('month', c.reported_date)::date AS accounting_month,
                   SUM(c.incurred_amount) AS claims_incurred,
                   COUNT(*) AS claim_count
            FROM insurance.fact_claims c
            JOIN insurance.dim_product pr ON pr.product_id = c.product_id
            LEFT JOIN insurance.dim_region r ON r.region_id = c.region_id
            WHERE (:start_date IS NULL OR c.reported_date >= :start_date)
              AND (:end_date IS NULL OR c.reported_date <= :end_date)
              AND (:lob IS NULL OR pr.line_of_business = :lob)
              AND (:region IS NULL OR r.region_name = :region)
            GROUP BY 1
        )
        SELECT COALESCE(p.accounting_month, c.accounting_month) AS period,
               COALESCE(p.earned_premium, 0) AS earned_premium,
               COALESCE(c.claims_incurred, 0) AS claims_incurred,
               COALESCE(c.claim_count, 0) AS claim_count,
               COALESCE(c.claims_incurred, 0)
                   / NULLIF(COALESCE(p.earned_premium, 0), 0) AS loss_ratio
        FROM premium p
        FULL OUTER JOIN claims c ON p.accounting_month = c.accounting_month
        ORDER BY 1
        LIMIT 60
        """
    )
    rows = (
        (
            await connection.execute(
                sql,
                {"start_date": start, "end_date": end, "lob": lob, "region": region},
            )
        )
        .mappings()
        .all()
    )
    points: list[KpiSeriesPoint] = []
    for row in rows:
        points.append(
            KpiSeriesPoint(
                period=row["period"].isoformat() if row["period"] else "",
                values={
                    "earned_premium": float(row["earned_premium"] or 0),
                    "claims_incurred": float(row["claims_incurred"] or 0),
                    "claim_count": float(row["claim_count"] or 0),
                    "loss_ratio": float(row["loss_ratio"])
                    if row["loss_ratio"] is not None
                    else None,
                },
            )
        )
    return points


async def fetch_insurance_breakdown(
    connection: AsyncConnection,
    *,
    by: str,
    start: date | None,
    end: date | None,
    lob: str | None,
    region: str | None,
) -> list[NamedValue]:
    if by == "lob":
        label_expr = "pr.line_of_business"
        metric = "SUM(c.incurred_amount)"
    elif by == "region":
        label_expr = "COALESCE(r.region_name, 'Unknown')"
        metric = "SUM(c.incurred_amount)"
    else:
        label_expr = "c.claim_status"
        metric = "COUNT(*)"
    # Identifiers are fixed literals from the branch above, not user input.
    sql = text(
        f"""
        SELECT {label_expr} AS label, {metric} AS value
        FROM insurance.fact_claims c
        JOIN insurance.dim_product pr ON pr.product_id = c.product_id
        LEFT JOIN insurance.dim_region r ON r.region_id = c.region_id
        WHERE (:start_date IS NULL OR c.reported_date >= :start_date)
          AND (:end_date IS NULL OR c.reported_date <= :end_date)
          AND (:lob IS NULL OR pr.line_of_business = :lob)
          AND (:region IS NULL OR r.region_name = :region)
        GROUP BY 1
        ORDER BY 2 DESC NULLS LAST
        LIMIT 20
        """
    )
    rows = (
        (
            await connection.execute(
                sql,
                {"start_date": start, "end_date": end, "lob": lob, "region": region},
            )
        )
        .mappings()
        .all()
    )
    return [
        NamedValue(
            name=str(row["label"]),
            value=float(row["value"] or 0),
            formatted=(
                format_currency(float(row["value"] or 0))
                if by != "status"
                else format_number(float(row["value"] or 0))
            ),
        )
        for row in rows
    ]


async def fetch_insurance_filter_options(connection: AsyncConnection) -> dict[str, Any]:
    lobs = (
        (
            await connection.execute(
                text(
                    "SELECT DISTINCT line_of_business FROM insurance.dim_product "
                    "ORDER BY 1 LIMIT 40"
                )
            )
        )
        .scalars()
        .all()
    )
    regions = (
        (
            await connection.execute(
                text("SELECT DISTINCT region_name FROM insurance.dim_region ORDER BY 1 LIMIT 40")
            )
        )
        .scalars()
        .all()
    )
    return {"lobs": list(lobs), "regions": list(regions)}

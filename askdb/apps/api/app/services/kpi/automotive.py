"""Automotive KPI SQL — SQL re-expression of legacy ``kpi_engine.compute_kpis``."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.schemas.kpi import KpiCard, KpiSeriesPoint, NamedValue
from app.services.kpi.windows import format_currency, format_number


async def fetch_automotive_summary(
    connection: AsyncConnection,
    *,
    start: date | None,
    end: date | None,
    make: str | None,
    region: str | None,
) -> list[KpiCard]:
    sql = text(
        """
        SELECT
            SUM(f.total_sales) AS revenue,
            SUM(f.order_qty) AS units_sold,
            COUNT(DISTINCT f.order_id) AS total_orders,
            COUNT(DISTINCT f.region_id) AS active_regions,
            SUM(f.total_sales) / NULLIF(COUNT(DISTINCT f.order_id), 0) AS avg_order_value,
            SUM(f.total_sales) / NULLIF(SUM(f.order_qty), 0) AS rev_per_unit
        FROM automotive.fact_sales f
        JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
        JOIN automotive.dim_region r ON r.region_id = f.region_id
        WHERE (CAST(:start_date AS date) IS NULL
               OR f.sales_date >= CAST(:start_date AS date))
          AND (CAST(:end_date AS date) IS NULL
               OR f.sales_date <= CAST(:end_date AS date))
          AND (CAST(:make AS text) IS NULL OR c.make = CAST(:make AS text))
          AND (CAST(:region AS text) IS NULL OR r.region_name = CAST(:region AS text))
        """
    )
    params = {
        "start_date": start,
        "end_date": end,
        "make": make,
        "region": region,
    }
    row = (await connection.execute(sql, params)).mappings().first()

    top_model = (
        (
            await connection.execute(
                text(
                    """
                SELECT c.model AS name, SUM(f.order_qty) AS units
                FROM automotive.fact_sales f
                JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
                JOIN automotive.dim_region r ON r.region_id = f.region_id
                WHERE (CAST(:start_date AS date) IS NULL
                       OR f.sales_date >= CAST(:start_date AS date))
                  AND (CAST(:end_date AS date) IS NULL
                       OR f.sales_date <= CAST(:end_date AS date))
                  AND (CAST(:make AS text) IS NULL OR c.make = CAST(:make AS text))
                  AND (CAST(:region AS text) IS NULL OR r.region_name = CAST(:region AS text))
                GROUP BY 1
                ORDER BY 2 DESC
                LIMIT 1
                """
                ),
                params,
            )
        )
        .mappings()
        .first()
    )

    top_make = (
        (
            await connection.execute(
                text(
                    """
                SELECT c.make AS name, SUM(f.order_qty) AS units
                FROM automotive.fact_sales f
                JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
                JOIN automotive.dim_region r ON r.region_id = f.region_id
                WHERE (CAST(:start_date AS date) IS NULL
                       OR f.sales_date >= CAST(:start_date AS date))
                  AND (CAST(:end_date AS date) IS NULL
                       OR f.sales_date <= CAST(:end_date AS date))
                  AND (CAST(:make AS text) IS NULL OR c.make = CAST(:make AS text))
                  AND (CAST(:region AS text) IS NULL OR r.region_name = CAST(:region AS text))
                GROUP BY 1
                ORDER BY 2 DESC
                LIMIT 1
                """
                ),
                params,
            )
        )
        .mappings()
        .first()
    )

    def f(key: str) -> float | None:
        value = row.get(key) if row is not None else None
        return float(value) if value is not None else None

    cards = [
        KpiCard(
            id="revenue",
            label="Total Revenue",
            value=f("revenue"),
            formatted=format_currency(f("revenue")),
            format="currency",
            formula="SUM(total_sales)",
        ),
        KpiCard(
            id="units_sold",
            label="Units Sold",
            value=f("units_sold"),
            formatted=format_number(f("units_sold")),
            format="integer",
            formula="SUM(order_qty)",
        ),
        KpiCard(
            id="total_orders",
            label="Orders",
            value=f("total_orders"),
            formatted=format_number(f("total_orders")),
            format="integer",
            formula="COUNT(DISTINCT order_id)",
        ),
        KpiCard(
            id="avg_order_value",
            label="Average Order Value",
            value=f("avg_order_value"),
            formatted=format_currency(f("avg_order_value")),
            format="currency",
            formula="revenue ÷ orders",
        ),
        KpiCard(
            id="rev_per_unit",
            label="Revenue per Unit",
            value=f("rev_per_unit"),
            formatted=format_currency(f("rev_per_unit")),
            format="currency",
            formula="revenue ÷ units",
        ),
        KpiCard(
            id="active_regions",
            label="Active Regions",
            value=f("active_regions"),
            formatted=format_number(f("active_regions")),
            format="integer",
            formula="COUNT(DISTINCT region_id)",
        ),
    ]
    if top_model:
        cards.append(
            KpiCard(
                id="top_model",
                label="Top Model",
                value=float(top_model["units"] or 0),
                formatted=str(top_model["name"]),
                format="text",
                formula="argmax SUM(order_qty) by model",
                meta={"units": float(top_model["units"] or 0)},
            )
        )
    if top_make:
        cards.append(
            KpiCard(
                id="top_make",
                label="Top Make",
                value=float(top_make["units"] or 0),
                formatted=str(top_make["name"]),
                format="text",
                formula="argmax SUM(order_qty) by make",
                meta={"units": float(top_make["units"] or 0)},
            )
        )
    return cards


async def fetch_automotive_series(
    connection: AsyncConnection,
    *,
    start: date | None,
    end: date | None,
    make: str | None,
    region: str | None,
) -> list[KpiSeriesPoint]:
    rows = (
        (
            await connection.execute(
                text(
                    """
                SELECT date_trunc('month', f.sales_date)::date AS period,
                       SUM(f.total_sales) AS revenue,
                       SUM(f.order_qty) AS units_sold
                FROM automotive.fact_sales f
                JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
                JOIN automotive.dim_region r ON r.region_id = f.region_id
                WHERE (CAST(:start_date AS date) IS NULL
                       OR f.sales_date >= CAST(:start_date AS date))
                  AND (CAST(:end_date AS date) IS NULL
                       OR f.sales_date <= CAST(:end_date AS date))
                  AND (CAST(:make AS text) IS NULL OR c.make = CAST(:make AS text))
                  AND (CAST(:region AS text) IS NULL OR r.region_name = CAST(:region AS text))
                GROUP BY 1
                ORDER BY 1
                LIMIT 60
                """
                ),
                {"start_date": start, "end_date": end, "make": make, "region": region},
            )
        )
        .mappings()
        .all()
    )
    return [
        KpiSeriesPoint(
            period=row["period"].isoformat(),
            values={
                "revenue": float(row["revenue"] or 0),
                "units_sold": float(row["units_sold"] or 0),
            },
        )
        for row in rows
    ]


async def fetch_automotive_breakdown(
    connection: AsyncConnection,
    *,
    by: str,
    start: date | None,
    end: date | None,
    make: str | None,
    region: str | None,
) -> list[NamedValue]:
    if by == "make":
        label = "c.make"
        metric = "SUM(f.order_qty)"
    elif by == "region":
        label = "r.region_name"
        metric = "SUM(f.total_sales)"
    else:
        label = "c.model"
        metric = "SUM(f.total_sales)"
    rows = (
        (
            await connection.execute(
                text(
                    f"""
                SELECT {label} AS label, {metric} AS value
                FROM automotive.fact_sales f
                JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
                JOIN automotive.dim_region r ON r.region_id = f.region_id
                WHERE (CAST(:start_date AS date) IS NULL
                       OR f.sales_date >= CAST(:start_date AS date))
                  AND (CAST(:end_date AS date) IS NULL
                       OR f.sales_date <= CAST(:end_date AS date))
                  AND (CAST(:make AS text) IS NULL OR c.make = CAST(:make AS text))
                  AND (CAST(:region AS text) IS NULL OR r.region_name = CAST(:region AS text))
                GROUP BY 1
                ORDER BY 2 DESC
                LIMIT 20
                """
                ),
                {"start_date": start, "end_date": end, "make": make, "region": region},
            )
        )
        .mappings()
        .all()
    )
    money = by != "make"
    return [
        NamedValue(
            name=str(row["label"]),
            value=float(row["value"] or 0),
            formatted=(
                format_currency(float(row["value"] or 0))
                if money
                else format_number(float(row["value"] or 0))
            ),
        )
        for row in rows
    ]


async def fetch_automotive_filter_options(connection: AsyncConnection) -> dict[str, list[str]]:
    makes = (
        (
            await connection.execute(
                text("SELECT DISTINCT make FROM automotive.dim_carline ORDER BY 1 LIMIT 40")
            )
        )
        .scalars()
        .all()
    )
    regions = (
        (
            await connection.execute(
                text("SELECT DISTINCT region_name FROM automotive.dim_region ORDER BY 1 LIMIT 40")
            )
        )
        .scalars()
        .all()
    )
    return {"makes": list(makes), "regions": list(regions)}

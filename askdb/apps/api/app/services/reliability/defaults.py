"""Built-in datasets and data-quality rules per industry.

Warehouse constraints (NOT NULL, CHECK, foreign keys) already stop many row-level defects
at load time, so the built-in rules concentrate on what constraints cannot express: business
reconciliations, cross-table consistency, forecast and plan accuracy, freshness and volume.
Every SQL statement here is static and read-only; user-created monitors never supply SQL.
"""

# ruff: noqa: S608, E501

from __future__ import annotations

from app.core.config import Industry
from app.services.reliability.model import DatasetSpec, RuleSpec

COCKPIT = "Executive KPI cockpit"
REVENUE = "Revenue dashboard"
PLAN = "Plan vs actual"
FORECAST = "Forecast panel"
GEO = "Geo intelligence"
DEALERS = "Dealer leaderboard"
CHAT = "AI Chat answers"
CLAIMS = "Claims dashboard"
PREMIUM = "Premium dashboard"
LOSS_RATIO = "Loss ratio KPIs"


def _daily_volume_sql(table: str, date_column: str) -> str:
    """Per-day (day, total, failed): a day fails when it has under 40% of its trailing average."""
    return f"""
        WITH anchor AS (SELECT MAX({date_column}) AS d FROM {table}),
        counts AS (
            SELECT t.{date_column} AS d, COUNT(*) AS n
            FROM {table} t CROSS JOIN anchor
            WHERE t.{date_column} > anchor.d - 120
            GROUP BY 1
        ),
        series AS (
            SELECT g::date AS d, COALESCE(counts.n, 0) AS n
            FROM anchor
            CROSS JOIN generate_series(anchor.d - 119, anchor.d, INTERVAL '1 day') AS g
            LEFT JOIN counts ON counts.d = g::date
        ),
        scored AS (
            SELECT d, n,
                AVG(n) OVER (ORDER BY d ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING) AS baseline
            FROM series
        )
        SELECT scored.d AS period, 1 AS total,
            CASE WHEN scored.n < 0.4 * scored.baseline THEN 1 ELSE 0 END AS failed
        FROM scored CROSS JOIN anchor
        WHERE scored.d > anchor.d - 90
    """


def _from_trend(trend_sql: str) -> str:
    return f"SELECT COUNT(*) AS total, COALESCE(SUM(failed), 0) AS failed FROM ({trend_sql}) x"


# --------------------------------------------------------------------------- automotive

_A_SALES = "automotive.fact_sales"

AUTOMOTIVE_DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        "fact_sales",
        _A_SALES,
        "Sales Transactions",
        "fact",
        "Sales",
        key_column="order_id",
        date_column="sales_date",
        cadence="daily",
        sla_hours=36,
        value_column="total_sales",
        assets=(COCKPIT, REVENUE, GEO, DEALERS, CHAT),
    ),
    DatasetSpec(
        "mv_sales_monthly",
        "automotive.mv_sales_monthly",
        "Monthly Sales Rollup",
        "aggregate",
        "Sales",
        date_column="month",
        cadence="monthly",
        sla_hours=24 * 3,
        assets=(COCKPIT, REVENUE),
        columns=("month", "make", "region", "revenue", "units"),
    ),
    DatasetSpec(
        "fact_forecast_monthly",
        "automotive.fact_forecast_monthly",
        "Demand Forecast",
        "plan",
        "Planning",
        key_column="forecast_id",
        date_column="sales_month",
        cadence="monthly",
        assets=(FORECAST, COCKPIT),
        columns=(
            "forecast_id",
            "sales_month",
            "carline_id",
            "region_id",
            "forecast_revenue",
            "forecast_units",
        ),
    ),
    DatasetSpec(
        "dim_targets",
        "automotive.dim_targets",
        "Sales Targets",
        "plan",
        "Planning",
        key_column="target_id",
        date_column="year_month",
        cadence="monthly",
        assets=(PLAN, COCKPIT),
    ),
    DatasetSpec(
        "dim_carline",
        "automotive.dim_carline",
        "Vehicle Master",
        "dimension",
        "Vehicle",
        key_column="carline_id",
        assets=(COCKPIT, CHAT),
    ),
    DatasetSpec(
        "dim_dealer",
        "automotive.dim_dealer",
        "Dealer Network",
        "dimension",
        "Dealer",
        key_column="dealer_id",
        assets=(DEALERS, GEO),
    ),
    DatasetSpec(
        "dim_region",
        "automotive.dim_region",
        "Geography",
        "dimension",
        "Geography",
        key_column="region_id",
        assets=(GEO,),
    ),
    DatasetSpec(
        "dim_salesman",
        "automotive.dim_salesman",
        "Salesforce",
        "dimension",
        "Sales",
        key_column="sales_person_id",
        assets=(DEALERS,),
    ),
    DatasetSpec(
        "dim_color",
        "automotive.dim_color",
        "Colour Catalogue",
        "dimension",
        "Vehicle",
        key_column="colour_id",
        assets=(CHAT,),
    ),
)

_A_FORECAST_MONTHS = """
    WITH anchor AS (SELECT date_trunc('month', MAX(sales_date))::date AS m FROM automotive.fact_sales),
    a AS (
        SELECT date_trunc('month', f.sales_date)::date AS m, c.make, SUM(f.order_qty)::numeric AS units
        FROM automotive.fact_sales f
        JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
        CROSS JOIN anchor
        WHERE f.sales_date >= anchor.m - INTERVAL '12 months' AND f.sales_date < anchor.m
        GROUP BY 1, 2
    ),
    fc AS (
        SELECT p.sales_month AS m, c.make, SUM(p.forecast_units)::numeric AS units
        FROM automotive.fact_forecast_monthly p
        JOIN automotive.dim_carline c ON c.carline_id = p.carline_id
        CROSS JOIN anchor
        WHERE p.sales_month >= anchor.m - INTERVAL '12 months' AND p.sales_month < anchor.m
        GROUP BY 1, 2
    ),
    scored AS (
        SELECT a.m, a.make, a.units AS actual, fc.units AS forecast,
            (fc.units IS NULL OR abs(fc.units - a.units) > 0.15 * a.units) AS missed
        FROM a LEFT JOIN fc ON fc.m = a.m AND fc.make = a.make
        WHERE a.units >= 50
    )
"""

_A_PRICE_BAND = """
    WITH anchor AS (SELECT MAX(sales_date) AS d FROM automotive.fact_sales),
    recent AS (
        SELECT f.order_id, f.carline_id, date_trunc('month', f.sales_date) AS m,
            f.price_per_unit, f.total_sales
        FROM automotive.fact_sales f CROSS JOIN anchor
        WHERE f.sales_date > anchor.d - 90
    ),
    medians AS (
        SELECT carline_id, m, percentile_cont(0.5) WITHIN GROUP (ORDER BY price_per_unit) AS median
        FROM recent GROUP BY 1, 2
    ),
    scored AS (
        SELECT r.order_id, r.total_sales,
            abs(r.price_per_unit - md.median) > 0.35 * md.median AS outlier
        FROM recent r JOIN medians md ON md.carline_id = r.carline_id AND md.m = r.m
    )
"""

_A_TARGET_GAPS = """
    WITH anchor AS (SELECT date_trunc('month', MAX(sales_date))::date AS m FROM automotive.fact_sales),
    sold AS (
        SELECT DISTINCT date_trunc('month', f.sales_date)::date AS m, c.make
        FROM automotive.fact_sales f
        JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
        CROSS JOIN anchor
        WHERE f.sales_date >= anchor.m - INTERVAL '24 months'
    ),
    gaps AS (
        SELECT s.m, s.make, t.target_id IS NULL AS missing
        FROM sold s
        LEFT JOIN automotive.dim_targets t ON t.year_month = s.m AND t.make = s.make
    )
"""

_A_DEALER_SILENT = """
    WITH anchor AS (SELECT MAX(sales_date) AS d FROM automotive.fact_sales),
    reporting AS (
        SELECT DISTINCT f.dealer_id FROM automotive.fact_sales f CROSS JOIN anchor
        WHERE f.sales_date > anchor.d - 30
    ),
    scored AS (
        SELECT d.dealer_id, d.dealer_name, d.city, r.dealer_id IS NULL AS silent
        FROM automotive.dim_dealer d LEFT JOIN reporting r ON r.dealer_id = d.dealer_id
        WHERE d.active
    )
"""

_A_FORECAST_HORIZON = """
    WITH anchor AS (SELECT MAX(sales_date) AS d FROM automotive.fact_sales),
    active AS (
        SELECT DISTINCT f.carline_id FROM automotive.fact_sales f CROSS JOIN anchor
        WHERE f.sales_date > anchor.d - 90
    ),
    planned AS (
        SELECT DISTINCT p.carline_id FROM automotive.fact_forecast_monthly p CROSS JOIN anchor
        WHERE p.sales_month = (date_trunc('month', anchor.d) + INTERVAL '1 month')::date
    ),
    scored AS (
        SELECT a.carline_id, c.carline_name, pl.carline_id IS NULL AS missing
        FROM active a
        JOIN automotive.dim_carline c ON c.carline_id = a.carline_id
        LEFT JOIN planned pl ON pl.carline_id = a.carline_id
    )
"""

_A_ROLLUP = """
    WITH anchor AS (SELECT date_trunc('month', MAX(sales_date))::date AS m FROM automotive.fact_sales),
    f AS (
        SELECT date_trunc('month', s.sales_date)::date AS m, SUM(s.total_sales) AS revenue
        FROM automotive.fact_sales s CROSS JOIN anchor
        WHERE s.sales_date >= anchor.m - INTERVAL '24 months'
        GROUP BY 1
    ),
    v AS (
        SELECT r.month AS m, SUM(r.revenue) AS revenue
        FROM automotive.mv_sales_monthly r CROSS JOIN anchor
        WHERE r.month >= anchor.m - INTERVAL '24 months'
        GROUP BY 1
    ),
    scored AS (
        SELECT COALESCE(f.m, v.m) AS m,
            abs(COALESCE(v.revenue, 0) - COALESCE(f.revenue, 0)) AS gap,
            (v.revenue IS NULL OR f.revenue IS NULL
                OR abs(v.revenue - f.revenue) > 0.0001 * GREATEST(abs(f.revenue), 1)) AS off
        FROM f FULL JOIN v ON v.m = f.m
    )
"""

_A_DAILY = _daily_volume_sql(_A_SALES, "sales_date")

AUTOMOTIVE_RULES: tuple[RuleSpec, ...] = (
    # Accuracy
    RuleSpec(
        id="auto.revenue_validation",
        name="Revenue Validation",
        dimension="accuracy",
        dataset="fact_sales",
        severity="critical",
        kind="row_check",
        description="Order revenue equals quantity x unit price and is never negative.",
        owner="Finance Data",
        tags=("revenue", "finance", "kpi"),
        impact="{failed} orders carry revenue that does not equal quantity x price; revenue KPIs would be misstated by {value}.",
        assets=(REVENUE, COCKPIT),
        unit="orders",
        condition="t.total_sales = t.order_qty * t.price_per_unit AND t.total_sales >= 0",
    ),
    RuleSpec(
        id="auto.rollup_reconciliation",
        name="Dashboard Revenue Reconciliation",
        dimension="accuracy",
        dataset="mv_sales_monthly",
        severity="high",
        kind="metric",
        description="Monthly rollup revenue matches the order ledger (0.01% tolerance, last 24 months).",
        owner="Data Engineering",
        tags=("revenue", "rollup", "kpi"),
        impact="{failed} months in the dashboard rollup differ from the order ledger by {value} in total; refresh the rollup before reviewing trends.",
        assets=(REVENUE, COCKPIT),
        unit="months",
        sql=_A_ROLLUP
        + "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE off) AS failed, SUM(gap) FILTER (WHERE off) AS value_at_risk FROM scored",
        sample_sql=_A_ROLLUP
        + "SELECT to_char(m, 'Mon YYYY') FROM scored WHERE off ORDER BY m DESC LIMIT 5",
    ),
    RuleSpec(
        id="auto.forecast_accuracy",
        name="Forecast Accuracy",
        dimension="accuracy",
        dataset="fact_forecast_monthly",
        severity="medium",
        kind="metric",
        threshold=85,
        description="Brand-month unit forecasts land within 15% of actual sales (last 12 complete months).",
        owner="Demand Planning",
        tags=("forecast", "planning"),
        impact="Forecasts missed actuals by more than 15% for {failed} of {total} brand-months; forecast-led decisions carry about {gap} points less accuracy than the {threshold}% target.",
        assets=(FORECAST, PLAN),
        unit="brand-months",
        sql=_A_FORECAST_MONTHS
        + "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE missed) AS failed FROM scored",
        sample_sql=_A_FORECAST_MONTHS
        + "SELECT make || ' ' || to_char(m, 'Mon YYYY') || ': forecast ' || COALESCE(round(forecast)::text, 'missing') || ' vs actual ' || round(actual)::text FROM scored WHERE missed ORDER BY abs(COALESCE(forecast, 0) - actual) DESC LIMIT 5",
        trend_sql=_A_FORECAST_MONTHS
        + "SELECT m AS period, COUNT(*) AS total, COUNT(*) FILTER (WHERE missed) AS failed FROM scored GROUP BY m",
    ),
    RuleSpec(
        id="auto.price_consistency",
        name="Price Consistency vs Model",
        dimension="accuracy",
        dataset="fact_sales",
        severity="medium",
        kind="metric",
        threshold=99.5,
        description="Orders are priced within 35% of the car line's median price that month (last 90 days).",
        owner="Sales Operations",
        tags=("pricing", "revenue"),
        impact="{failed} recent orders are priced far from their model's going rate ({value} of revenue); average selling price and discount views may be skewed.",
        assets=(REVENUE, COCKPIT),
        unit="orders",
        sql=_A_PRICE_BAND
        + "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE outlier) AS failed, SUM(total_sales) FILTER (WHERE outlier) AS value_at_risk FROM scored",
        sample_sql=_A_PRICE_BAND
        + "SELECT 'Order ' || order_id::text FROM scored WHERE outlier LIMIT 5",
    ),
    # Completeness
    RuleSpec(
        id="auto.order_completeness",
        name="Order Completeness",
        dimension="completeness",
        dataset="fact_sales",
        severity="critical",
        kind="row_check",
        description="Every order has its vehicle, colour, salesperson, dealer, region, date, quantity and price.",
        owner="Sales Operations",
        tags=("orders", "kpi"),
        impact="{failed} orders are missing a business key; they drop out of brand, dealer and geography breakdowns ({value}).",
        assets=(COCKPIT, GEO, DEALERS),
        unit="orders",
        condition=(
            "t.carline_id IS NOT NULL AND t.colour_id IS NOT NULL AND t.sales_person_id IS NOT NULL "
            "AND t.dealer_id IS NOT NULL AND t.region_id IS NOT NULL AND t.sales_date IS NOT NULL "
            "AND t.order_qty IS NOT NULL AND t.price_per_unit IS NOT NULL"
        ),
    ),
    RuleSpec(
        id="auto.daily_volume",
        name="Daily Sales Volume Completeness",
        dimension="completeness",
        dataset="fact_sales",
        severity="high",
        kind="metric",
        threshold=98,
        description="No trading day in the last 90 days has under 40% of its trailing 28-day average order volume.",
        owner="Data Engineering",
        tags=("volume", "anomaly"),
        impact="{failed} trading days look under-loaded; daily trends and month-to-date KPIs may be understated.",
        assets=(COCKPIT, REVENUE),
        unit="days",
        sql=_from_trend(_A_DAILY),
        sample_sql=f"SELECT to_char(period, 'DD Mon YYYY') FROM ({_A_DAILY}) x WHERE failed = 1 ORDER BY period DESC LIMIT 5",
        trend_sql=_A_DAILY,
    ),
    RuleSpec(
        id="auto.target_coverage",
        name="Target Coverage",
        dimension="completeness",
        dataset="dim_targets",
        severity="medium",
        kind="metric",
        description="Every brand with sales in a month (last 24 months) has a target for that month.",
        owner="Sales Planning",
        tags=("targets", "planning"),
        impact="Plan vs actual cannot be computed for {failed} brand-months, so achievement figures exclude them.",
        assets=(PLAN, COCKPIT),
        unit="brand-months",
        sql=_A_TARGET_GAPS
        + "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE missing) AS failed FROM gaps",
        sample_sql=_A_TARGET_GAPS
        + "SELECT make || ' ' || to_char(m, 'Mon YYYY') FROM gaps WHERE missing ORDER BY m DESC LIMIT 5",
    ),
    RuleSpec(
        id="auto.forecast_horizon",
        name="Forecast Horizon Coverage",
        dimension="completeness",
        dataset="fact_forecast_monthly",
        severity="medium",
        kind="metric",
        threshold=95,
        description="Every car line sold in the last 90 days has a forecast for next month.",
        owner="Demand Planning",
        tags=("forecast", "planning"),
        impact="{failed} selling car lines have no forecast for next month; the forecast panel understates next-month demand.",
        assets=(FORECAST,),
        unit="car lines",
        sql=_A_FORECAST_HORIZON
        + "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE missing) AS failed FROM scored",
        sample_sql=_A_FORECAST_HORIZON
        + "SELECT carline_name FROM scored WHERE missing ORDER BY carline_name LIMIT 5",
    ),
    RuleSpec(
        id="auto.dealer_reporting",
        name="Active Dealer Reporting",
        dimension="completeness",
        dataset="dim_dealer",
        severity="medium",
        kind="metric",
        threshold=98,
        description="Every active dealer reported at least one sale in the latest 30 days of data.",
        owner="Dealer Network Ops",
        tags=("dealers", "network"),
        impact="{failed} active dealers have not reported sales for 30 days; dealer rankings and geography views may undercount.",
        assets=(DEALERS, GEO),
        unit="dealers",
        sql=_A_DEALER_SILENT
        + "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE silent) AS failed FROM scored",
        sample_sql=_A_DEALER_SILENT
        + "SELECT dealer_name || ' (' || city || ')' FROM scored WHERE silent ORDER BY dealer_name LIMIT 5",
    ),
    # Consistency
    RuleSpec(
        id="auto.region_consistency",
        name="Region Consistency",
        dimension="consistency",
        dataset="fact_sales",
        severity="high",
        kind="metric",
        description="Each order's region matches the region of the dealer that booked it.",
        owner="Master Data",
        tags=("geography", "dealers"),
        impact="{failed} orders are attributed to a different region than their dealer ({value}); zone and state rankings may disagree with dealer views.",
        assets=(GEO, DEALERS),
        unit="orders",
        sql=(
            "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE f.region_id <> d.region_id) AS failed, "
            "SUM(f.total_sales) FILTER (WHERE f.region_id <> d.region_id) AS value_at_risk "
            "FROM automotive.fact_sales f JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id"
        ),
        sample_sql=(
            "SELECT 'Order ' || f.order_id::text FROM automotive.fact_sales f "
            "JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id "
            "WHERE f.region_id <> d.region_id LIMIT 5"
        ),
    ),
    RuleSpec(
        id="auto.dealer_city_consistency",
        name="Dealer City Consistency",
        dimension="consistency",
        dataset="dim_dealer",
        severity="medium",
        kind="metric",
        description="A dealer's city matches the city of its region record.",
        owner="Master Data",
        tags=("geography", "dealers"),
        impact="{failed} dealers sit in a different city than their region record; city drill-downs may misplace them.",
        assets=(GEO,),
        unit="dealers",
        sql=(
            "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE d.city <> r.city) AS failed "
            "FROM automotive.dim_dealer d JOIN automotive.dim_region r ON r.region_id = d.region_id"
        ),
        sample_sql=(
            "SELECT d.dealer_name || ': ' || d.city || ' vs ' || r.city FROM automotive.dim_dealer d "
            "JOIN automotive.dim_region r ON r.region_id = d.region_id WHERE d.city <> r.city LIMIT 5"
        ),
    ),
    RuleSpec(
        id="auto.vehicle_reference",
        name="Vehicle Reference Integrity",
        dimension="consistency",
        dataset="fact_sales",
        severity="critical",
        kind="reference",
        description="Every order points to a vehicle in the vehicle master.",
        owner="Master Data",
        tags=("vehicle", "integrity"),
        impact="{failed} orders reference unknown vehicles ({value}); brand and model totals would exclude them.",
        assets=(COCKPIT, CHAT),
        unit="orders",
        column="carline_id",
        ref_dataset="dim_carline",
        ref_column="carline_id",
    ),
    RuleSpec(
        id="auto.dealer_reference",
        name="Dealer Reference Integrity",
        dimension="consistency",
        dataset="fact_sales",
        severity="high",
        kind="reference",
        description="Every order points to a dealer in the dealer network.",
        owner="Dealer Network Ops",
        tags=("dealers", "integrity"),
        impact="{failed} orders reference unknown dealers ({value}); dealer leaderboards would exclude them.",
        assets=(DEALERS,),
        unit="orders",
        column="dealer_id",
        ref_dataset="dim_dealer",
        ref_column="dealer_id",
    ),
    RuleSpec(
        id="auto.brand_exclusivity",
        name="Dealer Brand Exclusivity",
        dimension="consistency",
        dataset="dim_dealer",
        severity="medium",
        kind="metric",
        description="Brand-exclusive outlets only sell their own brand (last 12 months of data).",
        owner="Dealer Network Ops",
        tags=("dealers", "brands"),
        impact="{failed} dealers sold more than one brand; brand-by-dealer rankings may double count outlets.",
        assets=(DEALERS,),
        unit="dealers",
        sql=(
            "WITH anchor AS (SELECT MAX(sales_date) AS d FROM automotive.fact_sales), "
            "brands AS (SELECT f.dealer_id, COUNT(DISTINCT c.make) AS makes FROM automotive.fact_sales f "
            "JOIN automotive.dim_carline c ON c.carline_id = f.carline_id CROSS JOIN anchor "
            "WHERE f.sales_date > anchor.d - 365 GROUP BY 1) "
            "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE makes > 1) AS failed FROM brands"
        ),
    ),
    RuleSpec(
        id="auto.target_brand_consistency",
        name="Target Brand Consistency",
        dimension="consistency",
        dataset="dim_targets",
        severity="low",
        kind="metric",
        description="Every brand with a target exists in the vehicle master.",
        owner="Sales Planning",
        tags=("targets", "brands"),
        impact="{failed} target rows name a brand that is not in the vehicle master; they can never be achieved.",
        assets=(PLAN,),
        unit="target rows",
        sql=(
            "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM automotive.dim_carline c "
            "WHERE c.make = t.make)) AS failed FROM automotive.dim_targets t"
        ),
    ),
    # Timeliness
    RuleSpec(
        id="auto.sales_freshness",
        name="Sales Data Freshness",
        dimension="timeliness",
        dataset="fact_sales",
        severity="critical",
        kind="freshness",
        description="The order ledger includes yesterday's trading (36-hour SLA).",
        owner="Data Engineering",
        tags=("freshness", "sla"),
        impact="Sales data is {lag} behind its {sla} SLA; every revenue and volume KPI shows stale figures.",
        assets=(COCKPIT, REVENUE, CHAT),
        unit="dataset",
        column="sales_date",
        max_age_hours=36,
    ),
    RuleSpec(
        id="auto.rollup_freshness",
        name="Dashboard Rollup Freshness",
        dimension="timeliness",
        dataset="mv_sales_monthly",
        severity="high",
        kind="metric",
        description="The monthly rollup includes the latest month in the order ledger.",
        owner="Data Engineering",
        tags=("freshness", "rollup"),
        impact="The dashboard rollup has not been refreshed for the latest month; trend charts stop short of current sales.",
        assets=(COCKPIT, REVENUE),
        unit="rollup",
        sql=(
            "SELECT 1 AS total, CASE WHEN COALESCE((SELECT MAX(month) FROM automotive.mv_sales_monthly), DATE '1900-01-01') "
            "< (SELECT date_trunc('month', MAX(sales_date))::date FROM automotive.fact_sales) THEN 1 ELSE 0 END AS failed"
        ),
    ),
    # Validity
    RuleSpec(
        id="auto.price_validation",
        name="Price Validation",
        dimension="validity",
        dataset="fact_sales",
        severity="high",
        kind="range",
        description="Unit prices sit in the Indian passenger-vehicle band (INR 1 lakh to 3 crore).",
        owner="Sales Operations",
        tags=("pricing", "revenue"),
        impact="{failed} orders carry implausible unit prices ({value}); revenue and average selling price would be distorted.",
        assets=(REVENUE, COCKPIT),
        unit="orders",
        column="price_per_unit",
        min_value=100_000,
        max_value=30_000_000,
    ),
    RuleSpec(
        id="auto.vehicle_master_validation",
        name="Vehicle Master Validation",
        dimension="validity",
        dataset="dim_carline",
        severity="high",
        kind="row_check",
        description="Car lines have a brand, model and valid powertrain (EVs carry no engine capacity; others 0.6-3.6 L).",
        owner="Master Data",
        tags=("vehicle", "master-data"),
        impact="{failed} car lines have an invalid powertrain record; EV share and engine-type mix may be misreported.",
        assets=(COCKPIT, CHAT),
        unit="car lines",
        condition=(
            "btrim(t.make) <> '' AND btrim(t.model) <> '' "
            "AND t.engine_type IN ('Petrol', 'Diesel', 'Hybrid', 'Electric') "
            "AND ((t.engine_type = 'Electric' AND t.engine_capacity IS NULL) "
            "OR (t.engine_type <> 'Electric' AND t.engine_capacity BETWEEN 0.6 AND 3.6))"
        ),
    ),
    RuleSpec(
        id="auto.sales_date_validity",
        name="Sales Date Validity",
        dimension="validity",
        dataset="fact_sales",
        severity="high",
        kind="row_check",
        description="Sales dates fall between January 2015 and today (no future-dated orders).",
        owner="Sales Operations",
        tags=("dates",),
        impact="{failed} orders are dated outside the trading window ({value}); period comparisons would shift.",
        assets=(COCKPIT, REVENUE),
        unit="orders",
        condition="t.sales_date BETWEEN DATE '2015-01-01' AND CURRENT_DATE",
    ),
    RuleSpec(
        id="auto.order_quantity_range",
        name="Order Quantity Range",
        dimension="validity",
        dataset="fact_sales",
        severity="medium",
        kind="range",
        description="Order quantities are between 1 and 50 units (fleet orders included).",
        owner="Sales Operations",
        tags=("orders",),
        impact="{failed} orders have implausible quantities ({value}); unit volumes may be inflated.",
        assets=(COCKPIT,),
        unit="orders",
        column="order_qty",
        min_value=1,
        max_value=50,
    ),
    RuleSpec(
        id="auto.salesperson_email",
        name="Salesperson Email Format",
        dimension="validity",
        dataset="dim_salesman",
        severity="low",
        kind="pattern",
        description="Salesperson emails are well formed.",
        owner="Dealer Network Ops",
        tags=("salesforce", "contact"),
        impact="{failed} salespeople have malformed emails; performance alerts cannot reach them.",
        assets=(DEALERS,),
        unit="salespeople",
        column="email",
        pattern=r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$",
    ),
    RuleSpec(
        id="auto.dealer_grade_validity",
        name="Dealer Grade Validity",
        dimension="validity",
        dataset="dim_dealer",
        severity="low",
        kind="allowed_values",
        description="Dealer grade is A, B or C.",
        owner="Dealer Network Ops",
        tags=("dealers",),
        impact="{failed} dealers have an unknown grade; grade-level comparisons exclude them.",
        assets=(DEALERS,),
        unit="dealers",
        column="dealer_grade",
        allowed=("A", "B", "C"),
    ),
    # Uniqueness
    RuleSpec(
        id="auto.duplicate_orders",
        name="Duplicate Order Detection",
        dimension="uniqueness",
        dataset="fact_sales",
        severity="high",
        kind="unique",
        threshold=99.5,
        description="No two orders in the last 365 days share dealer, salesperson, vehicle, colour, date, quantity and price.",
        owner="Sales Operations",
        tags=("orders", "duplicates"),
        impact="{failed} orders look like repeat bookings; units and revenue may be double counted.",
        assets=(COCKPIT, REVENUE),
        unit="orders",
        columns=(
            "dealer_id",
            "sales_person_id",
            "carline_id",
            "colour_id",
            "sales_date",
            "order_qty",
            "price_per_unit",
        ),
        scope="t.sales_date > (SELECT MAX(sales_date) FROM automotive.fact_sales) - 365",
    ),
    RuleSpec(
        id="auto.dealer_uniqueness",
        name="Dealer Uniqueness",
        dimension="uniqueness",
        dataset="dim_dealer",
        severity="high",
        kind="unique",
        description="Each dealer code identifies exactly one dealer.",
        owner="Dealer Network Ops",
        tags=("dealers", "master-data"),
        impact="{failed} dealer records share a code; dealer totals would be split or merged.",
        assets=(DEALERS,),
        unit="dealers",
        columns=("dealer_code",),
    ),
    RuleSpec(
        id="auto.salesperson_uniqueness",
        name="Salesperson Uniqueness",
        dimension="uniqueness",
        dataset="dim_salesman",
        severity="medium",
        kind="unique",
        description="Each salesperson email belongs to one person.",
        owner="Dealer Network Ops",
        tags=("salesforce", "master-data"),
        impact="{failed} salesperson records share an email; individual performance may be merged.",
        assets=(DEALERS,),
        unit="salespeople",
        columns=("email",),
    ),
    RuleSpec(
        id="auto.vehicle_master_uniqueness",
        name="Vehicle Master Uniqueness",
        dimension="uniqueness",
        dataset="dim_carline",
        severity="medium",
        kind="unique",
        description="Each brand, model and powertrain combination appears once in the vehicle master.",
        owner="Master Data",
        tags=("vehicle", "master-data"),
        impact="{failed} car lines duplicate another; model-level volumes would be split.",
        assets=(COCKPIT, CHAT),
        unit="car lines",
        columns=("make", "model", "engine_type", "engine_capacity"),
    ),
)


# --------------------------------------------------------------------------- insurance

_I_CLAIMS = "insurance.fact_claims"

INSURANCE_DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        "fact_claims",
        _I_CLAIMS,
        "Claims",
        "fact",
        "Claims",
        key_column="claim_id",
        date_column="reported_date",
        cadence="daily",
        sla_hours=48,
        value_column="incurred_amount",
        assets=(CLAIMS, LOSS_RATIO, CHAT),
    ),
    DatasetSpec(
        "fact_policy_monthly",
        "insurance.fact_policy_monthly",
        "Policy Premium (Monthly)",
        "fact",
        "Underwriting",
        key_column="policy_month_id",
        date_column="accounting_month",
        cadence="monthly",
        sla_hours=24 * 45,
        value_column="written_premium",
        assets=(PREMIUM, LOSS_RATIO),
    ),
    DatasetSpec(
        "mv_claims_monthly",
        "insurance.mv_claims_monthly",
        "Monthly Claims Rollup",
        "aggregate",
        "Claims",
        date_column="month",
        cadence="monthly",
        assets=(CLAIMS, LOSS_RATIO),
        columns=("month", "lob", "region", "claim_count", "claims_incurred", "claims_paid"),
    ),
    DatasetSpec(
        "fact_forecast_monthly",
        "insurance.fact_forecast_monthly",
        "Premium & Claims Forecast",
        "plan",
        "Planning",
        key_column="forecast_id",
        date_column="accounting_month",
        cadence="monthly",
        assets=(FORECAST,),
        columns=(
            "forecast_id",
            "accounting_month",
            "product_id",
            "region_id",
            "forecast_written_premium",
            "forecast_earned_premium",
            "forecast_claims_incurred",
        ),
    ),
    DatasetSpec(
        "dim_policy",
        "insurance.dim_policy",
        "Policy Register",
        "dimension",
        "Underwriting",
        key_column="policy_id",
        value_column="sum_insured",
        assets=(PREMIUM, CHAT),
    ),
    DatasetSpec(
        "dim_product",
        "insurance.dim_product",
        "Product Catalogue",
        "dimension",
        "Product",
        key_column="product_id",
        assets=(PREMIUM, CLAIMS),
    ),
    DatasetSpec(
        "dim_agent",
        "insurance.dim_agent",
        "Agent Network",
        "dimension",
        "Distribution",
        key_column="agent_id",
        assets=(PREMIUM,),
    ),
    DatasetSpec(
        "dim_region",
        "insurance.dim_region",
        "Geography",
        "dimension",
        "Geography",
        key_column="region_id",
        assets=(CLAIMS, PREMIUM),
    ),
)

_I_ROLLUP = """
    WITH anchor AS (SELECT date_trunc('month', MAX(reported_date))::date AS m FROM insurance.fact_claims),
    f AS (
        SELECT date_trunc('month', c.reported_date)::date AS m, SUM(c.incurred_amount) AS incurred
        FROM insurance.fact_claims c CROSS JOIN anchor
        WHERE c.reported_date >= anchor.m - INTERVAL '24 months'
        GROUP BY 1
    ),
    v AS (
        SELECT r.month AS m, SUM(r.claims_incurred) AS incurred
        FROM insurance.mv_claims_monthly r CROSS JOIN anchor
        WHERE r.month >= anchor.m - INTERVAL '24 months'
        GROUP BY 1
    ),
    scored AS (
        SELECT COALESCE(f.m, v.m) AS m,
            abs(COALESCE(v.incurred, 0) - COALESCE(f.incurred, 0)) AS gap,
            (v.incurred IS NULL OR f.incurred IS NULL
                OR abs(v.incurred - f.incurred) > 0.0001 * GREATEST(abs(f.incurred), 1)) AS off
        FROM f FULL JOIN v ON v.m = f.m
    )
"""

_I_FORECAST = """
    WITH anchor AS (SELECT MAX(accounting_month) AS m FROM insurance.fact_policy_monthly),
    a AS (
        SELECT p.accounting_month AS m, pr.line_of_business AS lob, SUM(p.written_premium) AS actual
        FROM insurance.fact_policy_monthly p
        JOIN insurance.dim_product pr ON pr.product_id = p.product_id
        CROSS JOIN anchor
        WHERE p.accounting_month >= anchor.m - INTERVAL '12 months' AND p.accounting_month < anchor.m
        GROUP BY 1, 2
    ),
    fc AS (
        SELECT f.accounting_month AS m, pr.line_of_business AS lob, SUM(f.forecast_written_premium) AS forecast
        FROM insurance.fact_forecast_monthly f
        JOIN insurance.dim_product pr ON pr.product_id = f.product_id
        CROSS JOIN anchor
        WHERE f.accounting_month >= anchor.m - INTERVAL '12 months' AND f.accounting_month < anchor.m
        GROUP BY 1, 2
    ),
    scored AS (
        SELECT a.m, a.lob, a.actual, fc.forecast,
            (fc.forecast IS NULL OR abs(fc.forecast - a.actual) > 0.15 * a.actual) AS missed
        FROM a LEFT JOIN fc ON fc.m = a.m AND fc.lob = a.lob
        WHERE a.actual > 0
    )
"""

_I_DAILY = _daily_volume_sql(_I_CLAIMS, "reported_date")

INSURANCE_RULES: tuple[RuleSpec, ...] = (
    # Accuracy
    RuleSpec(
        id="ins.incurred_validation",
        name="Incurred Amount Validation",
        dimension="accuracy",
        dataset="fact_claims",
        severity="critical",
        kind="row_check",
        description="Incurred amount equals paid plus reserve.",
        owner="Claims Finance",
        tags=("claims", "finance", "kpi"),
        impact="{failed} claims carry an incurred amount that does not reconcile ({value}); loss ratios would be misstated.",
        assets=(LOSS_RATIO, CLAIMS),
        unit="claims",
        condition="t.incurred_amount = t.paid_amount + t.reserve_amount",
    ),
    RuleSpec(
        id="ins.paid_within_approved",
        name="Paid Within Approved Amount",
        dimension="accuracy",
        dataset="fact_claims",
        severity="high",
        kind="row_check",
        threshold=99.5,
        description="Paid amount does not exceed the larger of approved and reported amount by more than 5%.",
        owner="Claims Operations",
        tags=("claims", "leakage"),
        impact="{failed} claims were paid above their approved amount ({value}); claims leakage KPIs may be understated.",
        assets=(CLAIMS, LOSS_RATIO),
        unit="claims",
        condition="t.paid_amount <= GREATEST(t.approved_amount, t.reported_amount) * 1.05",
    ),
    RuleSpec(
        id="ins.rollup_reconciliation",
        name="Claims Rollup Reconciliation",
        dimension="accuracy",
        dataset="mv_claims_monthly",
        severity="high",
        kind="metric",
        description="Monthly claims rollup matches the claims ledger (0.01% tolerance, last 24 months).",
        owner="Data Engineering",
        tags=("claims", "rollup"),
        impact="{failed} months in the claims rollup differ from the ledger by {value}; refresh the rollup before reviewing trends.",
        assets=(CLAIMS, LOSS_RATIO),
        unit="months",
        sql=_I_ROLLUP
        + "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE off) AS failed, SUM(gap) FILTER (WHERE off) AS value_at_risk FROM scored",
        sample_sql=_I_ROLLUP
        + "SELECT to_char(m, 'Mon YYYY') FROM scored WHERE off ORDER BY m DESC LIMIT 5",
    ),
    RuleSpec(
        id="ins.forecast_accuracy",
        name="Premium Forecast Accuracy",
        dimension="accuracy",
        dataset="fact_forecast_monthly",
        severity="medium",
        kind="metric",
        threshold=85,
        description="Line-of-business written premium forecasts land within 15% of actuals (last 12 months).",
        owner="Actuarial",
        tags=("forecast", "premium"),
        impact="Premium forecasts missed by more than 15% for {failed} of {total} line-months; plan-based decisions carry about {gap} points less accuracy than target.",
        assets=(FORECAST, PREMIUM),
        unit="line-months",
        sql=_I_FORECAST
        + "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE missed) AS failed FROM scored",
        sample_sql=_I_FORECAST
        + "SELECT lob || ' ' || to_char(m, 'Mon YYYY') FROM scored WHERE missed ORDER BY m DESC LIMIT 5",
        trend_sql=_I_FORECAST
        + "SELECT m AS period, COUNT(*) AS total, COUNT(*) FILTER (WHERE missed) AS failed FROM scored GROUP BY m",
    ),
    # Completeness
    RuleSpec(
        id="ins.claim_completeness",
        name="Claim Completeness",
        dimension="completeness",
        dataset="fact_claims",
        severity="high",
        kind="row_check",
        threshold=99,
        description="Claims carry a region, loss date and claim type.",
        owner="Claims Operations",
        tags=("claims", "kpi"),
        impact="{failed} claims are missing region, loss date or type ({value}); regional and peril breakdowns undercount.",
        assets=(CLAIMS,),
        unit="claims",
        condition="t.region_id IS NOT NULL AND t.loss_date IS NOT NULL AND NULLIF(btrim(t.claim_type), '') IS NOT NULL",
    ),
    RuleSpec(
        id="ins.policy_completeness",
        name="Policy Completeness",
        dimension="completeness",
        dataset="dim_policy",
        severity="medium",
        kind="row_check",
        threshold=98,
        description="Policies carry an agent, region, customer and sum insured.",
        owner="Underwriting Data",
        tags=("policy", "master-data"),
        impact="{failed} policies lack agent, region, customer or sum insured; distribution and exposure views undercount.",
        assets=(PREMIUM,),
        unit="policies",
        condition="t.agent_id IS NOT NULL AND t.region_id IS NOT NULL AND NULLIF(btrim(t.customer_key), '') IS NOT NULL AND t.sum_insured IS NOT NULL",
    ),
    RuleSpec(
        id="ins.daily_claims_volume",
        name="Daily Claims Volume Completeness",
        dimension="completeness",
        dataset="fact_claims",
        severity="high",
        kind="metric",
        threshold=98,
        description="No day in the last 90 days has under 40% of its trailing 28-day average claims volume.",
        owner="Data Engineering",
        tags=("volume", "anomaly"),
        impact="{failed} days look under-loaded; claims frequency and month-to-date KPIs may be understated.",
        assets=(CLAIMS,),
        unit="days",
        sql=_from_trend(_I_DAILY),
        trend_sql=_I_DAILY,
    ),
    # Consistency
    RuleSpec(
        id="ins.claim_date_sequence",
        name="Claim Date Sequence",
        dimension="consistency",
        dataset="fact_claims",
        severity="high",
        kind="row_check",
        threshold=99.5,
        description="Loss precedes reporting, and approval and settlement follow it.",
        owner="Claims Operations",
        tags=("claims", "dates"),
        impact="{failed} claims have impossible date sequences; reporting lag and cycle-time KPIs would be distorted.",
        assets=(CLAIMS,),
        unit="claims",
        condition=(
            "(t.loss_date IS NULL OR t.loss_date <= t.reported_date) "
            "AND (t.approved_date IS NULL OR t.approved_date >= t.reported_date) "
            "AND (t.settlement_date IS NULL OR t.settlement_date >= t.reported_date)"
        ),
    ),
    RuleSpec(
        id="ins.claim_policy_period",
        name="Claim Within Policy Period",
        dimension="consistency",
        dataset="fact_claims",
        severity="high",
        kind="metric",
        threshold=99.5,
        description="The loss date falls within the policy's inception and expiry dates.",
        owner="Claims Operations",
        tags=("claims", "policy", "fraud"),
        impact="{failed} claims fall outside their policy period ({value}); coverage validation and fraud screening need review.",
        assets=(CLAIMS, LOSS_RATIO),
        unit="claims",
        sql=(
            "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE c.loss_date NOT BETWEEN p.inception_date AND p.expiry_date) AS failed, "
            "SUM(c.incurred_amount) FILTER (WHERE c.loss_date NOT BETWEEN p.inception_date AND p.expiry_date) AS value_at_risk "
            "FROM insurance.fact_claims c JOIN insurance.dim_policy p ON p.policy_id = c.policy_id WHERE c.loss_date IS NOT NULL"
        ),
    ),
    RuleSpec(
        id="ins.claim_product_consistency",
        name="Claim Product Consistency",
        dimension="consistency",
        dataset="fact_claims",
        severity="medium",
        kind="metric",
        description="A claim's product matches its policy's product.",
        owner="Master Data",
        tags=("claims", "product"),
        impact="{failed} claims are booked to a different product than their policy; product loss ratios may be misallocated.",
        assets=(LOSS_RATIO,),
        unit="claims",
        sql=(
            "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE c.product_id <> p.product_id) AS failed "
            "FROM insurance.fact_claims c JOIN insurance.dim_policy p ON p.policy_id = c.policy_id"
        ),
    ),
    RuleSpec(
        id="ins.policy_reference",
        name="Policy Reference Integrity",
        dimension="consistency",
        dataset="fact_claims",
        severity="critical",
        kind="reference",
        description="Every claim points to a policy in the policy register.",
        owner="Master Data",
        tags=("claims", "integrity"),
        impact="{failed} claims reference unknown policies ({value}); they drop out of policy-level analysis.",
        assets=(CLAIMS,),
        unit="claims",
        column="policy_id",
        ref_dataset="dim_policy",
        ref_column="policy_id",
    ),
    # Timeliness
    RuleSpec(
        id="ins.claims_freshness",
        name="Claims Data Freshness",
        dimension="timeliness",
        dataset="fact_claims",
        severity="critical",
        kind="freshness",
        description="The claims ledger includes the last two days of reported claims (48-hour SLA).",
        owner="Data Engineering",
        tags=("freshness", "sla"),
        impact="Claims data is {lag} behind its {sla} SLA; claims KPIs show stale figures.",
        assets=(CLAIMS, LOSS_RATIO),
        unit="dataset",
        column="reported_date",
        max_age_hours=48,
    ),
    RuleSpec(
        id="ins.premium_freshness",
        name="Premium Data Freshness",
        dimension="timeliness",
        dataset="fact_policy_monthly",
        severity="high",
        kind="freshness",
        description="The latest closed accounting month is loaded within 45 days.",
        owner="Data Engineering",
        tags=("freshness", "sla"),
        impact="Premium data is {lag} behind its {sla} SLA; loss ratios use an out-of-date premium base.",
        assets=(PREMIUM, LOSS_RATIO),
        unit="dataset",
        column="accounting_month",
        max_age_hours=24 * 45,
    ),
    # Validity
    RuleSpec(
        id="ins.claim_amount_validity",
        name="Claim Amount Validity",
        dimension="validity",
        dataset="fact_claims",
        severity="medium",
        kind="row_check",
        description="Claim amounts are non-negative and below INR 100 crore.",
        owner="Claims Finance",
        tags=("claims", "amounts"),
        impact="{failed} claims carry implausible amounts ({value}); severity and loss ratio KPIs may be distorted.",
        assets=(CLAIMS, LOSS_RATIO),
        unit="claims",
        condition=(
            "t.reported_amount >= 0 AND t.approved_amount >= 0 AND t.paid_amount >= 0 "
            "AND t.reserve_amount >= 0 AND t.reported_amount < 1000000000"
        ),
    ),
    RuleSpec(
        id="ins.policy_term_validity",
        name="Policy Term Validity",
        dimension="validity",
        dataset="dim_policy",
        severity="medium",
        kind="row_check",
        description="Policy terms run forwards and last at most five years.",
        owner="Underwriting Data",
        tags=("policy", "dates"),
        impact="{failed} policies have implausible terms; exposure and renewal views may be wrong.",
        assets=(PREMIUM,),
        unit="policies",
        condition="t.expiry_date >= t.inception_date AND t.expiry_date <= t.inception_date + INTERVAL '5 years'",
    ),
    RuleSpec(
        id="ins.sum_insured_range",
        name="Sum Insured Range",
        dimension="validity",
        dataset="dim_policy",
        severity="low",
        kind="range",
        description="Sum insured is positive and below INR 500 crore.",
        owner="Underwriting Data",
        tags=("policy", "exposure"),
        impact="{failed} policies carry an implausible sum insured; exposure KPIs may be distorted.",
        assets=(PREMIUM,),
        unit="policies",
        column="sum_insured",
        min_value=1,
        max_value=5_000_000_000,
    ),
    # Uniqueness
    RuleSpec(
        id="ins.claim_uniqueness",
        name="Claim Uniqueness",
        dimension="uniqueness",
        dataset="fact_claims",
        severity="critical",
        kind="unique",
        description="Each claim number appears once.",
        owner="Claims Operations",
        tags=("claims", "duplicates"),
        impact="{failed} claims duplicate another claim number; claim counts and incurred would be double counted.",
        assets=(CLAIMS, LOSS_RATIO),
        unit="claims",
        columns=("claim_number",),
    ),
    RuleSpec(
        id="ins.policy_uniqueness",
        name="Policy Uniqueness",
        dimension="uniqueness",
        dataset="dim_policy",
        severity="high",
        kind="unique",
        description="Each policy number appears once.",
        owner="Underwriting Data",
        tags=("policy", "duplicates"),
        impact="{failed} policies duplicate another policy number; policy counts would be inflated.",
        assets=(PREMIUM,),
        unit="policies",
        columns=("policy_number",),
    ),
    RuleSpec(
        id="ins.policy_month_uniqueness",
        name="Policy Month Uniqueness",
        dimension="uniqueness",
        dataset="fact_policy_monthly",
        severity="medium",
        kind="unique",
        description="One premium row per policy per accounting month.",
        owner="Underwriting Data",
        tags=("premium", "duplicates"),
        impact="{failed} policy-months are duplicated; written premium would be overstated.",
        assets=(PREMIUM, LOSS_RATIO),
        unit="policy-months",
        columns=("policy_id", "accounting_month"),
    ),
)


def default_datasets(industry: Industry) -> tuple[DatasetSpec, ...]:
    return AUTOMOTIVE_DATASETS if industry is Industry.AUTOMOTIVE else INSURANCE_DATASETS


def default_rules(industry: Industry) -> tuple[RuleSpec, ...]:
    return AUTOMOTIVE_RULES if industry is Industry.AUTOMOTIVE else INSURANCE_RULES

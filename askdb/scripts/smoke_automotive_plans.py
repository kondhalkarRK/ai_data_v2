"""EXPLAIN smoke checks for the automotive star schema.

Usage
-----
    python scripts/smoke_automotive_plans.py

Acceptance (for the seeded 1M fact table):

- keyset / bounded queries must not sequentially scan the whole fact table
- no ``OFFSET`` pagination
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import psycopg

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.config import get_settings  # noqa: E402

QUERIES: dict[str, str] = {
    "keyset_preview": """
        SELECT order_id, sales_date, total_sales, dealer_id
        FROM automotive.fact_sales
        WHERE (sales_date, order_id) < (DATE '2025-06-01', 500000)
        ORDER BY sales_date DESC, order_id DESC
        LIMIT 50
    """,
    "make_monthly": """
        SELECT date_trunc('month', f.sales_date)::date AS month,
               c.make,
               SUM(f.order_qty) AS units,
               SUM(f.total_sales) AS revenue
        FROM automotive.fact_sales f
        JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
        WHERE f.sales_date >= DATE '2024-01-01'
          AND f.sales_date < DATE '2025-01-01'
        GROUP BY 1, 2
        ORDER BY 1, 2
    """,
    "dealer_in_region": """
        SELECT d.dealer_id, d.dealer_name,
               SUM(f.order_qty) AS units,
               SUM(f.total_sales) AS revenue
        FROM automotive.fact_sales f
        JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id
        WHERE f.region_id = 1
          AND f.sales_date >= DATE '2024-01-01'
          AND f.sales_date < DATE '2025-01-01'
        GROUP BY d.dealer_id, d.dealer_name
        ORDER BY revenue DESC
        LIMIT 25
    """,
    "ev_share_by_year": """
        SELECT EXTRACT(YEAR FROM f.sales_date)::int AS year,
               SUM(f.order_qty) FILTER (
                   WHERE c.engine_type = 'Electric'
               )::float / NULLIF(SUM(f.order_qty), 0) AS ev_share
        FROM automotive.fact_sales f
        JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
        GROUP BY 1
        ORDER BY 1
    """,
    "target_vs_actual": """
        WITH actual AS (
            SELECT date_trunc('month', f.sales_date)::date AS year_month,
                   c.make,
                   SUM(f.order_qty) AS units,
                   SUM(f.total_sales) AS revenue
            FROM automotive.fact_sales f
            JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
            WHERE f.sales_date >= DATE '2024-01-01'
              AND f.sales_date < DATE '2025-01-01'
            GROUP BY 1, 2
        )
        SELECT t.year_month, t.make,
               t.target_units, COALESCE(a.units, 0) AS actual_units,
               t.target_revenue, COALESCE(a.revenue, 0) AS actual_revenue
        FROM automotive.dim_targets t
        LEFT JOIN actual a
          ON a.year_month = t.year_month AND a.make = t.make
        WHERE t.year_month >= DATE '2024-01-01'
          AND t.year_month < DATE '2025-01-01'
        ORDER BY t.year_month, t.make
    """,
}

# Queries expected to stay off a full sequential scan of fact_sales.
BOUNDED_QUERIES = {"keyset_preview", "make_monthly", "dealer_in_region"}


def _to_psycopg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _walk_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    found = [node]
    for child in node.get("Plans") or []:
        found.extend(_walk_nodes(child))
    return found


def _uses_offset(sql_text: str) -> bool:
    return " offset " in f" {sql_text.lower()} "


def _fact_seq_scan(plan: dict[str, Any]) -> bool:
    for node in _walk_nodes(plan):
        if node.get("Node Type") == "Seq Scan" and node.get("Relation Name") == "fact_sales":
            return True
    return False


def run(*, database_url: str | None, analyze: bool) -> int:
    settings = get_settings()
    url = _to_psycopg_url(database_url or settings.automotive_database_url)
    option = "ANALYZE, BUFFERS, FORMAT JSON" if analyze else "FORMAT JSON"
    failures: list[str] = []

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM automotive.fact_sales")
        fact_count = cur.fetchone()[0]
        print(f"fact_sales rows: {fact_count:,}")

        for name, query in QUERIES.items():
            if _uses_offset(query):
                failures.append(f"{name}: query text contains OFFSET")
            explain = f"EXPLAIN ({option}) {query}"
            cur.execute(explain)
            payload = cur.fetchone()[0]
            plan = payload[0]["Plan"]
            seq = _fact_seq_scan(plan)
            node = plan.get("Node Type")
            print(f"[{name}] root={node} fact_seq_scan={seq}")
            if name in BOUNDED_QUERIES and seq and fact_count >= 100_000:
                failures.append(f"{name}: sequential scan over fact_sales with {fact_count:,} rows")

    if failures:
        print("SMOKE FAILED:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("SMOKE PASSED")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override AUTOMOTIVE_DATABASE_URL (reader is enough for EXPLAIN)",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run EXPLAIN ANALYZE (slower; executes the queries)",
    )
    parser.add_argument(
        "--dump-json",
        action="store_true",
        help="Print raw EXPLAIN JSON for debugging",
    )
    args = parser.parse_args()
    if args.dump_json:
        settings = get_settings()
        url = _to_psycopg_url(args.database_url or settings.automotive_database_url)
        with psycopg.connect(url) as conn, conn.cursor() as cur:
            for name, query in QUERIES.items():
                cur.execute(f"EXPLAIN (FORMAT JSON) {query}")
                print(name, json.dumps(cur.fetchone()[0], indent=2))
        return
    raise SystemExit(run(database_url=args.database_url, analyze=args.analyze))


if __name__ == "__main__":
    main()

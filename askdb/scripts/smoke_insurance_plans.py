"""EXPLAIN smoke checks for the insurance star schema."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import psycopg

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.config import get_settings  # noqa: E402

QUERIES: dict[str, str] = {
    "keyset_claims": """
        SELECT claim_id, reported_date, incurred_amount
        FROM insurance.fact_claims
        WHERE (reported_date, claim_id) < (DATE '2025-01-01', 500000)
        ORDER BY reported_date DESC, claim_id DESC
        LIMIT 50
    """,
    "product_monthly_claims": """
        SELECT date_trunc('month', reported_date)::date AS month,
               product_id,
               COUNT(*) AS claims,
               SUM(incurred_amount) AS incurred
        FROM insurance.fact_claims
        WHERE reported_date >= DATE '2024-01-01'
          AND reported_date < DATE '2025-01-01'
        GROUP BY 1, 2
        ORDER BY 1, 2
    """,
    "region_claims": """
        SELECT region_id, COUNT(*) AS claims, SUM(paid_amount) AS paid
        FROM insurance.fact_claims
        WHERE region_id = 1
          AND reported_date >= DATE '2024-01-01'
          AND reported_date < DATE '2025-01-01'
        GROUP BY region_id
    """,
    "premium_by_month": """
        SELECT accounting_month, SUM(earned_premium) AS earned
        FROM insurance.fact_policy_monthly
        WHERE accounting_month >= DATE '2024-01-01'
          AND accounting_month < DATE '2025-01-01'
        GROUP BY accounting_month
        ORDER BY accounting_month
    """,
}

BOUNDED = {"keyset_claims", "product_monthly_claims", "region_claims", "premium_by_month"}


def _to_psycopg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _walk(node: dict[str, Any]) -> list[dict[str, Any]]:
    found = [node]
    for child in node.get("Plans") or []:
        found.extend(_walk(child))
    return found


def _fact_seq(plan: dict[str, Any], relation: str) -> bool:
    return any(
        node.get("Node Type") == "Seq Scan" and node.get("Relation Name") == relation
        for node in _walk(plan)
    )


def run(*, database_url: str | None) -> int:
    settings = get_settings()
    url = _to_psycopg_url(database_url or settings.insurance_database_url)
    failures: list[str] = []
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM insurance.fact_claims")
        claim_count = cur.fetchone()[0]
        print(f"fact_claims rows: {claim_count:,}")
        for name, query in QUERIES.items():
            if " offset " in f" {query.lower()} ":
                failures.append(f"{name}: contains OFFSET")
            cur.execute(f"EXPLAIN (FORMAT JSON) {query}")
            plan = cur.fetchone()[0][0]["Plan"]
            relation = (
                "fact_policy_monthly" if "fact_policy_monthly" in query else "fact_claims"
            )
            seq = _fact_seq(plan, relation)
            print(f"[{name}] root={plan.get('Node Type')} {relation}_seq={seq}")
            if name in BOUNDED and seq and claim_count >= 100_000:
                failures.append(f"{name}: sequential scan over {relation}")
    if failures:
        print("SMOKE FAILED:")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("SMOKE PASSED")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    raise SystemExit(run(database_url=args.database_url))


if __name__ == "__main__":
    main()

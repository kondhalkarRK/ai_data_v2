"""Seed ``askdb_insurance`` with dimensions and ~1M claims.

Usage
-----
    python scripts/migrate.py insurance upgrade head
    python scripts/seed_insurance.py --claims 1000000 --replace
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import psycopg
from psycopg import sql

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.analytics.insurance_seed import (  # noqa: E402
    DEFAULT_CLAIM_ROWS,
    DEFAULT_MONTHLY_POLICY_SAMPLE,
    DEFAULT_POLICY_ROWS,
    InsuranceDimensions,
    build_dimensions,
    iter_claims,
    iter_operating_expense,
    iter_policy_monthly,
)
from app.core.config import get_settings  # noqa: E402


def _to_psycopg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _truncate(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            TRUNCATE TABLE
                insurance.fact_claims,
                insurance.fact_policy_monthly,
                insurance.fact_operating_expense_monthly,
                insurance.dim_policy,
                insurance.dim_agent,
                insurance.dim_product,
                insurance.dim_region
            RESTART IDENTITY CASCADE
            """
        )
    conn.commit()


def _insert_dims(conn: psycopg.Connection, dims: InsuranceDimensions) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO insurance.dim_product (
                product_id, product_code, product_name, line_of_business,
                product_family, coverage_type, active_flag
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    p.product_id,
                    p.product_code,
                    p.product_name,
                    p.line_of_business,
                    p.product_family,
                    p.coverage_type,
                    p.active_flag,
                )
                for p in dims.products
            ],
        )
        cur.executemany(
            """
            INSERT INTO insurance.dim_region (
                region_id, region_code, region_name, state_name, country_name
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (r.region_id, r.region_code, r.region_name, r.state_name, r.country_name)
                for r in dims.regions
            ],
        )
        cur.executemany(
            """
            INSERT INTO insurance.dim_agent (
                agent_id, agent_code, agent_name, channel_name, branch_name, active_flag
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    a.agent_id,
                    a.agent_code,
                    a.agent_name,
                    a.channel_name,
                    a.branch_name,
                    a.active_flag,
                )
                for a in dims.agents
            ],
        )
        cur.executemany(
            """
            INSERT INTO insurance.dim_policy (
                policy_id, policy_number, product_id, agent_id, region_id, customer_key,
                inception_date, expiry_date, policy_status, coverage_tier, sum_insured,
                cancelled_flag
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    p.policy_id,
                    p.policy_number,
                    p.product_id,
                    p.agent_id,
                    p.region_id,
                    p.customer_key,
                    p.inception_date,
                    p.expiry_date,
                    p.policy_status,
                    p.coverage_tier,
                    p.sum_insured,
                    p.cancelled_flag,
                )
                for p in dims.policies
            ],
        )
    conn.commit()


def _copy_rows(
    conn: psycopg.Connection,
    table: str,
    columns: tuple[str, ...],
    rows: object,
    *,
    label: str,
    log_every: int,
) -> int:
    started = time.perf_counter()
    schema_name, table_name = table.split(".", 1)
    copy_sql = sql.SQL("COPY {}.{} ({columns}) FROM STDIN").format(
        sql.Identifier(schema_name),
        sql.Identifier(table_name),
        columns=sql.SQL(", ").join(map(sql.Identifier, columns)),
    )
    count = 0
    with conn.cursor() as cur, cur.copy(copy_sql) as copy:
        for row in rows:  # type: ignore[attr-defined]
            copy.write_row(row)
            count += 1
            if count % log_every == 0:
                elapsed = time.perf_counter() - started
                rate = count / elapsed if elapsed else 0.0
                print(f"  {label}: {count:,} ({rate:,.0f} rows/s)", flush=True)
    conn.commit()
    print(
        f"{label} COPY finished: {count:,} rows in {time.perf_counter() - started:.1f}s",
        flush=True,
    )
    return count


def seed(
    *,
    claims: int,
    policies: int,
    monthly_sample: int,
    replace: bool,
    database_url: str | None,
) -> None:
    settings = get_settings()
    url = _to_psycopg_url(database_url or settings.insurance_migrate_database_url)
    dims = build_dimensions(policy_count=policies)
    print(
        f"Seeding insurance: {len(dims.products)} products, {len(dims.regions)} regions, "
        f"{len(dims.agents)} agents, {len(dims.policies):,} policies, {claims:,} claims",
        flush=True,
    )

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('insurance.fact_claims') IS NOT NULL")
            exists = cur.fetchone()
            if not exists or not exists[0]:
                raise SystemExit(
                    "insurance.fact_claims is missing. "
                    "Run: python scripts/migrate.py insurance upgrade head"
                )
            if not replace:
                cur.execute("SELECT COUNT(*) FROM insurance.fact_claims")
                count = cur.fetchone()
                if count and count[0] > 0:
                    raise SystemExit(
                        f"fact_claims already has {count[0]:,} rows. Pass --replace."
                    )

        if replace:
            print("Truncating existing insurance tables…", flush=True)
            _truncate(conn)

        _insert_dims(conn, dims)
        _copy_rows(
            conn,
            "insurance.fact_claims",
            (
                "claim_id",
                "claim_number",
                "policy_id",
                "product_id",
                "region_id",
                "loss_date",
                "reported_date",
                "approved_date",
                "settlement_date",
                "claim_status",
                "claim_type",
                "reported_amount",
                "approved_amount",
                "paid_amount",
                "reserve_amount",
                "approved_flag",
                "repudiated_flag",
                "fraud_suspected_flag",
                "catastrophe_code",
                "created_at",
            ),
            iter_claims(dims, row_count=claims),
            label="fact_claims",
            log_every=max(claims // 10, 50_000),
        )
        _copy_rows(
            conn,
            "insurance.fact_policy_monthly",
            (
                "policy_month_id",
                "policy_id",
                "product_id",
                "agent_id",
                "region_id",
                "accounting_month",
                "written_premium",
                "earned_premium",
                "exposure_units",
                "active_policy_flag",
                "due_for_renewal_flag",
                "renewed_flag",
            ),
            iter_policy_monthly(dims, sample_policies=monthly_sample),
            label="fact_policy_monthly",
            log_every=100_000,
        )
        _copy_rows(
            conn,
            "insurance.fact_operating_expense_monthly",
            (
                "expense_month_id",
                "accounting_month",
                "product_id",
                "region_id",
                "acquisition_expense",
                "operating_expense",
            ),
            iter_operating_expense(dims),
            label="fact_operating_expense_monthly",
            log_every=50_000,
        )

        with conn.cursor() as cur:
            cur.execute("ANALYZE insurance.fact_claims")
            cur.execute("SELECT COUNT(*) FROM insurance.fact_claims")
            claim_count = cur.fetchone()[0]
            # Sync identity sequences after explicit IDs.
            for table, column in (
                ("dim_product", "product_id"),
                ("dim_agent", "agent_id"),
                ("dim_region", "region_id"),
                ("dim_policy", "policy_id"),
                ("fact_policy_monthly", "policy_month_id"),
                ("fact_operating_expense_monthly", "expense_month_id"),
            ):
                cur.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('insurance.{table}', '{column}'),
                        COALESCE((SELECT MAX({column}) FROM insurance.{table}), 1)
                    )
                    """
                )
        conn.commit()

        # Forecast baseline for Scenario Mode (requires migration 0002).
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM insurance.fact_forecast_monthly")
                cur.execute(
                    """
                    INSERT INTO insurance.fact_forecast_monthly (
                        accounting_month, product_id, region_id,
                        forecast_written_premium, forecast_earned_premium, forecast_claims_incurred
                    )
                    SELECT
                        date_trunc('month', pm.accounting_month)::date,
                        pm.product_id,
                        pm.region_id,
                        SUM(pm.written_premium) * 1.05,
                        SUM(pm.earned_premium) * 1.05,
                        COALESCE((
                            SELECT SUM(c.incurred_amount) * 1.05
                            FROM insurance.fact_claims c
                            WHERE c.product_id = pm.product_id
                              AND c.region_id IS NOT DISTINCT FROM pm.region_id
                              AND date_trunc('month', c.reported_date)
                                  = date_trunc('month', pm.accounting_month)
                        ), 0)
                    FROM insurance.fact_policy_monthly pm
                    GROUP BY 1, 2, 3
                    """
                )
                cur.execute("REFRESH MATERIALIZED VIEW insurance.mv_claims_monthly")
            conn.commit()
            print("Forecast rows + MV refresh applied.", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(
                f"Forecast/MV seed skipped ({exc}). Apply migrate insurance upgrade head.",
                flush=True,
            )

    print(f"Done. fact_claims rows = {claim_count:,}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", type=int, default=DEFAULT_CLAIM_ROWS)
    parser.add_argument("--policies", type=int, default=DEFAULT_POLICY_ROWS)
    parser.add_argument("--monthly-sample", type=int, default=DEFAULT_MONTHLY_POLICY_SAMPLE)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    if args.claims < 1 or args.policies < 1:
        raise SystemExit("--claims and --policies must be >= 1")
    seed(
        claims=args.claims,
        policies=args.policies,
        monthly_sample=args.monthly_sample,
        replace=args.replace,
        database_url=args.database_url,
    )


if __name__ == "__main__":
    main()

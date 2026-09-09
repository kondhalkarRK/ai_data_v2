"""Seed ``askdb_automotive`` with dimensions and a deterministic fact table.

Usage
-----
    # from askdb/
    python scripts/seed_automotive.py
    python scripts/seed_automotive.py --rows 1000000
    python scripts/seed_automotive.py --rows 10000 --replace

Requires the automotive Alembic migration to have been applied with the owner role::

    python scripts/migrate.py automotive upgrade head
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

from app.analytics.automotive_seed import (  # noqa: E402
    DEFAULT_FACT_ROWS,
    DimensionBundle,
    build_dimensions,
    iter_fact_sales,
)
from app.core.config import get_settings  # noqa: E402

FACT_COLUMNS = (
    "order_id",
    "carline_id",
    "colour_id",
    "sales_person_id",
    "region_id",
    "dealer_id",
    "sales_date",
    "order_qty",
    "price_per_unit",
)


def _to_psycopg_url(url: str) -> str:
    """Strip the SQLAlchemy driver suffix so psycopg can connect directly."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _truncate(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            TRUNCATE TABLE
                automotive.fact_sales,
                automotive.dim_targets,
                automotive.dim_dealer,
                automotive.dim_salesman,
                automotive.dim_color,
                automotive.dim_carline,
                automotive.dim_region
            RESTART IDENTITY CASCADE
            """
        )
    conn.commit()


def _insert_dimensions(conn: psycopg.Connection, dims: DimensionBundle) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO automotive.dim_region
                (region_id, region_name, city, state_code, country)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [(r.region_id, r.region_name, r.city, r.state_code, r.country) for r in dims.regions],
        )
        cur.executemany(
            """
            INSERT INTO automotive.dim_carline
                (carline_id, carline_name, model, make, car_type,
                 engine_capacity, engine_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    c.carline_id,
                    c.carline_name,
                    c.model,
                    c.make,
                    c.car_type,
                    c.engine_capacity,
                    c.engine_type,
                )
                for c in dims.carlines
            ],
        )
        cur.executemany(
            """
            INSERT INTO automotive.dim_color
                (colour_id, colour_name, rcg_combination, patent_number)
            VALUES (%s, %s, %s, %s)
            """,
            [
                (c.colour_id, c.colour_name, c.rcg_combination, c.patent_number)
                for c in dims.colours
            ],
        )
        cur.executemany(
            """
            INSERT INTO automotive.dim_salesman
                (sales_person_id, first_name, last_name, email, corp_id, active)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    s.sales_person_id,
                    s.first_name,
                    s.last_name,
                    s.email,
                    s.corp_id,
                    s.active,
                )
                for s in dims.salesmen
            ],
        )
        cur.executemany(
            """
            INSERT INTO automotive.dim_dealer
                (dealer_id, dealer_code, dealer_name, region_id, city,
                 dealer_grade, active)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    d.dealer_id,
                    d.dealer_code,
                    d.dealer_name,
                    d.region_id,
                    d.city,
                    d.dealer_grade,
                    d.active,
                )
                for d in dims.dealers
            ],
        )
        cur.executemany(
            """
            INSERT INTO automotive.dim_targets
                (target_id, year_month, make, target_units, target_revenue)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (t.target_id, t.year_month, t.make, t.target_units, t.target_revenue)
                for t in dims.targets
            ],
        )
    conn.commit()


def _copy_facts(
    conn: psycopg.Connection,
    dims: DimensionBundle,
    *,
    rows: int,
    batch_log_every: int,
) -> None:
    started = time.perf_counter()
    copy_sql = sql.SQL("COPY automotive.fact_sales ({columns}) FROM STDIN").format(
        columns=sql.SQL(", ").join(map(sql.Identifier, FACT_COLUMNS))
    )

    with conn.cursor() as cur, cur.copy(copy_sql) as copy:
        for index, row in enumerate(iter_fact_sales(dims, row_count=rows), start=1):
            copy.write_row(row)
            if index % batch_log_every == 0:
                elapsed = time.perf_counter() - started
                rate = index / elapsed if elapsed else 0.0
                print(
                    f"  copied {index:,} / {rows:,} ({rate:,.0f} rows/s)",
                    flush=True,
                )
    conn.commit()
    elapsed = time.perf_counter() - started
    print(f"fact_sales COPY finished: {rows:,} rows in {elapsed:.1f}s", flush=True)


def seed(*, rows: int, replace: bool, database_url: str | None) -> None:
    settings = get_settings()
    url = _to_psycopg_url(database_url or settings.automotive_migrate_database_url)
    dims = build_dimensions()

    print(
        "Seeding automotive dimensions: "
        f"{len(dims.carlines)} carlines, {len(dims.colours)} colours, "
        f"{len(dims.salesmen)} salespeople, {len(dims.regions)} regions, "
        f"{len(dims.dealers)} dealers, {len(dims.targets)} targets",
        flush=True,
    )
    print(f"Connecting as owner to load {rows:,} fact_sales rows…", flush=True)

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT to_regclass('automotive.fact_sales') IS NOT NULL
                """
            )
            exists = cur.fetchone()
            if not exists or not exists[0]:
                raise SystemExit(
                    "automotive.fact_sales is missing. "
                    "Run: python scripts/migrate.py automotive upgrade head"
                )

        if replace:
            print("Truncating existing automotive tables…", flush=True)
            _truncate(conn)
        else:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM automotive.fact_sales")
                count = cur.fetchone()
                if count and count[0] > 0:
                    raise SystemExit(
                        f"fact_sales already has {count[0]:,} rows. Pass --replace to rebuild."
                    )

        _insert_dimensions(conn, dims)
        _copy_facts(conn, dims, rows=rows, batch_log_every=max(rows // 10, 50_000))

        with conn.cursor() as cur:
            cur.execute("ANALYZE automotive.fact_sales")
            cur.execute("SELECT COUNT(*) FROM automotive.fact_sales")
            fact_count = cur.fetchone()[0]
            cur.execute(
                """
                SELECT COUNT(*) FROM automotive.fact_sales f
                JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id
                WHERE f.region_id <> d.region_id
                """
            )
            mismatches = cur.fetchone()[0]
        conn.commit()

    if mismatches:
        raise SystemExit(f"Seed integrity failed: {mismatches:,} sales have region/dealer mismatch")
    print(f"Done. fact_sales rows = {fact_count:,}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rows",
        type=int,
        default=DEFAULT_FACT_ROWS,
        help=f"fact_sales row count (default {DEFAULT_FACT_ROWS:,})",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Truncate and reload all automotive tables",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override AUTOMOTIVE_MIGRATE_DATABASE_URL",
    )
    args = parser.parse_args()
    if args.rows < 1:
        raise SystemExit("--rows must be >= 1")
    seed(rows=args.rows, replace=args.replace, database_url=args.database_url)


if __name__ == "__main__":
    main()

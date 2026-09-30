"""Bulk-load the generated Indian automotive CSVs into PostgreSQL with COPY.

Usage
-----
    # from askdb/ (after: python scripts/migrate.py automotive upgrade head)
    python scripts/load_india_auto_dataset.py --replace                 # full reload
    python scripts/load_india_auto_dataset.py --data-dir data/india_auto --replace
    python scripts/load_india_auto_dataset.py --stage increment         # add post-split rows

Stages
------
``base``       load ``<data-dir>/*.csv`` (use ``--replace`` to truncate first)
``increment``  append ``<data-dir>/increment/*.csv`` (written with ``--split-date``)
``all``        base then increment in one run

Performance: the whole stage runs in one transaction; with ``--replace`` the tables are
truncated in that transaction and the fact indexes are dropped and rebuilt around COPY,
so PostgreSQL skips per-row index maintenance. ``total_sales`` is a generated column and
is never loaded. Afterwards the script ANALYZEs the tables and refreshes
``automotive.mv_sales_monthly``. Connects with ``AUTOMOTIVE_MIGRATE_DATABASE_URL``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import psycopg
from psycopg import sql

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.analytics.india_auto_generator import LOAD_ORDER, TABLE_COLUMNS  # noqa: E402

DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data" / "india_auto"
CHUNK = 1 << 20

# Secondary indexes rebuilt after a --replace load (definitions match the migrations).
FACT_INDEXES = {
    "idx_fact_sales_date_order": "automotive.fact_sales (sales_date DESC, order_id DESC)",
    "idx_fact_sales_carline_date": "automotive.fact_sales (carline_id, sales_date DESC)",
    "idx_fact_sales_region_date": "automotive.fact_sales (region_id, sales_date DESC)",
    "idx_fact_sales_dealer_date": "automotive.fact_sales (dealer_id, sales_date DESC)",
    "idx_fact_sales_salesperson_date": "automotive.fact_sales (sales_person_id, sales_date DESC)",
    "idx_auto_forecast_month": "automotive.fact_forecast_monthly (sales_month)",
}


def _to_psycopg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _database_url(override: str | None) -> str:
    if override:
        return _to_psycopg_url(override)
    from app.core.config import get_settings

    return _to_psycopg_url(get_settings().automotive_migrate_database_url)


def _check_schema(conn: psycopg.Connection) -> None:
    missing = [
        table
        for table in LOAD_ORDER
        if conn.execute("SELECT to_regclass(%s)", (f"automotive.{table}",)).fetchone()[0] is None
    ]
    if missing:
        raise SystemExit(
            f"Missing automotive tables: {', '.join(missing)}. "
            "Run: python scripts/migrate.py automotive upgrade head"
        )


def _check_headers(folder: Path) -> None:
    for table in LOAD_ORDER:
        path = folder / f"{table}.csv"
        if not path.is_file():
            raise SystemExit(f"{path} not found. Generate it with generate_india_auto_dataset.py")
        with path.open(encoding="utf-8") as handle:
            header = tuple(handle.readline().strip().split(","))
        if header != TABLE_COLUMNS[table]:
            raise SystemExit(f"{path.name}: unexpected header {header}")


def _copy(conn: psycopg.Connection, table: str, path: Path) -> int:
    statement = sql.SQL(
        "COPY automotive.{table} ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    ).format(
        table=sql.Identifier(table),
        columns=sql.SQL(", ").join(map(sql.Identifier, TABLE_COLUMNS[table])),
    )
    started = time.perf_counter()
    with conn.cursor() as cur:
        with cur.copy(statement) as copy, path.open("rb") as handle:
            while chunk := handle.read(CHUNK):
                copy.write(chunk)
        rows = cur.rowcount
    elapsed = time.perf_counter() - started
    rate = rows / elapsed if elapsed else 0.0
    print(f"  {table:<24} {rows:>12,} rows  {elapsed:6.1f}s  ({rate:,.0f} rows/s)", flush=True)
    return rows


def _fact_foreign_keys(conn: psycopg.Connection) -> list[tuple[str, str, str]]:
    return [
        (table, name, definition)
        for table in ("fact_sales", "fact_forecast_monthly")
        for name, definition in conn.execute(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = %s::regclass AND contype = 'f' ORDER BY conname",
            (f"automotive.{table}",),
        ).fetchall()
    ]


def _load_stage(conn: psycopg.Connection, folder: Path, *, replace: bool) -> None:
    _check_headers(folder)
    foreign_keys: list[tuple[str, str, str]] = []
    with conn.transaction():
        if replace:
            print("Truncating automotive tables...", flush=True)
            conn.execute(
                "TRUNCATE TABLE automotive.fact_forecast_monthly, automotive.fact_sales, "
                "automotive.dim_targets, automotive.dim_dealer, automotive.dim_salesman, "
                "automotive.dim_color, automotive.dim_carline, automotive.dim_region "
                "RESTART IDENTITY CASCADE"
            )
            for name in FACT_INDEXES:
                conn.execute(
                    sql.SQL("DROP INDEX IF EXISTS automotive.{}").format(sql.Identifier(name))
                )
            # Row-by-row FK triggers dominate COPY time; re-adding validates in one pass.
            foreign_keys = _fact_foreign_keys(conn)
            for table, name, _definition in foreign_keys:
                conn.execute(
                    sql.SQL("ALTER TABLE automotive.{} DROP CONSTRAINT {}").format(
                        sql.Identifier(table), sql.Identifier(name)
                    )
                )
        else:
            count = conn.execute("SELECT COUNT(*) FROM automotive.fact_sales").fetchone()[0]
            if count and folder.name != "increment":
                raise SystemExit(
                    f"fact_sales already has {count:,} rows. Pass --replace to reload."
                )
        for table in LOAD_ORDER:
            _copy(conn, table, folder / f"{table}.csv")
        if replace:
            started = time.perf_counter()
            for table, name, definition in foreign_keys:
                conn.execute(
                    sql.SQL("ALTER TABLE automotive.{} ADD CONSTRAINT {} {}").format(
                        sql.Identifier(table), sql.Identifier(name), sql.SQL(definition)
                    )
                )
            for name, target in FACT_INDEXES.items():
                conn.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {}").format(
                        sql.Identifier(name), sql.SQL(target)
                    )
                )
            print(
                f"Foreign keys validated + indexes rebuilt: {time.perf_counter() - started:.1f}s",
                flush=True,
            )


def _finish(conn: psycopg.Connection) -> None:
    started = time.perf_counter()
    with conn.transaction():
        for table in LOAD_ORDER:
            conn.execute(sql.SQL("ANALYZE automotive.{}").format(sql.Identifier(table)))
        conn.execute("REFRESH MATERIALIZED VIEW automotive.mv_sales_monthly")
        conn.execute("ANALYZE automotive.mv_sales_monthly")
    print(f"ANALYZE + mv_sales_monthly refresh: {time.perf_counter() - started:.1f}s", flush=True)
    mismatches = conn.execute(
        """
        SELECT COUNT(*) FROM automotive.fact_sales f
        JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id
        WHERE f.region_id <> d.region_id
        """
    ).fetchone()[0]
    if mismatches:
        raise SystemExit(f"Integrity failed: {mismatches:,} sales have a region/dealer mismatch")
    counts = {
        table: conn.execute(
            sql.SQL("SELECT COUNT(*) FROM automotive.{}").format(sql.Identifier(table))
        ).fetchone()[0]
        for table in LOAD_ORDER
    }
    print("Row counts: " + json.dumps(counts))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--stage", choices=("base", "increment", "all"), default="base")
    parser.add_argument("--replace", action="store_true", help="truncate before the base load")
    parser.add_argument("--database-url", default=None, help="override the owner database URL")
    args = parser.parse_args()

    folders: list[tuple[Path, bool]] = []
    if args.stage in {"base", "all"}:
        folders.append((args.data_dir, args.replace))
    if args.stage in {"increment", "all"}:
        increment = args.data_dir / "increment"
        if not increment.is_dir():
            raise SystemExit(f"{increment} not found. Generate with --split-date first.")
        folders.append((increment, False))

    started = time.perf_counter()
    with psycopg.connect(_database_url(args.database_url)) as conn:
        conn.autocommit = True
        _check_schema(conn)
        for folder, replace in folders:
            print(f"Loading {folder} ...", flush=True)
            _load_stage(conn, folder, replace=replace)
        _finish(conn)
    print(f"Done in {time.perf_counter() - started:.1f}s.")
    print("Next: Semantic Atlas > Entity Catalog > Refresh catalog (or restart the API).")


if __name__ == "__main__":
    main()

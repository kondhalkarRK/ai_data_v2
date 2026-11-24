"""Inspect, stage, load or roll back a protected Automotive demo increment.

Default operations are read-only. Loading requires a live DB snapshot, unchanged
inventory, a named approved batch, table locks and one transaction. Never truncates.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import psycopg
from app.analytics.automotive_increment import (
    CUTOFF,
    Inventory,
    calendars,
    json_write,
    read_csv_inventory,
    stage,
    validate_rows,
)
from app.analytics.india_auto_generator import TABLE_COLUMNS
from app.core.config import get_settings
from psycopg import sql

LEDGER = "demo_increment_batches"
SOURCES = ROOT / "database" / "automotive" / "refresh_2026_sources.json"


def connect(*, write: bool = False):
    settings = get_settings()
    url = (
        settings.automotive_migrate_database_url
        if write
        else settings.automotive_database_url
    )
    return psycopg.connect(
        url.replace("postgresql+psycopg://", "postgresql://", 1),
        connect_timeout=5,
        autocommit=True,
        options="-c statement_timeout=120000 -c lock_timeout=5000",
    )


def select_columns(table: str):
    return sql.SQL(", ").join(sql.Identifier(c) for c in TABLE_COLUMNS[table])


def inventory_db(conn) -> Inventory:
    inv = Inventory("database")
    for table in TABLE_COLUMNS:
        statement = sql.SQL("SELECT {} FROM automotive.{}").format(
            select_columns(table), sql.Identifier(table)
        )
        with conn.cursor(name="inventory_" + table) as cur:
            cur.execute(statement)
            inv.consume(
                table,
                (dict(zip(TABLE_COLUMNS[table], row, strict=True)) for row in cur),
            )
    return inv


def validate_snapshot_schema(schema: list) -> None:
    # The generator exports business columns, not the forecast surrogate key.
    # Both the migration-created table and a CSV-contract-only table are supported.
    optional_columns = {"fact_forecast_monthly": {"forecast_id"}}
    for table, columns in TABLE_COLUMNS.items():
        required = set(columns) | ({"total_sales"} if table == "fact_sales" else set())
        actual = {r[1] for r in schema if r[0] == table}
        missing = required - actual
        unexpected = actual - required - optional_columns.get(table, set())
        if missing or unexpected:
            raise ValueError(
                f"Review live schema drift in {table} before exporting: "
                f"missing columns={sorted(missing)}; unexpected columns={sorted(unexpected)}"
            )


def export_snapshot(folder: Path) -> None:
    if folder.exists():
        raise ValueError("Use a new snapshot directory")
    with connect() as conn, conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        schema = conn.execute(
            "SELECT table_name, column_name, data_type, is_generated "
            "FROM information_schema.columns "
            "WHERE table_schema='automotive' ORDER BY table_name, ordinal_position"
        ).fetchall()
        validate_snapshot_schema(schema)
        folder.mkdir(parents=True)
        for table in TABLE_COLUMNS:
            statement = sql.SQL(
                "COPY (SELECT {} FROM automotive.{}) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)"
            ).format(select_columns(table), sql.Identifier(table))
            with (
                conn.cursor() as cur,
                (folder / f"{table}.csv").open("wb") as handle,
                cur.copy(statement) as copy,
            ):
                while data := copy.read():
                    handle.write(data)
        identity = conn.execute(
            "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
        ).fetchone()
    inv = read_csv_inventory(folder, "database")
    json_write(
        folder / "snapshot.json",
        {
            "source_kind": "database",
            "database": identity,
            "baseline": inv.identity(),
            "schema": schema,
        },
    )
    json_write(folder / "coverage.json", inv.coverage())
    print(
        json.dumps(
            {
                "snapshot": str(folder),
                "source_kind": "database",
                "baseline": inv.identity(),
            }
        )
    )


def load_rows(path: Path, table: str) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != TABLE_COLUMNS[table]:
            raise ValueError(f"Unexpected staged columns in {table}")
        return list(reader)


def verify_files(folder: Path) -> dict:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    required = {
        "fact_sales.csv",
        "dim_carline.csv",
        "sources.json",
        "validation.json",
        "reference_model_calendar.csv",
        "coverage_before.json",
        "bucket_conflicts.json",
    }
    if not required <= set(manifest["files"]):
        raise ValueError("Batch is missing required evidence/files")
    for name, expected in manifest["files"].items():
        if Path(name).name != name or ":" in name or "\\" in name:
            raise ValueError("Invalid manifest filename")
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Checksum mismatch: {name}")
    if (
        manifest["protected_cutoff"] != CUTOFF.isoformat()
        or manifest["start"] != "2026-09-01"
    ):
        raise ValueError("The protected cutoff cannot be changed")
    if date.fromisoformat(manifest["end"]) >= date.fromisoformat(manifest["as_of"]):
        raise ValueError("Invalid date range")
    return manifest


def temp_tables(conn, folder: Path) -> None:
    for table in ("dim_carline", "fact_sales"):
        conn.execute(
            sql.SQL(
                "CREATE TEMP TABLE {} (LIKE automotive.{} INCLUDING GENERATED) ON COMMIT DROP"
            ).format(sql.Identifier("inc_" + table), sql.Identifier(table))
        )
        statement = sql.SQL(
            "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
        ).format(sql.Identifier("inc_" + table), select_columns(table))
        with (
            conn.cursor() as cur,
            (folder / f"{table}.csv").open("rb") as handle,
            cur.copy(statement) as copy,
        ):
            while data := handle.read(1 << 20):
                copy.write(data)


def verify_loaded_rows(conn) -> None:
    for table in ("dim_carline", "fact_sales"):
        missing = conn.execute(
            sql.SQL(
                "SELECT COUNT(*) FROM (SELECT {} FROM {} "
                "EXCEPT SELECT {} FROM automotive.{}) AS differences"
            ).format(
                select_columns(table),
                sql.Identifier("inc_" + table),
                select_columns(table),
                sql.Identifier(table),
            )
        ).fetchone()[0]
        if missing:
            raise ValueError(f"Loaded {table} rows are missing or modified")


def mutate(folder: Path, approved: str, *, rollback: bool = False) -> None:
    manifest = verify_files(folder)
    if approved != manifest["batch_id"]:
        raise ValueError("--approve-batch must name the exact reviewed batch")
    if not manifest["live_database_verified"] or manifest["source_kind"] != "database":
        raise ValueError("CSV candidates cannot be loaded; export live DB and restage")
    digest = hashlib.sha256((folder / "manifest.json").read_bytes()).hexdigest()
    with connect(write=True) as conn, conn.transaction():
        identity = conn.execute(
            "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
        ).fetchone()
        if list(identity) != manifest.get("database_identity"):
            raise ValueError("Database target differs from the reviewed live snapshot")
        conn.execute(
            sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(
                sql.SQL(", ").join(
                    sql.Identifier("automotive", t) for t in TABLE_COLUMNS
                )
            )
        )
        conn.execute(
            sql.SQL(
                "CREATE TABLE IF NOT EXISTS automotive.{} (batch_id TEXT PRIMARY KEY, "
                "manifest_sha256 TEXT NOT NULL, manifest JSONB NOT NULL, "
                "applied_at TIMESTAMPTZ NOT NULL "
                "DEFAULT now(), rolled_back_at TIMESTAMPTZ)"
            ).format(sql.Identifier(LEDGER))
        )
        recorded = conn.execute(
            sql.SQL(
                "SELECT manifest_sha256, rolled_back_at FROM automotive.{} "
                "WHERE batch_id=%s FOR UPDATE"
            ).format(sql.Identifier(LEDGER)),
            (approved,),
        ).fetchone()
        temp_tables(conn, folder)
        if recorded:
            if recorded[0] != digest:
                raise ValueError("Existing batch has a different manifest")
            if recorded[1] is not None:
                raise ValueError("Batch was rolled back; prepare a new reviewed batch")
            verify_loaded_rows(conn)
            if not rollback:
                print(
                    json.dumps(
                        {
                            "batch_id": approved,
                            "inserted": 0,
                            "status": "already_applied",
                        }
                    )
                )
                return
        elif rollback:
            raise ValueError("Batch has not been applied")
        current = inventory_db(conn)
        if rollback:
            if current.protected.value() != manifest["baseline"]["protected"]:
                raise ValueError("Protected history changed; review before rollback")
            conn.execute(
                "DELETE FROM automotive.fact_sales "
                "WHERE order_id IN (SELECT order_id FROM inc_fact_sales)"
            )
            # FK dependencies from any later load cause the entire rollback to abort.
            conn.execute(
                "DELETE FROM automotive.dim_carline "
                "WHERE carline_id IN (SELECT carline_id FROM inc_dim_carline)"
            )
            conn.execute(
                sql.SQL(
                    "UPDATE automotive.{} SET rolled_back_at=now() WHERE batch_id=%s"
                ).format(sql.Identifier(LEDGER)),
                (approved,),
            )
        else:
            if current.identity() != manifest["baseline"]:
                raise ValueError(
                    "Database changed after staging; restage against a new snapshot"
                )
            additions = load_rows(folder / "dim_carline.csv", "dim_carline")
            rows = load_rows(folder / "fact_sales.csv", "fact_sales")
            windows = calendars(current)
            with (folder / "reference_model_calendar.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                for r in csv.DictReader(handle):
                    windows[int(r["carline_id"])] = (
                        date.fromisoformat(r["on_sale_from"]),
                        None,
                    )
            validate_rows(
                current, additions, rows, windows, date.fromisoformat(manifest["end"])
            )
            for table in ("dim_carline", "fact_sales"):
                conn.execute(
                    sql.SQL("INSERT INTO automotive.{} ({}) SELECT {} FROM {}").format(
                        sql.Identifier(table),
                        select_columns(table),
                        select_columns(table),
                        sql.Identifier("inc_" + table),
                    )
                )
            verify_loaded_rows(conn)
            conn.execute(
                sql.SQL(
                    "INSERT INTO automotive.{} (batch_id, manifest_sha256, manifest) "
                    "VALUES (%s,%s,%s::jsonb)"
                ).format(sql.Identifier(LEDGER)),
                (approved, digest, json.dumps(manifest)),
            )
        protected_after = inventory_db(conn).protected.value()
        if protected_after != manifest["baseline"]["protected"]:
            raise ValueError("Protected history check failed; transaction rolled back")
        conn.execute("REFRESH MATERIALIZED VIEW automotive.mv_sales_monthly")
        conn.execute("ANALYZE automotive.fact_sales")
        conn.execute("ANALYZE automotive.mv_sales_monthly")
    print(
        json.dumps(
            {
                "batch_id": approved,
                "status": "rolled_back" if rollback else "applied",
                "new_orders": manifest["new_orders"],
                "protected_history_unchanged": True,
                "next": "Restart API caches, refresh Automotive Entity Catalog "
                "and run Data Trust checks.",
            }
        )
    )


async def refresh_metadata(folder: Path) -> None:
    """Refresh persisted catalog/DQ evidence; running API workers still need restart."""
    from app.core.config import Industry
    from app.semantic.service import SemanticService
    from app.services.catalog import EntityCatalogService
    from app.services.trust import DataTrustService
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    manifest = verify_files(folder)
    if not manifest["live_database_verified"]:
        raise ValueError("Cannot refresh metadata from an unverified CSV candidate")
    # The analytics reader need not have access to the owner-only operation journal.
    with connect(write=True) as audit, audit.transaction():
        audit.execute("SET TRANSACTION READ ONLY")
        identity = audit.execute(
            "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
        ).fetchone()
        if list(identity) != manifest.get("database_identity"):
            raise ValueError("Metadata target differs from the reviewed live snapshot")
        recorded = audit.execute(
            "SELECT manifest_sha256 FROM automotive.demo_increment_batches WHERE batch_id=%s",
            (manifest["batch_id"],),
        ).fetchone()
        if (
            not recorded
            or recorded[0]
            != hashlib.sha256((folder / "manifest.json").read_bytes()).hexdigest()
        ):
            raise ValueError("Metadata refresh requires the recorded reviewed batch")
    settings = get_settings()
    app_engine = create_async_engine(settings.app_database_url)
    analytics_engine = create_async_engine(settings.automotive_database_url)
    try:
        async with (
            async_sessionmaker(app_engine, expire_on_commit=False)() as session,
            analytics_engine.connect() as conn,
        ):
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            semantic = SemanticService(settings)
            catalog = EntityCatalogService(
                session, semantic, Industry.AUTOMOTIVE, analytics=conn
            )
            run = await catalog.refresh(
                scope="catalog", trigger="data_load", load_id=manifest["batch_id"]
            )
            if run.status != "completed":
                raise ValueError("Automotive catalog refresh did not complete")
            await session.commit()
            trust = await DataTrustService(
                connection=conn,
                semantic=semantic,
                settings=settings,
                industry=Industry.AUTOMOTIVE,
                app_session=session,
            ).get_center(force_refresh=True)
            if not trust.datasets:
                raise ValueError("Data Trust produced no dataset checks")
            await session.commit()
            json_write(
                folder / "post_refresh.json",
                {
                    "batch_id": manifest["batch_id"],
                    "catalog_status": run.status,
                    "data_as_of": trust.data_as_of,
                    "datasets_checked": len(trust.datasets),
                    "rules": len(trust.rules),
                    "incidents": len(trust.incidents),
                    "api_worker_restart_required": True,
                },
            )
    finally:
        await app_engine.dispose()
        await analytics_engine.dispose()
    print(
        json.dumps(
            {
                "metadata": "refreshed",
                "next": "Restart all API workers to clear process-local caches.",
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--snapshot-db", type=Path)
    modes.add_argument("--inspect-csv", type=Path)
    modes.add_argument("--stage-from", type=Path)
    modes.add_argument("--apply", type=Path)
    modes.add_argument("--rollback", type=Path)
    modes.add_argument("--refresh-metadata", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 11, 24))
    parser.add_argument("--seed", type=int, default=20261124)
    parser.add_argument("--approve-batch", default="")
    args = parser.parse_args()
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    if args.as_of > today:
        parser.error("--as-of cannot be a future Indian date")
    if args.snapshot_db:
        export_snapshot(args.snapshot_db)
    elif args.inspect_csv:
        inv = read_csv_inventory(args.inspect_csv)
        if not args.out:
            parser.error("--inspect-csv requires --out for coverage evidence")
        json_write(args.out, {"coverage": inv.coverage(), "baseline": inv.identity()})
        print(json.dumps({"coverage_report": str(args.out)}))
    elif args.stage_from:
        if not args.out:
            parser.error("--stage-from requires --out")
        meta = args.stage_from / "snapshot.json"
        kind = "csv_reference"
        if meta.exists():
            snapshot = json.loads(meta.read_text(encoding="utf-8"))
            kind = snapshot["source_kind"]
        inv = read_csv_inventory(args.stage_from, kind)
        if meta.exists() and inv.identity() != snapshot["baseline"]:
            raise ValueError("Snapshot files changed since export")
        manifest = stage(
            inv,
            json.loads(SOURCES.read_text(encoding="utf-8")),
            args.out,
            as_of=args.as_of,
            seed=args.seed,
            database_identity=snapshot["database"] if meta.exists() else None,
        )
        print(
            json.dumps(
                {
                    k: manifest[k]
                    for k in (
                        "batch_id",
                        "source_kind",
                        "new_orders",
                        "new_units",
                        "new_carlines",
                        "allocations",
                    )
                }
            )
        )
    else:
        folder = args.apply or args.rollback or args.refresh_metadata
        if args.apply or args.rollback:
            mutate(folder, args.approve_batch, rollback=bool(args.rollback))
        else:
            manifest = verify_files(folder)
            if args.approve_batch != manifest["batch_id"]:
                raise ValueError("Name the reviewed batch before refreshing metadata")
        # Windows psycopg requires this before asyncio creates its loop.
        import app.compat  # noqa: F401

        try:
            asyncio.run(refresh_metadata(folder))
        except Exception as exc:  # noqa: BLE001 -- committed data needs a distinct recovery status
            print(
                json.dumps(
                    {
                        "status": "metadata_refresh_failed",
                        "error_type": type(exc).__name__,
                        "message": "The data transaction may already be committed. "
                        "Use --refresh-metadata to retry; do not run a replacement loader.",
                    }
                )
            )
            raise SystemExit(2) from None


if __name__ == "__main__":
    try:
        main()
    except psycopg.Error as exc:
        # Never print a DSN, password, server diagnostic or unredacted exception.
        print(
            json.dumps(
                {
                    "status": "database_error",
                    "error_type": type(exc).__name__,
                    "message": "Check database availability and permissions; "
                    "no successful load was reported.",
                }
            )
        )
        raise SystemExit(1) from None

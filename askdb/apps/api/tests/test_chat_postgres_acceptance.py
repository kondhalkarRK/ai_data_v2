"""Opt-in native PostgreSQL math acceptance on an EMPTY, disposable test database.

Never uses APP/AUTOMOTIVE_DATABASE_URL. Setup is transactional and rolled back.
No office production/demo schema is overwritten or reused.
"""

import json
import os
import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import Industry, Settings
from app.semantic.service import SemanticService
from app.services.chat.request_compiler import compile_request
from app.services.chat.request_context import RequestPrincipal, build_request_context
from app.services.chat.request_contract import InterpretedRequest
from app.services.security.region_scope import RegionScope


@pytest.fixture
def native_database():
    url = os.environ.get("SCIO_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Native PostgreSQL not configured; SQLite is not native acceptance")
    parsed = make_url(url)
    if (
        parsed.get_backend_name() != "postgresql"
        or "test" not in (parsed.database or "").casefold()
        or os.environ.get("SCIO_ALLOW_EMPTY_TEST_DB_SETUP") != "yes"
    ):
        pytest.fail("Use a dedicated test-named database and explicit empty-test setup opt-in")
    engine = create_engine(url)
    pack = SemanticService(Settings(_env_file=None))._load_pack(Industry.AUTOMOTIVE)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                # Refuse even an existing unrelated user table: this database must be empty.
                existing = connection.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema NOT IN ('pg_catalog','information_schema') "
                        "AND LEFT(table_schema,3) <> 'pg_'"
                    )
                ).scalar_one()
                schema = connection.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.schemata "
                        "WHERE schema_name='automotive'"
                    )
                ).scalar_one()
                if existing or schema:
                    pytest.fail("Acceptance database is not empty. No test setup was applied.")
                connection.execute(text("CREATE SCHEMA automotive"))
                types = {
                    "decimal": "NUMERIC",
                    "date": "DATE",
                    "boolean": "BOOLEAN",
                    "integer": "INTEGER",
                    "bigint": "BIGINT",
                }
                for name, table in pack.model.tables.items():
                    columns = [
                        f'"{column}" {types.get(spec.type, "TEXT")}'
                        + (" PRIMARY KEY" if column == table.primary_key else "")
                        for column, spec in table.columns.items()
                    ]
                    connection.execute(
                        text(f'CREATE TABLE automotive."{name}" ({", ".join(columns)})')
                    )
                connection.execute(
                    text(
                        "INSERT INTO automotive.dim_carline(carline_id,make,model) "
                        "VALUES (1,'Fixture A','Helios'),(2,'Fixture B','Atlas')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO automotive.fact_sales(order_id,carline_id,sales_date,"
                        "order_qty,total_sales) VALUES (1,1,'2026-01-05',1,100),"
                        "(2,2,'2026-01-05',1,100),(3,1,'2026-02-05',3,900),"
                        "(4,2,'2026-02-05',1,50)"
                    )
                )
                yield pack, connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.mark.parametrize("comparison", [False, True])
def test_native_compiler_matches_independent_sql(native_database, comparison):
    pack, connection = native_database
    principal = RequestPrincipal(uuid.uuid4(), RegionScope.all_regions(), Industry.AUTOMOTIVE)
    context = build_request_context("revenue units ASP", pack=pack, principal=principal)
    payload = {
        "outcome": "analytics",
        "summary": "Native reference test",
        "measures": [{"id": "revenue"}, {"id": "units_sold"}, {"id": "average_selling_price"}],
        "period": {"label": "February", "start": "2026-02-01", "end_exclusive": "2026-03-01"},
    }
    if comparison:
        payload["comparisons"] = [
            {
                "kind": "period",
                "baseline": {
                    "label": "January",
                    "start": "2026-01-01",
                    "end_exclusive": "2026-02-01",
                },
            }
        ]
    compiled = compile_request(
        InterpretedRequest.model_validate_json(json.dumps(payload)),
        pack=pack,
        context=context,
        principal=principal,
        today=date(2026, 11, 26),
    )
    result = connection.execute(text(compiled.sql)).mappings().one()
    reference = (
        connection.execute(
            text(
                "SELECT SUM(total_sales) revenue,SUM(order_qty) units, "
                "SUM(total_sales)/NULLIF(SUM(order_qty),0) asp FROM automotive.fact_sales "
                "WHERE sales_date>='2026-02-01' AND sales_date<'2026-03-01'"
            )
        )
        .mappings()
        .one()
    )
    prefix = "current_" if comparison else ""
    assert result[prefix + "revenue"] == reference["revenue"]
    assert result[prefix + "units_sold"] == reference["units"]
    assert result[prefix + "average_selling_price"] == reference["asp"]
    if comparison:
        assert result["baseline_revenue"] == 200 and result["change_revenue"] == 750

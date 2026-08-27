from pathlib import Path

import pandas as pd
import yaml

from core.data_backend.csv_duckdb import CsvDuckDbBackend
from core.data_backend.postgres import PostgresBackend
from core.sql_guardrails import sql_is_safe
from features.okf_knowledge.pptx_extractor import extract_pptx_to_concepts


ROOT = Path(__file__).resolve().parents[1]
INSURANCE_DOCS = ROOT / "doc" / "business_knowledge" / "insurance"


def test_csv_backend_preserves_duckdb_query_path():
    frame = pd.DataFrame({"region": ["North", "South"], "amount": [10, 20]})
    backend = CsvDuckDbBackend(frame)

    result, error = backend.execute_sql(
        "SELECT region, SUM(amount) AS total FROM df GROUP BY region ORDER BY total"
    )

    assert error is None
    assert result is not None
    assert result["total"].tolist() == [10, 20]
    assert backend.backend_id == "csv_duckdb"


def test_csv_backend_caps_result_rows():
    frame = pd.DataFrame({"n": list(range(1200))})
    backend = CsvDuckDbBackend(frame)
    result, error = backend.execute_sql("SELECT n FROM df")
    assert error is None
    assert result is not None
    assert len(result) == 1000
    assert result.attrs.get("askdb_truncated") is True


def test_postgres_backend_exposes_catalog_helpers():
    backend = PostgresBackend({"password": None, "schema": "insurance"})
    assert backend.table_row_counts() == {}
    assert backend.list_foreign_keys() == []
    status = backend.public_status()
    assert status["healthy"] is False
    assert "row_counts" in status


def test_sql_guardrails_block_postgres_escape_paths():
    assert sql_is_safe("SELECT 1")[0] is True
    assert sql_is_safe("WITH x AS (SELECT 1) SELECT * FROM x")[0] is True
    assert sql_is_safe("COPY insurance.fact_claims TO '/tmp/x.csv'")[0] is False
    assert sql_is_safe("SELECT pg_sleep(5)")[0] is False
    assert sql_is_safe("SELECT 1; SELECT 2")[0] is False
    gap_sql = """
        WITH months AS (
            SELECT date_trunc('month', reported_date)::date AS m
            FROM insurance.fact_claims
            GROUP BY 1
        )
        SELECT generate_series(
            (SELECT MIN(m) FROM months),
            (SELECT MAX(m) FROM months),
            interval '1 month'
        )::date AS m
    """
    assert sql_is_safe(gap_sql)[0] is True
    assert sql_is_safe("SET search_path TO insurance")[0] is False
    assert sql_is_safe(
        "WITH x AS (DELETE FROM insurance.fact_claims RETURNING *) SELECT * FROM x"
    )[0] is False
    assert sql_is_safe("SELECT * INTO tmp FROM insurance.dim_region")[0] is False


def test_two_cfo_decks_extract_as_slide_citations():
    deck_paths = sorted(INSURANCE_DOCS.glob("INS-CFO-Q*-2026_*.pptx"))
    assert len(deck_paths) == 2

    for path in deck_paths:
        concepts = extract_pptx_to_concepts(path.read_bytes(), path.name)
        assert len(concepts) >= 7
        assert concepts[0]["doc_type"] == "quarterly_results"
        assert concepts[0]["source_locator"].startswith("slide ")
        combined = " ".join(item["body"] for item in concepts)
        assert "SYNTHETIC DEMO DATA" in combined
        assert "Loss ratio" in combined


def test_cg_studio_catalog_includes_listed_endpoints():
    from config.llm_catalog import CG_ENDPOINTS, get_profile

    ids = {item["id"] for item in CG_ENDPOINTS}
    assert "openai.gpt-5.1" in ids
    assert "openai.gpt-5-mini" in ids
    assert "openai.gpt-5-nano" in ids
    assert "openai.gpt-5" in ids
    assert "openai.gpt-4o" in ids
    assert "openai.gpt-3.5-turbo" in ids
    assert "anthropic.claude-haiku-4-5-20251001-v1:0" in ids
    assert "anthropic.claude-sonnet-5" in ids
    assert "anthropic.claude-opus-5" in ids
    haiku = get_profile("claude", "small")
    assert haiku["model"] == "anthropic.claude-haiku-4-5-20251001-v1:0"
    from datetime import date

    from config.llm_catalog import estimate_usd, tokens_per_dollar, questions_per_dollar
    from core.insurance_kpi_engine import (
        calendar_year_bounds,
        calendar_ytd_bounds,
        fy_april_march_bounds,
    )

    start, end = fy_april_march_bounds(date(2026, 6, 30), previous=False)
    assert start == date(2026, 4, 1)
    assert end == date(2026, 6, 30)
    prev_start, prev_end = fy_april_march_bounds(date(2026, 6, 30), previous=True)
    assert prev_start == date(2025, 4, 1)
    assert prev_end == date(2026, 3, 31)
    ytd_s, ytd_e = calendar_ytd_bounds(date(2026, 6, 30))
    assert ytd_s == date(2026, 1, 1) and ytd_e == date(2026, 6, 30)
    cy_s, cy_e = calendar_year_bounds(2025, date(2026, 6, 30))
    assert cy_s == date(2025, 1, 1) and cy_e == date(2025, 12, 31)
    assert tokens_per_dollar(10.0) == 100_000
    assert round(estimate_usd(100_000, 10.0), 2) == 1.0
    assert questions_per_dollar(10.0, with_narration=False) == 40
    assert questions_per_dollar(10.0, with_narration=True) == 16


def test_insurance_semantic_joins_connect_each_dimension():
    from core.semantic_joins import load_semantic_joins

    payload = load_semantic_joins()
    assert payload["ok"] is True
    assert payload["count"] >= 10
    coverage = {row["Dimension"]: row for row in payload["coverage"]}
    for dim in ("dim_product", "dim_region", "dim_agent", "dim_policy"):
        assert dim in coverage
        assert coverage[dim]["Connected"] == "Yes"


def test_postgres_insurance_semantics_use_separate_premium_grain():
    model_path = (
        ROOT
        / "semantic"
        / "packs"
        / "insurance"
        / "semantic_model_postgres.yaml"
    )
    glossary_path = (
        ROOT
        / "semantic"
        / "packs"
        / "insurance"
        / "business_glossary_postgres.yaml"
    )
    model = yaml.safe_load(model_path.read_text(encoding="utf-8"))
    glossary = yaml.safe_load(glossary_path.read_text(encoding="utf-8"))

    assert "fact_policy_monthly" in model["tables"]
    assert (
        model["measures"]["earned_premium"]["source_table"]
        == "fact_policy_monthly"
    )
    assert "earned premium" in glossary["terms"]["Loss Ratio"]["definition"].lower()

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


def test_postgres_backend_requires_password_before_connection():
    backend = PostgresBackend({"password": None, "schema": "insurance"})
    healthy, message = backend.health_check()
    assert healthy is False
    assert "password" in message.lower()


def test_sql_guardrails_block_postgres_escape_paths():
    assert sql_is_safe("SELECT 1")[0] is True
    assert sql_is_safe("WITH x AS (SELECT 1) SELECT * FROM x")[0] is True
    assert sql_is_safe("COPY insurance.fact_claims TO '/tmp/x.csv'")[0] is False
    assert sql_is_safe("SELECT pg_sleep(5)")[0] is False
    assert sql_is_safe("SELECT 1; SELECT 2")[0] is False


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

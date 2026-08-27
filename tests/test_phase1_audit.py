"""Phase 1 audit hardening — unit tests (no live Postgres required)."""
from __future__ import annotations

import pandas as pd

from core.question_normaliser import (
    detect_followup,
    is_standalone_analytical_question,
)
from core.sql_guardrails import sql_is_safe


def test_sql_guardrails_block_dml_inside_cte():
    bad = """
    WITH x AS (
        DELETE FROM insurance.fact_claims RETURNING *
    )
    SELECT * FROM x
    """
    ok, reason = sql_is_safe(bad)
    assert ok is False
    assert "DELETE" in reason.upper()


def test_sql_guardrails_block_select_into_and_for_update():
    assert sql_is_safe("SELECT * INTO tmp FROM insurance.fact_claims")[0] is False
    assert sql_is_safe("SELECT * FROM insurance.fact_claims FOR UPDATE")[0] is False
    assert sql_is_safe("WITH x AS (SELECT 1 AS n) SELECT n FROM x")[0] is True


def test_insurance_standalone_not_followup():
    q = "Show claims by region for 2025"
    assert is_standalone_analytical_question(q) is True
    assert detect_followup(q) is False

    q2 = "just show GWP by product for 2025"
    assert is_standalone_analytical_question(q2) is True
    assert detect_followup(q2) is False

    q3 = "Show loss ratio by region for 2025"
    assert is_standalone_analytical_question(q3) is True


def test_explicit_followup_still_detected_with_anchor(monkeypatch):
    monkeypatch.setattr(
        "core.question_normaliser._has_prior_query_context",
        lambda: True,
    )
    assert detect_followup("same but for East") is True
    assert detect_followup("only for West") is True
    assert detect_followup("what about Motor") is True


def test_postgres_url_auth_catalog_gate():
    from core.data_backend.postgres import PostgresBackend

    url_backend = PostgresBackend(
        {
            "connection_url": "postgresql://user:pass@host/db",
            "schema": "insurance",
            "password": None,
        }
    )
    assert url_backend._has_auth() is True

    bare = PostgresBackend({"schema": "insurance", "password": None})
    assert bare._has_auth() is False


def test_empty_result_not_cached_helper():
    from core.nlq_engine import _result_is_empty, _store_session_nlq_cache

    assert _result_is_empty(None) is True
    assert _result_is_empty(pd.DataFrame()) is True
    assert _result_is_empty(pd.DataFrame({"a": [1]})) is False

    class _FakeSession(dict):
        pass

    import streamlit as st

    mem = {}
    st.session_state.memory = mem
    st.session_state.last_glossary_matches = []
    st.session_state.last_glossary_hints = ""
    _store_session_nlq_cache("k", pd.DataFrame(), "SELECT 1")
    assert "k" not in mem
    _store_session_nlq_cache("k2", pd.DataFrame({"a": [1]}), "SELECT 1")
    assert "k2" in mem


def test_trust_score_caps_empty_results():
    from ui.tab_query import compute_trust_score

    evidence = {
        "execution_path": "semantic",
        "resolution_source": "semantic_llm",
        "glossary_matches": [{"term": "gwp"}, {"term": "region"}],
        "glossary_hints": "SUM(written_premium) AS gwp",
        "empty_result": True,
        "row_count": 0,
    }
    score, breakdown = compute_trust_score(evidence, pd.DataFrame(), None)
    assert score <= 45
    assert breakdown.get("empty_cap") is True


def test_detect_destructive_allows_analytical_drop_update():
    from ui.tab_query import detect_destructive

    assert detect_destructive("show drop in loss ratio by region") is False
    assert detect_destructive("status update on claims for 2025") is False
    assert detect_destructive("drop table fact_claims") is True
    assert detect_destructive("delete from fact_claims") is True


def test_factory_retry_helpers_importable():
    from core.data_backend.factory import (
        get_configured_backend_id,
        is_postgres_fallback_active,
        retry_postgres_backend,
    )

    assert get_configured_backend_id() in {"csv_duckdb", "postgres"}
    assert callable(retry_postgres_backend)
    assert isinstance(is_postgres_fallback_active(), bool)

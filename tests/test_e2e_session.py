"""
End-to-end functional test with mocked Streamlit session (sample_data loaded).
Run: python tests/test_e2e_session.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

# Minimal session_state mock
class _SS(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)
    def __setattr__(self, k, v):
        self[k] = v

st.session_state = _SS()

PASS = FAIL = 0


def ok(n):
    global PASS
    PASS += 1
    print(f"  PASS  {n}")


def fail(n, e):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {n}: {e}")


print("\n=== E2E session test (sample_data) ===")

try:
    from config.settings import init_session_state
    init_session_state()
    ok("init_session_state")
except Exception as e:
    fail("init_session_state", e)

try:
    sample = ROOT / "sample_data"
    dfs = {
        "fact_sales": pd.read_csv(sample / "fact_sales.csv", parse_dates=["sales_date"]),
        "dim_region": pd.read_csv(sample / "dim_region.csv"),
        "dim_carline": pd.read_csv(sample / "dim_carline.csv"),
        "dim_color": pd.read_csv(sample / "dim_color.csv"),
        "dim_salesman": pd.read_csv(sample / "dim_salesman.csv"),
    }
    st.session_state.dfs = dfs
    st.session_state.join_mode = "auto"
    ok(f"loaded {len(dfs)} tables")
except Exception as e:
    fail("load sample dfs", e)
    sys.exit(1)

try:
    from core.join_engine import get_working_df
    wdf = get_working_df()
    assert wdf is not None and len(wdf) > 1000
    assert "region_name" in wdf.columns or "region_id" in wdf.columns
    ok(f"working_df join ({len(wdf):,} rows, {wdf.shape[1]} cols)")
except Exception as e:
    fail("get_working_df", e)
    wdf = None

if wdf is not None:
    try:
        from features.okf_knowledge.okf_answer import answer_knowledge_question
        r = answer_knowledge_question("Does monthly sales align with target?", wdf)
        assert r and len(r["result_df"]) >= 1
        ok("target alignment E2E")
    except Exception as e:
        fail("target alignment E2E", e)

    try:
        from core.incomplete_question import assess_question_completeness
        a = assess_question_completeness("show sales", wdf)
        assert a["incomplete"]
        ok("incomplete question with df")
    except Exception as e:
        fail("incomplete question", e)

    try:
        from core.question_normaliser import detect_oob
        assert detect_oob("train a ml model on this data")
        assert not detect_oob("show units by region for 2025")
        ok("OOB detection")
    except Exception as e:
        fail("OOB", e)

    try:
        from features.narration_engine import NarrationEngine
        from core.nlq_engine import run_query
        import os
        from config.settings import LLM_API_KEY
        if LLM_API_KEY or os.environ.get("CAPGEMINI_LLM_API_KEY"):
            out = run_query(wdf, "show total order_qty by region_name for 2025")
            rdf = out[0]
            err = out[2] if len(out) > 2 else None
            if err:
                fail("NLQ query", err)
            else:
                narr = NarrationEngine().generate_narration(rdf, "units by region 2025")
                assert narr.get("headline")
                ok(f"NLQ + narration ({len(rdf)} rows)")
        else:
            print("  SKIP  NLQ live query (no API key)")
    except Exception as e:
        fail("NLQ + narration", traceback.format_exc(limit=1))

    try:
        from semantic.semantic_loader import get_semantic_loader
        from semantic.semantic_context_builder import get_context_builder
        loader = get_semantic_loader()
        builder = get_context_builder()
        ctx = builder.build_full_context("show units by make", wdf)
        assert ctx and len(ctx) > 50
        ok("semantic context build")
    except Exception as e:
        fail("semantic context", e)

    try:
        from features.okf_knowledge.okf_bootstrap import bootstrap_business_knowledge
        from features.okf_knowledge.okf_retriever import indexed_concept_count
        summary = bootstrap_business_knowledge(force=False)
        cnt = indexed_concept_count()
        assert cnt >= 0
        ok(f"OKF bootstrap/index ({cnt} concepts indexed)")
    except Exception as e:
        fail("OKF bootstrap", e)

print(f"\n=== E2E SUMMARY: PASS={PASS} FAIL={FAIL} ===")
sys.exit(1 if FAIL else 0)

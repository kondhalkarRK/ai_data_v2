"""
Unit tests for core modules — no LLM or network required.
Run: python tests/test_core_modules.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

PASS = FAIL = 0


class _SS(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


st.session_state = _SS()


def ok(name: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS  {name}")


def fail(name: str, err: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  FAIL  {name}: {err}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def load_sample_df() -> pd.DataFrame:
    sample = ROOT / "sample_data"
    fs = pd.read_csv(sample / "fact_sales.csv", parse_dates=["sales_date"])
    dr = pd.read_csv(sample / "dim_region.csv")
    dc = pd.read_csv(sample / "dim_carline.csv")
    return fs.merge(dr, on="region_id").merge(dc, on="carline_id")


# ---------------------------------------------------------------------------
section("1. SQL guardrails")
# ---------------------------------------------------------------------------
try:
    from core.sql_guardrails import sql_is_safe

    assert sql_is_safe("SELECT 1 AS x")[0] is True
    assert sql_is_safe("DELETE FROM t WHERE 1=1")[0] is False
    assert sql_is_safe("SELECT * FROM t; DROP TABLE t")[0] is False
    assert sql_is_safe("WITH cte AS (SELECT 1) SELECT * FROM cte")[0] is True
    ok("sql_is_safe allow/block")
except Exception:
    fail("sql guardrails", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("2. Chart engine")
# ---------------------------------------------------------------------------
try:
    from core.chart_engine import auto_chart_type

    trend_df = pd.DataFrame({"month": ["Jan", "Feb"], "units": [10, 20]})
    assert auto_chart_type(trend_df, "monthly revenue trend") == "Line"
    pie_df = pd.DataFrame({"region": ["N", "S", "E"], "share": [40, 35, 25]})
    assert auto_chart_type(pie_df, "share breakdown by region") == "Pie"
    ok("auto_chart_type trend/pie")
except Exception:
    fail("chart engine", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("3. Question normaliser + routing")
# ---------------------------------------------------------------------------
try:
    from core.question_normaliser import (
        detect_oob,
        detect_followup,
        is_standalone_analytical_question,
        classify_followup_intent,
    )
    from core.nlq_engine import enrich_query as nlq_enrich

    assert detect_oob("write me python code to delete the database")
    assert detect_oob("drop table users")
    assert not detect_oob("show revenue by region")
    ok("detect_oob")

    assert is_standalone_analytical_question("show total sales for 2023")
    assert not is_standalone_analytical_question("show only ford")
    assert nlq_enrich("test question") == "test question"
    assert nlq_enrich("follow-up text") == "follow-up text"
    ok("standalone + enrich_query passthrough")

    anchor = {"sql_anchor": "SELECT make, SUM(units) FROM t GROUP BY make"}
    assert classify_followup_intent("show total sales for 2023", anchor) == "new_question"
    assert classify_followup_intent("show only ford", anchor) == "filter_change"
    assert classify_followup_intent("drill down by model", anchor) == "new_question"
    assert classify_followup_intent("add region column", anchor) == "additive"
    ok("classify_followup_intent")

    assert detect_followup("show total sales for 2023") is False
    ok("detect_followup without prior context")
except Exception:
    fail("question normaliser", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("4. Conversation state + SQL anchor")
# ---------------------------------------------------------------------------
try:
    from core.conversation_state import (
        clear_state,
        set_sql_anchor,
        get_sql_anchor,
        should_use_anchor,
        detect_followup,
        is_data_question,
        resolve_clarification,
        set_pending_clarification,
    )

    clear_state()
    sql = (
        "SELECT make, SUM(order_qty) AS units FROM sales "
        "WHERE year = 2025 GROUP BY make ORDER BY units DESC LIMIT 10"
    )
    set_sql_anchor(sql, "units by make 2025")
    anchor = get_sql_anchor()
    assert anchor and anchor.get("sql_anchor_metric")
    assert anchor.get("sql_anchor_limit") == 10
    assert should_use_anchor("show only tata") is True
    assert should_use_anchor("show total revenue by region for 2024") is False
    assert detect_followup("drill down by region") is True
    assert is_data_question("show units by make") is True
    assert is_data_question("what's for dinner") is False
    ok("sql anchor parse + should_use_anchor")

    set_pending_clarification("show sales", suggestions=["Show units by make", "Monthly trend"])
    assert "units" in resolve_clarification("1").lower()
    ok("clarification resolve")
except Exception:
    fail("conversation state", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("5. Narration engine (rule-based)")
# ---------------------------------------------------------------------------
try:
    from features.narration_engine import NarrationEngine

    eng = NarrationEngine()
    assert eng.format_value(-150000, "currency") == "-₹1.50 L"

    align_df = pd.DataFrame({
        "month": ["Apr 2026"],
        "scope": ["National"],
        "actual_units": [900],
        "target_units": [10000],
        "variance_units": [-9100],
        "variance_pct": [-91.0],
        "status": ["Behind"],
    })
    narr = eng.generate_narration(align_df, "monthly vs target")
    headline = narr.get("headline", "").lower()
    assert "behind" in headline or "align" in headline or "plan" in headline
    ok("target alignment narration (OKF off)")

    ranked = pd.DataFrame({"make": ["Tata", "Maruti"], "units": [100, 80]})
    narr2 = eng.generate_narration(ranked, "top makes")
    assert narr2.get("headline")
    ok("ranked rule-based narration")
except Exception:
    fail("narration engine", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("6. PII mask")
# ---------------------------------------------------------------------------
try:
    from core.pii_mask import mask_pii_for_display, pii_columns_found, _mask_phone

    assert _mask_phone("+1 (555) 123-4567") == "***-***-4567"
    tdf = pd.DataFrame({"units": [10, 20], "region": ["North", "South"]})
    masked = mask_pii_for_display(tdf)
    assert masked["units"].equals(tdf["units"])
    ok("PII mask phone + numeric unchanged")
except Exception:
    fail("PII mask", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("7. Join engine")
# ---------------------------------------------------------------------------
try:
    from core.join_engine import _join_score, auto_join

    left = pd.DataFrame({"region_id": [1, 2, 3], "units": [10, 20, 30]})
    right = pd.DataFrame({"region_id": [1, 2, 3], "region_name": ["N", "S", "E"]})
    score = _join_score(left["region_id"], right["region_id"])
    assert score >= 0.9

    merged, join_log = auto_join({"sales": left, "regions": right})
    assert merged is not None and len(merged) == 3
    assert join_log and join_log[0].get("note", "").startswith("OK")
    ok("join score + auto_join")
except Exception:
    fail("join engine", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("8. Evidence builder")
# ---------------------------------------------------------------------------
try:
    from core.evidence_builder import build_evidence, get_execution_badge

    st.session_state.memory = {}
    df = pd.DataFrame({"x": [1, 2]})
    ev = build_evidence("SELECT 1", df, "cache", "test q")
    assert ev["execution_path"] == "cache"
    assert ev["result_row_count"] == 2
    badge = get_execution_badge({"execution_path": "deterministic"})
    assert badge["label"] == "Deterministic"
    ok("evidence builder")
except Exception:
    fail("evidence builder", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("9. Incomplete question")
# ---------------------------------------------------------------------------
try:
    from core.incomplete_question import assess_question_completeness, build_suggestions

    df = load_sample_df()
    vague = assess_question_completeness("show revenue", df)
    assert vague.get("incomplete") and vague.get("reason") == "missing_time_or_dim"
    complete = assess_question_completeness("show total units by make for 2025", df)
    assert not complete.get("incomplete")
    sugs = build_suggestions("tell me about Ford", df)
    assert any("ford" in s.lower() for s in sugs)
    ok("incomplete question + suggestions")
except Exception:
    fail("incomplete question", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("10. Module imports (smoke)")
# ---------------------------------------------------------------------------
MODULES = [
    "core.nlq_engine",
    "core.kpi_engine",
    "core.metric_registry",
    "core.data_quality_engine",
    "core.analysis_engine",
    "core.intent_resolver",
    "core.semantic_resolver",
    "features.anomaly_engine",
    "features.proactive_engine",
    "features.whatif_engine",
    "semantic.semantic_context_builder",
    "ui.tab_query",
    "ui.tab_kpi",
]
for mod in MODULES:
    try:
        __import__(mod)
        ok(f"import {mod}")
    except Exception as e:
        fail(f"import {mod}", str(e))


print(f"\n=== CORE MODULE TEST SUMMARY ===")
print(f"PASS={PASS}  FAIL={FAIL}")
sys.exit(1 if FAIL else 0)

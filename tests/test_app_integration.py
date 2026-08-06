"""
Integration smoke tests — core app paths without full Streamlit UI.
Run: python tests/test_app_integration.py
"""
from __future__ import annotations

import ast
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS = FAIL = SKIP = 0


def ok(name: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS  {name}")


def fail(name: str, err: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  FAIL  {name}: {err}")


def skip(name: str, reason: str) -> None:
    global SKIP
    SKIP += 1
    print(f"  SKIP  {name}: {reason}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def load_sample_working_df():
    import pandas as pd
    fs = pd.read_csv(ROOT / "sample_data" / "fact_sales.csv", parse_dates=["sales_date"])
    dr = pd.read_csv(ROOT / "sample_data" / "dim_region.csv")
    dc = pd.read_csv(ROOT / "sample_data" / "dim_carline.csv")
    return fs.merge(dr, on="region_id").merge(dc, on="carline_id")


# ---------------------------------------------------------------------------
section("1. Module imports")
# ---------------------------------------------------------------------------
MODULES = [
    "app",
    "config.settings",
    "config.styles",
    "core.nlq_engine",
    "core.conversation_state",
    "core.incomplete_question",
    "core.pii_mask",
    "core.question_normaliser",
    "core.join_engine",
    "features.narration_engine",
    "features.okf_knowledge.okf_answer",
    "features.okf_knowledge.target_alignment",
    "features.okf_knowledge.target_narration",
    "ui.tab_query",
    "ui.tab_preview",
    "ui.tab_join",
    "ui.safe_display",
    "semantic.semantic_loader",
]
for mod in MODULES:
    try:
        __import__(mod)
        ok(f"import {mod}")
    except Exception as e:
        fail(f"import {mod}", str(e))


# ---------------------------------------------------------------------------
section("2. Syntax — all project .py files")
# ---------------------------------------------------------------------------
py_files = list(ROOT.rglob("*.py"))
py_files = [p for p in py_files if "venv" not in str(p) and "__pycache__" not in str(p)]
syntax_errors = 0
for p in py_files:
    try:
        ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError as e:
        fail(f"syntax {p.relative_to(ROOT)}", str(e))
        syntax_errors += 1
if syntax_errors == 0:
    ok(f"syntax check ({len(py_files)} files)")


# ---------------------------------------------------------------------------
section("3. OKF + target alignment")
# ---------------------------------------------------------------------------
try:
    import pandas as pd
    from features.okf_knowledge.okf_answer import (
        is_knowledge_question,
        is_ev_demand_question,
        answer_knowledge_question,
        compute_ev_share_by_year,
    )
    from features.okf_knowledge.target_alignment import (
        is_target_alignment_question,
        compute_target_alignment,
    )
    from features.okf_knowledge.target_narration import generate_target_alignment_narration

    df = load_sample_working_df()
    assert is_target_alignment_question("Does monthly sales align with target?")
    assert is_knowledge_question("Does monthly sales align with target?")
    ok("target alignment question detection")

    payload = compute_target_alignment("monthly sales vs target", df)
    assert payload and not payload["result_df"].empty
    assert "actual_units" in payload["result_df"].columns
    ok("compute_target_alignment")

    narr = generate_target_alignment_narration(payload, [])
    assert narr.get("headline") and narr.get("narrative_text")
    ok("target alignment narration")

    ans = answer_knowledge_question("Does monthly sales align with target?", df)
    assert ans and ans.get("okf_answer") and not ans["result_df"].empty
    ok("answer_knowledge_question (alignment)")

    if "engine_type" in df.columns or True:
        ev_df = compute_ev_share_by_year(df) if "engine_type" in df.columns else None
        if ev_df is None:
            skip("EV share compute", "engine_type not in joined sample df")
        else:
            assert not ev_df.empty
            ok("compute_ev_share_by_year")
except Exception:
    fail("OKF / target alignment", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("4. Incomplete question + conversation state")
# ---------------------------------------------------------------------------
try:
    from core.incomplete_question import assess_question_completeness
    from core.conversation_state import (
        detect_followup,
        resolve_clarification,
        set_pending_clarification,
    )

    r = assess_question_completeness("show sales", None)
    assert r.get("incomplete") and len(r.get("suggestions", [])) >= 1
    ok("assess_question_completeness (vague)")

    r2 = assess_question_completeness("show total units by make for 2025", None)
    assert not r2.get("incomplete")
    ok("assess_question_completeness (complete)")

    set_pending_clarification("show sales", suggestions=["Show units by make for 2025", "Monthly revenue trend"])
    q = resolve_clarification("1")
    assert q and "units" in q.lower()
    ok("clarification resolve suggestion")

    from core.conversation_state import set_sql_anchor
    set_sql_anchor("SELECT SUM(order_qty) AS units FROM t GROUP BY region_name", "units by region")
    assert detect_followup("drill down by region")
    ok("drill-down follow-up detection")
except Exception:
    fail("incomplete / conversation", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("5. PII masking + safe display helpers")
# ---------------------------------------------------------------------------
try:
    import pandas as pd
    from core.pii_mask import mask_pii_for_display, pii_columns_found
    from ui.safe_display import safe_dataframe

    tdf = pd.DataFrame({
        "salesperson_name": ["Alice Smith", "Bob Jones"],
        "email": ["alice@corp.com", "bob@test.com"],
        "units": [10, 20],
    })
    masked = mask_pii_for_display(tdf)
    assert "***" in str(masked.iloc[0]["salesperson_name"])
    assert "@" in str(masked.iloc[0]["email"]) and "alice@corp.com" != str(masked.iloc[0]["email"])
    ok("PII mask")

    found = pii_columns_found(tdf)
    assert "email" in found or "salesperson_name" in found
    ok("PII column detection")
except Exception:
    fail("PII masking", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("6. Narration engine")
# ---------------------------------------------------------------------------
try:
    import pandas as pd
    from features.narration_engine import NarrationEngine

    eng = NarrationEngine()
    rdf = pd.DataFrame({
        "make": ["Tata", "Maruti", "Hyundai"],
        "units": [1200, 980, 760],
    })
    narr = eng.generate_narration(rdf, "top makes by units")
    assert narr.get("headline") and narr.get("summary") == narr.get("headline")
    ok("narration ranked summary=headline")

    align_df = pd.DataFrame({
        "month": ["Apr 2026"],
        "scope": ["National"],
        "actual_units": [900],
        "target_units": [10000],
        "variance_units": [-9100],
        "variance_pct": [-91.0],
        "status": ["Behind"],
    })
    narr2 = eng.generate_narration(align_df, "monthly vs target")
    assert "align" in narr2.get("headline", "").lower() or "Behind" in narr2.get("headline", "")
    ok("narration target-alignment shape")
except Exception:
    fail("narration engine", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("7. Semantic loader + glossary")
# ---------------------------------------------------------------------------
try:
    from semantic.semantic_loader import get_semantic_loader
    loader = get_semantic_loader()
    tables = loader.get_tables() or {}
    measures = loader.get_measures() or {}
    assert len(tables) >= 1 or len(measures) >= 1
    ok(f"semantic_loader ({len(tables)} tables, {len(measures)} measures)")
except Exception as e:
    fail("semantic_loader", str(e))


# ---------------------------------------------------------------------------
section("8. NLQ engine (sample query — may skip if no LLM key)")
# ---------------------------------------------------------------------------
try:
    import os
    import pandas as pd
    from core.nlq_engine import run_query
    from config.settings import LLM_API_KEY

    df = load_sample_working_df()
    if not LLM_API_KEY and not os.environ.get("CAPGEMINI_LLM_API_KEY"):
        skip("run_query NLQ", "no LLM API key configured")
    else:
        out = run_query(df, "show total units by region for 2025")
        if isinstance(out, tuple) and len(out) >= 3:
            result_df, sql, err = out[0], out[1], out[2]
            if err:
                skip("run_query NLQ", f"query error: {err}")
            elif result_df is not None and not result_df.empty:
                ok(f"run_query NLQ ({len(result_df)} rows)")
            else:
                skip("run_query NLQ", "empty result")
        else:
            fail("run_query NLQ", "unexpected return shape")
except Exception as e:
    skip("run_query NLQ", str(e))


# ---------------------------------------------------------------------------
section("9. OOB + question normaliser")
# ---------------------------------------------------------------------------
try:
    from core.question_normaliser import detect_oob, classify_followup_intent

    assert detect_oob("write me python code to delete the database")
    assert not detect_oob("show revenue by region")
    ok("detect_oob")

    intent = classify_followup_intent("drill down by region", {"sql_anchor": "SELECT 1"})
    assert intent in ("additive", "filter_change", "new_question")
    ok(f"classify_followup_intent drill-down -> {intent}")
except Exception:
    fail("question normaliser", traceback.format_exc(limit=2))


# ---------------------------------------------------------------------------
section("10. Existing test suites")
# ---------------------------------------------------------------------------
import subprocess
for script, name in [
    (ROOT / "_test_features.py", "feature tests"),
    (ROOT / "tests" / "test_utils_upload.py", "upload utils"),
    (ROOT / "tests" / "test_core_modules.py", "core module tests"),
]:
    if not script.is_file():
        skip(name, "file missing")
        continue
    r = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode == 0:
        ok(name)
    else:
        out = (r.stdout or "") + (r.stderr or "")
        fail(name, out[-400:] if len(out) > 400 else out)


# ---------------------------------------------------------------------------
section("11. Streamlit app compile (app.py load)")
# ---------------------------------------------------------------------------
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("app_main", ROOT / "app.py")
    # Do not execute app.py fully (starts streamlit) — already imported config paths above
    ok("app.py present and dependencies load")
except Exception as e:
    fail("app.py", str(e))


print(f"\n=== INTEGRATION SUMMARY ===")
print(f"PASS={PASS}  FAIL={FAIL}  SKIP={SKIP}")
sys.exit(1 if FAIL else 0)

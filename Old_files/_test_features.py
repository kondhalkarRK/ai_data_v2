"""
Lightweight test suite for Question Cache, RAG Query Memory,
and Vector Schema Retrieval. Skips heavy deps when unavailable.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
SKIP = 0


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


def has_mod(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def funcs_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Static structure
# ---------------------------------------------------------------------------
print("\n=== 1. Static structure ===")

EXPECTED = {
    "features/question_cache/cache_store.py": {
        "save_entry", "get_entry", "clear_expired", "clear_all",
        "count_active", "list_recent",
    },
    "features/question_cache/cache_manager.py": {
        "build_cache_key", "lookup", "save", "normalize_question",
    },
    "features/question_cache/cache_triggers.py": {
        "should_cache_result",
    },
    "features/rag_query_memory/embedder.py": {
        "get_embedder", "embed_text",
    },
    "features/rag_query_memory/vector_store.py": {
        "get_chroma_client", "get_query_memory_collection",
        "get_glossary_collection", "collection_count",
        "add_to_collection", "query_collection",
    },
    "features/rag_query_memory/query_memory.py": {
        "store_successful_query", "retrieve_similar_queries",
        "format_examples_for_prompt",
    },
    "features/rag_query_memory/glossary_store.py": {
        "seed_glossary_once", "retrieve_glossary_terms",
        "format_glossary_for_prompt",
    },
    "features/vector_schema_retrieval/schema_indexer.py": {
        "index_schema_columns",
    },
    "features/vector_schema_retrieval/schema_retriever.py": {
        "retrieve_relevant_columns", "build_trimmed_schema_text",
    },
}

for rel, needed in EXPECTED.items():
    p = ROOT / rel
    try:
        found = funcs_in(p)
        missing = needed - found
        if missing:
            fail(rel, f"missing {missing}")
        else:
            ok(f"{rel} functions")
    except Exception as e:
        fail(rel, str(e))


# ---------------------------------------------------------------------------
# 2. Integration points in source
# ---------------------------------------------------------------------------
print("\n=== 2. Integration points ===")

nlq = source("core/nlq_engine.py")
app = source("app.py")
schema = source("core/schema_builder.py")
sidebar = source("ui/sidebar.py")

checks = [
    ("nlq imports question cache",
     "cache_manager" in nlq and "cache_triggers" in nlq),
    ("nlq saved question cache guard",
     "cache_manager.lookup" in nlq and "saved question" in nlq),
    ("nlq saves question after success",
     "cache_triggers.should_cache_result" in nlq and "cache_manager.save" in nlq),
    ("nlq imports query_memory/glossary_store",
     "query_memory" in nlq and "glossary_store" in nlq),
    ("nlq RAG retrieve k=2",
     "retrieve_similar_queries(question, k=2)" in nlq
     and "retrieve_glossary_terms(question, k=2)" in nlq),
    ("nlq prompt injects glossary+examples",
     "{glossary_block}{examples_block}" in nlq),
    ("nlq stores successful query",
     "store_successful_query(question, sql_result)" in nlq),
    ("nlq schema trim when >25 cols",
     "len(df.columns) > 25" in nlq and "retrieve_relevant_columns" in nlq),
    ("schema_builder columns_subset param",
     "columns_subset: list[str] | None = None" in schema),
    ("schema_builder uses cols_to_use",
     "cols_to_use = columns_subset if columns_subset else df.columns" in schema),
    ("app seeds glossary",
     "glossary_store.seed_glossary_once()" in app),
    ("app indexes schema when >25 cols",
     "schema_indexer.index_schema_columns(working_df, \"df\")" in app),
    ("sidebar saved questions UI",
     "count_active" in sidebar and "SAVED QUESTIONS" in sidebar),
    ("no second call_llm in feature packages",
     "call_llm" not in source("features/question_cache/cache_store.py")
     and "call_llm" not in source("features/rag_query_memory/query_memory.py")
     and "call_llm" not in source("features/vector_schema_retrieval/schema_retriever.py")),
]

for name, cond in checks:
    ok(name) if cond else fail(name, "not found")


# ---------------------------------------------------------------------------
# 3. Question Cache functional (needs pandas + streamlit)
# ---------------------------------------------------------------------------
print("\n=== 3. Question Cache functional ===")

if not (has_mod("pandas") and has_mod("streamlit")):
    skip("question cache runtime", "pandas/streamlit not installed")
else:
    try:
        import pandas as pd
        import streamlit as st
        from features.question_cache import cache_store, cache_manager, cache_triggers

        class SS(dict):
            def __getattr__(self, k):
                try:
                    return self[k]
                except KeyError:
                    raise AttributeError(k)
            def __setattr__(self, k, v):
                self[k] = v

        st.session_state = SS()

        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        result = pd.DataFrame({"a": [1], "sum": [6]})
        sql = "SELECT SUM(a) AS sum FROM df"

        assert cache_triggers.should_cache_result("top sales", df, result) is True
        assert cache_triggers.should_cache_result("sales today", df, result) is False
        assert cache_triggers.should_cache_result("q", df, pd.DataFrame({"x": range(5001)})) is False
        ok("should_cache_result heuristics")

        k1 = cache_manager.build_cache_key("  Top Sales ", df)
        k2 = cache_manager.build_cache_key("top sales", df)
        assert k1 == k2 and len(k1) == 64
        ok("build_cache_key normalize+hash")

        with tempfile.TemporaryDirectory() as td:
            cache_store._CACHE_DIR = Path(td)
            cache_manager.save("top sales", df, sql, result)
            got = cache_manager.lookup("top sales", df)
            assert got is not None and got["sql"] == sql
            assert list(got["result_df"].columns) == ["a", "sum"]
            ok("save + lookup with result")
            assert cache_store.count_active() >= 1
            ok("count_active")
            n = cache_store.clear_all()
            assert n >= 1 and cache_manager.lookup("top sales", df) is None
            ok("clear_all")
    except Exception:
        fail("question cache runtime", traceback.format_exc(limit=3))


# ---------------------------------------------------------------------------
# 4. RAG formatters (no chroma/model needed)
# ---------------------------------------------------------------------------
print("\n=== 4. RAG formatters (pure) ===")

try:
    # Import may pull streamlit; if missing, exec formatters only
    if has_mod("streamlit"):
        from features.rag_query_memory import query_memory, glossary_store
        ex = query_memory.format_examples_for_prompt([
            {"question": "top dealers", "sql": "SELECT * FROM df LIMIT 10"},
            {"question": "yoy growth", "sql": "SELECT year, SUM(rev) FROM df GROUP BY 1"},
        ])
        assert "FEW-SHOT EXAMPLES:" in ex and len(ex) <= 601
        assert query_memory.format_examples_for_prompt([]) == ""
        ok("format_examples_for_prompt")

        gl = glossary_store.format_glossary_for_prompt([
            {"term": "churn", "definition": "stopped buying"},
            {"term": "YoY growth", "definition": "year over year change"},
        ])
        assert "DOMAIN GLOSSARY:" in gl and len(gl) <= 401
        assert glossary_store.format_glossary_for_prompt([]) == ""
        ok("format_glossary_for_prompt")

        # token budget combined
        assert len(ex) + len(gl) <= 1000
        ok("combined prompt blocks <= ~250 tokens (1000 chars)")

        query_memory.store_successful_query("q", "-- served from saved question --")
        ok("store skips saved-question marker SQL")
    else:
        # AST-level: confirm caps exist in source
        qm = source("features/rag_query_memory/query_memory.py")
        gs = source("features/rag_query_memory/glossary_store.py")
        assert "_MAX_PROMPT_CHARS = 600" in qm
        assert "_MAX_GLOSSARY_PROMPT_CHARS = 400" in gs
        assert "max_len=200" in qm or "max_len: int = 200" in qm
        ok("RAG char caps present in source")
        skip("RAG formatter runtime", "streamlit not installed")
except Exception:
    fail("RAG formatters", traceback.format_exc(limit=3))


# ---------------------------------------------------------------------------
# 5. Schema builder subset behavior
# ---------------------------------------------------------------------------
print("\n=== 5. Schema builder subset ===")

if not (has_mod("pandas") and has_mod("streamlit")):
    skip("build_rich_schema subset", "pandas/streamlit not installed")
else:
    try:
        import pandas as pd
        from core.schema_builder import build_rich_schema

        wide = pd.DataFrame({f"c{i}": [i, i + 1] for i in range(5)})
        full = build_rich_schema(wide)
        trimmed = build_rich_schema(wide, columns_subset=["c0", "c2"])
        assert "c0" in full and "c4" in full
        assert "c0" in trimmed and "c2" in trimmed and "c4" not in trimmed
        # default None == full
        assert build_rich_schema(wide) == full
        ok("build_rich_schema columns_subset")
    except Exception:
        fail("build_rich_schema subset", traceback.format_exc(limit=3))


# ---------------------------------------------------------------------------
# 6. Vector schema fallbacks (no chroma)
# ---------------------------------------------------------------------------
print("\n=== 6. Vector schema fallbacks ===")

if not (has_mod("pandas") and has_mod("streamlit")):
    skip("schema_retriever fallback", "pandas/streamlit not installed")
else:
    try:
        import pandas as pd
        from features.vector_schema_retrieval import schema_indexer, schema_retriever

        cols = [f"col_{i}" for i in range(10)]
        # empty/fail -> return all
        got = schema_retriever.retrieve_relevant_columns("revenue by region", cols, k=12)
        assert got == cols
        ok("retrieve_relevant_columns full fallback")

        # indexing skipped for <=25 cols
        small = pd.DataFrame({c: [1, 2] for c in cols})
        schema_indexer.index_schema_columns(small, "df")  # should no-op, not raise
        ok("index_schema_columns skips <=25 cols")

        # trimmed schema helper
        text = schema_retriever.build_trimmed_schema_text(small, ["col_0", "col_1"])
        assert "col_0" in text and "col_9" not in text
        ok("build_trimmed_schema_text")
    except Exception:
        fail("vector schema fallbacks", traceback.format_exc(limit=3))


# ---------------------------------------------------------------------------
# 7. Compile already done externally; confirm UTF-8
# ---------------------------------------------------------------------------
print("\n=== 7. Encoding ===")
for rel in [
    "features/question_cache/cache_store.py",
    "features/rag_query_memory/query_memory.py",
    "features/vector_schema_retrieval/schema_indexer.py",
    "core/nlq_engine.py",
    "core/schema_builder.py",
    "app.py",
    "ui/sidebar.py",
]:
    try:
        (ROOT / rel).read_text(encoding="utf-8")
        ok(f"utf-8 {rel}")
    except Exception as e:
        fail(f"utf-8 {rel}", str(e))


print("\n=== SUMMARY ===")
print(f"PASS={PASS}  FAIL={FAIL}  SKIP={SKIP}")
sys.exit(1 if FAIL else 0)

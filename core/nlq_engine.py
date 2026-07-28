"""
core/nlq_engine.py
Semantic-first NLQ: glossary + semantic context enrich LLM SQL generation.
Deterministic sql_compiler / intent_resolver are NOT the primary path.
"""
import re
import duckdb
import pandas as pd
import streamlit as st

from core.llm_client import call_llm
from core.sql_guardrails import sql_is_safe
from core.schema_builder import build_rich_schema
from features.materialized_views import view_manager, view_triggers
from features.rag_query_memory import query_memory, glossary_store
from features.vector_schema_retrieval import schema_retriever

try:
    from core.conversation_state import (
        get_state,
        update_state,
        build_chat_context_string,
    )
    _CONV_OK = True
except ImportError:
    _CONV_OK = False

    def build_chat_context_string(n_turns=5):
        return ""

try:
    from core.evidence_builder import build_evidence
    _EVIDENCE_OK = True
except ImportError:
    _EVIDENCE_OK = False

try:
    from core.question_normaliser import detect_oob, fingerprint_question
    _CACHE_OK = True
except ImportError:
    _CACHE_OK = False

    def detect_oob(q):
        return False

    def fingerprint_question(q):
        return ""

try:
    from semantic.semantic_context_builder import get_context_builder
    _SEM_CTX_OK = True
except ImportError:
    _SEM_CTX_OK = False


def update_history(q: str, plan: dict):
    st.session_state.last_query = q
    st.session_state.last_plan = plan
    if q not in st.session_state.query_history:
        st.session_state.query_history.insert(0, q)
    st.session_state.query_history = st.session_state.query_history[:8]


def format_result_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if str(df[col].dtype).startswith("period"):
            df[col] = df[col].astype(str).str[:7]
            continue
        if df[col].dtype == object:
            sample = df[col].dropna().head(10)
            ts_count = sum(
                1 for v in sample
                if isinstance(v, str)
                and re.match(r"\d{4}-\d{2}-\d{2}", str(v))
                and len(str(v)) > 7
            )
            col_lower = col.lower()
            if ts_count >= max(1, len(sample) // 2) and any(
                x in col_lower
                for x in ["month", "period", "date", "time", "ym", "year_month"]
            ):
                df[col] = df[col].astype(str).str[:7]
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            if any(x in col.lower() for x in ["month", "period", "ym", "year_month"]):
                df[col] = df[col].dt.strftime("%Y-%m")
    return df


def nlq_to_sql(question: str, df: pd.DataFrame, status=None) -> str | None:
    """LLM SQL generation enriched by semantic layer + glossary (PRIMARY PATH)."""
    if status is not None:
        status.update(label="🔍 Building semantic context...")

    # Schema (optionally narrowed)
    if len(df.columns) > 25:
        relevant_cols = schema_retriever.retrieve_relevant_columns(
            question, list(df.columns), k=12
        )
        schema = build_rich_schema(df, columns_subset=relevant_cols)
    else:
        schema = build_rich_schema(df)

    name_cols = [
        c for c in df.columns
        if any(x in c.lower() for x in ["first", "last", "fname", "lname", "name", "full"])
    ]

    # RAG (local embeddings)
    rag_examples = query_memory.retrieve_similar_queries(question, k=2)
    rag_glossary = glossary_store.retrieve_glossary_terms(question, k=2)
    examples_block = query_memory.format_examples_for_prompt(rag_examples)
    glossary_block = glossary_store.format_glossary_for_prompt(rag_glossary)

    # Semantic + glossary enrichment (PRIMARY) — each block isolated
    semantic_context = ""
    glossary_sql_hints = ""
    domain_rules = ""
    sql_patterns_block = ""
    builder = None
    if _SEM_CTX_OK:
        try:
            builder = get_context_builder()
        except Exception:
            builder = None

    if builder is not None:
        conv = None
        chat_hist = ""
        if _CONV_OK:
            try:
                conv = get_state()
            except Exception:
                conv = None
            try:
                chat_hist = build_chat_context_string(5)
            except Exception:
                chat_hist = ""

        try:
            semantic_context = builder.build_full_context(
                question, df, conv_state=conv, chat_history=chat_hist or None
            )
        except Exception:
            semantic_context = ""

        try:
            glossary_sql_hints = builder.build_glossary_sql_hints(question)
        except Exception:
            glossary_sql_hints = ""

        try:
            domain_rules = builder.build_domain_rules_block()
        except Exception:
            domain_rules = ""

        try:
            loader = builder._loader
            patterns = loader.get_sql_patterns()
            if patterns:
                lines = ["SQL QUERY PATTERNS:"]
                for pat_name, pat_val in patterns.items():
                    if not isinstance(pat_val, dict):
                        continue
                    desc = pat_val.get("description", pat_name)
                    triggers = pat_val.get("trigger_words", [])
                    trigger_str = ", ".join(triggers[:5]) if triggers else ""
                    lines.append(
                        f"  {desc}"
                        + (f" (triggers: {trigger_str})" if trigger_str else "")
                    )
                sql_patterns_block = "\n".join(lines)
        except Exception:
            sql_patterns_block = ""

    # Caps to protect token budget
    MAX_SEM_CHARS = 3000
    if len(semantic_context) > MAX_SEM_CHARS:
        semantic_context = (
            semantic_context[:MAX_SEM_CHARS] + "\n...[context trimmed]"
        )
    if len(glossary_sql_hints) > 800:
        glossary_sql_hints = glossary_sql_hints[:800] + "\n...[hints trimmed]"
    if len(domain_rules) > 600:
        domain_rules = domain_rules[:600] + "\n...[rules trimmed]"

    # Persist for UI badges / expander
    try:
        st.session_state.last_semantic_context = semantic_context
        st.session_state.last_glossary_hints = glossary_sql_hints
        st.session_state.last_domain_rules = domain_rules
        st.session_state.last_sql_patterns = sql_patterns_block
        if builder is not None:
            try:
                st.session_state.last_glossary_matches = (
                    builder._loader.get_glossary_hints_for_question(question)
                )
            except Exception:
                st.session_state.last_glossary_matches = []
        else:
            st.session_state.last_glossary_matches = []
    except Exception:
        pass

    prompt = f"""You are an expert DuckDB SQL generator.

{semantic_context}

{glossary_sql_hints}

{domain_rules}

{sql_patterns_block}

TABLE NAME: df
{schema}
{glossary_block}{examples_block}
RULES:
1. Follow all SQL HINTS above exactly
2. Apply all DOMAIN RULES above always
3. Always SELECT meaningful labels. If first_name and last_name exist, concatenate: first_name || ' ' || last_name AS salesperson_name
4. For "best/top/worst" queries: ORDER BY metric DESC/ASC with LIMIT (default 10)
5. For trend queries: use strftime('%Y-%m', date_col) AS month — never DATE_TRUNC
6. For quarter: ((CAST(strftime('%m', sales_date) AS INTEGER)-1)/3)+1 — NEVER /4
7. For "by X and Y" queries: GROUP BY both columns
8. For count of orders: COUNT(order_id); for units: SUM(order_qty)
9. Revenue always means SUM(total_sales) — never price_per_unit
10. Always use meaningful column aliases
11. Specific values (ford, red, SUV): WHERE col ILIKE '%value%'
12. Never return more than 500 rows unless explicitly asked
13. Return ONLY the SQL string, no explanation, no markdown fences

NAME COLUMNS DETECTED: {name_cols}

QUESTION: {question}

SQL:"""

    if status is not None:
        status.update(label="✨ Generating SQL with AI...")
    sql_result = call_llm(prompt)
    if sql_result is not None:
        query_memory.store_successful_query(question, sql_result)
    return sql_result


def run_sql(sql: str, df: pd.DataFrame) -> tuple[pd.DataFrame | None, str | None]:
    safe, reason = sql_is_safe(sql)
    if not safe:
        return None, f"\U0001f512 Blocked: {reason}"
    try:
        con = duckdb.connect()
        con.register("df", df)
        result = con.execute(sql.strip()).df()
        con.close()
        result = format_result_dates(result)
        return result, None
    except Exception as e:
        return None, str(e)


def enrich_query(q: str) -> str:
    if not st.session_state.get("last_plan"):
        return q
    triggers = [
        "top", "lowest", "highest", "now", "only", "for", "in",
        "show", "filter", "same", "also",
    ]
    if any(w in q.lower() for w in triggers) and len(q.split()) <= 7:
        prev = st.session_state.get("last_query", "")
        if prev:
            return prev + " " + q
    return q


def _pack_return(result, sql, err, evidence=None):
    return result, sql, err, evidence


def run_query(working_df: pd.DataFrame, question: str, status=None):
    """
    Semantic-first query path:
      OOB → caches → nlq_to_sql (semantic enriched) → run_sql → evidence
    """
    if working_df is None or working_df.empty:
        return _pack_return(None, "", "No data loaded.", None)

    evidence = None
    execution_path = "semantic"

    try:
        if _CACHE_OK and detect_oob(question):
            evidence = (
                build_evidence("", None, "fallback", question)
                if _EVIDENCE_OK else None
            )
            return _pack_return(
                None, "",
                "out_of_scope: Question is outside the scope of this dataset analytics tool",
                evidence,
            )

        if status is not None:
            status.update(label="🧠 Loading metadata & schema...")

        cached_view = view_manager.get_or_none(question, working_df)
        if cached_view is not None:
            if status is not None:
                status.update(label="⚡ Served from cached materialized view...")
            evidence = (
                build_evidence(
                    "-- served from materialized view --",
                    cached_view, "cache", question,
                ) if _EVIDENCE_OK else None
            )
            return _pack_return(
                cached_view, "-- served from materialized view --", None, evidence
            )

        q = enrich_query(question)
        cache_key = f"nlq_{q}"
        if cache_key in st.session_state.memory:
            cached = st.session_state.memory[cache_key]
            result, sql, err = cached[0], cached[1], cached[2]
            evidence = (
                build_evidence(sql or "", result, "cache", question)
                if _EVIDENCE_OK else None
            )
            update_history(question, {"sql": sql, "evidence": evidence, "execution_path": "cache"})
            return _pack_return(result, sql, err, evidence)

        # PRIMARY: semantic-enriched LLM SQL
        sql = nlq_to_sql(q, working_df, status=status)
        if not sql:
            evidence = (
                build_evidence("", None, "fallback", question)
                if _EVIDENCE_OK else None
            )
            return _pack_return(None, "", "LLM did not return SQL.", evidence)

        sql = sql.strip().strip("`").strip()
        if sql.lower().startswith("sql"):
            sql = sql[3:].strip()

        if status is not None:
            status.update(label="⚙️ Executing query on your data...")
        result, err = run_sql(sql, working_df)

        if err and not err.startswith("\U0001f512"):
            if status is not None:
                status.update(label="🔁 Auto-fixing SQL & retrying...")
            retry_prompt = f"""The following DuckDB SQL failed with error: {err}
SQL: {sql}
Schema columns: {list(working_df.columns)}
Fix and return ONLY corrected SQL:"""
            sql2 = call_llm(retry_prompt)
            if sql2:
                sql2 = sql2.strip().strip("`").strip()
                if status is not None:
                    status.update(label="⚙️ Re-executing corrected query...")
                result, err = run_sql(sql2, working_df)
                sql = sql2

        if result is not None:
            st.session_state.memory[cache_key] = (result, sql, None)
            if view_triggers.should_materialize(question, working_df, result):
                view_manager.materialize(question, working_df, result)

            if _EVIDENCE_OK:
                evidence = build_evidence(sql, result, execution_path, question)
                evidence["resolution_source"] = "semantic_llm"

            if _CONV_OK:
                try:
                    update_state(
                        {"intent_type": "semantic_sql"},
                        {"sql": sql, "metric_name": None},
                        question,
                    )
                except Exception:
                    pass

            update_history(
                question,
                {
                    "sql": sql,
                    "evidence": evidence,
                    "execution_path": execution_path,
                },
            )
        elif _EVIDENCE_OK:
            evidence = build_evidence(sql or "", None, execution_path, question)

        return _pack_return(result, sql, err, evidence)

    except Exception as e:
        return _pack_return(
            None, "",
            f"Unexpected error while processing your question: {e}",
            None,
        )

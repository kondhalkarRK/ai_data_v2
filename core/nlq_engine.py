"""
core/nlq_engine.py
NLQ orchestration with ISANA-style conversation, semantics, and evidence.
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

# ISANA integration — graceful import fallbacks
try:
    from core.conversation_state import (
        get_state,
        update_state,
        detect_followup,
        inherit_context,
        to_context_string,
    )
    _CONV_OK = True
except ImportError:
    _CONV_OK = False

try:
    from core.semantic_resolver import resolve_semantics
    _SEM_RES_OK = True
except ImportError:
    _SEM_RES_OK = False

try:
    from core.evidence_builder import build_evidence, get_execution_badge  # noqa: F401
    _EVIDENCE_OK = True
except ImportError:
    _EVIDENCE_OK = False

try:
    from core.metric_registry import get_metric_registry  # noqa: F401
    _METRIC_OK = True
except ImportError:
    _METRIC_OK = False

try:
    from core.intent_resolver import resolve_intent
    _INTENT_OK = True
except ImportError:
    _INTENT_OK = False

try:
    from core.sql_compiler import compile_from_contract, compile_intent
    _COMPILER_OK = True
except ImportError:
    _COMPILER_OK = False

try:
    from core.intent_cache import get_cached_intent, store_intent
    from core.question_normaliser import (
        fingerprint_question,
        detect_oob,
        normalise_question,
    )
    _CACHE_OK = True
except ImportError:
    _CACHE_OK = False


# -----------------------------------------------------------------
# UTILITIES
# -----------------------------------------------------------------
def update_history(q: str, plan: dict):
    st.session_state.last_query = q
    st.session_state.last_plan = plan
    if q not in st.session_state.query_history:
        st.session_state.query_history.insert(0, q)
    st.session_state.query_history = st.session_state.query_history[:8]


# -----------------------------------------------------------------
# FORMAT RESULT DATES -> YYYY-MM
# -----------------------------------------------------------------
def format_result_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if str(df[col].dtype).startswith("period"):
            df[col] = df[col].astype(str).str[:7]
            continue
        if df[col].dtype == object:
            sample = df[col].dropna().head(10)
            ts_count = sum(
                1
                for v in sample
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
            if any(
                x in col.lower() for x in ["month", "period", "ym", "year_month"]
            ):
                df[col] = df[col].dt.strftime("%Y-%m")
    return df


# -----------------------------------------------------------------
# CORE NLQ ENGINE
# -----------------------------------------------------------------
def nlq_to_sql(question: str, df: pd.DataFrame, status=None) -> str | None:
    if status is not None:
        status.update(label="🔍 Discovering relevant schema & columns...")
    if len(df.columns) > 25:
        relevant_cols = schema_retriever.retrieve_relevant_columns(
            question, list(df.columns), k=12
        )
        schema = build_rich_schema(df, columns_subset=relevant_cols)
    else:
        schema = build_rich_schema(df)
    name_cols = [
        c
        for c in df.columns
        if any(
            x in c.lower()
            for x in ["first", "last", "fname", "lname", "name", "full"]
        )
    ]
    rag_examples = query_memory.retrieve_similar_queries(question, k=2)
    rag_glossary = glossary_store.retrieve_glossary_terms(question, k=2)
    examples_block = query_memory.format_examples_for_prompt(rag_examples)
    glossary_block = glossary_store.format_glossary_for_prompt(rag_glossary)
    prompt = f"""You are an expert DuckDB SQL generator. Given a dataset schema and a natural language question, generate the best DuckDB SQL query.

TABLE NAME: df
{schema}
{glossary_block}{examples_block}
RULES:
1. Always SELECT meaningful labels. If there are separate first_name and last_name columns, concatenate: first_name || ' ' || last_name AS salesperson_name
2. For "best/top/worst" queries: always ORDER BY metric DESC/ASC with LIMIT (default 10 if not specified)
3. For trend queries: use strftime('%Y-%m', date_col) AS month to group by month - always alias as 'month'
4. For "by X and Y" queries: GROUP BY both X and Y columns
5. For count queries: use COUNT(*) or COUNT(DISTINCT col)
6. For comparison queries (vs/compare): use CASE or multiple aggregations
7. Always use meaningful column aliases
8. If question involves a specific value (ford, red, SUV), use WHERE col ILIKE '%value%'
9. Never return more than 500 rows unless explicitly asked
10. For salesperson/person queries: combine first+last name if both exist
11. For date columns, handle NULL safely with IS NOT NULL where needed
12. Multi-column group: if user says "by brand and type", GROUP BY make, car_type
13. Return ONLY the SQL string, no explanation, no markdown fences.
14. For month/period grouping ALWAYS use strftime('%Y-%m', date_col) AS month - never DATE_TRUNC which returns timestamps

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


def _pick_date_col(df: pd.DataFrame) -> str:
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            return c
        if "date" in c.lower():
            return c
    return "sales_date"


def _pack_return(result, sql, err, evidence=None):
    """Always return 4-tuple; callers may unpack 3 or 4."""
    return result, sql, err, evidence


def run_query(working_df: pd.DataFrame, question: str, status=None):
    if working_df is None or working_df.empty:
        return _pack_return(None, "", "No data loaded.", None)

    evidence = None
    intent = None
    contract = None
    execution_path = "fallback"

    try:
        # ── Conversation / follow-up ──────────────────────────────
        conv_state = get_state() if _CONV_OK else {}
        is_followup = False
        inherited = {}
        if _CONV_OK:
            try:
                is_followup = detect_followup(question)
                if is_followup:
                    inherited = inherit_context(question)
                    conv_state["is_followup"] = True
                    conv_state["inherited_context"] = inherited
            except Exception:
                is_followup = False

        # ── OOB early exit ────────────────────────────────────────
        if _CACHE_OK and detect_oob(question):
            evidence = (
                build_evidence("", None, "fallback", question)
                if _EVIDENCE_OK
                else {
                    "execution_path": "fallback",
                    "execution_status": "error",
                    "advisory_only": True,
                }
            )
            if isinstance(evidence, dict):
                evidence["execution_path"] = "fallback"
                evidence["oob"] = True
            return _pack_return(
                None,
                "",
                "out_of_scope: Question is outside the scope of this dataset analytics tool",
                evidence,
            )

        if status is not None:
            status.update(label="🧠 Loading metadata & schema...")

        # Materialized view cache
        cached_view = view_manager.get_or_none(question, working_df)
        if cached_view is not None:
            if status is not None:
                status.update(label="⚡ Served from cached materialized view...")
            evidence = (
                build_evidence(
                    "-- served from materialized view --",
                    cached_view,
                    "cache",
                    question,
                )
                if _EVIDENCE_OK
                else None
            )
            return _pack_return(
                cached_view, "-- served from materialized view --", None, evidence
            )

        # Enrich short follow-ups with prior question context
        q = enrich_query(question)
        if is_followup and inherited and inherited.get("metric"):
            # Soft merge: append prior metric hint for downstream resolvers
            q = f"[prior_metric={inherited.get('metric')}] {q}"

        # Session result cache (Layer 1)
        cache_key = f"nlq_{q}"
        if cache_key in st.session_state.memory:
            cached = st.session_state.memory[cache_key]
            # cached may be 3-tuple or 4-tuple
            if len(cached) >= 3:
                result, sql, err = cached[0], cached[1], cached[2]
            else:
                result, sql, err = None, "", "Invalid cache entry"
            evidence = (
                build_evidence(sql or "", result, "cache", question)
                if _EVIDENCE_OK
                else None
            )
            update_history(
                question,
                {"sql": sql, "evidence": evidence, "execution_path": "cache"},
            )
            return _pack_return(result, sql, err, evidence)

        # Fingerprint + disk intent cache (Layer 2)
        fp = fingerprint_question(question) if _CACHE_OK else None
        cached_intent = get_cached_intent(fp) if (_CACHE_OK and fp) else None
        from_intent_cache = False

        if cached_intent:
            intent = cached_intent
            from_intent_cache = True
            if status is not None:
                status.update(label="🔒 Intent loaded from cache...")
        elif _INTENT_OK:
            conv_payload = {
                "to_context_string": to_context_string if _CONV_OK else (lambda: ""),
            }
            intent = resolve_intent(
                question, working_df, status=status, conv_state=conv_payload
            )
            if intent and intent.get("intent_type") == "out_of_scope":
                evidence = (
                    build_evidence("", None, "fallback", question)
                    if _EVIDENCE_OK
                    else None
                )
                if isinstance(evidence, dict):
                    evidence["oob"] = True
                return _pack_return(
                    None,
                    "",
                    "out_of_scope: "
                    + (intent.get("reason") or "Question is outside scope"),
                    evidence,
                )
            if intent and _CACHE_OK and fp:
                store_intent(fp, intent)

        sql = None

        # Semantic resolve → contract → compile
        if intent and _SEM_RES_OK and _COMPILER_OK:
            if status is not None:
                status.update(label="📐 Resolving semantics & compiling SQL...")
            contract = resolve_semantics(intent, working_df)

            if contract.get("bypass"):
                # Skip deterministic path → LLM fallback
                sql = None
            else:
                try:
                    date_col = _pick_date_col(working_df)
                    sql = compile_from_contract(contract, date_col=date_col)
                    execution_path = (
                        "cache" if from_intent_cache else "deterministic"
                    )
                    # Registry-sourced metrics count as deterministic
                    if contract.get("resolution_source") in (
                        "registry",
                        "synonym",
                    ):
                        execution_path = (
                            "cache" if from_intent_cache else "deterministic"
                        )
                    elif contract.get("resolution_source") == "llm_fallback":
                        # Still compiled deterministically from intent
                        execution_path = (
                            "cache" if from_intent_cache else "deterministic"
                        )
                except Exception:
                    sql = None

        # Fallback: LLM SQL
        if not sql:
            execution_path = "fallback"
            if status is not None:
                status.update(label="✨ Generating SQL with AI...")
            sql = nlq_to_sql(q, working_df, status=status)
            if not sql:
                evidence = (
                    build_evidence("", None, "fallback", question)
                    if _EVIDENCE_OK
                    else None
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
                execution_path = "fallback"

        if result is not None:
            st.session_state.memory[cache_key] = (result, sql, None)
            if view_triggers.should_materialize(question, working_df, result):
                view_manager.materialize(question, working_df, result)

            if _EVIDENCE_OK:
                evidence = build_evidence(sql, result, execution_path, question)
                if contract:
                    evidence["resolution_source"] = contract.get(
                        "resolution_source"
                    )
                    evidence["metric_name"] = contract.get("metric_name")
                    evidence["display_label"] = contract.get("display_label")
                    evidence["expression"] = contract.get("expression")

            if _CONV_OK:
                try:
                    resolved_for_state = dict(contract or {})
                    resolved_for_state["sql"] = sql
                    update_state(intent, resolved_for_state, question)
                except Exception:
                    pass

            update_history(
                question,
                {
                    "sql": sql,
                    "evidence": evidence,
                    "execution_path": execution_path,
                    "intent": intent,
                    "contract": contract,
                },
            )

        elif _EVIDENCE_OK:
            evidence = build_evidence(sql or "", None, execution_path, question)

        return _pack_return(result, sql, err, evidence)

    except Exception as e:
        return _pack_return(
            None,
            "",
            f"Unexpected error while processing your question: {e}",
            None,
        )

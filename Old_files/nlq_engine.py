"""
core/nlq_engine.py
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

# -----------------------------------------------------------------
# UTILITIES
# -----------------------------------------------------------------
def update_history(q: str, plan: dict):
    st.session_state.last_query = q
    st.session_state.last_plan  = plan
    if q not in st.session_state.query_history:
        st.session_state.query_history.insert(0, q)
    st.session_state.query_history = st.session_state.query_history[:8]

# -----------------------------------------------------------------
# FORMAT RESULT DATES -> YYYY-MM
# -----------------------------------------------------------------
def format_result_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if str(df[col].dtype).startswith('period'):
            df[col] = df[col].astype(str).str[:7]
            continue
        if df[col].dtype == object:
            sample = df[col].dropna().head(10)
            ts_count = sum(
                1 for v in sample
                if isinstance(v, str) and re.match(r'\d{4}-\d{2}-\d{2}', str(v)) and len(str(v)) > 7
            )
            col_lower = col.lower()
            if ts_count >= max(1, len(sample) // 2) and any(
                x in col_lower for x in ['month','period','date','time','ym','year_month']
            ):
                df[col] = df[col].astype(str).str[:7]
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            if any(x in col.lower() for x in ['month','period','ym','year_month']):
                df[col] = df[col].dt.strftime('%Y-%m')
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
    name_cols = [c for c in df.columns if any(x in c.lower() for x in
                 ["first","last","fname","lname","name","full"])]
    # LOCAL EMBEDDING - ZERO LLM COST
    rag_examples  = query_memory.retrieve_similar_queries(question, k=2)
    # LOCAL EMBEDDING - ZERO LLM COST
    rag_glossary  = glossary_store.retrieve_glossary_terms(question, k=2)
    examples_block  = query_memory.format_examples_for_prompt(rag_examples)
    glossary_block  = glossary_store.format_glossary_for_prompt(rag_glossary)
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
    triggers = ["top","lowest","highest","now","only","for","in","show","filter","same","also"]
    if any(w in q.lower() for w in triggers) and len(q.split()) <= 7:
        prev = st.session_state.get("last_query","")
        if prev:
            return prev + " " + q
    return q


def run_query(working_df: pd.DataFrame, question: str, status=None):
    if working_df is None or working_df.empty:
        return None, "", "No data loaded."
    try:
        if status is not None:
            status.update(label="🧠 Loading metadata & schema...")
        cached_view = view_manager.get_or_none(question, working_df)
        if cached_view is not None:
            if status is not None:
                status.update(label="⚡ Served from cached materialized view...")
            return cached_view, "-- served from materialized view --", None
        q = enrich_query(question)
        cache_key = f"nlq_{q}"
        if cache_key in st.session_state.memory:
            cached = st.session_state.memory[cache_key]
            update_history(question, {"sql": cached[1]})
            return cached
        sql = nlq_to_sql(q, working_df, status=status)
        if not sql:
            return None, "", "LLM did not return SQL."
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
            update_history(question, {"sql": sql})
        return result, sql, err
    except Exception as e:
        # Defensive: never let an unexpected internal failure crash the
        # calling UI — surface it as a normal query error instead.
        return None, "", f"Unexpected error while processing your question: {e}"

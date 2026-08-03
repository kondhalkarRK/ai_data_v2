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
        get_sql_anchor,
        set_sql_anchor,
        clear_sql_anchor,
        should_use_anchor,
    )
    _CONV_OK = True
except ImportError:
    _CONV_OK = False

    def build_chat_context_string(n_turns=5):
        return ""

    def get_sql_anchor():
        return None

    def set_sql_anchor(*a, **k):
        pass

    def clear_sql_anchor():
        pass

    def should_use_anchor(q):
        return False

try:
    from core.evidence_builder import build_evidence
    _EVIDENCE_OK = True
except ImportError:
    _EVIDENCE_OK = False

try:
    from core.question_normaliser import (
        detect_oob,
        classify_followup_intent,
        extract_intent_subject,
    )
    _CACHE_OK = True
except ImportError:
    _CACHE_OK = False

    def detect_oob(q):
        return False

    def classify_followup_intent(q, anchor):
        return "new_question"

    def extract_intent_subject(q, intent, df=None):
        return None

try:
    from semantic.semantic_context_builder import get_context_builder
    _SEM_CTX_OK = True
except ImportError:
    _SEM_CTX_OK = False


def update_history(q: str, plan: dict):
    st.session_state.last_query = q
    st.session_state.last_plan = plan


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


def _filter_instruction(question: str, subject: str | None) -> str:
    q = (question or "").strip().lower()
    sub = (subject or "").strip()
    year_m = re.search(r"\b(20\d{2}|19\d{2})\b", q)
    if year_m:
        y = year_m.group(1)
        return f"Add: strftime('%Y', sales_date) = '{y}'"
    if "last month" in q:
        return "Add a last-calendar-month filter on sales_date"
    if "this year" in q:
        return "Add: strftime('%Y', sales_date) = strftime('%Y', CURRENT_DATE)"
    if sub:
        # Prefer make / colour style text filters
        return f"Add: relevant dimension ILIKE '%{sub}%' (prefer make/colour_name/model/region_name)"
    return f"Apply filter from user request: {question}"


def _sort_instruction(question: str, subject: str | None) -> str:
    q = (question or "").strip().lower()
    m = re.search(r"\b(?:top|show|bottom)\s+(\d+)", q)
    if m:
        n = m.group(1)
        direction = "ASC" if "bottom" in q or "lowest" in q else "DESC"
        return f"Set LIMIT {n}; keep ORDER BY metric {direction}"
    if "order by" in q or "sort by" in q:
        return f"Replace ORDER BY with: {subject or question}"
    return f"Adjust ORDER BY / LIMIT per: {question}"


def build_modification_prompt(
    question: str,
    intent_type: str,
    subject: str | None,
    anchor: dict,
    df: pd.DataFrame,
) -> str:
    """Surgical SQL-edit prompt — modify anchor, do not rewrite from scratch."""
    base_sql = anchor.get("sql_anchor") or ""
    cols = list(df.columns)
    subject_s = subject or "(infer from question)"

    if intent_type == "additive":
        return f"""You are modifying an existing SQL query.
Add ONE thing only. Change nothing else.

EXISTING SQL (this is your base):
```sql
{base_sql}
```

TASK: Add column "{subject_s}" to the query.

STRICT RULES:
- Add "{subject_s}" to SELECT clause only
- Add "{subject_s}" to GROUP BY if it exists
- DO NOT change WHERE clause
- DO NOT change ORDER BY
- DO NOT change LIMIT
- DO NOT change any aggregations
- DO NOT add any new filters
- DO NOT remove any existing columns
- Return ONLY the modified SQL

COLUMN TO ADD: {subject_s}
TABLE: df
AVAILABLE COLUMNS: {cols}

Modified SQL:"""

    if intent_type == "subtractive":
        return f"""You are modifying an existing SQL query.
Remove ONE thing only. Change nothing else.

EXISTING SQL:
```sql
{base_sql}
```

TASK: Remove column "{subject_s}" from results.

STRICT RULES:
- Remove "{subject_s}" from SELECT only
- Remove "{subject_s}" from GROUP BY if present
- DO NOT change WHERE clause
- DO NOT change ORDER BY
- DO NOT change LIMIT
- DO NOT change any aggregations
- DO NOT add anything new
- Return ONLY the modified SQL

Modified SQL:"""

    if intent_type == "filter_change":
        filt = _filter_instruction(question, subject)
        return f"""You are modifying an existing SQL query.
Change only the filter. Keep everything else.

EXISTING SQL:
```sql
{base_sql}
```

TASK: Apply filter "{question}"

WHAT TO CHANGE: {filt}

STRICT RULES:
- Add or modify WHERE clause only
- DO NOT change SELECT columns
- DO NOT change ORDER BY
- DO NOT change LIMIT
- DO NOT change GROUP BY
- DO NOT change aggregations
- Combine with existing WHERE using AND
- Return ONLY the modified SQL
TABLE: df
AVAILABLE COLUMNS: {cols}

Modified SQL:"""

    # sort_change
    sort_i = _sort_instruction(question, subject)
    return f"""You are modifying an existing SQL query.
Change only the sort or limit.

EXISTING SQL:
```sql
{base_sql}
```

TASK: "{question}"

WHAT TO CHANGE: {sort_i}

STRICT RULES:
- Change ORDER BY or LIMIT only
- DO NOT change SELECT
- DO NOT change WHERE
- DO NOT change GROUP BY
- DO NOT change aggregations
- Return ONLY the modified SQL

Modified SQL:"""


def validate_anchor_preserved(
    new_sql: str,
    anchor: dict,
    intent_type: str,
) -> tuple[bool, str]:
    """Check that a modification kept clauses it should preserve."""
    if not new_sql or not anchor:
        return False, "missing sql or anchor"
    ns = new_sql.lower()
    filters = anchor.get("sql_anchor_filters") or []
    order = anchor.get("sql_anchor_order")
    limit = anchor.get("sql_anchor_limit")
    group = anchor.get("sql_anchor_group_by")
    cols = anchor.get("sql_anchor_columns") or []

    def _has_fragment(frag: str | None) -> bool:
        if not frag:
            return True
        # Compare loosely — strip whitespace
        key = re.sub(r"\s+", " ", frag.lower()).strip()[:80]
        return key[:40] in re.sub(r"\s+", " ", ns)

    if intent_type in ("additive", "subtractive"):
        for f in filters:
            if f and not _has_fragment(f):
                return False, f"WHERE clause lost: {f[:60]}"
        if order and "order by" in (anchor.get("sql_anchor") or "").lower():
            if "order by" not in ns:
                return False, "ORDER BY missing"
        if limit is not None and f"limit {limit}" not in ns and "limit" not in ns:
            return False, f"LIMIT {limit} missing"
        return True, ""

    if intent_type == "filter_change":
        # SELECT / ORDER / LIMIT should remain
        if order and "order by" in (anchor.get("sql_anchor") or "").lower():
            if "order by" not in ns:
                return False, "ORDER BY changed/removed"
        if limit is not None and "limit" not in ns:
            return False, "LIMIT removed"
        if group and "group by" not in ns:
            return False, "GROUP BY removed"
        return True, ""

    if intent_type == "sort_change":
        for f in filters:
            if f and not _has_fragment(f):
                return False, f"WHERE clause lost: {f[:60]}"
        if group and "group by" not in ns:
            return False, "GROUP BY removed"
        # At least one prior select column name should still appear
        if cols:
            found = sum(1 for c in cols if str(c).lower() in ns)
            if found == 0:
                return False, "SELECT columns changed"
        return True, ""

    return True, ""


def nlq_to_sql(question: str, df: pd.DataFrame, status=None) -> str | None:
    """LLM SQL generation enriched by semantic layer + glossary (PRIMARY PATH)."""
    if status is not None:
        status.update(label="🔍 Building semantic context...")

    # ── SQL-anchor routing for multi-turn continuity ─────────────
    followup_intent = "new_question"
    followup_subject = None
    anchor = None
    if _CONV_OK and _CACHE_OK:
        try:
            anchor = get_sql_anchor()
        except Exception:
            anchor = None
        if anchor and should_use_anchor(question):
            followup_intent = classify_followup_intent(question, anchor)
            followup_subject = extract_intent_subject(question, followup_intent, df)
            try:
                st.session_state["_followup_intent"] = followup_intent
                st.session_state["_followup_subject"] = followup_subject
                state = get_state()
                state["last_followup_intent"] = followup_intent
                state["last_followup_subject"] = followup_subject
            except Exception:
                pass

            if followup_intent == "new_question":
                try:
                    clear_sql_anchor()
                except Exception:
                    pass
            else:
                # Ambiguous / missing column for additive
                if followup_intent == "additive" and followup_subject:
                    cols_l = {str(c).lower() for c in df.columns}
                    if followup_subject.lower() not in cols_l and not any(
                        followup_subject.lower() in str(c).lower() for c in df.columns
                    ):
                        # Signal missing column via sentinel — caller may show chat reply
                        st.session_state["_anchor_missing_column"] = followup_subject
                        return None

                if status is not None:
                    status.update(label=f"✏️ Modifying prior SQL ({followup_intent})...")
                prompt = build_modification_prompt(
                    question, followup_intent, followup_subject, anchor, df
                )
                sql_result = call_llm(prompt)
                if sql_result:
                    sql_clean = sql_result.strip().strip("`").strip()
                    if sql_clean.lower().startswith("sql"):
                        sql_clean = sql_clean[3:].strip()
                    ok, reason = validate_anchor_preserved(
                        sql_clean, anchor, followup_intent
                    )
                    if not ok:
                        retry = (
                            prompt
                            + f"\n\nCRITICAL: Previous attempt failed validation: {reason}. "
                            f"The WHERE clause must still contain: "
                            f"{anchor.get('sql_anchor_filters')}. "
                            "Return ONLY corrected SQL."
                        )
                        sql2 = call_llm(retry)
                        if sql2:
                            sql_clean = sql2.strip().strip("`").strip()
                            if sql_clean.lower().startswith("sql"):
                                sql_clean = sql_clean[3:].strip()
                            st.session_state["_sql_retry_used"] = True
                    try:
                        st.session_state["_modification_used"] = True
                        state = get_state()
                        state["modification_depth"] = int(
                            state.get("modification_depth") or 0
                        ) + 1
                    except Exception:
                        pass
                    query_memory.store_successful_query(question, sql_clean)
                    return sql_clean

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
                    trigger_str = ", ".join(triggers[:8]) if triggers else ""
                    lines.append(f"  {pat_name}: {desc}")
                    if trigger_str:
                        lines.append(f"    triggers: {trigger_str}")
                    if pat_val.get("pattern"):
                        pat = " ".join(str(pat_val["pattern"]).split())
                        lines.append(f"    pattern: {pat}")
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
    if len(domain_rules) > 900:
        domain_rules = domain_rules[:900] + "\n...[rules trimmed]"
    if len(sql_patterns_block) > 1200:
        sql_patterns_block = sql_patterns_block[:1200] + "\n...[patterns trimmed]"

    # Persist for UI badges / expander
    try:
        st.session_state.last_semantic_context = semantic_context
        st.session_state.last_glossary_hints = glossary_sql_hints
        st.session_state.last_domain_rules = domain_rules
        st.session_state.last_sql_patterns = sql_patterns_block
        st.session_state["_modification_used"] = False
        st.session_state["_followup_intent"] = "new_question"
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

    # OKF business-document context (SOPs) — capped, optional
    okf_block = ""
    try:
        from features.okf_knowledge.okf_retriever import get_relevant_context
        okf_ctx = get_relevant_context(question, top_k=3, max_context_chars=900)
        if okf_ctx:
            okf_block = (
                "BUSINESS KNOWLEDGE (SOPs — use for metric meaning / COVID / EV / "
                "region interpretation; do NOT invent columns from documents):\n"
                f"{okf_ctx}\n\n"
            )
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
6. For quarter labels use ONLY this CASE expression (format Q1-2023, never decimals, never /3 float):
   CASE WHEN CAST(strftime('%m', sales_date) AS INTEGER) BETWEEN 1 AND 3 THEN 'Q1-' || strftime('%Y', sales_date)
        WHEN CAST(strftime('%m', sales_date) AS INTEGER) BETWEEN 4 AND 6 THEN 'Q2-' || strftime('%Y', sales_date)
        WHEN CAST(strftime('%m', sales_date) AS INTEGER) BETWEEN 7 AND 9 THEN 'Q3-' || strftime('%Y', sales_date)
        ELSE 'Q4-' || strftime('%Y', sales_date) END AS quarter
   NEVER use ((month-1)/3)+1 — DuckDB / is floating point and produces Q1.333...
7. For "by X and Y" queries: GROUP BY both columns
8. For count of orders: COUNT(order_id); for units: SUM(order_qty)
9. Revenue always means SUM(total_sales) — never price_per_unit
10. "top selling" / "best selling" / "most sold" / "top car" / "most popular" → SUM(order_qty) DESC (units), NEVER SUM(total_sales). Prefer grouping by model or carline_name (then make).
11. Always use meaningful column aliases
12. Specific values (ford, red, SUV): WHERE col ILIKE '%value%'
13. Never return more than 500 rows unless explicitly asked
14. Return ONLY the SQL string, no explanation, no markdown fences
15. Follow-up questions inherit filters/metric/dimensions from PRIOR CONTEXT / SQL ANCHOR when present
16. "gained / lost / changed most between YEAR1 and YEAR2" (e.g. units between 2021 and 2025):
    MUST return FOUR columns: [dimension], units_YEAR1, units_YEAR2, units_gained (= YEAR2 - YEAR1).
    Use SUM(CASE WHEN year=YEAR1 ...) / SUM(CASE WHEN year=YEAR2 ...) pivot — NEVER one combined total for both years.
    Default dimension = make unless the user asks for model / car_type / region.
    ORDER BY units_gained DESC LIMIT 10.
17. EV / electric vehicle / electric car / "ev car" / BEV → filter engine_type = 'Electric' (exact).
    Do NOT use Hybrid unless the user says electrified. Prefer SUM(order_qty) for EV volume/share.

NAME COLUMNS DETECTED: {name_cols}

{okf_block}QUESTION: {question}

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
    """
    Legacy string-concat enrich — only when there is NO SQL anchor.
    With an anchor, surgical modification prompts handle follow-ups;
    concatenating prior+current confuses intent and breaks memory.
    """
    if not q:
        return q
    # Prefer SQL-anchor continuity over string stitching
    try:
        if _CONV_OK and should_use_anchor(q):
            return q
        if _CONV_OK and get_sql_anchor():
            # Short relative follow-ups stay as-is; anchor path will classify
            ql = q.strip().lower()
            follow_cues = (
                "same", "also", "only", "add ", "remove ", "what about",
                "how about", "and for", "now for", "filter", "top ", "bottom ",
            )
            if any(c in ql for c in follow_cues) and len(ql.split()) <= 12:
                return q
    except Exception:
        pass

    if not st.session_state.get("last_plan"):
        return q
    triggers = [
        "now", "only", "for", "same", "also", "filter",
    ]
    # Do NOT trigger on bare "top"/"show"/"highest" — those are often new questions
    if any(w in q.lower() for w in triggers) and len(q.split()) <= 7:
        prev = st.session_state.get("last_query", "")
        if prev and prev.strip().lower() != q.strip().lower():
            return prev + " — follow-up: " + q
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
        # Keep original question for anchor classification / evidence
        st.session_state["_original_question"] = question
        cache_key = f"nlq_{question.strip().lower()}"
        if cache_key in st.session_state.memory:
            cached = st.session_state.memory[cache_key]
            result, sql, err = cached[0], cached[1], cached[2]
            evidence = (
                build_evidence(sql or "", result, "cache", question)
                if _EVIDENCE_OK else None
            )
            update_history(question, {"sql": sql, "evidence": evidence, "execution_path": "cache"})
            return _pack_return(result, sql, err, evidence)

        # PRIMARY: semantic-enriched LLM SQL (pass original for follow-up routing)
        sql = nlq_to_sql(question, working_df, status=status)
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
                try:
                    st.session_state["_sql_retry_used"] = True
                except Exception:
                    pass

        if result is not None:
            st.session_state.memory[cache_key] = (result, sql, None)
            if view_triggers.should_materialize(question, working_df, result):
                view_manager.materialize(question, working_df, result)

            if _EVIDENCE_OK:
                evidence = build_evidence(sql, result, execution_path, question)
                evidence["resolution_source"] = "semantic_llm"
                evidence["sql_retry"] = bool(st.session_state.get("_sql_retry_used"))
                evidence["modified"] = bool(st.session_state.get("_modification_used"))
                evidence["followup_intent"] = st.session_state.get("_followup_intent")
                evidence["followup_subject"] = st.session_state.get("_followup_subject")

            if _CONV_OK:
                try:
                    update_state(
                        {"intent_type": "semantic_sql"},
                        {"sql": sql, "metric_name": None},
                        question,
                    )
                    set_sql_anchor(sql, question, working_df)
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
            try:
                st.session_state["_sql_retry_used"] = False
            except Exception:
                pass
        elif _EVIDENCE_OK:
            evidence = build_evidence(sql or "", None, execution_path, question)

        # Missing-column follow-up → friendly chat signal
        missing = st.session_state.pop("_anchor_missing_column", None)
        if missing and result is None:
            avail = ", ".join(str(c) for c in list(working_df.columns)[:10])
            return _pack_return(
                None, "",
                f"missing_column:{missing}|{avail}",
                evidence,
            )

        return _pack_return(result, sql, err, evidence)

    except Exception as e:
        return _pack_return(
            None, "",
            f"Unexpected error while processing your question: {e}",
            None,
        )

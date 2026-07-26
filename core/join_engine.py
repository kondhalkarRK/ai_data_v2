"""
core/join_engine.py
"""
import duckdb
import pandas as pd
import streamlit as st

from core.utils          import norm
from core.sql_guardrails import sql_is_safe
from semantic.semantic_loader import get_semantic_loader

# ─────────────────────────────────────────────────────────────────
# COLUMN NORMALISATION HELPERS  (unchanged)
# ─────────────────────────────────────────────────────────────────
def _col_norm_map(df: pd.DataFrame) -> dict:
    return {norm(c): c for c in df.columns}


def _join_score(left_series: pd.Series, right_series: pd.Series) -> float:
    try:
        l_vals     = set(left_series.dropna().astype(str).unique())
        r_vals     = set(right_series.dropna().astype(str).unique())
        if not l_vals or not r_vals:
            return 0.0
        overlap    = len(l_vals & r_vals) / min(len(l_vals), len(r_vals))
        card_ratio = min(len(l_vals), len(r_vals)) / max(len(l_vals), len(r_vals))
        dtype_match = 1.0 if left_series.dtype == right_series.dtype else 0.7
        name_bonus  = (
            1.1 if any(
                x in norm(left_series.name)
                for x in ["id", "key", "code", "num"]
            ) else 1.0
        )
        score = overlap * 0.6 + card_ratio * 0.3 + (dtype_match - 1) * 0.1
        return round(min(score * dtype_match * name_bonus * 100, 100), 1)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────
# ORIGINAL AUTO-JOIN  (unchanged — kept as fallback)
# ─────────────────────────────────────────────────────────────────
def auto_join(
    dfs: dict,
    base_name: str | None = None,
) -> tuple[pd.DataFrame, list[dict]]:

    tables = list(dfs.items())
    if len(tables) == 1:
        return tables[0][1], []

    if base_name and base_name in dfs:
        other_tables = [(n, d) for n, d in tables if n != base_name]
        tables = [(base_name, dfs[base_name])] + other_tables

    base_name_actual, base = tables[0][0], tables[0][1].copy()
    remaining  = list(tables[1:])
    join_log   = []
    max_passes = len(remaining) + 1

    pass_num = 0
    while remaining and pass_num < max_passes:
        pass_num     += 1
        still_waiting = []

        for r_name, right in remaining:
            l_map = _col_norm_map(base)
            r_map = _col_norm_map(right)

            common_norms = set(l_map.keys()) & set(r_map.keys())

            if not common_norms:
                for lk in l_map:
                    for rk in r_map:
                        if lk in rk or rk in lk:
                            common_norms.add(lk)
                            r_map.setdefault(lk, r_map.get(rk))
                            break

            if not common_norms:
                still_waiting.append((r_name, right))
                join_log.append({
                    "left_table":  base_name_actual,
                    "right_table": r_name,
                    "left_col":    "—",
                    "right_col":   "—",
                    "score":       0,
                    "note":        f"No matching columns — deferred to pass {pass_num + 1}",
                })
                continue

            best_score, best_lc, best_rc = -1, None, None
            for n_key in common_norms:
                lc = l_map.get(n_key)
                rc = r_map.get(n_key)
                if lc and rc and lc in base.columns and rc in right.columns:
                    l_is_num = pd.api.types.is_numeric_dtype(base[lc].dtype)
                    r_is_num = pd.api.types.is_numeric_dtype(right[rc].dtype)
                    if l_is_num != r_is_num:
                        continue
                    s = _join_score(base[lc], right[rc])
                    if s > best_score:
                        best_score, best_lc, best_rc = s, lc, rc

            if best_lc is None or best_score < 5:
                still_waiting.append((r_name, right))
                join_log.append({
                    "left_table":  base_name_actual,
                    "right_table": r_name,
                    "left_col":    "—",
                    "right_col":   "—",
                    "score":       best_score,
                    "note":        f"Score too low ({best_score}) — deferred",
                })
                continue

            try:
                if base[best_lc].dtype != right[best_rc].dtype:
                    try:
                        right = right.copy()
                        right[best_rc] = right[best_rc].astype(base[best_lc].dtype)
                    except Exception:
                        pass

                merged = pd.merge(
                    base, right,
                    left_on=best_lc, right_on=best_rc,
                    how="left",
                    suffixes=("", f"_{r_name}"),
                )
                merged = merged[[
                    c for c in merged.columns
                    if not (
                        c.endswith(f"_{r_name}")
                        and c[: -len(f"_{r_name}")] in merged.columns
                    )
                ]]
                base = merged
                join_log.append({
                    "left_table":  base_name_actual,
                    "right_table": r_name,
                    "left_col":    best_lc,
                    "right_col":   best_rc,
                    "score":       best_score,
                    "note":        f"OK (pass {pass_num})",
                })
            except Exception as e:
                still_waiting.append((r_name, right))
                join_log.append({
                    "left_table":  base_name_actual,
                    "right_table": r_name,
                    "left_col":    best_lc,
                    "right_col":   best_rc,
                    "score":       best_score,
                    "note":        f"Merge error: {e}",
                })

        remaining = still_waiting

    for r_name, _ in remaining:
        already = any(
            e["right_table"] == r_name and "pass" not in e["note"]
            for e in join_log
        )
        if not already:
            join_log.append({
                "left_table":  base_name_actual,
                "right_table": r_name,
                "left_col":    "—",
                "right_col":   "—",
                "score":       0,
                "note":        "Could not join after all passes",
            })

    return base, join_log


# ─────────────────────────────────────────────────────────────────
# MANUAL JOIN  (unchanged)
# ─────────────────────────────────────────────────────────────────
def manual_join(dfs: dict, joins: dict) -> pd.DataFrame:
    if not joins:
        return list(dfs.values())[0]
    first = list(joins.values())[0]
    if first["left"] not in dfs:
        return list(dfs.values())[0]
    base = dfs[first["left"]].copy()
    for j in joins.values():
        if not j.get("left_on") or not j.get("right_on"):
            continue
        if j["right"] not in dfs:
            continue
        try:
            base = pd.merge(
                base, dfs[j["right"]],
                left_on=j["left_on"],
                right_on=j["right_on"],
                how=j.get("type", "inner"),
                suffixes=("", "_r"),
            )
            base = base[[c for c in base.columns if not c.endswith("_r")]]
        except Exception as e:
            st.warning(f"Join error: {e}")
    return base


# ─────────────────────────────────────────────────────────────────
# SQL JOIN  (unchanged)
# ─────────────────────────────────────────────────────────────────
def sql_join(dfs: dict, sql: str) -> pd.DataFrame | None:
    safe, reason = sql_is_safe(sql)
    if not safe:
        st.error(f"🔒 Blocked: {reason}")
        return None
    try:
        con = duckdb.connect()
        for name, df in dfs.items():
            con.register(name, df)
        result = con.execute(sql).df()
        con.close()
        return result
    except Exception as e:
        st.error(f"SQL join error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
# SEMANTIC JOIN HELPERS
# ─────────────────────────────────────────────────────────────────
def _match_df_to_semantic_table(df: pd.DataFrame, tables: dict) -> str | None:
    """
    Match one uploaded DataFrame to the best-fitting semantic table
    using normalised column-name overlap.
    Requires >= 40% of the semantic table's columns to be present.
    """
    df_cols_norm = set(norm(c) for c in df.columns)
    best_table   = None
    best_score   = 0.0

    for tname, tval in tables.items():
        table_cols      = tval.get("columns", {})
        table_cols_norm = set(norm(c) for c in table_cols.keys())
        if not table_cols_norm:
            continue
        overlap = len(df_cols_norm & table_cols_norm)
        score   = overlap / len(table_cols_norm)
        if score > best_score:
            best_score = score
            best_table = tname

    return best_table if best_score >= 0.4 else None


def _build_semantic_table_map(dfs: dict) -> dict:
    """
    Returns {semantic_table_key: (df_name, DataFrame)} for every
    uploaded file that matches a semantic table above the threshold.
    """
    loader       = get_semantic_loader()
    tables       = loader.get_tables()
    semantic_map = {}
    for df_name, df in dfs.items():
        matched = _match_df_to_semantic_table(df, tables)
        if matched:
            semantic_map[matched] = (df_name, df)
    return semantic_map


def _build_semantic_join_sql(
    semantic_map: dict,
) -> tuple[str | None, list[dict]]:
    """
    Builds an explicit SELECT with LEFT JOINs driven entirely by the
    relationships block in semantic_model.yaml.

    Key fix vs earlier version: uses an explicit column list instead
    of SELECT * to eliminate duplicate join-key columns in the result.
    """
    loader        = get_semantic_loader()
    tables        = loader.get_tables()
    relationships = loader.get_relationships()
    join_log: list[dict] = []

    # ── Find fact table ───────────────────────────────────────────
    fact_table_name: str | None = None
    for tname in semantic_map:
        if tables.get(tname, {}).get("type") == "fact":
            fact_table_name = tname
            break

    if fact_table_name is None:
        return None, [{
            "left_table": "—", "right_table": "—",
            "left_col": "—", "right_col": "—", "score": 0,
            "note": "No fact table matched — cannot build semantic join",
        }]

    fact_alias    = semantic_map[fact_table_name][0]
    joined_tables = {fact_table_name}
    join_clauses: list[str] = []

    # Tracks which physical columns have already been included in
    # the SELECT list so join-key duplicates are suppressed.
    included_cols: set[str] = set()

    # ── Build column SELECT list for fact table ───────────────────
    fact_df      = semantic_map[fact_table_name][1]
    select_parts = []
    for col in fact_df.columns:
        select_parts.append(f'"{fact_alias}"."{col}"')
        included_cols.add(col)

    # ── Fixed-point loop over relationships ───────────────────────
    changed = True
    while changed:
        changed = False
        for rel in relationships:
            from_t = rel["from_table"]
            to_t   = rel["to_table"]

            # Forward: joined table → new dimension
            if (
                from_t in joined_tables
                and to_t in semantic_map
                and to_t not in joined_tables
            ):
                left_alias  = semantic_map[from_t][0]
                right_alias = semantic_map[to_t][0]
                right_df    = semantic_map[to_t][1]

                join_clauses.append(
                    f'LEFT JOIN "{right_alias}" ON '
                    f'"{left_alias}"."{rel["from_column"]}" = '
                    f'"{right_alias}"."{rel["to_column"]}"'
                )

                # Add dimension columns — skip join key if already in SELECT
                for col in right_df.columns:
                    if col not in included_cols:
                        select_parts.append(f'"{right_alias}"."{col}"')
                        included_cols.add(col)

                joined_tables.add(to_t)
                join_log.append({
                    "left_table":  from_t,
                    "right_table": to_t,
                    "left_col":    rel["from_column"],
                    "right_col":   rel["to_column"],
                    "score":       100,
                    "note":        "Semantic relationship (semantic_model.yaml)",
                })
                changed = True

            # Reverse: new table references an already-joined table
            elif (
                to_t in joined_tables
                and from_t in semantic_map
                and from_t not in joined_tables
            ):
                left_alias  = semantic_map[from_t][0]
                right_alias = semantic_map[to_t][0]
                left_df     = semantic_map[from_t][1]

                join_clauses.append(
                    f'LEFT JOIN "{left_alias}" ON '
                    f'"{left_alias}"."{rel["from_column"]}" = '
                    f'"{right_alias}"."{rel["to_column"]}"'
                )

                for col in left_df.columns:
                    if col not in included_cols:
                        select_parts.append(f'"{left_alias}"."{col}"')
                        included_cols.add(col)

                joined_tables.add(from_t)
                join_log.append({
                    "left_table":  from_t,
                    "right_table": to_t,
                    "left_col":    rel["from_column"],
                    "right_col":   rel["to_column"],
                    "score":       100,
                    "note":        "Semantic relationship (semantic_model.yaml, reverse)",
                })
                changed = True

    # ── Log tables matched but unreachable via relationships ───────
    for tname in semantic_map:
        if tname not in joined_tables:
            join_log.append({
                "left_table":  fact_table_name,
                "right_table": tname,
                "left_col":    "—",
                "right_col":   "—",
                "score":       0,
                "note":        "Matched semantic table but no relationship path found — excluded",
            })

    sql = (
        f"SELECT {', '.join(select_parts)}\n"
        f'FROM "{fact_alias}"\n'
        + "\n".join(join_clauses)
    )
    return sql, join_log


# ─────────────────────────────────────────────────────────────────
# SEMANTIC AUTO-JOIN  (main entry point)
# ─────────────────────────────────────────────────────────────────
def semantic_auto_join(
    dfs: dict,
) -> tuple[pd.DataFrame | None, list[dict], str | None]:
    """
    Joins uploaded DataFrames using semantic_model.yaml relationships.
    Returns (result_df, join_log, sql_used).
    result_df is None on any failure — caller falls back to auto_join().
    """
    if not dfs:
        return None, [], None

    if len(dfs) == 1:
        return list(dfs.values())[0], [], None

    semantic_map = _build_semantic_table_map(dfs)
    if not semantic_map:
        return None, [{
            "left_table": "—", "right_table": "—",
            "left_col": "—", "right_col": "—", "score": 0,
            "note": "No uploaded files matched any table in semantic_model.yaml",
        }], None

    sql, join_log = _build_semantic_join_sql(semantic_map)
    if sql is None:
        return None, join_log, None

    safe, reason = sql_is_safe(sql)
    if not safe:
        join_log.append({
            "left_table": "—", "right_table": "—",
            "left_col": "—", "right_col": "—", "score": 0,
            "note": f"Semantic join SQL blocked by guardrails: {reason}",
        })
        return None, join_log, sql

    try:
        con = duckdb.connect()
        for df_name, df in dfs.items():
            con.register(df_name, df)
        result = con.execute(sql).df()
        con.close()
        return result, join_log, sql
    except Exception as e:
        join_log.append({
            "left_table": "—", "right_table": "—",
            "left_col": "—", "right_col": "—", "score": 0,
            "note": f"Semantic join execution error: {e}",
        })
        return None, join_log, sql


# ─────────────────────────────────────────────────────────────────
# get_working_df  (orchestrator — tries semantic first)
# ─────────────────────────────────────────────────────────────────
def get_working_df() -> pd.DataFrame | None:
    dfs = st.session_state.dfs
    if not dfs:
        return None
    if len(dfs) == 1:
        return list(dfs.values())[0]

    mode = st.session_state.join_mode

    if mode == "auto":
        sem_result, sem_log, sem_sql = semantic_auto_join(dfs)

        st.session_state.semantic_join_log = sem_log
        st.session_state.semantic_join_sql = sem_sql

        if sem_result is not None and not sem_result.empty:
            st.session_state.semantic_join_used = True
            return sem_result

        # Fallback to original fuzzy auto_join
        st.session_state.semantic_join_used = False
        base = st.session_state.get("auto_join_base") or list(dfs.keys())[0]
        df, _ = auto_join(dfs, base_name=base)
        return df

    elif mode == "manual":
        return manual_join(dfs, st.session_state.manual_joins)

    elif mode == "sql":
        sql = st.session_state.sql_join_text
        return sql_join(dfs, sql) if sql.strip() else list(dfs.values())[0]

    return list(dfs.values())[0]
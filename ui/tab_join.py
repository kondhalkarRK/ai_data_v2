"""
ui/tab_join.py
"""
import streamlit as st

from core.join_engine import (
    auto_join,
    sql_join,
    semantic_auto_join,
)


def render(working_df, tables, dfs):
    if len(dfs) == 1:
        st.info("Only one table loaded — no joining needed. Go to AI Query.")
        return

    semantic_used = st.session_state.get("semantic_join_used", None)
    semantic_loader = st.session_state.get("semantic_loader")

    if semantic_used is True:
        semantic_status = "🧠 Semantic Join Active"
        semantic_desc = "Tables joined using relationships defined in <code>semantic_model.yaml</code>."
    elif semantic_used is False:
        semantic_status = "⚠️ Fallback Join Active"
        semantic_desc = "Uploaded tables did not match semantic_model.yaml, so fuzzy join fallback is active."
    else:
        semantic_status = "⏳ Semantic Join Pending"
        semantic_desc = "Auto-join will try the semantic model first and fall back only if needed."

    loader_text = "Semantic layer unavailable"
    if semantic_loader is not None:
        try:
            table_count = len(semantic_loader.get_tables() or {})
            measure_count = len(semantic_loader.get_measures() or {})
            dim_count = len(semantic_loader.get_dimensions() or {})
            loader_text = f"Loaded {table_count} tables · {measure_count} measures · {dim_count} dimensions"
        except Exception:
            loader_text = "Semantic layer load error"

    st.markdown(
        f"<div class='status-card' style='background:#050a14;border:1px solid rgba(255,255,255,0.10);border-radius:14px;padding:14px 16px;box-shadow:0 10px 28px rgba(0,0,0,0.28);'>"
        f"<div style='font-size:13px;font-weight:800;color:#7ec8ff;margin-bottom:8px;'>{semantic_status}</div>"
        f"<div style='font-size:12px;color:#f8fafc;line-height:1.5;'>{semantic_desc}</div>"
        f"<div style='font-size:12px;color:#cbd5e1;line-height:1.5;margin-top:8px;'>{loader_text}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    mode_label = st.radio(
        "Join Method",
        ["🤖 Auto-detect (recommended)", "📝 SQL Query"],
        horizontal=True,
    )
    st.session_state.join_mode = "auto" if "Auto" in mode_label else "sql"
    st.markdown("---")

    # ─────────────────────────────────────────────────────────────
    # AUTO MODE
    # ─────────────────────────────────────────────────────────────
    if st.session_state.join_mode == "auto":

        # ── [SEMANTIC] Check if semantic join already ran via get_working_df()
        # These keys are written by get_working_df() in join_engine.py
        # before this tab renders — so we can read them directly.
        semantic_used = st.session_state.get("semantic_join_used", None)
        semantic_log  = st.session_state.get("semantic_join_log",  [])
        semantic_sql  = st.session_state.get("semantic_join_sql",  None)

        # ── Strategy description banner ───────────────────────────
        if semantic_used is True:
            st.markdown(
                "<div style='background:#050a14;border-left:4px solid #e5e7eb;"
                "padding:10px 16px;border-radius:6px;margin-bottom:12px;'>"
                "🧠 <b>Semantic Join Active</b> — tables joined using relationships "
                "defined in <code>semantic_model.yaml</code>. "
                "This is the authoritative join path for this domain."
                "</div>",
                unsafe_allow_html=True,
            )
        elif semantic_used is False:
            st.markdown(
                "<div style='background:#050a14;border-left:4px solid #e5e7eb;"
                "padding:10px 16px;border-radius:6px;margin-bottom:12px;'>"
                "⚠️ <b>Fallback Join Active</b> — uploaded files did not match "
                "tables in <code>semantic_model.yaml</code>. "
                "Using fuzzy column-name + value-overlap scoring instead."
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            # Session just started — semantic join hasn't run yet
            st.markdown(
                "Auto-join first attempts to use **semantic_model.yaml** "
                "relationships. If no match is found, it falls back to "
                "column-name similarity + value-overlap scoring."
            )

        # ── Preview button ────────────────────────────────────────
        if st.button("▶️ Preview Auto-Join"):
            with st.spinner("Running semantic join…"):
                sem_result, sem_log, sem_sql = semantic_auto_join(dfs)

            if sem_result is not None and not sem_result.empty:
                # ── Semantic join succeeded ───────────────────────
                st.session_state.semantic_join_used = True
                st.session_state.semantic_join_log  = sem_log
                st.session_state.semantic_join_sql  = sem_sql

                st.success(
                    f"✅ Semantic join — "
                    f"{sem_result.shape[0]:,} rows × {sem_result.shape[1]} cols"
                )

                # ── Show SQL that was executed ────────────────────
                if sem_sql:
                    with st.expander("🔍 Semantic Join SQL (auto-generated from semantic_model.yaml)"):
                        st.code(sem_sql, language="sql")

                # ── Join quality report ───────────────────────────
                if sem_log:
                    st.markdown("**Semantic Relationship Map**")
                    for entry in sem_log:
                        score = entry["score"]
                        icon  = "✅" if score == 100 else "❌"
                        st.markdown(
                            f"{icon} `{entry['left_table']}`.`{entry['left_col']}` "
                            f"↔ `{entry['right_table']}`.`{entry['right_col']}` "
                            f"— _{entry.get('note', '')}_",
                            unsafe_allow_html=True,
                        )

                st.dataframe(sem_result.head(100), use_container_width=True)

            else:
                # ── Semantic join failed — show fallback result ───
                st.session_state.semantic_join_used = False
                st.session_state.semantic_join_log  = sem_log
                st.session_state.semantic_join_sql  = None

                # Show why semantic join failed
                if sem_log:
                    st.warning("⚠️ Semantic join could not complete — see details below.")
                    with st.expander("🔍 Semantic Join Failure Reason"):
                        for entry in sem_log:
                            st.markdown(
                                f"❌ `{entry['left_table']}` ↔ `{entry['right_table']}` "
                                f"— {entry.get('note', '')}",
                                unsafe_allow_html=True,
                            )

                # Fall back to original fuzzy auto_join() for preview
                st.markdown(
                    "<div style='background:#050a14;border-left:4px solid #22c55e;"
                    "padding:8px 14px;border-radius:6px;'>"
                    "⚠️ Falling back to fuzzy column-match join."
                    "</div>",
                    unsafe_allow_html=True,
                )

                current_base = st.session_state.get("auto_join_base") or tables[0]
                if current_base not in tables:
                    current_base = tables[0]

                with st.spinner("Running fallback fuzzy join…"):
                    joined, join_log = auto_join(dfs, base_name=current_base)

                if joined is not None:
                    st.success(
                        f"✅ Fallback join — "
                        f"{joined.shape[0]:,} rows × {joined.shape[1]} cols"
                    )
                    # ── Fallback join quality report ──────────────
                    if join_log:
                        st.markdown("**Fallback Join Quality Report**")
                        for entry in join_log:
                            score = entry["score"]
                            cls   = (
                                "score-high" if score >= 60 else
                                "score-med"  if score >= 30 else
                                "score-low"
                            )
                            icon  = (
                                "✅" if score >= 60 else
                                "⚠️" if score >= 30 else
                                "❌"
                            )
                            st.markdown(
                                f"{icon} `{entry['left_table']}`.`{entry['left_col']}` "
                                f"↔ `{entry['right_table']}`.`{entry['right_col']}` "
                                f"— <span class='{cls}'>score {score}</span> "
                                f"&nbsp; _{entry.get('note', '')}_",
                                unsafe_allow_html=True,
                            )
                    st.dataframe(joined.head(100), use_container_width=True)

        # ── Base table selector (kept for fallback path) ──────────
        with st.expander("⚙️ Fallback Join Settings", expanded=False):
            st.caption(
                "Only used if semantic_model.yaml matching fails."
            )
            current_base = st.session_state.get("auto_join_base") or tables[0]
            if current_base not in tables:
                current_base = tables[0]
            base_choice = st.selectbox(
                "📌 Fallback Base Table",
                options=tables,
                index=tables.index(current_base),
                help="Anchor table used only when semantic join is not available.",
                key="auto_join_base_select",
            )
            st.session_state.auto_join_base = base_choice
            other_tables = [t for t in tables if t != base_choice]
            if other_tables:
                st.caption(
                    f"Will join **{', '.join(other_tables)}** onto **{base_choice}**"
                )

    # ─────────────────────────────────────────────────────────────
    # SQL MODE
    # ─────────────────────────────────────────────────────────────
    elif st.session_state.join_mode == "sql":
        st.markdown(
            "**Available tables:** " + ", ".join([f"`{t}`" for t in tables])
        )
        sql_text = st.text_area(
            "SQL Join Query",
            value=st.session_state.sql_join_text or (
                f"SELECT *\nFROM {tables[0]}\n"
                + (
                    f"LEFT JOIN {tables[1]} ON {tables[0]}.id = {tables[1]}.id"
                    if len(tables) > 1 else ""
                )
            ),
            height=140,
        )
        st.session_state.sql_join_text = sql_text
        if st.button("▶️ Execute & Preview"):
            jdf = sql_join(dfs, sql_text)
            if jdf is not None:
                st.success(f"✅ {jdf.shape[0]:,} rows × {jdf.shape[1]} cols")
                st.dataframe(jdf.head(100), use_container_width=True)
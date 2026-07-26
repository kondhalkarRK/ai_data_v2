"""
ui/tab_query.py
"""
import html
import pandas as pd
import streamlit as st

from core.nlq_engine      import run_query, run_sql
from core.sql_guardrails  import sql_is_safe
from core.chart_engine    import auto_chart_type, build_chart
from core.analysis_engine import generate_analysis


def render(working_df, tables, dfs):
    if working_df is None or working_df.empty:
        st.warning("⚠️ No data available.")
        st.stop()

    # ── [SEMANTIC #1] Read singletons from session_state ─────────
    semantic_builder  = st.session_state.get("semantic_builder", None)
    semantic_search   = st.session_state.get("semantic_search",  None)
    semantic_base_ctx = st.session_state.get("semantic_base_context", "")
    semantic_col_map  = st.session_state.get("semantic_column_map",   "")

    # ── [SEMANTIC #2] Status badge ────────────────────────────────
    if semantic_builder is not None:
        st.markdown(
            "<div style='font-size:11px;color:#6b7280;margin-bottom:4px;'>"
            "🧠 <b>Semantic layer active</b> — "
            "business glossary &amp; column mappings loaded"
            "</div>",
            unsafe_allow_html=True,
        )

    # ── Quick Filters ─────────────────────────────────────────────
    with st.expander("🎛️ Quick Filters", expanded=False):
        qf    = {}
        qcols = st.columns(4)
        idx   = 0
        cat_candidates = [
            c for c in working_df.columns
            if working_df[c].dtype == object
            and working_df[c].nunique() <= 40
        ]
        for col in cat_candidates[:3]:
            vals    = ["All"] + sorted(working_df[col].dropna().unique().tolist())
            sel_val = qcols[idx % 4].selectbox(col, vals, key=f"qf_{col}")
            if sel_val != "All":
                qf[col] = sel_val
            idx += 1

        date_cols = [
            c for c in working_df.columns
            if pd.api.types.is_datetime64_any_dtype(working_df[c])
        ]
        if date_cols:
            dc = date_cols[0]
            mn = int(working_df[dc].dt.year.min())
            mx = int(working_df[dc].dt.year.max())
            if mn < mx:
                yr = st.slider("Year Range", mn, mx, (mn, mx), key="qf_yr")
                qf["__year__"] = (dc, yr)

        if qf:
            for col, val in qf.items():
                if col == "__year__":
                    dc2, (y1, y2) = val
                    working_df = working_df[working_df[dc2].dt.year.between(y1, y2)]
                else:
                    working_df = working_df[
                        working_df[col].astype(str).str.strip().str.lower()
                        == str(val).strip().lower()
                    ]
            st.success(f"✅ Filters applied — {working_df.shape[0]:,} rows")

    _wdf = working_df
    st.markdown("---")

    # ── Query history ─────────────────────────────────────────────
    if st.session_state.query_history:
        st.markdown("**Recent Queries**")
        hcols = st.columns(min(len(st.session_state.query_history), 4))
        for i, hq in enumerate(st.session_state.query_history[:4]):
            if hcols[i].button(
                f"↩ {hq[:28]}{'…' if len(hq) > 28 else ''}",
                key=f"h{i}",
            ):
                st.session_state.query_input = hq
                st.rerun()

    st.session_state.setdefault("query_processing", False)

    # ── Input row ─────────────────────────────────────────────────
    qcol, runcol, clrcol = st.columns([8, 1, 1])
    q = qcol.text_input(
        "Ask anything",
        key="query_input",
        placeholder="e.g. top 10 salespersons by revenue",
        label_visibility="collapsed",
        disabled=st.session_state.query_processing,
    )
    run_clicked = runcol.button(
        "⏳ Running..." if st.session_state.query_processing else "▶️ Run",
        use_container_width=True,
        disabled=st.session_state.query_processing,
    )
    clr_clicked = clrcol.button(
        "🗑️ Clear",
        use_container_width=True,
        disabled=st.session_state.query_processing,
    )

    if clr_clicked:
        st.session_state.last_result        = None
        st.session_state.last_analysis      = None
        st.session_state.pending_suggestion = None
        st.rerun()

    # ── [SEMANTIC #3] Per-question enrichment helper ──────────────
    def _build_enriched_question(raw_q: str) -> tuple[str, str]:
        if semantic_builder is None or semantic_search is None:
            return raw_q, ""
        try:
            resolutions  = semantic_search.resolve_query_terms(raw_q)
            resolved_ctx = semantic_builder.build_resolved_context(
                raw_q, resolutions,
            )
            r_measures   = resolutions.get("resolved_measures",   [])
            r_dimensions = resolutions.get("resolved_dimensions", [])

            hint_parts = []
            if r_measures:
                hint_parts.append(f"measures: {', '.join(r_measures)}")
            if r_dimensions:
                hint_parts.append(f"dimensions: {', '.join(r_dimensions)}")

            enriched_q = (
                f"[Semantic hints — {'; '.join(hint_parts)}] {raw_q}"
                if hint_parts else raw_q
            )
            return enriched_q, resolved_ctx
        except Exception:
            return raw_q, ""

    # ── Trigger ───────────────────────────────────────────────────
    if run_clicked and q.strip() and not st.session_state.query_processing:
        st.session_state.query_processing     = True
        st.session_state.pending_run_question = q.strip()
        st.rerun()

    if st.session_state.pending_suggestion and not st.session_state.query_processing:
        st.session_state.query_processing     = True
        st.session_state.pending_run_question = st.session_state.pending_suggestion
        st.session_state.pending_suggestion   = None
        st.rerun()

    # ── Execute ───────────────────────────────────────────────────
    if st.session_state.query_processing and st.session_state.get("pending_run_question"):
        asked_raw = st.session_state.pending_run_question

        enriched_q, resolved_ctx = _build_enriched_question(asked_raw)
        st.session_state.last_resolved_ctx = resolved_ctx

        try:
            with st.status("🧠 Loading metadata & schema...", expanded=False) as status_box:
                result, sql, err = run_query(_wdf, enriched_q, status=status_box)
                if err:
                    status_box.update(label="⚠️ Finished with an issue", state="error")
                else:
                    status_box.update(label="✅ Query complete", state="complete")
        except Exception as e:
            result, sql, err = None, "", f"Unexpected error while running your question: {e}"

        st.session_state.last_result          = (result, sql, err, asked_raw)
        st.session_state.last_analysis        = None
        st.session_state.pending_suggestion   = None
        st.session_state.view_toggle          = "📋 Table"
        st.session_state.query_processing     = False
        st.session_state.pending_run_question = None
        st.rerun()

    st.markdown("---")

    if st.session_state.last_result is not None:
        result, sql, err, asked_q = st.session_state.last_result

        if err and result is None:
            st.error(f"❌ {err}")
            if sql:
                with st.expander("🔍 SQL Attempted"):
                    st.code(sql, language="sql")

        elif result is not None and not result.empty:
            sql_safe_preview = html.escape((sql or "").strip().replace("\n", " "))
            first80 = sql_safe_preview[:120] + (
                "…" if len(sql_safe_preview) > 120 else ""
            )
            st.markdown(
                f'<div class="sql-strip">'
                f'<span class="badge">SQL</span>'
                f'<span class="sql-text">{first80}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── [SEMANTIC #5] Resolved term badges ───────────────
            if semantic_search is not None and asked_q:
                try:
                    hits       = semantic_search.resolve_query_terms(asked_q)
                    all_res    = hits.get("all_resolutions", [])
                    confident  = [r for r in all_res if r.get("score", 0) >= 0.35]

                    if confident:
                        type_colours = {
                            "measure":   ("rgba(124,58,237,0.18)", "#c4b5fd"),
                            "dimension": ("rgba(79,124,255,0.18)", "#93c5fd"),
                            "attribute": ("rgba(0,209,122,0.16)", "#6ee7b7"),
                            "glossary":  ("rgba(251,191,36,0.16)", "#fde68a"),
                        }
                        badges = ""
                        for r in confident[:5]:
                            bg, fg = type_colours.get(
                                r["type"], ("rgba(255,255,255,0.08)", "#e2e8f0")
                            )
                            label = r["canonical"]
                            rtype = r["type"].capitalize()
                            badges += (
                                f"<span style='background:{bg};color:{fg};"
                                f"border-radius:4px;padding:2px 8px;"
                                f"font-size:11px;margin-right:4px;"
                                f"font-weight:600;'>"
                                f"{html.escape(label)}"
                                f"<span style='opacity:0.6;font-weight:400;"
                                f"margin-left:3px;'>({rtype})</span>"
                                f"</span>"
                            )
                        st.markdown(
                            f"<div style='margin-bottom:8px;'>"
                            f"🏷️ <b style='font-size:11px;color:#9db4e0;'>"
                            f"Resolved:</b> {badges}"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                except Exception:
                    pass

            # ── Edit & Re-run SQL ─────────────────────────────────
            with st.expander("✏️ View / Edit & Re-run SQL", expanded=False):
                edited_sql = st.text_area(
                    "Edit then Re-run",
                    value=(sql or "").strip(),
                    height=140,
                    key="edited_sql_area",
                )
                rcol, _ = st.columns([2, 8])
                if rcol.button("▶️ Re-run SQL", key="rerun_sql_btn"):
                    safe, reason = sql_is_safe(edited_sql.strip())
                    if not safe:
                        st.error(f"🔒 Blocked: {reason}")
                    else:
                        try:
                            with st.spinner("⚙️ Executing edited query..."):
                                new_result, new_err = run_sql(
                                    edited_sql.strip(), _wdf
                                )
                        except Exception as e:
                            new_result, new_err = None, f"Unexpected error: {e}"
                        if new_err:
                            st.error(f"SQL error: {new_err}")
                        elif new_result is not None:
                            st.session_state.last_result  = (
                                new_result, edited_sql.strip(), None, asked_q
                            )
                            st.session_state.last_analysis = None
                            st.session_state.view_toggle   = "📋 Table"
                            st.rerun()

            # ── Stat cards ────────────────────────────────────────
            num_c   = result.select_dtypes(include="number").columns.tolist()
            total_v = f"{result[num_c[0]].sum():,.1f}" if num_c else "—"
            total_l = num_c[0] if num_c else "Total"
            st.markdown(
                f"""<div class="stat-row">
                  <div class="stat-card">
                    <div class="sv">{result.shape[0]:,}</div>
                    <div class="sl">Rows</div>
                  </div>
                  <div class="stat-card">
                    <div class="sv">{result.shape[1]}</div>
                    <div class="sl">Columns</div>
                  </div>
                  <div class="stat-card">
                    <div class="sv">{total_v}</div>
                    <div class="sl">{total_l}</div>
                  </div>
                </div>""",
                unsafe_allow_html=True,
            )

            # ── Chart / Table toggle ──────────────────────────────
            view = st.radio(
                "View", ["📊 Chart", "📋 Table"],
                horizontal=True,
                key="view_toggle",
            )

            if view == "📊 Chart":
                all_cols = list(result.columns)
                num_cols = result.select_dtypes(include="number").columns.tolist()
                str_cols = result.select_dtypes(exclude="number").columns.tolist()
                ctrl_col, chart_col = st.columns([2, 8])
                auto_ct    = auto_chart_type(result, asked_q)
                chart_type = ctrl_col.selectbox(
                    "Chart Type",
                    ["Bar", "Line", "Pie", "Scatter", "Area"],
                    index=["Bar","Line","Pie","Scatter","Area"].index(auto_ct),
                    key="ct_sel",
                )
                default_x = str_cols[0] if str_cols else all_cols[0]
                default_y = num_cols[0] if num_cols else (
                    all_cols[1] if len(all_cols) > 1 else all_cols[0]
                )
                if default_x not in all_cols: default_x = all_cols[0]
                if default_y not in all_cols: default_y = all_cols[-1]
                x_axis = ctrl_col.selectbox(
                    "X Axis", all_cols,
                    index=all_cols.index(default_x), key="xa"
                )
                y_default_idx = all_cols.index(default_y)
                if default_y == x_axis and len(all_cols) > 1:
                    y_default_idx = (all_cols.index(x_axis) + 1) % len(all_cols)
                y_axis = ctrl_col.selectbox(
                    "Y Axis", all_cols,
                    index=y_default_idx, key="ya"
                )
                with chart_col:
                    if isinstance(x_axis, str) and isinstance(y_axis, str):
                        try:
                            with st.spinner("🎨 Rendering chart..."):
                                build_chart(result, chart_type, x_axis, y_axis)
                        except Exception as e:
                            st.error(f"⚠️ Chart could not be rendered: {e}")
                    else:
                        st.warning("⚠️ Please select valid X and Y columns.")
            else:
                st.dataframe(result, use_container_width=True)
                st.download_button(
                    "⬇️ Download CSV",
                    data=result.to_csv(index=False).encode(),
                    file_name="result.csv",
                    mime="text/csv",
                )

            # ── AI Analysis ───────────────────────────────────────
            st.markdown("---")
            st.markdown("##### 🧠 Insights ?*")

            if st.button("✨ Generate Analysis", use_container_width=True):
                try:
                    with st.spinner("🧠 AI is analysing your results..."):

                        resolved_ctx = st.session_state.get(
                            "last_resolved_ctx", ""
                        )

                        # CHANGED: cap each context block independently
                        # before combining to keep total prompt small
                        # and avoid LLM timeout
                        _MAX_CTX_CHARS = 800   # per context block cap

                        def _cap(text: str, limit: int = _MAX_CTX_CHARS) -> str:
                            """Trim a context block to limit characters."""
                            if not text:
                                return ""
                            return text[:limit] + (
                                "\n...[trimmed]" if len(text) > limit else ""
                            )

                        # CHANGED: cap each block then join — total context
                        # sent to LLM stays well under ~2400 chars
                        full_extra = "\n\n".join(filter(bool, [
                            _cap(semantic_base_ctx),  # static model context
                            _cap(resolved_ctx),       # per-question resolutions
                            _cap(semantic_col_map),   # physical column map
                        ]))

                        # CHANGED: also cap the result dataframe rows sent
                        # to analysis — only send top 50 rows max to LLM
                        result_for_analysis = (
                            result.head(50)
                            if len(result) > 50
                            else result
                        )

                        st.session_state.last_analysis = generate_analysis(
                            result_for_analysis,
                            asked_q,
                            extra_context=full_extra,
                        )

                except Exception as e:
                    err_str = str(e).lower()
                    # CHANGED: specific timeout message vs generic error
                    if "timed out" in err_str or "timeout" in err_str:
                        st.error(
                            "⏱️ Analysis timed out. "
                            "Try running with fewer rows or a simpler question."
                        )
                    else:
                        st.error(f"⚠️ Analysis could not be generated: {e}")

            if st.session_state.get("last_analysis"):
                ana = st.session_state.last_analysis
                sum_col, ins_col = st.columns([1, 1])

                with sum_col:
                    st.markdown("##### 📋 Summary — *What happened?*")
                    if ana.get("summary"):
                        st.markdown(
                            f"<div class='exec-box'>"
                            f"{html.escape(ana['summary'])}"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                with ins_col:
                    st.markdown("##### 💡 Key Facts")
                    if ana.get("facts"):
                        facts_html = "".join(
                            f"<div style='padding:6px 0;"
                            f"border-bottom:1px solid rgba(255,255,255,0.08);"
                            f"font-size:13px;'>"
                            f"<span style='color:#7c3aed;"
                            f"font-weight:700;'>•</span> "
                            f"{html.escape(f)}</div>"
                            for f in ana["facts"]
                        )
                        st.markdown(
                            f"<div class='exec-box' "
                            f"style='border-left-color:#7c3aed;"
                            f"padding:10px 16px;'>{facts_html}</div>",
                            unsafe_allow_html=True,
                        )

        elif result is not None and result.empty:
            st.warning("⚠️ Query returned no rows.")
            with st.expander("🔍 Generated SQL"):
                st.code(sql, language="sql")

    elif not run_clicked:
        st.markdown(
            "<div style='text-align:center;padding:56px;color:#8b949e;"
            "font-size:15px;'>💬 Type a question above and press <b>Run</b></div>",
            unsafe_allow_html=True,
        )
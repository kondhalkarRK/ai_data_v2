"""
core/data_quality_engine.py
"""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.kpi_engine import _find_col
from config.constants import _DATE_CANDIDATES

# ─────────────────────────────────────────────────────────────────
# DATA QUALITY ENGINE  (zero LLM — pure Pandas)
# ─────────────────────────────────────────────────────────────────


def _is_metric_col(col_name: str, series: pd.Series) -> bool:
    """
    Returns True only if column is a genuine business metric.
    Filters out ID, key, index and code columns.
    """
    col_lower = col_name.lower()

    # ── Explicit ID/key patterns to exclude ──────
    exclude_patterns = [
        "id", "_id", "id_", "key", "_key",
        "code", "_code", "code_",
        "index", "idx", "_idx",
        "num", "_num", "number",
        "ref", "_ref", "seq",
        "row", "record", "pk", "fk",
        # Attribute / catalogue fields — not financial metrics for outlier IQR
        "capacity", "engine", "patent",
    ]
    for pattern in exclude_patterns:
        if col_lower == pattern:                    return False
        if col_lower.endswith(f"_{pattern}"):       return False
        if col_lower.startswith(f"{pattern}_"):     return False
        if col_lower.endswith(pattern):             return False

    # ── Statistical check — IDs have near-unique values ──────
    if series.nunique() / max(len(series), 1) > 0.95:
        return False   # 95%+ unique → almost certainly an ID

    # ── IDs are usually sequential integers — check range ────
    if pd.api.types.is_integer_dtype(series):
        col_min = series.min()
        col_max = series.max()
        col_mean = series.mean()
        # If min value is 1 or 0 and values are evenly spread → ID
        if col_min >= 0 and col_max == series.nunique():
            return False

    # ── Explicit metric keywords to include ──────
    metric_patterns = [
        "sale", "sales", "revenue", "amount", "total",
        "price", "cost", "value", "profit", "margin",
        "unit", "units", "qty", "quantity", "count",
        "volume", "rate", "score", "age", "salary",
        "income", "expense", "tax", "discount", "share",
        "growth", "change", "pct", "percent", "ratio"
    ]
    for pattern in metric_patterns:
        if pattern in col_lower:
            return True

    # ── Default — if none of the above matched ───────
    # Small range of values = likely a metric not an ID
    if series.nunique() < 1000:
        return True

    return False

@st.cache_data(show_spinner=False)
def compute_data_quality(df: pd.DataFrame) -> dict:
    report = {}
    total_rows  = len(df)
    total_cells = total_rows * len(df.columns)

    null_counts = df.isnull().sum()
    null_pct    = (null_counts / total_rows * 100).round(2)
    report["null_summary"] = {
        col: {"count": int(null_counts[col]), "pct": float(null_pct[col])}
        for col in df.columns if null_counts[col] > 0
    }
    report["total_null_cells"] = int(null_counts.sum())
    report["total_null_pct"]   = round(float(null_counts.sum()) / total_cells * 100, 2)

    dup_mask = df.duplicated()
    report["duplicate_count"] = int(dup_mask.sum())
    report["duplicate_pct"]   = round(float(dup_mask.sum()) / total_rows * 100, 2)
    if dup_mask.sum() > 0:
        report["duplicate_sample"] = df[dup_mask].head(5).to_dict(orient="records")

    outlier_report = {}
    num_cols = df.select_dtypes(include="number").columns.tolist()
    for col in num_cols:
        if not _is_metric_col(col, df[col]):
            continue
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(s) < 10: continue
        Q1, Q3 = s.quantile(0.25), s.quantile(0.75)
        IQR = Q3 - Q1
        if IQR == 0: continue
        lower    = Q1 - 3.0 * IQR
        upper    = Q3 + 3.0 * IQR
        out_mask = (s < lower) | (s > upper)
        out_count = int(out_mask.sum())
        if out_count > 0:
            outlier_report[col] = {
                "count":       out_count,
                "pct":         round(out_count / len(s) * 100, 2),
                "lower_fence": round(float(lower), 2),
                "upper_fence": round(float(upper), 2),
                "min_outlier": round(float(s[out_mask].min()), 2),
                "max_outlier": round(float(s[out_mask].max()), 2),
                "sample":      [round(float(x), 2) for x in s[out_mask].head(5).tolist()],
            }
    report["outliers"] = outlier_report

    date_col     = _find_col(df, _DATE_CANDIDATES)
    spike_report = {}
    if date_col:
        try:
            tmp = df.copy()
            tmp["__dt__"] = pd.to_datetime(tmp[date_col], errors="coerce")
            tmp = tmp.dropna(subset=["__dt__"])
            tmp["__period__"] = tmp["__dt__"].dt.to_period("M")
            for col in [c for c in num_cols if _is_metric_col(c, df[c])][:6]:
                try:
                    tmp[col]     = pd.to_numeric(tmp[col], errors="coerce")
                    monthly      = tmp.groupby("__period__")[col].sum().sort_index()
                    if len(monthly) < 4: continue
                    rolling_mean = monthly.rolling(3, min_periods=2).mean().shift(1)
                    rolling_std  = monthly.rolling(3, min_periods=2).std().shift(1)
                    z_scores     = ((monthly - rolling_mean) / rolling_std.replace(0, np.nan)).abs()
                    spikes       = z_scores[z_scores > 2.5].dropna()
                    if not spikes.empty:
                        spike_report[col] = [
                            {
                                "period":    str(p),
                                "value":     round(float(monthly[p]), 2),
                                "z_score":   round(float(z_scores[p]), 2),
                                "direction": "▲ Spike UP" if monthly[p] > rolling_mean[p] else "▼ Spike DOWN",
                            }
                            for p in spikes.index
                        ]
                except Exception:
                    continue
        except Exception:
            pass
    report["spikes"]   = spike_report
    report["date_col"] = date_col

    type_issues = []
    for col in df.select_dtypes(include="object").columns:
        sample_vals = df[col].dropna().head(500)
        if len(sample_vals) == 0: continue
        numeric_convertible = pd.to_numeric(sample_vals, errors="coerce").notna().sum()
        pct_numeric         = numeric_convertible / len(sample_vals)
        if pct_numeric >= 0.85:
            type_issues.append({
                "column": col, "issue": "Stored as text but looks numeric",
                "pct_numeric": round(pct_numeric * 100, 1), "sample": sample_vals.head(3).tolist(),
            })
        date_convertible = pd.to_datetime(sample_vals, errors="coerce").notna().sum()
        pct_date         = date_convertible / len(sample_vals)
        if pct_date >= 0.85 and pct_numeric < 0.5:
            type_issues.append({
                "column": col, "issue": "Stored as text but looks like a date",
                "pct_date": round(pct_date * 100, 1), "sample": sample_vals.head(3).tolist(),
            })
    report["type_issues"] = type_issues

    cardinality_flags = []
    for col in df.select_dtypes(include="object").columns:
        uniq  = df[col].nunique()
        total = df[col].notna().sum()
        if total == 0: continue
        uniq_ratio = uniq / total
        if uniq_ratio > 0.95 and uniq > 100:
            cardinality_flags.append({"column": col, "issue": "Very high cardinality — possible free-text or ID column", "unique": uniq, "ratio": round(uniq_ratio * 100, 1)})
        elif uniq == 1:
            cardinality_flags.append({"column": col, "issue": "Only 1 unique value — constant column, no analytical value", "unique": 1, "ratio": round(uniq_ratio * 100, 1)})
        elif uniq == total and total > 50:
            cardinality_flags.append({"column": col, "issue": "All values unique — likely an ID/key column", "unique": uniq, "ratio": 100.0})
    report["cardinality_flags"] = cardinality_flags

    date_gaps = []
    if date_col:
        try:
            dt_series = pd.to_datetime(df[date_col], errors="coerce").dropna()
            if len(dt_series) >= 3:
                periods   = dt_series.dt.to_period("M").unique()
                all_range = pd.period_range(periods.min(), periods.max(), freq="M")
                missing   = all_range.difference(periods)
                if len(missing) > 0:
                    date_gaps = [str(p) for p in missing[:12]]
        except Exception:
            pass
    report["date_gaps"] = date_gaps

    score = 100.0
    score -= min(report["total_null_pct"] * 1.5, 25)
    score -= min(report["duplicate_pct"] * 2.0, 20)
    score -= min(len(outlier_report) * 3, 15)
    score -= min(len(type_issues) * 4, 16)
    score -= min(len(cardinality_flags) * 2, 10)
    score -= min(len(date_gaps) * 1, 10)
    
    report["health_score"] = max(round(score, 1), 0.0)
    report["total_rows"]   = total_rows
    report["total_cols"]   = len(df.columns)
    return report


def render_data_quality(df: pd.DataFrame, table_name: str):
    with st.spinner("Running data quality checks…"):
        dq = compute_data_quality(df)

    st.markdown("### 🔬 Data Quality Intelligence")
    st.caption("Automated data health checks — zero AI involvement. Pure statistical analysis.")

    score = dq["health_score"]
    if score >= 90:
        score_color = "#10b981"; score_label = "Excellent"; badge_cls = "dq-badge-green"
    elif score >= 70:
        score_color = "#f59e0b"; score_label = "Good"; badge_cls = "dq-badge-amber"
    elif score >= 50:
        score_color = "#f97316"; score_label = "Needs Attention"; badge_cls = "dq-badge-amber"
    else:
        score_color = "#ef4444"; score_label = "Poor Quality"; badge_cls = "dq-badge-red"

    null_pct = dq["total_null_pct"]
    null_color = "#6ee7b7" if null_pct == 0 else ("#fcd34d" if null_pct < 5 else "#fca5a5")
    dup_color = "#6ee7b7" if dq["duplicate_count"] == 0 else "#fca5a5"
    out_color = "#6ee7b7" if len(dq["outliers"]) == 0 else "#fcd34d"

    n_num = int(df.select_dtypes(include="number").shape[1])
    n_txt = int(df.select_dtypes(include=["object", "string", "category"]).shape[1])
    n_date = int(df.select_dtypes(include=["datetime", "datetimetz"]).shape[1])
    # also count parsed-looking date cols
    for c in df.columns:
        if n_date == 0 and any(x in str(c).lower() for x in ("date", "time", "year", "month")):
            n_date += 1
            break
    n_bool = int(df.select_dtypes(include="bool").shape[1])
    completeness = round(100.0 - float(null_pct), 1)

    glow = (
        "drop-shadow(0 0 12px rgba(16,185,129,0.4))" if score >= 90
        else ("drop-shadow(0 0 10px rgba(245,158,11,0.3))" if score >= 70
              else "drop-shadow(0 0 10px rgba(239,68,68,0.3))")
    )

    # 25% / 45% / 30% layout
    g_col1, g_col2, g_col3 = st.columns([25, 45, 30])
    with g_col1:
        st.markdown(
            f"<div style='text-align:center;padding:8px 0;filter:{glow};'>"
            f"<div style='font-size:52px;font-weight:900;color:{score_color};line-height:1;'>{score}%</div>"
            f"<div class='dq-health-label'>Data Health Score</div>"
            f"<div class='dq-status-pill'>{score_label}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number", value=score,
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1},
                "bar": {"color": score_color},
                "steps": [
                    {"range": [0, 50], "color": "#1c0505"},
                    {"range": [50, 70], "color": "#1c1204"},
                    {"range": [70, 100], "color": "#052e16"},
                ],
                "threshold": {
                    "line": {"color": score_color, "width": 3},
                    "thickness": 0.8, "value": score,
                },
            },
            number={"suffix": "%", "font": {"size": 22, "color": score_color}},
        ))
        fig_gauge.update_layout(
            height=150, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#8b949e"),
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

    with g_col2:
        r1 = st.columns(3)
        stats_primary = [
            (f"{dq['total_rows']:,}", "Total Rows", "#818cf8"),
            (str(dq["total_cols"]), "Columns", "#818cf8"),
            (f"{null_pct}%", "Null Rate", null_color),
        ]
        for col, (val, lab, color) in zip(r1, stats_primary):
            with col:
                st.markdown(
                    f'<div class="dq-stat-box"><div class="sv" style="color:{color}">{val}</div>'
                    f'<div class="sl">{lab}</div></div>',
                    unsafe_allow_html=True,
                )
        r2 = st.columns(2)
        stats_r2 = [
            (f"{dq['duplicate_count']:,}", "Duplicates", dup_color),
            (str(len(dq["outliers"])), "Outlier Cols", out_color),
        ]
        for col, (val, lab, color) in zip(r2, stats_r2):
            with col:
                st.markdown(
                    f'<div class="dq-stat-box" style="margin-top:8px;"><div class="sv" style="color:{color}">{val}</div>'
                    f'<div class="sl">{lab}</div></div>',
                    unsafe_allow_html=True,
                )

    with g_col3:
        secondary = [
            (f"{completeness}%", "Completeness", "#6ee7b7"),
            (str(n_num), "Numeric Cols", "#93c5fd"),
            (str(n_txt), "Text Cols", "#6ee7b7"),
            (str(n_date), "Date Cols", "#fcd34d"),
        ]
        for val, lab, color in secondary:
            st.markdown(
                f'<div class="dq-stat-box" style="margin-bottom:6px;"><div class="sv" style="color:{color}">{val}</div>'
                f'<div class="sl">{lab}</div></div>',
                unsafe_allow_html=True,
            )

    # Schema composition pills
    st.markdown(
        f'<div style="margin:10px 0 4px;font-size:11px;color:#64748b;font-weight:700;'
        f'letter-spacing:1px;text-transform:uppercase;">🔬 Schema Composition</div>'
        f'<span class="schema-pill num">Numeric: {n_num}</span>'
        f'<span class="schema-pill txt">Text: {n_txt}</span>'
        f'<span class="schema-pill date">Date: {n_date}</span>'
        f'<span class="schema-pill bool">Boolean: {n_bool}</span>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    if dq["null_summary"]:
        st.markdown(
            '<div class="dq-banner-warn">⚠️ Null values detected in some columns — review the analysis below.</div>',
            unsafe_allow_html=True,
        )
        st.markdown("#### 🕳️ Null Value Analysis")
        null_df = pd.DataFrame([
            {"Column": col, "Null Count": v["count"], "Null %": v["pct"],
             "Status": "🔴 Critical" if v["pct"] > 30 else ("🟡 Warning" if v["pct"] > 10 else "🟢 Minor")}
            for col, v in dq["null_summary"].items()
        ]).sort_values("Null %", ascending=False)
        nc1, nc2 = st.columns([3, 2])
        with nc1:
            fig_null = px.bar(
                null_df, x="Null %", y="Column", orientation="h",
                color="Null %", color_continuous_scale=["#22c55e", "#f59e0b", "#ef4444"],
                range_color=[0, 100], text="Null %", title="Missing Data % by Column",
            )
            fig_null.update_layout(
                height=max(250, len(null_df) * 32), margin=dict(l=0, r=0, t=30, b=0),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                coloraxis_showscale=False,
            )
            fig_null.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            st.plotly_chart(fig_null, use_container_width=True)
        with nc2:
            st.dataframe(null_df, use_container_width=True, hide_index=True)
        st.markdown("---")
    else:
        st.markdown(
            '<div class="dq-banner-ok">✅ No null values detected — data is complete!</div>',
            unsafe_allow_html=True,
        )

    # Column Health Report
    with st.expander("📋 Column Health Report", expanded=False):
        rows = []
        for col in list(df.columns)[:15]:
            s = df[col]
            total = max(len(s), 1)
            comp = round(100.0 * float(s.notna().sum()) / total, 1)
            if pd.api.types.is_numeric_dtype(s):
                icon = "🔢"
            elif pd.api.types.is_datetime64_any_dtype(s):
                icon = "📅"
            else:
                icon = "📝"
            if comp >= 100:
                status = "✅ Complete"
            elif comp >= 95:
                status = "🟡 Minor gaps"
            elif comp >= 80:
                status = "🟠 Gaps"
            else:
                status = "🔴 Sparse"
            rows.append({
                "Column": col,
                "Type": f"{icon} {s.dtype}",
                "Completeness %": comp,
                "Unique": int(s.nunique()),
                "Status": status,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Numeric profiles
    num_cols = df.select_dtypes(include="number").columns.tolist()[:8]
    if num_cols:
        with st.expander("📊 Numeric Column Profiles", expanded=False):
            profiles = []
            for col in num_cols:
                s = pd.to_numeric(df[col], errors="coerce").dropna()
                if s.empty:
                    continue
                mean_v = float(s.mean())
                med_v = float(s.median())
                skew_flag = "🔴 skewed" if abs(mean_v - med_v) > (abs(med_v) * 0.25 + 1e-9) else "🟢 normal"
                profiles.append({
                    "Column": col,
                    "Min": round(float(s.min()), 2),
                    "Max": round(float(s.max()), 2),
                    "Mean": round(mean_v, 2),
                    "Std Dev": round(float(s.std()), 2) if len(s) > 1 else 0,
                    "Shape": skew_flag,
                })
            if profiles:
                st.dataframe(pd.DataFrame(profiles), use_container_width=True, hide_index=True)

    # Top values
    cat_cols = [
        c for c in df.columns
        if (df[c].dtype == object or str(df[c].dtype).startswith("string"))
        and df[c].nunique() <= max(50, int(len(df) * 0.5))
    ][:5]
    if cat_cols:
        with st.expander("🏷️ Top Values by Column", expanded=False):
            for col in cat_cols:
                top = df[col].astype(str).value_counts().head(3)
                bits = " · ".join(f"**{idx}** ({cnt})" for idx, cnt in top.items())
                st.markdown(f"**{col}:** {bits}")

    st.markdown("#### 👥 Duplicate Row Detection")
    if dq["duplicate_count"] > 0:
        st.markdown(
            f'<div class="dq-banner-warn">⚠️ <b>{dq["duplicate_count"]:,} duplicate rows</b> '
            f'({dq["duplicate_pct"]}% of data). These may skew aggregations and KPIs.</div>',
            unsafe_allow_html=True,
        )
        # Top repeated values hint
        try:
            hints = []
            for c in df.columns[:12]:
                vc = df[c].astype(str).value_counts()
                if len(vc) and vc.iloc[0] > 1:
                    hints.append((c, int(vc.iloc[0])))
            hints.sort(key=lambda x: x[1], reverse=True)
            if hints:
                top_c, top_n = hints[0]
                st.caption(f"Top repeated: `{top_c}` ({top_n} times) · {dq['duplicate_pct']}% of rows are duplicates")
        except Exception:
            pass
        if "duplicate_sample" in dq:
            with st.expander("👁️ Preview Duplicate Rows"):
                st.dataframe(pd.DataFrame(dq["duplicate_sample"]), use_container_width=True, hide_index=True)
    else:
        st.markdown(
            '<div class="dq-banner-ok">🎉 Perfect — No duplicate rows</div>',
            unsafe_allow_html=True,
        )
    st.markdown("---")

    st.markdown("#### 📊 Statistical Outlier Detection")
    st.caption("Using IQR × 3.0 method — extreme values only flagged, not standard variation.")
    if dq["outliers"]:
        out_rows = [{"Column": col, "Outlier Count": info["count"], "Outlier %": info["pct"],
                     "Lower Fence": info["lower_fence"], "Upper Fence": info["upper_fence"],
                     "Min Outlier": info["min_outlier"], "Max Outlier": info["max_outlier"],
                     "Sample Values": str(info["sample"])} for col, info in dq["outliers"].items()]
        out_df = pd.DataFrame(out_rows).sort_values("Outlier %", ascending=False)
        oc1, oc2 = st.columns([2, 3])
        with oc1:
            fig_out = px.bar(out_df, x="Column", y="Outlier %", color="Outlier %",
                             color_continuous_scale=["#f59e0b","#ef4444"], text="Outlier Count", title="Outlier Count by Column")
            fig_out.update_layout(margin=dict(l=0,r=0,t=30,b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", coloraxis_showscale=False)
            st.plotly_chart(fig_out, use_container_width=True)
        with oc2:
            st.dataframe(out_df, use_container_width=True, hide_index=True)
    else:
        st.markdown(
            '<div class="dq-banner-ok">✅ No significant outliers detected across numeric columns!</div>',
            unsafe_allow_html=True,
        )
    st.markdown("---")

    st.markdown("#### 🔧 Data Type Issue Detection")
    st.caption("Columns stored in wrong format — affects calculations and joins.")
    if dq["type_issues"]:
        for issue in dq["type_issues"]:
            col_name = issue["column"]; issue_txt = issue["issue"]
            if "numeric" in issue_txt:
                pct_info = f"{issue.get('pct_numeric','')}% of values are numeric"; badge = "dq-badge-amber"; icon = "🔢"
            else:
                pct_info = f"{issue.get('pct_date','')}% of values look like dates"; badge = "dq-badge-amber"; icon = "📅"
            st.markdown(f"<div class='dq-issue-row'>{icon} <b>{col_name}</b> — <span class='{badge}'>{issue_txt}</span> &nbsp; <span style='color:#8b949e;font-size:12px;'>{pct_info} &nbsp;|&nbsp; Sample: {issue.get('sample', [])}</span></div>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:12px;color:#8b949e;margin-top:4px;'>💡 <b>Recommendation:</b> Convert these columns to their correct data types before analysis to ensure accurate aggregations and joins.</div>", unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="dq-banner-ok">✅ All columns appear to be stored in the correct data type!</div>',
            unsafe_allow_html=True,
        )
    st.markdown("---")

    st.markdown("#### 🏷️ Column Cardinality Analysis")
    st.caption("Detects columns with suspiciously high or low unique value counts.")
    if dq["cardinality_flags"]:
        card_df = pd.DataFrame([{"Column": f["column"], "Issue": f["issue"], "Unique Values": f["unique"], "Unique %": f["ratio"]} for f in dq["cardinality_flags"]])
        cc1, cc2 = st.columns([2, 3])
        with cc1:
            fig_card = px.bar(card_df, x="Column", y="Unique %", color="Unique %",
                              color_continuous_scale=["#4fc3f7","#7c3aed"], text="Unique Values", title="Unique Value % by Column")
            fig_card.update_layout(margin=dict(l=0,r=0,t=30,b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", coloraxis_showscale=False)
            st.plotly_chart(fig_card, use_container_width=True)
        with cc2:
            st.dataframe(card_df, use_container_width=True, hide_index=True)
    else:
        st.markdown(
            '<div class="dq-banner-ok">✅ All categorical columns have healthy cardinality!</div>',
            unsafe_allow_html=True,
        )
    st.markdown("---")

    st.markdown("#### 📅 Time-Series Continuity Check")
    st.caption("Checks for missing months in your date column — gaps can distort trend analysis.")
    if dq.get("date_col"):
        if dq["date_gaps"]:
            st.markdown(
                f'<div class="dq-banner-warn">⚠️ <b>{len(dq["date_gaps"])} missing month(s)</b> detected in column '
                f'`{dq["date_col"]}`. This may affect trend analysis.</div>',
                unsafe_allow_html=True,
            )
            gap_cols = st.columns(min(len(dq["date_gaps"]), 6))
            for i, gap in enumerate(dq["date_gaps"][:6]):
                gap_cols[i].markdown(f"<div class='dq-badge-red' style='text-align:center;'>📭 {gap}</div>", unsafe_allow_html=True)
            if len(dq["date_gaps"]) > 6:
                st.caption(f"… and {len(dq['date_gaps']) - 6} more missing periods.")
        else:
            st.markdown(
                f'<div class="dq-banner-ok">✅ No date gaps found in `{dq["date_col"]}` — time series is continuous!</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("ℹ️ No date column detected — skipping time-series continuity check.")
    st.markdown("---")

    st.markdown("#### 📋 Complete Issues Summary")
    all_issues = []
    for col, v in dq["null_summary"].items():
        severity = "🔴 Critical" if v["pct"] > 30 else ("🟡 Warning" if v["pct"] > 10 else "🟢 Minor")
        all_issues.append({"Column": col, "Issue": "Missing / Null Values", "Detail": f"{v['count']:,} nulls ({v['pct']}%)", "Severity": severity})
    if dq["duplicate_count"] > 0:
        all_issues.append({"Column": "— (row level)", "Issue": "Duplicate Rows", "Detail": f"{dq['duplicate_count']:,} rows ({dq['duplicate_pct']}%)", "Severity": "🔴 Critical" if dq["duplicate_pct"] > 10 else "🟡 Warning"})
    for col, info in dq["outliers"].items():
        all_issues.append({"Column": col, "Issue": "Statistical Outliers", "Detail": f"{info['count']} values outside [{info['lower_fence']}, {info['upper_fence']}]", "Severity": "🟡 Warning" if info["pct"] < 5 else "🔴 Critical"})
    for issue in dq["type_issues"]:
        all_issues.append({"Column": issue["column"], "Issue": "Data Type Mismatch", "Detail": issue["issue"], "Severity": "🟡 Warning"})
    for f in dq["cardinality_flags"]:
        all_issues.append({"Column": f["column"], "Issue": "Cardinality", "Detail": f["issue"], "Severity": "🟢 Minor"})
    for gap in dq.get("date_gaps") or []:
        all_issues.append({"Column": dq.get("date_col", "date"), "Issue": "Date Gap", "Detail": str(gap), "Severity": "🟡 Warning"})

    if all_issues:
        issues_df = pd.DataFrame(all_issues)
        sev_order = {"🔴 Critical": 0, "🟡 Warning": 1, "🟢 Minor": 2}
        issues_df["_sort"] = issues_df["Severity"].map(sev_order)
        issues_df = issues_df.sort_values("_sort").drop(columns=["_sort"])
        st.dataframe(issues_df, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download Quality Report (CSV)",
            data=issues_df.to_csv(index=False).encode(),
            file_name=f"data_quality_{table_name}.csv",
            mime="text/csv",
        )
    else:
        st.markdown(
            '<div class="dq-banner-ok">🎉 No issues found — dataset looks healthy!</div>',
            unsafe_allow_html=True,
        )
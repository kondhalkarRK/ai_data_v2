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
        "row", "record", "pk", "fk"
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
    if score >= 80:
        score_color = "#22c55e"; score_label = "Excellent";      badge_cls = "dq-badge-green"
    elif score >= 60:
        score_color = "#f59e0b"; score_label = "Needs Attention"; badge_cls = "dq-badge-amber"
    else:
        score_color = "#ef4444"; score_label = "Poor Quality";    badge_cls = "dq-badge-red"

    g_col1, g_col2, g_col3 = st.columns([1, 2, 3])
    with g_col1:
        st.markdown(
            f"<div style='text-align:center;padding:16px 0;'>"
            f"<div style='font-size:56px;font-weight:800;color:{score_color};line-height:1;'>{score}%</div>"
            f"<div style='font-size:12px;color:#8b949e;margin-top:6px;'>Data Health Score</div>"
            f"<div class='{badge_cls}' style='margin-top:8px;display:inline-block;'>{score_label}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with g_col2:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number", value=score,
            gauge={
                "axis":  {"range": [0, 100], "tickwidth": 1},
                "bar":   {"color": score_color},
                "steps": [{"range": [0,60], "color": "#1c0505"}, {"range": [60,80], "color": "#1c1204"}, {"range": [80,100], "color": "#052e16"}],
                "threshold": {"line": {"color": score_color, "width": 3}, "thickness": 0.8, "value": score},
            },
            number={"suffix": "%", "font": {"size": 28, "color": score_color}},
        ))
        fig_gauge.update_layout(height=180, margin=dict(l=10,r=10,t=20,b=10), paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#8b949e"))
        st.plotly_chart(fig_gauge, use_container_width=True)
    with g_col3:
        st.markdown(f"""
        <div class="stat-row" style="margin-top:12px;">
          <div class="stat-card"><div class="sv">{dq['total_rows']:,}</div><div class="sl">Total Rows</div></div>
          <div class="stat-card"><div class="sv">{dq['total_cols']}</div><div class="sl">Columns</div></div>
          <div class="stat-card"><div class="sv" style="color:{'#ef4444' if dq['total_null_pct']>10 else '#4fc3f7'};">{dq['total_null_pct']}%</div><div class="sl">Null Rate</div></div>
          <div class="stat-card"><div class="sv" style="color:{'#ef4444' if dq['duplicate_count']>0 else '#22c55e'};">{dq['duplicate_count']:,}</div><div class="sl">Duplicates</div></div>
          <div class="stat-card"><div class="sv" style="color:{'#f59e0b' if len(dq['outliers'])>0 else '#22c55e'};">{len(dq['outliers'])}</div><div class="sl">Outlier Cols</div></div>
        
        </div>""", unsafe_allow_html=True)

    st.markdown("---")

    if dq["null_summary"]:
        st.markdown("#### 🕳️ Null Value Analysis")
        null_df = pd.DataFrame([
            {"Column": col, "Null Count": v["count"], "Null %": v["pct"],
             "Status": "🔴 Critical" if v["pct"] > 30 else ("🟡 Warning" if v["pct"] > 10 else "🟢 Minor")}
            for col, v in dq["null_summary"].items()
        ]).sort_values("Null %", ascending=False)
        nc1, nc2 = st.columns([3, 2])
        with nc1:
            fig_null = px.bar(null_df, x="Null %", y="Column", orientation="h",
                              color="Null %", color_continuous_scale=["#22c55e","#f59e0b","#ef4444"],
                              range_color=[0,100], text="Null %", title="Missing Data % by Column")
            fig_null.update_layout(height=max(250, len(null_df)*32), margin=dict(l=0,r=0,t=30,b=0),
                                   paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", coloraxis_showscale=False)
            fig_null.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            st.plotly_chart(fig_null, use_container_width=True)
        with nc2:
            st.dataframe(null_df, use_container_width=True, hide_index=True)
        st.markdown("---")
    else:
        st.success("✅ No null values detected — data is complete!")
        st.markdown("---")

    st.markdown("#### 👥 Duplicate Row Detection")
    if dq["duplicate_count"] > 0:
        st.warning(f"⚠️ **{dq['duplicate_count']:,} duplicate rows** found ({dq['duplicate_pct']}% of data). These may skew aggregations and KPIs.")
        if "duplicate_sample" in dq:
            with st.expander("👁️ Preview Duplicate Rows"):
                st.dataframe(pd.DataFrame(dq["duplicate_sample"]), use_container_width=True, hide_index=True)
    else:
        st.success("✅ No duplicate rows found — data is unique!")
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
        st.success("✅ No significant outliers detected across numeric columns!")
    st.markdown("---")

    # st.markdown("#### ⚡ Time-Series Spike Detection")
    # st.caption("Flags months where values deviate > 2.5 standard deviations from rolling average.")
    # if dq["spikes"]:
    #     for col, spike_list in dq["spikes"].items():
    #         with st.expander(f"📌 **{col}** — {len(spike_list)} spike(s) detected", expanded=True):
    #             spike_df = pd.DataFrame(spike_list)
    #             spike_df.columns = ["Period","Value","Z-Score","Direction"]
    #             sc1, sc2 = st.columns([3, 2])
    #             with sc1:
    #                 fig_spike = px.bar(spike_df, x="Period", y="Value", color="Z-Score",
    #                                    color_continuous_scale=["#f59e0b","#ef4444"], text="Direction", title=f"Spikes in {col}")
    #                 fig_spike.update_layout(margin=dict(l=0,r=0,t=30,b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", coloraxis_showscale=False)
    #                 st.plotly_chart(fig_spike, use_container_width=True)
    #             with sc2:
    #                 st.dataframe(spike_df, use_container_width=True, hide_index=True)
    # else:
    #     st.success("✅ No unusual spikes detected in time-series columns!")
    # st.markdown("---")

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
        st.success("✅ All columns appear to be stored in the correct data type!")
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
        st.success("✅ All categorical columns have healthy cardinality!")
    st.markdown("---")

    st.markdown("#### 📅 Time-Series Continuity Check")
    st.caption("Checks for missing months in your date column — gaps can distort trend analysis.")
    if dq.get("date_col"):
        if dq["date_gaps"]:
            st.warning(f"⚠️ **{len(dq['date_gaps'])} missing month(s)** detected in column `{dq['date_col']}`. This may affect trend analysis and forecasting accuracy.")
            gap_cols = st.columns(min(len(dq["date_gaps"]), 6))
            for i, gap in enumerate(dq["date_gaps"][:6]):
                gap_cols[i].markdown(f"<div class='dq-badge-red' style='text-align:center;'>📭 {gap}</div>", unsafe_allow_html=True)
            if len(dq["date_gaps"]) > 6:
                st.caption(f"… and {len(dq['date_gaps']) - 6} more missing periods.")
            st.markdown("<div style='font-size:12px;color:#8b949e;margin-top:8px;'>💡 <b>Recommendation:</b> Fill missing periods with zero values or interpolated estimates before running time-series analysis.</div>", unsafe_allow_html=True)
        else:
            st.success(f"✅ No date gaps found in `{dq['date_col']}` — time series is continuous!")
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
    # for col, spike_list in dq["spikes"].items():
    #     for sp in spike_list:
    #         all_issues.append({"Column": col, "Issue": "Time-Series Spike", "Detail": f"{sp['period']} — value {sp['value']:,} (Z={sp['z_score']}) {sp['direction']}", "Severity": "🟡 Warning"})
    for issue in dq["type_issues"]:
        all_issues.append({"Column": issue["column"], "Issue": "Data Type Mismatch", "Detail": issue["issue"], "Severity": "🟡 Warning"})
    for flag in dq["cardinality_flags"]:
        all_issues.append({"Column": flag["column"], "Issue": "Cardinality Anomaly", "Detail": flag["issue"], "Severity": "🟢 Minor"})
    for gap in dq["date_gaps"]:
        all_issues.append({"Column": dq.get("date_col","date"), "Issue": "Date Gap", "Detail": f"Missing period: {gap}", "Severity": "🟡 Warning"})

    if all_issues:
        issues_df = pd.DataFrame(all_issues)
        sev_order = {"🔴 Critical": 0, "🟡 Warning": 1, "🟢 Minor": 2}
        issues_df["_sort"] = issues_df["Severity"].map(sev_order)
        issues_df = issues_df.sort_values("_sort").drop(columns=["_sort"])
        st.dataframe(issues_df, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Download Quality Report (CSV)", data=issues_df.to_csv(index=False).encode(), file_name=f"data_quality_{table_name}.csv", mime="text/csv")
    else:
        st.success("🎉 No issues found — this dataset is in excellent shape!")

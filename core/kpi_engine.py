"""
core/kpi_engine.py
"""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from core.utils import norm
from config.constants import (
    _REV_CANDIDATES, _VOL_CANDIDATES, _DATE_CANDIDATES, _SEG_CANDIDATES,
    _MODEL_CANDIDATES, _REGION_CANDIDATES, _SALES_CANDIDATES, _MKTSH_CANDIDATES,
    _FIRST_NAME_CANDIDATES, _LAST_NAME_CANDIDATES,
)

# ─────────────────────────────────────────────────────────────────
# KPI ENGINE — helpers
# ─────────────────────────────────────────────────────────────────
def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    col_norms = {norm(c): c for c in df.columns}
    for cand in candidates:
        if norm(cand) in col_norms:
            return col_norms[norm(cand)]
    for cand in candidates:
        for c in df.columns:
            if cand in norm(c):
                return c
    return None

def _safe_sum(series: pd.Series) -> float:
    try:
        return float(pd.to_numeric(series, errors="coerce").dropna().sum())
    except Exception:
        return 0.0

def _fmt_currency(v: float) -> str:
    if v >= 1_000_000_000: return f"₹{v/1_000_000_000:.2f}B"
    if v >= 1_000_000:     return f"₹{v/1_000_000:.2f}M"
    if v >= 1_000:         return f"₹{v/1_000:.1f}K"
    return f"₹{v:,.0f}"

def _fmt_number(v: float) -> str:
    if v >= 1_000_000: return f"{v/1_000_000:.2f}M"
    if v >= 1_000:     return f"{v/1_000:.1f}K"
    return f"{v:,.0f}"

# ─────────────────────────────────────────────────────────────────
# KPI ENGINE
# ─────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)  
def compute_kpis(df: pd.DataFrame) -> dict:
    kpis = {}
    rev_col    = _find_col(df, _REV_CANDIDATES)
    vol_col    = _find_col(df, _VOL_CANDIDATES)
    date_col   = _find_col(df, _DATE_CANDIDATES)
    seg_col    = _find_col(df, _SEG_CANDIDATES)
    model_col  = _find_col(df, _MODEL_CANDIDATES)
    region_col = _find_col(df, _REGION_CANDIDATES)
    sales_col  = _find_col(df, _SALES_CANDIDATES)
    mktsh_col  = _find_col(df, _MKTSH_CANDIDATES)
    first_name_col = _find_col(df, _FIRST_NAME_CANDIDATES)
    last_name_col  = _find_col(df, _LAST_NAME_CANDIDATES)

    if rev_col:
        kpis["revenue"] = _safe_sum(df[rev_col]); kpis["revenue_col"] = rev_col
    if vol_col:
        kpis["units_sold"] = _safe_sum(df[vol_col]); kpis["vol_col"] = vol_col

    if date_col and (sales_col or first_name_col) and (rev_col or vol_col):
        try:
            metric_col = rev_col or vol_col
            tmp = df.copy()
            tmp["__dt__"] = pd.to_datetime(tmp[date_col], errors="coerce")
            tmp[metric_col] = pd.to_numeric(tmp[metric_col], errors="coerce")
            tmp = tmp.dropna(subset=["__dt__", metric_col])
            latest_month = tmp["__dt__"].dt.to_period("M").max()
            month_df = tmp[tmp["__dt__"].dt.to_period("M") == latest_month]
            if not month_df.empty:
                if first_name_col and last_name_col and first_name_col in month_df.columns and last_name_col in month_df.columns:
                    month_df = month_df.copy()
                    month_df["__full_name__"] = (month_df[first_name_col].fillna("").astype(str).str.strip() + " " + month_df[last_name_col].fillna("").astype(str).str.strip()).str.strip()
                    sp_col = "__full_name__"
                elif first_name_col and first_name_col in month_df.columns:
                    sp_col = first_name_col
                else:
                    sp_col = sales_col
                best_sp = month_df.groupby(sp_col)[metric_col].sum().idxmax()
                kpis["best_salesperson"] = str(best_sp)
                kpis["best_salesperson_month"] = str(latest_month)
        except Exception:
            pass

    if date_col and (rev_col or vol_col):
        try:
            tmp = df.copy()
            tmp["__year__"] = pd.to_datetime(tmp[date_col], errors="coerce").dt.year
            metric_col = rev_col or vol_col
            yearly = (tmp.groupby("__year__")[metric_col].apply(lambda s: pd.to_numeric(s, errors="coerce").sum()).sort_index())
            if len(yearly) >= 2:
                cy = float(yearly.iloc[-1]); py = float(yearly.iloc[-2])
                kpis["yoy_growth"]    = ((cy - py) / py * 100) if py else None
                kpis["yoy_curr_year"] = int(yearly.index[-1])
        except Exception:
            pass

    if mktsh_col:
        try:
            kpis["market_share"] = float(pd.to_numeric(df[mktsh_col], errors="coerce").dropna().mean())
        except Exception:
            pass

    # Top model is a VOLUME KPI — always rank by units (order_qty), never revenue
    if model_col and vol_col:
        try:
            tmp = df.copy()
            tmp[vol_col] = pd.to_numeric(tmp[vol_col], errors="coerce")
            by_vol = tmp.groupby(model_col)[vol_col].sum().sort_values(ascending=False)
            kpis["top_model"] = str(by_vol.index[0])
            kpis["top_model_units"] = int(by_vol.iloc[0])
            kpis["top_model_by"] = "volume"
        except Exception:
            pass
    elif model_col and rev_col:
        try:
            tmp = df.copy()
            tmp[rev_col] = pd.to_numeric(tmp[rev_col], errors="coerce")
            kpis["top_model"] = str(tmp.groupby(model_col)[rev_col].sum().idxmax())
            kpis["top_model_by"] = "revenue_fallback"
        except Exception:
            pass

    if region_col:
        try: kpis["active_regions"] = int(df[region_col].nunique())
        except Exception: pass

    # ── Extra KPI cards (UI upgrade) ─────────────────────────────
    order_col = _find_col(df, ["order_id", "orderid", "orders", "transaction_id"])
    colour_col = _find_col(df, ["colour_name", "color_name", "colour", "color"])
    make_col = _find_col(df, ["make", "brand", "manufacturer"])

    n_orders = None
    if order_col:
        try:
            n_orders = int(df[order_col].nunique())
            kpis["total_orders"] = n_orders
        except Exception:
            n_orders = len(df)
            kpis["total_orders"] = n_orders
    else:
        n_orders = len(df)

    if rev_col and n_orders:
        try:
            kpis["avg_order_value"] = float(kpis.get("revenue", 0) or 0) / max(n_orders, 1)
            kpis["avg_order_n"] = n_orders
        except Exception:
            pass

    if rev_col and vol_col and kpis.get("units_sold"):
        try:
            units = float(kpis["units_sold"])
            if units:
                kpis["rev_per_unit"] = float(kpis.get("revenue", 0) or 0) / units
        except Exception:
            pass

    if colour_col and rev_col:
        try:
            tmp = df.copy()
            tmp[rev_col] = pd.to_numeric(tmp[rev_col], errors="coerce")
            kpis["top_colour"] = str(tmp.groupby(colour_col)[rev_col].sum().idxmax())
        except Exception:
            pass

    if make_col and vol_col:
        try:
            tmp = df.copy()
            tmp[vol_col] = pd.to_numeric(tmp[vol_col], errors="coerce")
            kpis["top_make"] = str(tmp.groupby(make_col)[vol_col].sum().idxmax())
        except Exception:
            pass
    elif make_col and rev_col:
        try:
            tmp = df.copy()
            tmp[rev_col] = pd.to_numeric(tmp[rev_col], errors="coerce")
            kpis["top_make"] = str(tmp.groupby(make_col)[rev_col].sum().idxmax())
        except Exception:
            pass

    if date_col:
        try:
            dts = pd.to_datetime(df[date_col], errors="coerce").dropna()
            if not dts.empty:
                dmin, dmax = dts.min(), dts.max()
                kpis["date_range"] = f"{dmin.strftime('%b %Y')} — {dmax.strftime('%b %Y')}"
                kpis["date_range_raw"] = (dmin, dmax)
        except Exception:
            pass

    if seg_col and vol_col:
        try:
            tmp = df.copy(); tmp[vol_col] = pd.to_numeric(tmp[vol_col], errors="coerce")
            seg_totals = tmp.groupby(seg_col)[vol_col].sum().sort_values(ascending=False)
            grand = seg_totals.sum()
            if grand > 0:
                kpis["segment_mix"] = {str(k): {"units": float(v), "pct": round(float(v)/grand*100, 1)} for k, v in seg_totals.items()}
        except Exception:
            pass

    if model_col and rev_col:
        try:
            tmp = df.copy(); tmp[rev_col] = pd.to_numeric(tmp[rev_col], errors="coerce")
            m5 = tmp.groupby(model_col)[rev_col].sum().nlargest(5)
            total_rev = kpis.get("revenue", m5.sum()) or m5.sum()
            kpis["top5_models"] = [{"model": str(k), "revenue": float(v), "pct": round(float(v)/total_rev*100,1) if total_rev else 0} for k, v in m5.items()]
        except Exception:
            pass

    if seg_col and date_col and (vol_col or rev_col):
        try:
            metric_col = vol_col or rev_col
            tmp = df.copy()
            tmp["__year__"] = pd.to_datetime(tmp[date_col], errors="coerce").dt.year
            tmp[metric_col] = pd.to_numeric(tmp[metric_col], errors="coerce")
            years = sorted(tmp["__year__"].dropna().unique())
            if len(years) >= 2:
                cy, py = years[-1], years[-2]
                curr = tmp[tmp["__year__"]==cy].groupby(seg_col)[metric_col].sum()
                prev = tmp[tmp["__year__"]==py].groupby(seg_col)[metric_col].sum()
                growth = ((curr - prev) / prev.replace(0, np.nan) * 100).dropna()
                if not growth.empty:
                    kpis["fastest_seg"] = str(growth.idxmax()); kpis["fastest_seg_pct"] = round(float(growth.max()), 1)
        except Exception:
            pass

    kpis["_date_col"] = date_col; kpis["_rev_col"] = rev_col
    kpis["_vol_col"]  = vol_col;  kpis["_model_col"] = model_col; kpis["_region_col"] = region_col
    return kpis


def _kpi_card_html(
    label: str,
    value: str,
    sub: str,
    accent: str,
    delay: float = 0.0,
    trend: str | None = None,
    trend_up: bool | None = None,
    featured: bool = False,
) -> str:
    trend_html = ""
    if trend:
        cls = "up" if trend_up else "down"
        trend_html = f'<div class="kpi-trend {cls}">{trend}</div>'
    feat = " kpi-featured" if featured else ""
    return (
        f'<div class="kpi-card kpi-anim accent-{accent}{feat}" '
        f'style="animation-delay:{delay:.2f}s">'
        f'<div class="kpi-accent"></div>{trend_html}'
        f'<div class="kv">{value}</div>'
        f'<div class="kl">{label}</div>'
        f'<div class="ks">{sub}</div>'
        f"</div>"
    )


def render_kpi_tab(df: pd.DataFrame):
    if df is None or df.empty:
        st.warning("No data available for KPI analysis.")
        return

    date_col_detect = _find_col(df, _DATE_CANDIDATES)
    filtered_df = df.copy()

    if date_col_detect:
        try:
            filtered_df[date_col_detect] = pd.to_datetime(
                filtered_df[date_col_detect], errors="coerce"
            )
            all_years = sorted(
                filtered_df[date_col_detect].dt.year.dropna().unique().astype(int).tolist()
            )
            month_names = {
                1: "January", 2: "February", 3: "March", 4: "April",
                5: "May", 6: "June", 7: "July", 8: "August",
                9: "September", 10: "October", 11: "November", 12: "December",
            }
            all_months_in_data = sorted(
                filtered_df[date_col_detect].dt.month.dropna().unique().astype(int).tolist()
            )
            st.markdown('<div class="kpi-filter-row">', unsafe_allow_html=True)
            fcol1, fcol2 = st.columns(2)
            sel_year = fcol1.selectbox(
                "Year",
                options=["All"] + [str(y) for y in all_years],
                key="kpi_year_filter",
            )
            sel_month = fcol2.selectbox(
                "Month",
                options=["All"] + [month_names[m] for m in all_months_in_data],
                key="kpi_month_filter",
            )
            st.markdown("</div>", unsafe_allow_html=True)
            if sel_year != "All":
                filtered_df = filtered_df[
                    filtered_df[date_col_detect].dt.year == int(sel_year)
                ]
            if sel_month != "All":
                month_num = {v: k for k, v in month_names.items()}[sel_month]
                filtered_df = filtered_df[
                    filtered_df[date_col_detect].dt.month == month_num
                ]
            if sel_year != "All" or sel_month != "All":
                st.caption(
                    f"📌 {'Year ' + sel_year if sel_year != 'All' else 'All Years'} · "
                    f"{'Month: ' + sel_month if sel_month != 'All' else 'All Months'} — "
                    f"{filtered_df.shape[0]:,} rows"
                )
            st.markdown('<hr class="kpi-filter-sep"/>', unsafe_allow_html=True)
        except Exception:
            filtered_df = df.copy()

    with st.spinner("Computing KPIs…"):
        kpis = compute_kpis(filtered_df)

    if not kpis:
        st.info("Could not detect standard KPI columns.")
        return

    st.markdown(
        '<div class="kpi-section-title">Executive KPI Summary</div>'
        '<div class="kpi-section-sub">📊 Live metrics · Zero AI · Pure data</div>',
        unsafe_allow_html=True,
    )

    cards: list[tuple] = []
    order_n = kpis.get("avg_order_n") or kpis.get("total_orders") or len(filtered_df)

    if "revenue" in kpis:
        cards.append((
            "💰 TOTAL REVENUE",
            _fmt_currency(kpis["revenue"]),
            f"based on {order_n:,} orders",
            "revenue",
            None,
            None,
        ))
    if "units_sold" in kpis:
        cards.append((
            "🚗 UNITS SOLD",
            _fmt_number(kpis["units_sold"]),
            "total vehicle units",
            "units",
            None,
            None,
        ))
    if "yoy_growth" in kpis and kpis["yoy_growth"] is not None:
        g = kpis["yoy_growth"]
        arrow = "▲" if g >= 0 else "▼"
        prev_y = (kpis.get("yoy_curr_year") or 0) - 1
        cards.append((
            "📈 YOY GROWTH",
            f"{arrow} {abs(g):.1f}%",
            f"vs {prev_y}" if prev_y else "year over year",
            "yoy",
            f"{arrow} {abs(g):.1f}%",
            g >= 0,
        ))
    if "market_share" in kpis:
        cards.append((
            "🏷️ MARKET SHARE",
            f"{kpis['market_share']:.1f}%",
            "average share",
            "share",
            None,
            None,
        ))
    if "best_salesperson" in kpis:
        cards.append((
            "🌟 BEST PERSON",
            kpis["best_salesperson"],
            f"month {kpis.get('best_salesperson_month', '')}".strip(),
            "person",
            None,
            None,
        ))
    if "top_model" in kpis:
        units = kpis.get("top_model_units")
        if units is not None:
            sub = f"{units:,} units sold"
        else:
            sub = "by units sold"
        cards.append((
            "📦 TOP MODEL BY VOLUME",
            kpis["top_model"],
            sub,
            "model",
            None,
            None,
        ))
    if "active_regions" in kpis:
        cards.append((
            "🌍 ACTIVE REGIONS",
            str(kpis["active_regions"]),
            "unique regions",
            "regions",
            None,
            None,
        ))
    if "avg_order_value" in kpis:
        cards.append((
            "🛒 AVG ORDER VALUE",
            _fmt_currency(kpis["avg_order_value"]),
            f"based on {kpis.get('avg_order_n', order_n):,} orders",
            "aov",
            None,
            None,
        ))
    if "top_colour" in kpis:
        cards.append((
            "🎨 TOP COLOUR",
            kpis["top_colour"],
            "by revenue",
            "colour",
            None,
            None,
        ))
    if "total_orders" in kpis:
        cards.append((
            "📦 TOTAL ORDERS",
            _fmt_number(kpis["total_orders"]),
            "distinct orders",
            "orders",
            None,
            None,
        ))
    if "rev_per_unit" in kpis:
        cards.append((
            "💰 REV PER UNIT",
            _fmt_currency(kpis["rev_per_unit"]),
            "revenue ÷ units",
            "rpu",
            None,
            None,
        ))
    if "date_range" in kpis:
        cards.append((
            "📅 DATE RANGE",
            kpis["date_range"],
            kpis["date_range"],
            "date",
            None,
            None,
        ))
    if "top_make" in kpis:
        cards.append((
            "🏭 TOP MAKE",
            kpis["top_make"],
            "by units" if kpis.get("_vol_col") else "by revenue",
            "make",
            None,
            None,
        ))

    # Uniform 4-column grid (empty slots stay empty)
    for i in range(0, len(cards), 4):
        row = cards[i:i + 4]
        cols = st.columns(4)
        for j, col in enumerate(cols):
            with col:
                if j < len(row):
                    label, value, sub, accent, trend, trend_up = row[j]
                    delay = (i + j) * 0.05
                    featured = (i + j) == 0
                    st.markdown(
                        _kpi_card_html(
                            label, value, sub, accent, delay, trend, trend_up, featured
                        ),
                        unsafe_allow_html=True,
                    )
        st.markdown(
            "<div style='margin-bottom:10px;'></div>", unsafe_allow_html=True
        )

    st.markdown("---")

    with st.expander("📋 Show Detailed KPIs ▼", expanded=False):
        if "segment_mix" in kpis:
            st.markdown("#### 🥧 Vehicle Sales Mix by Segment")
            seg_df = pd.DataFrame([
                {"Segment": k, "Units Sold": v["units"], "Share %": v["pct"]}
                for k, v in kpis["segment_mix"].items()
            ])
            c1, c2 = st.columns([1, 1])
            with c1:
                st.markdown('<div class="kpi-chart-card">', unsafe_allow_html=True)
                fig = px.pie(
                    seg_df, names="Segment", values="Units Sold", hole=0.35,
                    color_discrete_sequence=px.colors.qualitative.Plotly, title="Sales Mix",
                )
                fig.update_layout(
                    margin=dict(l=0, r=0, t=30, b=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)
            with c2:
                st.dataframe(seg_df, use_container_width=True, hide_index=True)
            st.markdown("---")

        if "top5_models" in kpis:
            st.markdown("#### 🏎️ Top 5 Models by Revenue")
            m5_df = pd.DataFrame(kpis["top5_models"])
            m5_df.columns = ["Model", "Revenue", "Contribution %"]
            m5_df["Revenue Display"] = m5_df["Revenue"].apply(_fmt_currency)
            c1, c2 = st.columns([1, 1])
            with c1:
                st.markdown('<div class="kpi-chart-card">', unsafe_allow_html=True)
                fig = px.bar(
                    m5_df, y="Model", x="Revenue", orientation="h",
                    text="Revenue Display", color_discrete_sequence=["#818cf8"],
                    title="Revenue by Model",
                )
                fig.update_layout(
                    margin=dict(l=0, r=0, t=30, b=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)
            with c2:
                st.dataframe(
                    m5_df[["Model", "Revenue Display", "Contribution %"]],
                    use_container_width=True, hide_index=True,
                )
            st.markdown("---")

        if "fastest_seg" in kpis:
            st.markdown("#### 🚀 Fastest Growing Segment")
            st.success(
                f"**{kpis['fastest_seg']}** grew **{kpis['fastest_seg_pct']}%** YoY"
            )
            st.markdown("---")
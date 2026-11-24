"""
features/proactive_engine.py
Simplified insights for welcome / post-result context.
No suggestion chips, no HTML rendering.
"""
from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

try:
    import streamlit as st
except ImportError:
    st = None  # type: ignore


def _df_hash(df: pd.DataFrame) -> str:
    try:
        sig = f"{df.shape}|{list(df.columns)}"
        return hashlib.md5(sig.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return str(id(df))


class ProactiveEngine:
    def generate_proactive_insights(
        self,
        df: pd.DataFrame,
        limit: int = 4,
        context: dict | None = None,
    ) -> list[dict]:
        if df is None or df.empty:
            return []

        h = _df_hash(df)
        if st is not None:
            if st.session_state.get("_proactive_df_hash") == h:
                cached = st.session_state.get("proactive_insights")
                if isinstance(cached, list):
                    return cached[:limit]

        insights: list[dict] = []
        nums = df.select_dtypes(include="number").columns.tolist()
        cats = [
            c for c in df.columns
            if (df[c].dtype == object or str(df[c].dtype) == "category")
            and 1 < df[c].nunique() <= 40
        ]
        # Volume metric preferred for TOP MODEL / sales volume insights
        vol_metric = None
        for pref in ("order_qty", "units_sold", "quantity", "qty"):
            for c in nums:
                if pref == c.lower() or pref in c.lower():
                    vol_metric = c
                    break
            if vol_metric:
                break

        metric = None
        for pref in ("total_sales", "revenue", "order_qty"):
            for c in nums:
                if pref in c.lower():
                    metric = c
                    break
            if metric:
                break
        if metric is None and nums:
            metric = nums[0]

        date_c = None
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]) or "date" in c.lower():
                date_c = c
                break

        # Prefer model / carline for volume top-performer card
        model_dims = [
            c for c in df.columns
            if str(c).lower() in ("model", "carline_name", "make", "car_type")
            and 1 < df[c].nunique() <= 80
        ]
        top_dim = model_dims[0] if model_dims else (cats[0] if cats else None)
        top_metric = vol_metric or metric

        # A) Top performer by VOLUME (units sold)
        if top_metric and top_dim:
            try:
                g = df.groupby(top_dim)[top_metric].sum().sort_values(ascending=False)
                if len(g) >= 2:
                    top_name, top_val = g.index[0], float(g.iloc[0])
                    avg = float(g.mean())
                    pct = ((top_val / avg) - 1) * 100 if avg else 0
                    insights.append({
                        "type": "top_performer",
                        "title": f"📦 Top model by volume: {top_name}",
                        "summary": (
                            f"{top_name} — {int(top_val):,} units sold "
                            f"({pct:.0f}% above average)"
                        ),
                        "direction": "up",
                        "suggested_question": f"Which {top_dim} has highest units sold?",
                        "priority": 2,
                    })
            except Exception:
                pass

        # B) Recent trend
        if metric and date_c:
            try:
                tmp = df[[date_c, metric]].copy()
                tmp[date_c] = pd.to_datetime(tmp[date_c], errors="coerce")
                tmp = tmp.dropna(subset=[date_c])
                tmp["period"] = tmp[date_c].dt.to_period("M").astype(str)
                series = tmp.groupby("period")[metric].sum().sort_index()
                if len(series) >= 2:
                    last, prev = float(series.iloc[-1]), float(series.iloc[-2])
                    chg = (last - prev) / abs(prev) * 100 if prev else 0
                    insights.append({
                        "type": "trend" if chg >= 0 else "drop",
                        "title": f"{'Upward' if chg >= 0 else 'Downward'} trend in {metric}",
                        "summary": f"Latest period {chg:+.0f}% vs prior",
                        "direction": "up" if chg >= 0 else "down",
                        "suggested_question": f"Show {metric} trend by month",
                        "priority": 1 if abs(chg) >= 15 else 2,
                    })
            except Exception:
                pass

        # C) Concentration
        if metric and cats:
            dim = cats[0]
            try:
                g = df.groupby(dim)[metric].sum()
                total = float(g.sum())
                if total > 0:
                    top_name = g.idxmax()
                    share = float(g.max()) / total * 100
                    if share > 40:
                        insights.append({
                            "type": "concentration",
                            "title": f"Concentration in {dim}",
                            "summary": f"{top_name} holds {share:.0f}% of {metric}",
                            "direction": "neutral",
                            "suggested_question": f"Show {metric} by {dim}",
                            "priority": 2,
                        })
            except Exception:
                pass

        # D) Lowest performer
        if metric and cats:
            dim = cats[0]
            try:
                g = df.groupby(dim)[metric].sum().sort_values()
                if len(g) >= 2:
                    low_name, low_val = g.index[0], float(g.iloc[0])
                    insights.append({
                        "type": "growth",
                        "title": f"Opportunity: {low_name}",
                        "summary": f"{low_name} is lowest on {metric} at {low_val:,.1f}",
                        "direction": "down",
                        "suggested_question": f"Show {metric} for {low_name}",
                        "priority": 3,
                    })
            except Exception:
                pass

        insights.sort(key=lambda x: x.get("priority", 99))
        insights = insights[:limit]
        if st is not None:
            st.session_state["proactive_insights"] = insights
            st.session_state["_proactive_df_hash"] = h
        return insights

    def get_suggested_questions(self, df: pd.DataFrame, limit: int = 5) -> list[str]:
        """Return a few ready-to-ask NL questions for OOB redirects / concierge."""
        suggestions = [
            "Show revenue by colour",
            "Top 10 salespeople by revenue",
            "Monthly revenue trend",
            "Units sold by make",
            "Revenue by car type",
        ]
        if df is not None and not df.empty:
            cols = {str(c).lower() for c in df.columns}
            out = []
            if any("colour" in c or "color" in c for c in cols):
                out.append("Show revenue by colour")
            if any("make" in c for c in cols):
                out.append("Units sold by make")
            if any("first_name" in c or "sales" in c for c in cols):
                out.append("Top salespeople by revenue")
            if any("date" in c for c in cols):
                out.append("Monthly revenue trend")
            if out:
                suggestions = out + [s for s in suggestions if s not in out]
        return suggestions[: max(1, int(limit))]

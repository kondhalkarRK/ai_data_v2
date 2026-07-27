"""
features/proactive_engine.py
Surfaces insights the user has not asked for.
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
        sig = f"{df.shape}|{list(df.columns)}|{df.head(3).to_csv(index=False)}"
        return hashlib.md5(sig.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return str(id(df))


def _numeric_cols(df: pd.DataFrame) -> list[str]:
    return df.select_dtypes(include="number").columns.tolist()


def _cat_cols(df: pd.DataFrame, max_unique: int = 40) -> list[str]:
    out = []
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype) == "category":
            if 1 < df[c].nunique() <= max_unique:
                out.append(c)
        elif pd.api.types.is_datetime64_any_dtype(df[c]):
            continue
    return out


def _date_col(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            return c
        if "date" in c.lower():
            try:
                pd.to_datetime(df[c].dropna().head(5))
                return c
            except Exception:
                continue
    return None


def _metric_col(df: pd.DataFrame) -> str | None:
    prefs = ["total_sales", "revenue", "order_qty", "price_per_unit", "amount", "sales"]
    nums = _numeric_cols(df)
    for p in prefs:
        for c in nums:
            if p in c.lower():
                return c
    return nums[0] if nums else None


class ProactiveEngine:
    """Automatic insight cards from loaded DataFrame."""

    def generate_proactive_insights(
        self,
        df: pd.DataFrame,
        context: dict | None = None,
    ) -> list[dict]:
        if df is None or df.empty:
            return []

        h = _df_hash(df)
        if st is not None:
            cached_h = st.session_state.get("_proactive_df_hash")
            cached = st.session_state.get("proactive_insights")
            if cached_h == h and isinstance(cached, list):
                return cached

        insights: list[dict] = []
        metric = _metric_col(df)
        cats = _cat_cols(df)
        date_c = _date_col(df)

        # A) Top performer
        if metric and cats:
            dim = cats[0]
            try:
                grouped = df.groupby(dim, dropna=True)[metric].sum().sort_values(ascending=False)
                if len(grouped) >= 2:
                    top_name, top_val = grouped.index[0], float(grouped.iloc[0])
                    bot_val = float(grouped.iloc[-1])
                    avg = float(grouped.mean())
                    gap = top_val - bot_val
                    if avg > 0 and gap > 2 * avg:
                        pct = ((top_val / avg) - 1) * 100
                        insights.append({
                            "type": "top_performer",
                            "title": f"{top_name} leads {metric}",
                            "summary": (
                                f"{top_name} leads {metric} at {top_val:,.1f}, "
                                f"which is {pct:.0f}% above average"
                            ),
                            "metric": metric,
                            "value": top_val,
                            "change": pct,
                            "direction": "up",
                            "confidence": "high",
                            "chart_hint": "bar",
                            "suggested_question": f"Which {dim} has highest {metric}?",
                            "priority": 2,
                        })
            except Exception:
                pass

        # B) Trend + E) Sudden drop
        if metric and date_c:
            try:
                tmp = df[[date_c, metric]].copy()
                tmp[date_c] = pd.to_datetime(tmp[date_c], errors="coerce")
                tmp = tmp.dropna(subset=[date_c])
                tmp["period"] = tmp[date_c].dt.to_period("M").astype(str)
                series = tmp.groupby("period")[metric].sum().sort_index()
                if len(series) >= 2:
                    last = float(series.iloc[-1])
                    prev = float(series.iloc[-2])
                    if prev != 0:
                        chg = (last - prev) / abs(prev) * 100
                        if chg <= -15:
                            insights.append({
                                "type": "drop",
                                "title": f"Sudden drop in {metric}",
                                "summary": (
                                    f"{series.index[-1]} is {abs(chg):.0f}% below "
                                    f"{series.index[-2]}"
                                ),
                                "metric": metric,
                                "value": last,
                                "change": chg,
                                "direction": "down",
                                "confidence": "high",
                                "chart_hint": "line",
                                "suggested_question": f"Show {metric} trend by month",
                                "priority": 1,
                            })
                        elif chg > 10:
                            insights.append({
                                "type": "trend",
                                "title": f"Upward trend in {metric}",
                                "summary": (
                                    f"Latest period up {chg:.0f}% vs prior period"
                                ),
                                "metric": metric,
                                "value": last,
                                "change": chg,
                                "direction": "up",
                                "confidence": "medium",
                                "chart_hint": "line",
                                "suggested_question": f"Show {metric} trend by month",
                                "priority": 2,
                            })
                        elif chg < -10:
                            insights.append({
                                "type": "trend",
                                "title": f"Downward trend in {metric}",
                                "summary": (
                                    f"Latest period down {abs(chg):.0f}% vs prior period"
                                ),
                                "metric": metric,
                                "value": last,
                                "change": chg,
                                "direction": "down",
                                "confidence": "medium",
                                "chart_hint": "line",
                                "suggested_question": f"Show {metric} trend by month",
                                "priority": 2,
                            })
            except Exception:
                pass

        # C) Concentration
        if metric and cats:
            for dim in cats[:3]:
                try:
                    grouped = df.groupby(dim, dropna=True)[metric].sum()
                    total = float(grouped.sum())
                    if total <= 0 or grouped.empty:
                        continue
                    top_name = grouped.idxmax()
                    share = float(grouped.max()) / total * 100
                    if share > 40:
                        insights.append({
                            "type": "concentration",
                            "title": f"Concentration in {dim}",
                            "summary": (
                                f"{top_name} holds {share:.0f}% of all {metric}"
                            ),
                            "metric": metric,
                            "value": share,
                            "change": None,
                            "direction": "neutral",
                            "confidence": "high" if share > 50 else "medium",
                            "chart_hint": "pie",
                            "suggested_question": f"Show {metric} by {dim}",
                            "priority": 2 if share > 50 else 3,
                        })
                        break
                except Exception:
                    continue

        # D) Growth opportunity — below-average category with positive recent trend
        if metric and cats and date_c:
            try:
                dim = cats[0]
                means = df.groupby(dim)[metric].mean()
                overall = float(means.mean()) if len(means) else 0
                tmp = df[[dim, date_c, metric]].copy()
                tmp[date_c] = pd.to_datetime(tmp[date_c], errors="coerce")
                tmp = tmp.dropna(subset=[date_c])
                tmp["period"] = tmp[date_c].dt.to_period("M").astype(str)
                for cat, avg in means.items():
                    if overall and float(avg) >= overall:
                        continue
                    sub = tmp[tmp[dim] == cat].groupby("period")[metric].sum().sort_index()
                    if len(sub) < 2:
                        continue
                    if float(sub.iloc[-1]) > float(sub.iloc[-2]):
                        insights.append({
                            "type": "growth",
                            "title": f"Growth opportunity: {cat}",
                            "summary": (
                                f"{cat} is below average on {metric} but trending up"
                            ),
                            "metric": metric,
                            "value": float(avg),
                            "change": None,
                            "direction": "up",
                            "confidence": "low",
                            "chart_hint": "bar",
                            "suggested_question": f"Show {metric} for {cat} by month",
                            "priority": 4,
                        })
                        break
            except Exception:
                pass

        insights.sort(key=lambda x: x.get("priority", 99))
        insights = insights[:5]

        if st is not None:
            st.session_state["proactive_insights"] = insights
            st.session_state["_proactive_df_hash"] = h

        return insights

    def format_insight_card(self, insight: dict) -> str:
        icon_map = {
            "top_performer": "🏆",
            "trend": "📈",
            "drop": "📉",
            "concentration": "🎯",
            "growth": "🚀",
            "outlier": "⚠️",
        }
        icon = icon_map.get(insight.get("type", ""), "💡")
        title = insight.get("title", "Insight")
        summary = insight.get("summary", "")
        return (
            f'<div class="proactive-insight-card">'
            f'<div class="proactive-insight-icon">{icon}</div>'
            f'<div style="flex:1;">'
            f'<div class="proactive-insight-title">{title}</div>'
            f'<div class="proactive-insight-summary">{summary}</div>'
            f"</div>"
            f'<div class="proactive-ask-arrow">Ask →</div>'
            f"</div>"
        )

    def get_suggested_questions(
        self,
        df: pd.DataFrame,
        limit: int = 5,
    ) -> list[str]:
        if df is None or df.empty:
            return []

        metric = "revenue"
        try:
            from core.metric_registry import get_metric_registry
            reg = get_metric_registry()
            measures = reg.list_measures()
            if measures:
                metric = measures[0]
        except Exception:
            mcol = _metric_col(df)
            if mcol:
                metric = mcol

        cats = _cat_cols(df)
        dim = cats[0] if cats else (list(df.columns)[0] if len(df.columns) else "category")
        dim2 = cats[1] if len(cats) > 1 else "make"

        qs = [
            f"Which {dim} has highest {metric}?",
            f"Show {metric} trend by month",
            f"Top 10 {dim} by {metric}",
            f"Show {metric} by {dim2}",
            "Find anomalies in my data",
            f"What if {metric} increased by 20%?",
        ]

        # Blend with proactive insight suggestions
        for ins in self.generate_proactive_insights(df):
            sq = ins.get("suggested_question")
            if sq and sq not in qs:
                qs.insert(0, sq)

        # de-dupe preserve order
        seen = set()
        out = []
        for q in qs:
            if q not in seen:
                seen.add(q)
                out.append(q)
        return out[:limit]

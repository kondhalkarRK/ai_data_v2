"""
features/narration_engine.py
Convert query results into plain-English narratives.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd


class NarrationEngine:
    """Narrate DataFrame results for Ask / Chat modes."""

    def generate_narration(
        self,
        result_df: pd.DataFrame,
        question: str,
        intent: dict | None = None,
        evidence: dict | None = None,
        mode: str = "standard",
    ) -> dict[str, Any]:
        if result_df is None or result_df.empty:
            return {
                "headline": "No results",
                "summary": "The query returned no rows.",
                "key_findings": ["No data matched this question."],
                "narrative_text": "I couldn't find matching records for that question.",
                "data_points": [],
                "trend_comment": None,
                "recommendation": "Try broadening filters or choosing another dimension.",
                "word_count": 12,
            }

        num_cols = result_df.select_dtypes(include="number").columns.tolist()
        str_cols = result_df.select_dtypes(exclude="number").columns.tolist()
        n = len(result_df)

        # Detect type
        is_time = any(
            c.lower() in ("month", "year", "quarter", "period", "day")
            or "date" in c.lower()
            for c in result_df.columns
        )
        if n == 1 and len(num_cols) >= 1 and not str_cols:
            kind = "scalar"
        elif is_time and num_cols:
            kind = "trend"
        elif len(str_cols) >= 2 and num_cols:
            kind = "grouped"
        elif str_cols and num_cols:
            kind = "ranked"
        else:
            kind = "grouped"

        metric = num_cols[0] if num_cols else "value"
        dim = str_cols[0] if str_cols else None

        if kind == "scalar":
            val = float(result_df[metric].iloc[0])
            headline = f"Total {metric.replace('_', ' ')}"
            narrative = f"Total {metric.replace('_', ' ')} across returned records is {val:,.2f}."
            findings = [
                f"Single aggregated value: {val:,.2f}",
                f"Question: {question}",
                "Result is a scalar summary, not a breakdown.",
            ]
            recommendation = "Ask to break this down by a dimension (colour, make, region)."
        elif kind == "ranked":
            ordered = result_df.sort_values(metric, ascending=False)
            top = ordered.iloc[0]
            bot = ordered.iloc[-1]
            total = float(ordered[metric].sum()) or 1.0
            top_share = float(top[metric]) / total * 100
            bot_share = float(bot[metric]) / total * 100
            top3 = float(ordered[metric].head(3).sum()) / total * 100
            headline = f"{metric.replace('_', ' ').title()} by {dim}"
            narrative = (
                f"Across {n} {dim} values, {top[dim]} leads with "
                f"{float(top[metric]):,.1f} ({top_share:.0f}% of total), "
                f"while {bot[dim]} is lowest at {float(bot[metric]):,.1f} "
                f"({bot_share:.0f}%)."
            )
            findings = [
                f"{top[dim]} dominates at {top_share:.0f}% share",
                f"Top 3 = {top3:.0f}% of total {metric}",
                f"{bot[dim]} underperforms relative to the leader",
            ]
            recommendation = f"Drill into why {bot[dim]} is low, or compare top vs bottom."
        elif kind == "trend":
            time_c = next(
                (c for c in result_df.columns if c.lower() in ("month", "year", "quarter", "period") or "date" in c.lower()),
                result_df.columns[0],
            )
            ordered = result_df.sort_values(time_c)
            last = ordered.iloc[-1]
            prev = ordered.iloc[-2] if n > 1 else last
            last_v = float(last[metric])
            prev_v = float(prev[metric]) if n > 1 else last_v
            chg = ((last_v - prev_v) / abs(prev_v) * 100) if prev_v else 0.0
            avg = float(ordered[metric].mean())
            direction = "upward" if chg >= 0 else "downward"
            headline = f"{metric.replace('_', ' ').title()} trend"
            narrative = (
                f"{metric.replace('_', ' ').title()} shows a {direction} move. "
                f"Most recent period ({last[time_c]}) reached {last_v:,.1f}, "
                f"{chg:+.0f}% vs prior ({prev[time_c]}: {prev_v:,.1f}). "
                f"Average across the series is {avg:,.1f}."
            )
            findings = [
                f"Latest period: {last[time_c]} = {last_v:,.1f}",
                f"Period change: {chg:+.1f}%",
                f"Series average: {avg:,.1f}",
            ]
            recommendation = "Ask for a year filter or compare two periods side by side."
        else:
            headline = f"Breakdown of {metric.replace('_', ' ')}"
            if dim and metric in result_df.columns:
                ordered = result_df.sort_values(metric, ascending=False)
                top = ordered.iloc[0]
                bot = ordered.iloc[-1]
                narrative = (
                    f"Breaking down {metric.replace('_', ' ')} across {n} groups: "
                    f"{top[dim]} leads at {float(top[metric]):,.1f}, while "
                    f"{bot[dim]} shows the lowest at {float(bot[metric]):,.1f}."
                )
                findings = [
                    f"Top group: {top[dim]}",
                    f"Lowest group: {bot[dim]}",
                    f"{n} groups returned",
                ]
            else:
                narrative = f"Returned {n} rows and {result_df.shape[1]} columns for your question."
                findings = [
                    f"{n} rows returned",
                    f"Columns: {', '.join(map(str, result_df.columns[:5]))}",
                    f"Question: {question}",
                ]
            recommendation = "Try sorting by the main metric or filtering to one segment."

        if mode == "executive":
            narrative = narrative.split(".")[0] + "."
            findings = findings[:2]
        elif mode == "detailed":
            path = (evidence or {}).get("execution_path")
            if path:
                findings.append(f"Execution path: {path}")

        text = narrative
        out = {
            "headline": headline,
            "summary": narrative,
            "key_findings": findings[:3],
            "narrative_text": text,
            "data_points": [
                {"label": metric, "rows": n},
            ],
            "trend_comment": findings[1] if kind == "trend" and len(findings) > 1 else None,
            "recommendation": recommendation,
            "word_count": len(text.split()),
        }
        return out

    def generate_whatif_narration(self, scenario_result: dict) -> str:
        if not scenario_result:
            return "No what-if result available."
        if scenario_result.get("narrative"):
            return str(scenario_result["narrative"])
        try:
            from features.whatif_engine import WhatIfEngine
            return WhatIfEngine().generate_whatif_narrative(scenario_result)
        except Exception:
            return "Scenario analysis complete."

    def generate_anomaly_narration(self, anomalies: list[dict]) -> str:
        try:
            from features.anomaly_engine import AnomalyEngine
            return AnomalyEngine().summarise_anomalies(anomalies or [])
        except Exception:
            if not anomalies:
                return "No anomalies found."
            return f"Found {len(anomalies)} anomalies."

    def should_auto_narrate(self, question: str) -> bool:
        if not question:
            return False
        q = question.lower()
        triggers = [
            "why", "explain", "describe", "tell me about",
            "what does", "analyse", "analyze", "insights",
            "summary", "overview", "what if", "suppose",
        ]
        return any(t in q for t in triggers)

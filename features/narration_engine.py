"""
features/narration_engine.py
Pure Python data-driven narration — no LLM calls.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


class NarrationEngine:
    def format_value(self, value, format_type: str = "decimal") -> str:
        try:
            v = float(value)
        except Exception:
            return str(value)
        if format_type == "percent":
            return f"{v:.1f}%"
        if format_type == "integer":
            return f"{int(round(v)):,}"
        if format_type == "currency":
            av = abs(v)
            sign = "-" if v < 0 else ""
            if av >= 1_000_000:
                return f"{sign}£{av/1_000_000:.1f}M"
            if av >= 1_000:
                return f"{sign}£{av/1_000:.1f}K"
            return f"{sign}£{av:,.0f}"
        return f"{v:,.2f}"

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
                "narrative_text": "The query returned no rows.",
                "key_findings": ["No data matched this question."],
                "recommendation": "Try broadening filters or another dimension.",
                "result_summary": "No rows returned",
                "summary": "The query returned no rows.",
                "word_count": 6,
            }

        num_cols = result_df.select_dtypes(include="number").columns.tolist()
        str_cols = result_df.select_dtypes(exclude="number").columns.tolist()
        n = len(result_df)
        metric = num_cols[0] if num_cols else "value"
        metric_label = str(metric).replace("_", " ")
        dim = str_cols[0] if str_cols else None
        dim_label = str(dim).replace("_", " ") if dim else "group"

        is_time = any(
            c.lower() in ("month", "year", "quarter", "period", "day")
            or "date" in c.lower()
            for c in result_df.columns
        )

        if n == 1 and num_cols and not str_cols:
            kind = "scalar"
        elif is_time and num_cols:
            kind = "trend"
        elif len(str_cols) >= 2 and num_cols:
            kind = "grouped"
        elif str_cols and num_cols:
            kind = "ranked"
        else:
            kind = "grouped"

        fmt = "currency" if any(x in metric.lower() for x in ("sales", "revenue", "price", "amount")) else "decimal"

        if kind == "scalar":
            val = float(result_df[metric].iloc[0])
            headline = f"Total {metric_label}"
            narrative = f"The total {metric_label} across all records is {self.format_value(val, fmt)}."
            findings = [f"Single aggregated value: {self.format_value(val, fmt)}"]
            recommendation = "Ask to break this down by a dimension (colour, make, region)."
            result_summary = f"Total {metric_label}: {self.format_value(val, fmt)}"

        elif kind == "ranked":
            ordered = result_df.sort_values(metric, ascending=False)
            top = ordered.iloc[0]
            bot = ordered.iloc[-1]
            total = float(ordered[metric].sum()) or 1.0
            top_pct = float(top[metric]) / total * 100
            top3_pct = float(ordered[metric].head(3).sum()) / total * 100
            headline = f"{metric_label.title()} by {dim_label}"
            narrative = (
                f"Across {n} {dim_label} values, {top[dim]} leads with "
                f"{self.format_value(top[metric], fmt)} ({top_pct:.0f}% of total). "
                f"{bot[dim]} is lowest at {self.format_value(bot[metric], fmt)}. "
                f"Total {metric_label}: {self.format_value(total, fmt)}."
            )
            findings = [
                f"{top[dim]} holds the top position with {top_pct:.0f}% share",
                f"Top 3 account for {top3_pct:.0f}% of total",
                f"Range spans from {self.format_value(bot[metric], fmt)} to {self.format_value(top[metric], fmt)}",
            ]
            recommendation = f"Drill into why {bot[dim]} is low, or compare top vs bottom."
            result_summary = (
                f"{metric_label.title()} by {dim_label}: {top[dim]} leads "
                f"{self.format_value(top[metric], fmt)}, {n} values, "
                f"range {self.format_value(bot[metric], fmt)}-{self.format_value(top[metric], fmt)}"
            )

        elif kind == "trend":
            time_c = next(
                (c for c in result_df.columns
                 if c.lower() in ("month", "year", "quarter", "period") or "date" in c.lower()),
                result_df.columns[0],
            )
            ordered = result_df.sort_values(time_c)
            last = ordered.iloc[-1]
            prior = ordered.iloc[-2] if n > 1 else None
            last_v = float(last[metric])
            change_bit = ""
            if prior is not None:
                prev_v = float(prior[metric])
                change = ((last_v - prev_v) / abs(prev_v) * 100) if prev_v else 0.0
                direction = "up" if change > 0 else "down"
                change_bit = f", {direction} {abs(change):.1f}% from prior period"
            avg = float(ordered[metric].mean())
            headline = f"{metric_label.title()} trend"
            narrative = (
                f"The {metric_label} trend shows {n} periods. "
                f"The most recent period ({last[time_c]}) reached "
                f"{self.format_value(last_v, fmt)}{change_bit}. "
                f"Average across all periods: {self.format_value(avg, fmt)}."
            )
            findings = [
                f"Latest: {last[time_c]} = {self.format_value(last_v, fmt)}",
                f"Average: {self.format_value(avg, fmt)}",
                f"{n} periods in series",
            ]
            recommendation = "Ask for a year filter or compare two periods."
            result_summary = (
                f"{metric_label} trend: latest {last[time_c]} "
                f"{self.format_value(last_v, fmt)}, {n} periods"
            )

        else:
            headline = f"Breakdown of {metric_label}"
            if dim and metric in result_df.columns:
                ordered = result_df.sort_values(metric, ascending=False)
                top = ordered.iloc[0]
                dim2 = str_cols[1] if len(str_cols) > 1 else None
                if dim2:
                    narrative = (
                        f"Breaking down {metric_label} across {n} combinations of "
                        f"{dim_label} and {str(dim2).replace('_',' ')}. "
                        f"{top[dim]} / {top[dim2]} leads at "
                        f"{self.format_value(top[metric], fmt)}."
                    )
                else:
                    narrative = (
                        f"Breaking down {metric_label} across {n} groups. "
                        f"{top[dim]} leads at {self.format_value(top[metric], fmt)}."
                    )
                findings = [f"Top: {top[dim]}", f"{n} groups returned", f"Question: {question}"]
                result_summary = f"{metric_label} breakdown: {top[dim]} leads, {n} groups"
            else:
                narrative = f"Returned {n} rows and {result_df.shape[1]} columns."
                findings = [f"{n} rows", f"Columns: {', '.join(map(str, result_df.columns[:5]))}"]
                result_summary = f"{n} rows returned"
            recommendation = "Try sorting by the main metric or filtering to one segment."

        return {
            "headline": headline,
            "narrative_text": narrative,
            "summary": narrative,
            "key_findings": findings[:3],
            "recommendation": recommendation,
            "result_summary": result_summary,
            "data_points": [{"label": metric, "rows": n}],
            "word_count": len(narrative.split()),
        }

    def generate_whatif_narration(self, scenario_result: dict) -> str:
        return (scenario_result or {}).get("narrative") or "Scenario analysis complete."

    def generate_anomaly_narration(self, anomalies: list[dict]) -> str:
        if not anomalies:
            return "No anomalies found."
        return f"Found {len(anomalies)} anomalies."

    def should_auto_narrate(self, question: str) -> bool:
        if not question:
            return False
        q = question.lower()
        triggers = [
            "why", "explain", "describe", "tell me about",
            "what does this mean", "analyse", "analyze", "analysis",
            "insights", "summary", "overview", "understand", "what if",
        ]
        return any(t in q for t in triggers)

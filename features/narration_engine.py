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
            if av >= 10_000_000:
                return f"{sign}₹{av/10_000_000:.2f} Cr"
            if av >= 100_000:
                return f"{sign}₹{av/100_000:.2f} L"
            if av >= 1_000:
                return f"{sign}₹{av/1_000:.1f}K"
            return f"{sign}₹{av:,.0f}"
        return f"{v:,.2f}"

    def generate_narration(
        self,
        result_df: pd.DataFrame,
        question: str,
        intent: dict | None = None,
        evidence: dict | None = None,
        mode: str = "standard",
        knowledge_snippets: list | None = None,
    ) -> dict[str, Any]:
        if result_df is None or result_df.empty:
            base = {
                "headline": "No results",
                "narrative_text": "The query returned no rows.",
                "key_findings": ["No data matched this question."],
                "recommendation": "Try broadening filters or another dimension.",
                "result_summary": "No rows returned",
                "summary": "The query returned no rows.",
                "word_count": 6,
                "knowledge_citations": [],
            }
            return self._enrich_with_knowledge(base, question, knowledge_snippets)

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
        if any(x in metric.lower() for x in ("qty", "unit", "order_qty", "volume")):
            fmt = "integer"

        if kind == "scalar":
            val = result_df[metric].iloc[0]
            headline = f"{metric_label.title()}: {self.format_value(val, fmt)}"
            narrative = f"The result for your question is {self.format_value(val, fmt)}."
            findings = [f"{metric_label}: {self.format_value(val, fmt)}"]
            recommendation = "Ask to break this down by make, region, or month."
            result_summary = headline
        elif kind == "trend":
            time_c = next(
                (
                    c for c in result_df.columns
                    if c.lower() in ("month", "year", "quarter", "period", "day")
                    or "date" in c.lower()
                ),
                str_cols[0] if str_cols else result_df.columns[0],
            )
            ordered = result_df.sort_values(time_c)
            first, last = ordered.iloc[0], ordered.iloc[-1]
            first_v, last_v = float(first[metric]), float(last[metric])
            chg = ((last_v - first_v) / abs(first_v) * 100) if first_v else 0
            headline = f"{metric_label.title()} trend"
            narrative = (
                f"{metric_label.title()} moved from {self.format_value(first_v, fmt)} "
                f"({first[time_c]}) to {self.format_value(last_v, fmt)} ({last[time_c]}), "
                f"a {chg:+.0f}% change across {n} periods."
            )
            findings = [
                f"Start: {first[time_c]} = {self.format_value(first_v, fmt)}",
                f"End: {last[time_c]} = {self.format_value(last_v, fmt)}",
                f"{n} periods in series",
            ]
            recommendation = "Ask for a year filter or compare two periods."
            result_summary = (
                f"{metric_label} trend: latest {last[time_c]} "
                f"{self.format_value(last_v, fmt)}, {n} periods"
            )
        else:
            # Multi-dimension / generic result — clear leader summary, not "Breakdown"
            if dim and metric in result_df.columns:
                ordered = result_df.sort_values(metric, ascending=False)
                top = ordered.iloc[0]
                dim2 = str_cols[1] if len(str_cols) > 1 else None
                if dim2:
                    headline = f"Top result: {top[dim]} × {top[dim2]}"
                    narrative = (
                        f"Among {n} result rows, the leading combination is "
                        f"{top[dim]} with {top[dim2]} at "
                        f"{self.format_value(top[metric], fmt)}."
                    )
                    findings = [
                        f"Leader: {top[dim]} / {top[dim2]}",
                        f"{self.format_value(top[metric], fmt)} on {metric_label}",
                        f"{n} rows in the result",
                    ]
                    result_summary = (
                        f"Top: {top[dim]} / {top[dim2]} = "
                        f"{self.format_value(top[metric], fmt)} ({n} rows)"
                    )
                else:
                    headline = f"Top {dim_label}: {top[dim]}"
                    narrative = (
                        f"Across {n} {dim_label} values, {top[dim]} leads with "
                        f"{self.format_value(top[metric], fmt)}."
                    )
                    findings = [
                        f"Leader: {top[dim]}",
                        f"{n} groups in the result",
                    ]
                    result_summary = (
                        f"{top[dim]} leads with "
                        f"{self.format_value(top[metric], fmt)}"
                    )
                recommendation = "Ask for a chart view, or filter to one region/make."
            else:
                headline = "Query results"
                narrative = f"Returned {n} rows and {result_df.shape[1]} columns."
                findings = [f"{n} rows returned"]
                result_summary = f"{n} rows returned"
                recommendation = "Try a more specific metric or dimension."

        base = {
            "headline": headline,
            "narrative_text": narrative,
            "summary": narrative,
            "key_findings": findings[:3],
            "recommendation": recommendation,
            "result_summary": result_summary,
            "data_points": [{"label": metric, "rows": n}],
            "word_count": len(narrative.split()),
            "knowledge_citations": [],
        }
        return self._enrich_with_knowledge(base, question, knowledge_snippets)

    def _enrich_with_knowledge(
        self,
        narration: dict[str, Any],
        question: str,
        knowledge_snippets: list | None = None,
    ) -> dict[str, Any]:
        """Merge OKF / SOP context into narrative (L3 contextual insights)."""
        snippets = knowledge_snippets
        if snippets is None:
            try:
                from features.okf_knowledge.okf_retriever import get_relevant_snippets
                snippets = get_relevant_snippets(question or "", top_k=2, max_context_chars=700)
            except Exception:
                snippets = []

        if not snippets:
            return narration

        citations = []
        context_bits = []
        for s in snippets[:2]:
            src = s.get("source_doc") or "SOP"
            title = s.get("title") or ""
            snip = (s.get("snippet") or "").replace("\n", " ")
            # Prefer short actionable sentence
            if len(snip) > 220:
                snip = snip[:217] + "…"
            context_bits.append(snip)
            citations.append({
                "source_doc": src,
                "source_page": s.get("source_page"),
                "title": title,
            })

        # Append contextual sentence (SOP-guided)
        extra = " ".join(context_bits[:1])
        if extra:
            narration["narrative_text"] = (
                f"{narration.get('narrative_text', '')} "
                f"Business context: {extra}"
            ).strip()
            narration["summary"] = narration["narrative_text"]

        findings = list(narration.get("key_findings") or [])
        src0 = citations[0]["source_doc"] if citations else "SOP"
        findings.append(f"Knowledge: guided by {src0}")
        narration["key_findings"] = findings[:4]

        # Soft recommendation upgrade when EV/COVID/region keywords hit
        q = (question or "").lower()
        rec = narration.get("recommendation") or ""
        if any(w in q for w in ("covid", "2020", "recovery")):
            rec = "Compare vs 2019 baseline — treat 2020 as COVID-depressed (IND-PV-SOP-002)."
        elif any(w in q for w in ("ev", "electric", "powertrain")):
            rec = "Report EV share on units (not orders) and separate ICE volume (IND-PV-SOP-003)."
        elif any(w in q for w in ("region", "territory", "city", "metro")):
            rec = "Drill Country → Zone → City before model-level conclusions (IND-PV-SOP-004)."
        narration["recommendation"] = rec
        narration["knowledge_citations"] = citations
        narration["word_count"] = len(str(narration.get("narrative_text", "")).split())
        return narration

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

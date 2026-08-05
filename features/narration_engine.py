"""
features/narration_engine.py
Pure Python data-driven narration — no LLM calls.
Produces 3–5 sentence leadership-ready insights.
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

    def _metric_format(self, metric: str) -> str:
        m = str(metric).lower()
        if any(x in m for x in ("sales", "revenue", "price", "amount", "aov", "asp")):
            return "currency"
        if any(x in m for x in ("qty", "unit", "order_qty", "volume", "count", "gained", "diff")):
            return "integer"
        if any(x in m for x in ("pct", "share", "percent", "rate")):
            return "percent"
        return "decimal"

    def _find_gain_cols(self, df: pd.DataFrame) -> tuple[str | None, str | None, str | None]:
        """Detect year1 / year2 / diff columns from between-year pivots."""
        cols = {str(c).lower(): c for c in df.columns}
        gained = None
        for key, orig in cols.items():
            if any(t in key for t in ("gained", "diff", "delta", "change")):
                gained = orig
                break
        year_cols = []
        for key, orig in cols.items():
            if key.startswith("units_") and key.replace("units_", "").isdigit():
                year_cols.append((int(key.replace("units_", "")), orig))
            elif key.startswith("revenue_") and key.replace("revenue_", "").isdigit():
                year_cols.append((int(key.replace("revenue_", "")), orig))
        year_cols.sort()
        if len(year_cols) >= 2:
            return year_cols[0][1], year_cols[-1][1], gained
        return None, None, gained

    def _q_hint(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return "this question"
        if len(q) > 90:
            return q[:87].rstrip() + "…"
        return q

    def _join_paras(self, parts: list[str]) -> str:
        return "\n\n".join(p.strip() for p in parts if p and str(p).strip())

    def generate_narration(
        self,
        result_df: pd.DataFrame,
        question: str,
        intent: dict | None = None,
        evidence: dict | None = None,
        mode: str = "standard",
        knowledge_snippets: list | None = None,
    ) -> dict[str, Any]:
        q_hint = self._q_hint(question)

        if result_df is None or result_df.empty:
            base = {
                "headline": "No results",
                "narrative_text": self._join_paras([
                    f'For "{q_hint}", the query returned no matching rows.',
                    "That usually means filters are too tight, the time window is empty, or the dimension values do not exist in the loaded dataset.",
                    "Widen the year/region filter, check spelling of makes/models, or restate the question with a broader metric such as total units or revenue.",
                ]),
                "key_findings": [],
                "recommendation": "Retry with broader filters or a clearer metric (units vs revenue).",
                "result_summary": "No rows returned",
                "summary": "No rows returned for this question.",
                "word_count": 40,
                "knowledge_citations": [],
            }
            return self._enrich_with_knowledge(base, question, knowledge_snippets)

        align_cols = {"actual_units", "target_units", "variance_pct", "status"}
        if align_cols.issubset(set(result_df.columns)):
            try:
                from features.okf_knowledge.target_narration import generate_target_alignment_narration
                payload = {
                    "result_df": result_df,
                    "registry": {},
                    "scope": (
                        str(result_df.iloc[0]["scope"])
                        if "scope" in result_df.columns
                        else "National"
                    ),
                    "grain": "monthly" if "month" in result_df.columns else "ytd",
                    "fy_label": "FY2026",
                    "doc_code": "IND-PV-REG-001",
                    "question": question,
                }
                narr = generate_target_alignment_narration(payload, knowledge_snippets or [])
                narr["word_count"] = len(narr.get("narrative_text", "").split())
                return narr
            except Exception:
                pass

        num_cols = result_df.select_dtypes(include="number").columns.tolist()
        str_cols = result_df.select_dtypes(exclude="number").columns.tolist()
        n = len(result_df)
        y1_col, y2_col, gain_col = self._find_gain_cols(result_df)

        if gain_col and gain_col in result_df.columns:
            metric = gain_col
        elif y2_col and y2_col in result_df.columns:
            metric = y2_col
        else:
            metric = num_cols[0] if num_cols else "value"
        metric_label = str(metric).replace("_", " ")
        dim = str_cols[0] if str_cols else None
        dim_label = str(dim).replace("_", " ") if dim else "group"

        is_time = any(
            c.lower() in ("month", "year", "quarter", "period", "day")
            or "date" in c.lower()
            for c in result_df.columns
        )

        if y1_col and y2_col and dim and gain_col:
            kind = "yoy_gain"
        elif n == 1 and num_cols and not str_cols:
            kind = "scalar"
        elif is_time and num_cols:
            kind = "trend"
        elif len(str_cols) >= 2 and num_cols:
            kind = "grouped"
        elif str_cols and num_cols:
            kind = "ranked"
        else:
            kind = "grouped"

        fmt = self._metric_format(metric)

        if kind == "yoy_gain":
            ordered = result_df.sort_values(gain_col, ascending=False)
            top = ordered.iloc[0]
            bottom = ordered.iloc[-1]
            mid = ordered.iloc[1] if n > 1 else None
            total_gain = float(pd.to_numeric(result_df[gain_col], errors="coerce").fillna(0).sum())
            top_gain = float(top[gain_col])
            share = (top_gain / total_gain * 100) if total_gain else 0
            y1_lab = str(y1_col).replace("_", " ")
            y2_lab = str(y2_col).replace("_", " ")
            headline = f"{top[dim]} gained the most"
            paras = [
                f'Answering "{q_hint}": across {n} {dim_label}s, {top[dim]} delivered the strongest net gain — '
                f"moving from {self.format_value(top[y1_col], 'integer')} ({y1_lab}) to "
                f"{self.format_value(top[y2_col], 'integer')} ({y2_lab}), a net "
                f"{self.format_value(top_gain, 'integer')} units ({share:.0f}% of total net gains).",
            ]
            if mid is not None:
                paras.append(
                    f"Next in line is {mid[dim]} at "
                    f"{self.format_value(mid[gain_col], 'integer')} net units, while the softest performer is "
                    f"{bottom[dim]} ({self.format_value(bottom[gain_col], 'integer')}). "
                    f"The spread between leader and softest shows where growth is concentrating versus fading."
                )
            else:
                paras.append(
                    f"The softest outcome in this cut is {bottom[dim]} at "
                    f"{self.format_value(bottom[gain_col], 'integer')}. "
                    f"Use that contrast to prioritise investment and turnaround attention."
                )
            paras.append(
                "For leadership action: protect the leader’s momentum with stock and dealer focus, "
                "and run a region/car-type drill-down on the softest name before changing the overall plan."
            )
            recommendation = (
                f"Next: break {top[dim]} and {bottom[dim]} by region or car type to see where the gain/loss is coming from."
            )
            result_summary = (
                f"{top[dim]} gained {self.format_value(top_gain, 'integer')} units"
            )

        elif kind == "scalar":
            val = result_df[metric].iloc[0]
            headline = f"{metric_label.title()}: {self.format_value(val, fmt)}"
            paras = [
                f'For "{q_hint}", the single-number answer is {self.format_value(val, fmt)} '
                f"({metric_label}).",
                "This is a headline KPI — useful for a board snapshot, but it does not yet explain "
                "which make, region, or period is driving the figure.",
                "Ask for a breakdown by make, region, or month to turn this number into an actionable narrative.",
            ]
            recommendation = "Break this down by make, region, or month for decision context."
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
            peak_idx = ordered[metric].astype(float).idxmax()
            trough_idx = ordered[metric].astype(float).idxmin()
            peak = ordered.loc[peak_idx]
            trough = ordered.loc[trough_idx]
            direction = "up" if chg >= 0 else "down"
            headline = f"{metric_label.title()} trend ({chg:+.0f}%)"
            paras = [
                f'On "{q_hint}", {metric_label} moved {direction} from '
                f"{self.format_value(first_v, fmt)} in {first[time_c]} to "
                f"{self.format_value(last_v, fmt)} in {last[time_c]} "
                f"({chg:+.0f}% across {n} periods).",
                f"The peak period was {peak[time_c]} at {self.format_value(peak[metric], fmt)}, "
                f"while the low point was {trough[time_c]} at {self.format_value(trough[metric], fmt)} — "
                f"useful anchors for seasonality and campaign timing.",
                "Leadership takeaway: treat the end-point as the current run-rate, and investigate whether "
                "the peak is repeatable (product mix, region push, or one-off incentives).",
            ]
            recommendation = "Compare two years or add a make/region filter to explain the peak and trough."
            result_summary = (
                f"{metric_label} trend: latest {last[time_c]} "
                f"{self.format_value(last_v, fmt)}, {n} periods"
            )

        else:
            if dim and metric in result_df.columns:
                ordered = result_df.sort_values(metric, ascending=False)
                top = ordered.iloc[0]
                runner = ordered.iloc[1] if n > 1 else None
                third = ordered.iloc[2] if n > 2 else None
                bottom = ordered.iloc[-1]
                total = float(pd.to_numeric(result_df[metric], errors="coerce").fillna(0).sum())
                top_v = float(top[metric])
                share = (top_v / total * 100) if total else 0
                dim2 = str_cols[1] if len(str_cols) > 1 else None
                top_share_note = f"{share:.0f}% of total {metric_label}"

                if dim2:
                    headline = f"Top: {top[dim]} × {top[dim2]}"
                    paras = [
                        f'For "{q_hint}", the leading combination is {top[dim]} with {top[dim2]} at '
                        f"{self.format_value(top_v, fmt)} — {top_share_note} across {n} result rows.",
                    ]
                    if runner is not None:
                        paras.append(
                            f"Runner-up is {runner[dim]} × {runner[dim2]} at "
                            f"{self.format_value(runner[metric], fmt)}. "
                            f"Together, the top two set the competitive shape of this cut; "
                            f"the lowest row is {bottom[dim]} × {bottom[dim2]} at "
                            f"{self.format_value(bottom[metric], fmt)}."
                        )
                    paras.append(
                        "For leadership: double-down where the top combination is winning, and test whether "
                        "the gap to #2 is structural (product/region) or executable (stock, pricing, dealer focus)."
                    )
                    result_summary = (
                        f"Top: {top[dim]} / {top[dim2]} = "
                        f"{self.format_value(top_v, fmt)} ({n} rows)"
                    )
                else:
                    headline = f"Top {dim_label}: {top[dim]}"
                    paras = [
                        f'Answering "{q_hint}": among {n} {dim_label}s, {top[dim]} leads with '
                        f"{self.format_value(top_v, fmt)} ({top_share_note}).",
                    ]
                    if runner is not None and third is not None:
                        paras.append(
                            f"The next tier is {runner[dim]} "
                            f"({self.format_value(runner[metric], fmt)}) and {third[dim]} "
                            f"({self.format_value(third[metric], fmt)}). "
                            f"At the other end, {bottom[dim]} sits at "
                            f"{self.format_value(bottom[metric], fmt)} — a clear underperformer versus the leader."
                        )
                    elif runner is not None:
                        paras.append(
                            f"Runner-up is {runner[dim]} at "
                            f"{self.format_value(runner[metric], fmt)}. "
                            f"The softest name in this list is {bottom[dim]} at "
                            f"{self.format_value(bottom[metric], fmt)}."
                        )
                    else:
                        paras.append(
                            f"Only one {dim_label} appears in this cut, so concentration risk is high — "
                            f"validate with a second dimension (region or month) before locking a plan."
                        )
                    paras.append(
                        "Leadership view: the leader’s share shows how concentrated performance is. "
                        "If one name holds a large share, growth plans should either reinforce that strength "
                        "or deliberately diversify into the next tier."
                    )
                    result_summary = (
                        f"{top[dim]} leads with "
                        f"{self.format_value(top_v, fmt)} ({share:.0f}% share)"
                    )
                recommendation = (
                    f"Drill {top[dim]} by region or month, and compare against {bottom[dim]} for a gap story."
                )
            else:
                headline = "Query results"
                paras = [
                    f'For "{q_hint}", the query returned {n} rows and {result_df.shape[1]} columns.',
                    "The shape of the result is usable for inspection, but a clearer metric/dimension "
                    "pairing will produce a sharper leadership summary.",
                    "Try asking for a ranked view (top makes by units) or a trend (monthly revenue).",
                ]
                recommendation = "Ask for a specific metric and dimension (e.g. units by make)."
                result_summary = f"{n} rows returned"

        narrative = self._join_paras(paras)
        base = {
            "headline": headline,
            "narrative_text": narrative,
            "summary": headline,
            "key_findings": [],  # prose carries the insight; avoid one-word bullet noise
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
            if len(snip) > 280:
                snip = snip[:277] + "…"
            context_bits.append(snip)
            citations.append({
                "source_doc": src,
                "source_page": s.get("source_page"),
                "title": title,
            })

        extra = context_bits[0] if context_bits else ""
        if extra:
            body = narration.get("narrative_text", "")
            narration["narrative_text"] = (
                f"{body}\n\nBusiness context from operating guidance: {extra}"
            ).strip()
            narration["summary"] = narration["narrative_text"]

        q = (question or "").lower()
        rec = narration.get("recommendation") or ""
        if any(w in q for w in ("covid", "2020", "recovery")):
            rec = "Compare vs 2019 baseline — treat 2020 as COVID-depressed (IND-PV-SOP-002)."
        elif any(w in q for w in ("ev", "electric", "powertrain", "bev")):
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

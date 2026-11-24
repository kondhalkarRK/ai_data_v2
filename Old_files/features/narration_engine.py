"""
features/narration_engine.py
LLM-driven executive narration grounded in query result DataFrames.
Falls back to rule-based summaries when the LLM is unavailable.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from core.llm_client import call_llm_narration

try:
    from config.constants import OKF_ENABLED
except ImportError:
    OKF_ENABLED = False

try:
    from config.constants import (
        NARRATION_USE_LLM,
        NARRATION_MAX_SAMPLE_ROWS,
    )
except ImportError:
    NARRATION_USE_LLM = False
    NARRATION_MAX_SAMPLE_ROWS = 12


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

    @staticmethod
    def _wants_llm_narration(question: str) -> bool:
        q = (question or "").lower()
        return any(
            w in q
            for w in (
                "why ", "explain", "how come", "interpret",
                "tell me more", "what caused", "deep dive",
            )
        )

    def _join_paras(self, parts: list[str]) -> str:
        return "\n\n".join(p.strip() for p in parts if p and str(p).strip())

    def _build_data_context(self, result_df: pd.DataFrame, max_rows: int | None = None) -> str:
        """Compact tabular summary for optional LLM narration."""
        cap = max_rows if max_rows is not None else NARRATION_MAX_SAMPLE_ROWS
        lines = [
            f"Shape: {len(result_df)} rows × {result_df.shape[1]} columns",
            f"Columns: {', '.join(str(c) for c in result_df.columns)}",
        ]
        num_cols = result_df.select_dtypes(include="number").columns.tolist()
        for col in num_cols[:8]:
            s = pd.to_numeric(result_df[col], errors="coerce").dropna()
            if s.empty:
                continue
            lines.append(
                f"  {col}: min={s.min():,.2f}, max={s.max():,.2f}, "
                f"sum={s.sum():,.2f}, mean={s.mean():,.2f}"
            )
        str_cols = result_df.select_dtypes(exclude="number").columns.tolist()
        for col in str_cols[:3]:
            top = result_df[col].astype(str).value_counts().head(5)
            if not top.empty:
                pairs = ", ".join(f"{k} ({v})" for k, v in top.items())
                lines.append(f"  Top {col}: {pairs}")
        sample = result_df.head(max_rows)
        lines.append("\nRESULT TABLE (CSV):")
        lines.append(sample.to_csv(index=False))
        if len(result_df) > max_rows:
            lines.append(f"\n... {len(result_df) - max_rows} additional rows not shown")
        return "\n".join(lines)

    def _parse_llm_narration(self, text: str, question: str) -> dict[str, Any] | None:
        if not text or not str(text).strip():
            return None
        raw = str(text).strip()

        def _section(label: str) -> str:
            m = re.search(
                rf"(?:^|\n){label}\s*:?\s*\n(.*?)(?=\n(?:HEADLINE|NARRATIVE|FINDINGS|RECOMMENDATION)\s*:|\Z)",
                raw,
                flags=re.IGNORECASE | re.DOTALL,
            )
            return m.group(1).strip() if m else ""

        headline = _section("HEADLINE") or raw.split("\n", 1)[0].strip()
        narrative = _section("NARRATIVE") or raw
        findings_raw = _section("FINDINGS")
        recommendation = _section("RECOMMENDATION")

        findings: list[str] = []
        if findings_raw:
            for line in findings_raw.splitlines():
                line = line.strip().lstrip("-•*").strip()
                if line:
                    findings.append(line)

        if not headline and not narrative:
            return None

        narrative = narrative.strip()
        if headline and narrative.startswith(headline):
            narrative = narrative[len(headline):].strip()

        return {
            "headline": headline[:200] or "Executive insight",
            "narrative_text": narrative or headline,
            "summary": narrative or headline,
            "key_findings": findings[:6],
            "recommendation": recommendation or "Drill into the top and bottom performers by region or month.",
            "result_summary": headline[:120],
            "data_points": [],
            "word_count": len((narrative or headline).split()),
            "knowledge_citations": [],
            "narration_source": "llm",
        }

    def _generate_llm_narration(
        self,
        result_df: pd.DataFrame,
        question: str,
        evidence: dict | None = None,
        knowledge_snippets: list | None = None,
    ) -> dict[str, Any] | None:
        try:
            data_ctx = self._build_data_context(result_df)
            sql_hint = ""
            if evidence and evidence.get("execution_path"):
                sql_hint = f"Query path: {evidence.get('execution_path')}"

            knowledge_lines = []
            for snippet in (knowledge_snippets or [])[:3]:
                source = snippet.get("source_doc") or "business document"
                locator = snippet.get("source_locator") or (
                    f"page {snippet.get('source_page', '')}"
                )
                body = (snippet.get("snippet") or "")[:420]
                knowledge_lines.append(f"[{source}, {locator}] {body}")
            knowledge_context = "\n".join(knowledge_lines) or "None retrieved."

            prompt = f"""You are a senior insurance BI analyst writing executive insights.
Use DATA only for numbers. Prefer actionable intelligence over generic summaries.

QUESTION: "{question}"
{sql_hint}

DATA:
{data_ctx}

BUSINESS KNOWLEDGE:
{knowledge_context}

Cover when supported by DATA (skip empty sections):
- Trend analysis (growth, decline, seasonality)
- Risk (concentration by region/product, claim pressure)
- Financial (premium-to-claim / loss ratio signals)
- Anomalies (spikes, drops, outliers)
- One concrete business recommendation

Format (max ~160 words):

HEADLINE: one line with the key business takeaway
NARRATIVE: 1–2 short paragraphs with specific values
FINDINGS: 3–5 bullets with numbers (trend/risk/financial/anomaly)
RECOMMENDATION: one actionable follow-up

No markdown fences. No invented figures."""

            text = call_llm_narration(prompt)
            parsed = self._parse_llm_narration(text or "", question)
            if parsed and knowledge_snippets:
                parsed["knowledge_citations"] = [
                    {
                        "source_doc": snippet.get("source_doc"),
                        "source_page": snippet.get("source_page"),
                        "source_locator": snippet.get("source_locator"),
                        "title": snippet.get("title"),
                    }
                    for snippet in knowledge_snippets[:3]
                ]
            return parsed
        except Exception:
            return None

    def generate_narration(
        self,
        result_df: pd.DataFrame,
        question: str,
        intent: dict | None = None,
        evidence: dict | None = None,
        mode: str = "standard",
        knowledge_snippets: list | None = None,
        force_llm: bool = False,
    ) -> dict[str, Any]:
        q_hint = self._q_hint(question)

        if result_df is None or result_df.empty:
            return {
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

        use_llm = bool(force_llm) or NARRATION_USE_LLM or self._wants_llm_narration(question)
        if use_llm:
            if knowledge_snippets is None and OKF_ENABLED:
                try:
                    from features.okf_knowledge.okf_retriever import (
                        get_relevant_snippets,
                    )
                    knowledge_snippets = get_relevant_snippets(
                        question, top_k=3, max_context_chars=1000
                    )
                except Exception:
                    knowledge_snippets = []
            llm_narr = self._generate_llm_narration(
                result_df,
                question,
                evidence,
                knowledge_snippets=knowledge_snippets,
            )
            if llm_narr:
                return llm_narr

        try:
            from features.business_insights import generate_business_insights
            bi = generate_business_insights(result_df, question)
            if bi and (bi.get("key_findings") or bi.get("narrative_text")):
                return bi
        except Exception:
            pass

        return self._generate_rule_based_narration(
            result_df, question, intent=intent, evidence=evidence,
            knowledge_snippets=knowledge_snippets,
        )

    def _generate_rule_based_narration(
        self,
        result_df: pd.DataFrame,
        question: str,
        intent: dict | None = None,
        evidence: dict | None = None,
        knowledge_snippets: list | None = None,
    ) -> dict[str, Any]:
        q_hint = self._q_hint(question)

        if result_df is None or result_df.empty:
            return {
                "headline": "No results",
                "narrative_text": "",
                "key_findings": [],
                "recommendation": "",
                "result_summary": "No rows returned",
                "summary": "No rows returned",
                "word_count": 0,
                "knowledge_citations": [],
            }

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
            "key_findings": [],
            "recommendation": recommendation,
            "result_summary": result_summary,
            "data_points": [{"label": metric, "rows": n}],
            "word_count": len(narrative.split()),
            "knowledge_citations": [],
            "narration_source": "rule_based",
        }
        if OKF_ENABLED:
            return self._enrich_with_knowledge(base, question, knowledge_snippets)
        return base

    def _enrich_with_knowledge(
        self,
        narration: dict[str, Any],
        question: str,
        knowledge_snippets: list | None = None,
    ) -> dict[str, Any]:
        """Merge OKF / SOP context into narrative — only when OKF_ENABLED."""
        if not OKF_ENABLED:
            return narration
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
            src = s.get("source_doc") or "Business document"
            title = s.get("title") or ""
            snip = (s.get("snippet") or "").replace("\n", " ")
            if len(snip) > 280:
                snip = snip[:277] + "…"
            context_bits.append(snip)
            citations.append({
                "source_doc": src,
                "source_page": s.get("source_page"),
                "source_locator": s.get("source_locator"),
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

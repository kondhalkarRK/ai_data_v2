"""
features/whatif_engine.py
Interactive what-if scenarios on DataFrame copies (slider support).
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

try:
    import streamlit as st
except ImportError:
    st = None  # type: ignore


_WHATIF_PATTERNS = [
    r"\bwhat\s+if\b",
    r"\bsuppose\b",
    r"\bassume\b",
    r"\bsimulate\b",
    r"\bscenario\b",
    r"\bwhat\s+would\s+happen\b",
    r"\bwhat\s+happens\s+when\b",
    r"\bif\s+we\s+(increase|decrease)\b",
    r"\bproject\b",
    r"\bif\s+.+\bchange[sd]?\s+by\b",
    r"\b\d+\s*%\b",
]


class WhatIfEngine:
    def detect_whatif_query(self, question: str) -> bool:
        if not question:
            return False
        q = question.lower()
        return any(re.search(p, q) for p in _WHATIF_PATTERNS)

    def parse_scenario(self, question: str, df: pd.DataFrame | None = None) -> dict[str, Any]:
        q = (question or "").strip()
        ql = q.lower()

        direction = "increase"
        if any(w in ql for w in ["decrease", "drop", "reduce", "fall", "down"]):
            direction = "decrease"

        change_type = "percent"
        change_value = 10.0
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", ql)
        if m:
            change_value = float(m.group(1))
            change_type = "percent"
        else:
            m = re.search(r"(?:by|sold|add(?:ed)?|more)\s+(\d+(?:\.\d+)?)", ql)
            if m:
                change_value = float(m.group(1))
                change_type = "absolute"

        metric = "revenue"
        for key, canon in (
            ("units", "units_sold"),
            ("volume", "units_sold"),
            ("orders", "order_count"),
            ("revenue", "revenue"),
            ("sales", "revenue"),
        ):
            if key in ql:
                metric = canon
                break

        metric_column = self._resolve_column(df, metric) if df is not None else "total_sales"

        filter_dimension = None
        filter_value = None
        m = re.search(r"\b([A-Z][a-zA-Z]+)\s+(sales|revenue)\b", q)
        if m:
            filter_dimension = "make"
            filter_value = m.group(1)
        for dim in ("make", "colour_name", "color", "region", "model", "car_type"):
            if dim.replace("_", " ") in ql or dim in ql:
                filter_dimension = "colour_name" if dim in ("color", "colour_name") else dim
                break

        return {
            "metric": metric,
            "metric_column": metric_column,
            "change_type": change_type,
            "change_value": change_value,
            "direction": direction,
            "filter_dimension": filter_dimension,
            "filter_value": filter_value,
            "confidence": "high" if m or "%" in q else "medium",
        }

    def _resolve_column(self, df: pd.DataFrame, metric: str | None) -> str | None:
        if df is None or df.empty:
            return None
        mapping = {
            "revenue": ["total_sales", "revenue", "sales", "amount"],
            "units_sold": ["order_qty", "units_sold", "quantity", "qty"],
            "order_count": ["order_id", "orders"],
        }
        candidates = mapping.get(metric or "", [metric or ""])
        lower = {c.lower(): c for c in df.columns}
        for cand in candidates:
            if cand in df.columns:
                return cand
            if cand and cand.lower() in lower:
                return lower[cand.lower()]
        nums = df.select_dtypes(include="number").columns.tolist()
        return nums[0] if nums else None

    def run_scenario(
        self,
        df: pd.DataFrame,
        scenario: dict,
        override_value: float | None = None,
    ) -> dict[str, Any]:
        scenario = dict(scenario or {})
        work = df.copy()
        col = scenario.get("metric_column") or self._resolve_column(work, scenario.get("metric"))
        if col is None:
            return {
                "baseline_total": 0.0,
                "scenario_total": 0.0,
                "delta_absolute": 0.0,
                "delta_percent": 0.0,
                "direction": "up",
                "dimension_impact": pd.DataFrame(),
                "narrative": "Could not resolve a metric column.",
                "assumptions": ["No numeric metric column found."],
                "change_applied": 0.0,
                # legacy keys for older UI
                "baseline": {"value": 0.0, "label": "N/A"},
                "scenario": {"value": 0.0, "label": "N/A"},
                "delta": {"absolute": 0.0, "percent": 0.0, "direction": "up"},
                "chart_data": pd.DataFrame(),
            }

        fdim = scenario.get("filter_dimension")
        fval = scenario.get("filter_value")
        mask = pd.Series(True, index=work.index)
        if fdim and fdim in work.columns and fval:
            mask = work[fdim].astype(str).str.lower().str.contains(str(fval).lower(), na=False)

        baseline_total = float(work.loc[mask, col].sum()) if mask.any() else float(work[col].sum())

        change_value = float(
            override_value if override_value is not None else (scenario.get("change_value") or 0)
        )
        direction = scenario.get("direction", "increase")
        change_type = scenario.get("change_type", "percent")

        changed = work.copy()
        target = changed.loc[mask, col] if mask.any() else changed[col]
        if change_type == "percent":
            factor = change_value / 100.0
            if direction == "decrease":
                factor = -abs(factor)
            else:
                factor = abs(factor) if override_value is None else factor
            # If override from slider, treat as signed percent directly
            if override_value is not None:
                factor = float(override_value) / 100.0
            new_vals = target * (1 + factor)
            applied = factor * 100
        else:
            delta = change_value if direction != "decrease" else -change_value
            if override_value is not None:
                delta = float(override_value)
            new_vals = target + delta
            applied = delta

        if mask.any():
            changed.loc[mask, col] = new_vals
        else:
            changed[col] = new_vals

        scenario_total = float(changed.loc[mask, col].sum()) if mask.any() else float(changed[col].sum())
        abs_delta = scenario_total - baseline_total
        pct = (abs_delta / baseline_total * 100) if baseline_total else 0.0
        dir_label = "up" if abs_delta >= 0 else "down"

        # Dimension impact
        dim_candidates = [
            c for c in ("make", "colour_name", "car_type", "model", "region")
            if c in work.columns
        ]
        impact = pd.DataFrame()
        if dim_candidates:
            dim = dim_candidates[0]
            try:
                b = work.groupby(dim)[col].sum().rename("baseline")
                s = changed.groupby(dim)[col].sum().rename("scenario")
                impact = pd.concat([b, s], axis=1).fillna(0)
                impact["delta"] = impact["scenario"] - impact["baseline"]
                impact["delta_pct"] = impact.apply(
                    lambda r: (r["delta"] / r["baseline"] * 100) if r["baseline"] else 0,
                    axis=1,
                )
                impact = impact.sort_values("delta", key=abs, ascending=False).reset_index()
            except Exception:
                impact = pd.DataFrame()

        label = scenario.get("metric") or col
        assumptions = [
            f"Applied to column `{col}`",
            f"Change applied: {applied:+.1f}{'%' if change_type == 'percent' or override_value is not None else ''}",
            "Simulation uses a DataFrame copy — source data unchanged",
        ]
        if fdim and fval:
            assumptions.append(f"Filter: {fdim}={fval}")

        narrative = (
            f"If {label} changed by {applied:+.1f}"
            f"{'%' if change_type == 'percent' or override_value is not None else ''}, "
            f"total would move from {baseline_total:,.1f} to {scenario_total:,.1f} "
            f"({pct:+.1f}%)."
        )
        if not impact.empty:
            top = impact.iloc[0]
            narrative += (
                f" Largest impact: {top[impact.columns[0]]} "
                f"({float(top['delta']):+.1f})."
            )

        chart_data = pd.DataFrame({
            "scenario": ["Baseline", "What-If"],
            "value": [baseline_total, scenario_total],
        })

        return {
            "baseline_total": baseline_total,
            "scenario_total": scenario_total,
            "delta_absolute": abs_delta,
            "delta_percent": pct,
            "direction": dir_label,
            "dimension_impact": impact,
            "narrative": narrative,
            "assumptions": assumptions,
            "change_applied": float(applied),
            "baseline": {"value": baseline_total, "label": f"Current {label}"},
            "scenario": {"value": scenario_total, "label": "After change"},
            "delta": {"absolute": abs_delta, "percent": pct, "direction": dir_label},
            "chart_data": chart_data,
        }

    def generate_whatif_narrative(self, scenario_result: dict) -> str:
        return (scenario_result or {}).get("narrative") or "No scenario result."

    def generate_interactive_result(self, scenario_result: dict, question: str, df: pd.DataFrame, scenario: dict):
        """Render interactive what-if UI with live slider."""
        if st is None:
            return
        if not scenario_result:
            st.info("No what-if result.")
            return

        st.markdown(
            f"""
            <div class="narration-card">
              <div class="narration-headline">🔍 What-If Analysis</div>
              <div class="narration-body">{scenario_result.get('narrative','')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        current = float(scenario_result.get("change_applied") or 0)
        key = "whatif_slider"
        new_value = st.slider(
            "Adjust scenario percentage",
            min_value=-100,
            max_value=200,
            value=int(current),
            step=5,
            format="%d%%",
            key=key,
        )

        if int(new_value) != int(current):
            scenario_result = self.run_scenario(df, scenario, override_value=float(new_value))
            st.session_state["whatif_last_result"] = scenario_result

        result = st.session_state.get("whatif_last_result", scenario_result)
        direction = result.get("direction", "up")
        colour = "#34d399" if direction == "up" else "#fca5a5"
        icon = "⬆️" if direction == "up" else "⬇️"

        c1, c2, c3 = st.columns([2, 1, 2])
        with c1:
            st.markdown(
                f"""
                <div class="whatif-baseline-box">
                  <div class="whatif-value-label">BASELINE</div>
                  <div class="whatif-value-number" style="color:#a5b4fc;">
                    {result.get('baseline_total', 0):,.1f}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"""
                <div style="text-align:center;padding:16px 0;">
                  <div style="font-size:28px;">{icon}</div>
                  <div style="font-size:16px;font-weight:700;color:{colour};">
                    {float(result.get('delta_percent') or 0):+.1f}%
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c3:
            box = "whatif-scenario-box-up" if direction == "up" else "whatif-scenario-box-down"
            st.markdown(
                f"""
                <div class="{box}">
                  <div class="whatif-value-label">SCENARIO</div>
                  <div class="whatif-value-number" style="color:{colour};">
                    {result.get('scenario_total', 0):,.1f}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        impact = result.get("dimension_impact")
        if isinstance(impact, pd.DataFrame) and not impact.empty:
            st.markdown("**Impact by dimension:**")
            st.dataframe(impact.head(12), use_container_width=True, height=200)

        assumptions = result.get("assumptions") or []
        if assumptions:
            st.markdown("**Assumptions:**")
            for a in assumptions:
                st.caption(f"• {a}")

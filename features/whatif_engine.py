"""
features/whatif_engine.py
Forward-looking scenario simulation on DataFrame copies.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd


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
    r"\bforecast\b",
    r"\bif\s+.+\bchange[sd]?\s+by\b",
    r"\b\d+\s*%\b",
]


class WhatIfEngine:
    """Statistical what-if scenarios on CSV/DataFrame data."""

    def detect_whatif_query(self, question: str) -> bool:
        if not question:
            return False
        q = question.lower()
        return any(re.search(p, q) for p in _WHATIF_PATTERNS)

    def parse_scenario(self, question: str) -> dict[str, Any]:
        q = (question or "").strip()
        ql = q.lower()

        change_type = "increase"
        if any(w in ql for w in ["decrease", "drop", "reduce", "fall", "down"]):
            change_type = "decrease"
        elif re.search(r"\bset\s+to\b", ql):
            change_type = "set_to"
        elif re.search(r"\bmultipl", ql):
            change_type = "multiply"

        change_unit = "percent"
        change_value = None
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", ql)
        if m:
            change_value = float(m.group(1))
            change_unit = "percent"
        else:
            m = re.search(
                r"(?:by|sold|add(?:ed)?|more)\s+(\d+(?:\.\d+)?)",
                ql,
            )
            if m:
                change_value = float(m.group(1))
                change_unit = "absolute"

        metric = None
        for key in ("revenue", "sales", "units", "orders", "price", "volume"):
            if key in ql:
                metric = {
                    "revenue": "revenue",
                    "sales": "revenue",
                    "units": "units_sold",
                    "volume": "units_sold",
                    "orders": "order_count",
                    "price": "avg_price",
                }[key]
                break

        dimension = None
        filt = None
        for dim_key in ("make", "brand", "colour", "color", "region", "model", "category"):
            if dim_key in ql:
                dimension = {
                    "brand": "make",
                    "colour": "colour_name",
                    "color": "colour_name",
                }.get(dim_key, dim_key)
                # try capture a value after the dimension word or before "sales"
                m = re.search(
                    rf"\b([A-Za-z][A-Za-z0-9_-]+)\s+(?:sales|revenue|{dim_key})",
                    q,
                    re.I,
                )
                if m and m.group(1).lower() not in (
                    "what", "if", "the", "our", "all", "total",
                ):
                    filt = {dimension: m.group(1)}
                break

        # "Ford sales" style
        m = re.search(r"\b([A-Z][a-zA-Z]+)\s+(sales|revenue)\b", q)
        if m:
            filt = filt or {"make": m.group(1)}
            dimension = dimension or "make"
            metric = metric or "revenue"

        return {
            "metric": metric or "revenue",
            "dimension": dimension,
            "change_type": change_type,
            "change_value": change_value if change_value is not None else 10.0,
            "change_unit": change_unit,
            "filter": filt,
            "time_horizon": None,
        }

    def _resolve_column(self, df: pd.DataFrame, metric: str | None) -> str | None:
        if not metric:
            return None
        mapping = {
            "revenue": ["total_sales", "revenue", "sales", "amount"],
            "units_sold": ["order_qty", "units_sold", "quantity", "qty"],
            "order_count": ["order_id", "orders"],
            "avg_price": ["price_per_unit", "price", "avg_price"],
        }
        candidates = mapping.get(metric, [metric])
        lower = {c.lower(): c for c in df.columns}
        for cand in candidates:
            if cand in df.columns:
                return cand
            if cand.lower() in lower:
                return lower[cand.lower()]
        nums = df.select_dtypes(include="number").columns.tolist()
        return nums[0] if nums else None

    def run_scenario(self, df: pd.DataFrame, scenario: dict) -> dict[str, Any]:
        scenario = scenario or {}
        work = df.copy()
        col = self._resolve_column(work, scenario.get("metric"))
        if col is None:
            return {
                "baseline": {"value": 0.0, "label": "N/A", "breakdown": pd.DataFrame()},
                "scenario": {"value": 0.0, "label": "N/A", "breakdown": pd.DataFrame()},
                "delta": {"absolute": 0.0, "percent": 0.0, "direction": "up"},
                "narrative": "Could not resolve a numeric metric column for this scenario.",
                "chart_data": pd.DataFrame(),
                "assumptions": ["No suitable metric column found in the dataset."],
            }

        filt = scenario.get("filter") or {}
        mask = pd.Series(True, index=work.index)
        for k, v in filt.items():
            if k in work.columns:
                mask = mask & work[k].astype(str).str.lower().str.contains(
                    str(v).lower(), na=False
                )

        baseline_val = float(work.loc[mask, col].sum()) if mask.any() else float(work[col].sum())

        # Apply change on a copy — never mutate original
        changed = work.copy()
        ctype = scenario.get("change_type", "increase")
        cval = float(scenario.get("change_value") or 0)
        unit = scenario.get("change_unit", "percent")

        target = changed.loc[mask, col] if mask.any() else changed[col]
        if unit == "percent":
            factor = cval / 100.0
            if ctype == "decrease":
                factor = -factor
            elif ctype == "multiply":
                factor = cval - 1  # treat as multiplier delta
            new_vals = target * (1 + factor)
        else:
            delta = cval if ctype != "decrease" else -cval
            if ctype == "set_to":
                new_vals = pd.Series(cval, index=target.index)
            else:
                new_vals = target + delta

        if mask.any():
            changed.loc[mask, col] = new_vals
        else:
            changed[col] = new_vals

        scenario_val = float(changed.loc[mask, col].sum()) if mask.any() else float(changed[col].sum())
        abs_delta = scenario_val - baseline_val
        pct = (abs_delta / baseline_val * 100) if baseline_val else 0.0
        direction = "up" if abs_delta >= 0 else "down"

        label = scenario.get("metric") or col
        assumptions = [
            f"Applied to column `{col}`",
            f"Change: {ctype} by {cval}{'%' if unit == 'percent' else ''} ({unit})",
            "Simulation uses a DataFrame copy — source data unchanged",
        ]
        if filt:
            assumptions.append(f"Filter applied: {filt}")

        narrative = (
            f"If {label} {ctype}d by {cval}"
            f"{'%' if unit == 'percent' else ''}, "
            f"total would move from {baseline_val:,.1f} to {scenario_val:,.1f}, "
            f"a change of {abs_delta:,.1f} ({pct:+.1f}%)."
        )

        chart_data = pd.DataFrame({
            "scenario": ["Baseline", "What-If"],
            "value": [baseline_val, scenario_val],
        })

        dim = scenario.get("dimension")
        breakdown = pd.DataFrame()
        if dim and dim in work.columns:
            try:
                b = work.groupby(dim)[col].sum().rename("baseline")
                s = changed.groupby(dim)[col].sum().rename("scenario")
                breakdown = pd.concat([b, s], axis=1).reset_index()
            except Exception:
                breakdown = pd.DataFrame()

        return {
            "baseline": {
                "value": baseline_val,
                "label": f"Current {label}",
                "breakdown": breakdown,
            },
            "scenario": {
                "value": scenario_val,
                "label": f"After {ctype}",
                "breakdown": breakdown,
            },
            "delta": {
                "absolute": abs_delta,
                "percent": pct,
                "direction": direction,
            },
            "narrative": narrative,
            "chart_data": chart_data,
            "assumptions": assumptions,
        }

    def generate_whatif_narrative(self, scenario_result: dict) -> str:
        if not scenario_result:
            return "No scenario result available."
        base = scenario_result.get("baseline", {})
        scen = scenario_result.get("scenario", {})
        delta = scenario_result.get("delta", {})
        assumptions = scenario_result.get("assumptions") or []
        parts = [
            scenario_result.get("narrative")
            or (
                f"Baseline {base.get('label', 'value')} is {base.get('value', 0):,.1f}. "
                f"Scenario reaches {scen.get('value', 0):,.1f} "
                f"({delta.get('percent', 0):+.1f}%)."
            ),
            "Assumptions: " + "; ".join(assumptions),
            "Confidence: illustrative statistical simulation on loaded CSV data only.",
        ]
        return " ".join(parts)

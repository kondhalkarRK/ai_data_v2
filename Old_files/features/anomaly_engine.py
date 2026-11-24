"""
features/anomaly_engine.py
Statistical anomaly detection for loaded DataFrames.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


_SENSITIVITY_Z = {
    "low": 3.0,
    "medium": 2.0,
    "high": 1.5,
}


class AnomalyEngine:
    """Detect statistical anomalies in CSV/DataFrame data."""

    def detect_anomalies(
        self,
        df: pd.DataFrame,
        sensitivity: str = "medium",
    ) -> list[dict]:
        if df is None or df.empty:
            return []

        z_thresh = _SENSITIVITY_Z.get(sensitivity, 2.0)
        anomalies: list[dict] = []
        num_cols = df.select_dtypes(include="number").columns.tolist()

        # A) Z-score
        for col in num_cols[:8]:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(s) < 5:
                continue
            mean, std = float(s.mean()), float(s.std())
            if std == 0 or np.isnan(std):
                continue
            z = (s - mean) / std
            extreme = z.abs().sort_values(ascending=False).head(5)
            for idx, zv in extreme.items():
                if abs(float(zv)) < z_thresh:
                    continue
                val = float(s.loc[idx])
                anomalies.append({
                    "type": "outlier",
                    "column": col,
                    "dimension": None,
                    "value": val,
                    "expected": mean,
                    "deviation": val - mean,
                    "deviation_pct": ((val - mean) / abs(mean) * 100) if mean else 0.0,
                    "direction": "high" if val > mean else "low",
                    "severity": (
                        "critical" if abs(float(zv)) >= 3
                        else "warning" if abs(float(zv)) >= 2
                        else "info"
                    ),
                    "description": (
                        f"{col.replace('_', ' ').title()} value {val:,.2f} is "
                        f"{abs(float(zv)):.1f}σ from the mean ({mean:,.2f})"
                    ),
                    "suggested_question": f"Show details for extreme {col} values",
                    "row_reference": {"index": int(idx) if str(idx).isdigit() else idx},
                })

        # B) IQR
        for col in num_cols[:6]:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(s) < 8:
                continue
            q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
            iqr = q3 - q1
            if iqr == 0:
                continue
            low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            outliers = s[(s < low) | (s > high)]
            for idx, val in outliers.head(3).items():
                val = float(val)
                anomalies.append({
                    "type": "outlier",
                    "column": col,
                    "dimension": None,
                    "value": val,
                    "expected": float(s.median()),
                    "deviation": val - float(s.median()),
                    "deviation_pct": (
                        (val - float(s.median())) / abs(float(s.median())) * 100
                        if s.median() else 0.0
                    ),
                    "direction": "high" if val > high else "low",
                    "severity": "warning",
                    "description": (
                        f"{col.replace('_', ' ').title()} {val:,.2f} is outside "
                        f"IQR fences [{low:,.1f}, {high:,.1f}]"
                    ),
                    "suggested_question": f"Show distribution of {col}",
                    "row_reference": None,
                })

        # C) Temporal
        date_cols = [
            c for c in df.columns
            if pd.api.types.is_datetime64_any_dtype(df[c]) or "date" in c.lower()
        ]
        if date_cols and num_cols:
            dc, mc = date_cols[0], num_cols[0]
            try:
                tmp = df[[dc, mc]].copy()
                tmp[dc] = pd.to_datetime(tmp[dc], errors="coerce")
                tmp = tmp.dropna(subset=[dc])
                tmp["period"] = tmp[dc].dt.to_period("M").astype(str)
                series = tmp.groupby("period")[mc].sum().sort_index()
                if len(series) >= 4:
                    roll = series.rolling(3, min_periods=2).mean()
                    last_p = series.index[-1]
                    last_v = float(series.iloc[-1])
                    exp = float(roll.iloc[-1]) if not np.isnan(roll.iloc[-1]) else last_v
                    if exp:
                        pct = (last_v - exp) / abs(exp) * 100
                        if abs(pct) >= 20:
                            anomalies.append({
                                "type": "temporal",
                                "column": mc,
                                "dimension": last_p,
                                "value": last_v,
                                "expected": exp,
                                "deviation": last_v - exp,
                                "deviation_pct": pct,
                                "direction": "high" if pct > 0 else "low",
                                "severity": "critical" if abs(pct) >= 40 else "warning",
                                "description": (
                                    f"{mc.replace('_', ' ').title()} in {last_p} was "
                                    f"{pct:+.0f}% vs 3-month rolling average"
                                ),
                                "suggested_question": f"Show {mc} trend by month",
                                "row_reference": None,
                            })
            except Exception:
                pass

        # D) Categorical concentration / deviation
        cat_cols = [
            c for c in df.columns
            if (df[c].dtype == object or str(df[c].dtype) == "category")
            and 1 < df[c].nunique() <= 40
        ]
        if cat_cols and num_cols:
            dim, mc = cat_cols[0], num_cols[0]
            try:
                g = df.groupby(dim)[mc].sum()
                total = float(g.sum())
                if total > 0:
                    top = g.idxmax()
                    share = float(g.max()) / total * 100
                    mean_share = 100 / max(len(g), 1)
                    if share > max(40, mean_share * 2.5):
                        anomalies.append({
                            "type": "categorical",
                            "column": mc,
                            "dimension": str(top),
                            "value": float(g.max()),
                            "expected": total / len(g),
                            "deviation": float(g.max()) - total / len(g),
                            "deviation_pct": share - mean_share,
                            "direction": "high",
                            "severity": "info",
                            "description": (
                                f"{top} holds {share:.0f}% of {mc}, "
                                f"well above equal-share ({mean_share:.0f}%)"
                            ),
                            "suggested_question": f"Show {mc} by {dim}",
                            "row_reference": None,
                        })
            except Exception:
                pass

        # Deduplicate-ish by description, keep most severe
        sev_rank = {"critical": 0, "warning": 1, "info": 2}
        anomalies.sort(key=lambda a: (sev_rank.get(a.get("severity", "info"), 9), -abs(a.get("deviation_pct", 0))))
        return anomalies[:12]

    def summarise_anomalies(self, anomalies: list[dict]) -> str:
        if not anomalies:
            return "I did not find significant anomalies in your data at the current sensitivity."
        lines = [f"I found {len(anomalies)} anomalies in your data:"]
        for a in anomalies[:5]:
            lines.append(f"• {a.get('description', 'Unusual value detected')}")
        return "\n".join(lines)

    def get_anomaly_badge(self, anomaly: dict) -> dict[str, str]:
        sev = (anomaly or {}).get("severity", "info")
        if sev == "critical":
            return {"icon": "🔴", "colour": "red", "label": "Critical"}
        if sev == "warning":
            return {"icon": "🟡", "colour": "amber", "label": "Warning"}
        return {"icon": "🔵", "colour": "blue", "label": "Info"}

    def run_smart_anomaly_check(
        self,
        df: pd.DataFrame,
        question: str,
    ) -> list[dict]:
        q = (question or "").lower()
        triggers = [
            "anomaly", "anomalies", "unusual", "outlier",
            "what's wrong", "flag", "stands out", "anything strange",
            "anything odd", "what stands out",
        ]
        if not any(t in q for t in triggers):
            return []
        return self.detect_anomalies(df)

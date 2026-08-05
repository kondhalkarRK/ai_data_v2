"""
features/okf_knowledge/target_alignment.py
Compare retail actuals (working dataset) vs OKF FY2026 targets (IND-PV-REG-001).
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

_ZONES = ("North", "West", "South", "East", "Central")
_REGISTRY_PATH = Path(__file__).resolve().parent / "targets_fy2026.yaml"

_ALIGNMENT_SIGNALS = (
    "align with target", "aligned with target", "alignment with target",
    "on track", "on-track", "vs target", "versus target", "against target",
    "gap to target", "gap vs target", "target vs actual", "actual vs target",
    "meet target", "meeting target", "missing target", "behind target",
    "ahead of target", "ahead of plan", "behind plan",
    "monthly sales align", "sales align", "volume align", "units align",
    "compare to target", "compare with target", "compared to target",
    "how are we doing against", "are we hitting target",
)


def _load_registry() -> dict:
    if not _REGISTRY_PATH.is_file():
        return {}
    with open(_REGISTRY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def is_target_alignment_question(question: str) -> bool:
    q = (question or "").lower().strip()
    if not q:
        return False
    if any(s in q for s in _ALIGNMENT_SIGNALS):
        return True
    if "target" in q and any(
        w in q for w in (
            "align", "track", "gap", "vs", "versus", "actual",
            "compare", "monthly", "plan", "forecast", "variance",
        )
    ):
        return True
    return False


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {str(c).lower(): c for c in df.columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    for cand in candidates:
        for k, v in lower.items():
            if cand in k:
                return v
    return None


def _parse_zone(question: str) -> str | None:
    q = (question or "").lower()
    for z in _ZONES:
        if z.lower() in q:
            return z
    return None


def _parse_grain(question: str) -> str:
    q = (question or "").lower()
    if any(w in q for w in ("monthly", "by month", "each month", "month by month")):
        return "monthly"
    if any(w in q for w in ("ytd", "year to date", "so far", "to date")):
        return "ytd"
    if "month" in q:
        return "monthly"
    return "monthly"


def _monthly_national_target(reg: dict, period: pd.Period) -> float:
    nat = reg.get("national") or {}
    h1 = set(str(m) for m in (reg.get("h1_months") or []))
    h2 = set(str(m) for m in (reg.get("h2_months") or []))
    key = str(period)
    if key in h1:
        return float(nat.get("h1_units", 65320)) / max(len(h1), 1)
    if key in h2:
        return float(nat.get("h2_units", 76680)) / max(len(h2), 1)
    return float(nat.get("annual_units", 142000)) / 12.0


def _monthly_zone_target(reg: dict, zone: str, period: pd.Period) -> float:
    zones = reg.get("zones") or {}
    zdata = zones.get(zone) or {}
    annual = float(zdata.get("annual_units") or 0)
    if not annual:
        return 0.0
    nat_annual = float((reg.get("national") or {}).get("annual_units") or 142000)
    nat_month = _monthly_national_target(reg, period)
    if nat_annual <= 0:
        return annual / 12.0
    return annual * (nat_month / (nat_annual / 12.0))


def _status(variance_pct: float, reg: dict) -> str:
    th = reg.get("thresholds") or {}
    on_track = float(th.get("on_track_min_pct", -5.0))
    ahead = float(th.get("ahead_min_pct", 5.0))
    if variance_pct >= ahead:
        return "Ahead"
    if variance_pct >= on_track:
        return "On Track"
    return "Behind"


def compute_target_alignment(
    question: str,
    working_df: pd.DataFrame | None,
) -> dict[str, Any] | None:
    """
    Build actual vs target comparison table + metadata for narration.
    Returns None if data or registry unavailable.
    """
    if working_df is None or working_df.empty:
        return None
    reg = _load_registry()
    if not reg:
        return None

    qty_col = _find_col(working_df, ["order_qty", "units", "quantity", "qty"])
    date_col = _find_col(working_df, ["sales_date", "sale_date", "order_date", "date"])
    region_col = _find_col(working_df, ["region_name", "region", "zone"])
    if not qty_col or not date_col:
        return None

    df = working_df[[qty_col, date_col] + ([region_col] if region_col else [])].copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[qty_col] = pd.to_numeric(df[qty_col], errors="coerce")
    df = df.dropna(subset=[date_col, qty_col])
    if df.empty:
        return None

    fy_start = pd.Timestamp(reg.get("fy_start", "2026-04-01"))
    fy_end = pd.Timestamp(reg.get("fy_end", "2027-03-31"))
    df = df[(df[date_col] >= fy_start) & (df[date_col] <= fy_end)]
    if df.empty:
        return None

    zone = _parse_zone(question)
    grain = _parse_grain(question)
    scope = zone or "National"
    fy_label = reg.get("fy_label", "FY2026")

    if zone and region_col:
        df = df[df[region_col].astype(str).str.lower() == zone.lower()]
        if df.empty:
            return None

    df["period"] = df[date_col].dt.to_period("M")

    if grain == "monthly":
        rows: list[dict] = []
        for period, g in df.groupby("period", sort=True):
            actual = float(g[qty_col].sum())
            if zone:
                target = _monthly_zone_target(reg, zone, period)
            else:
                target = _monthly_national_target(reg, period)
            var_u = actual - target
            var_pct = (var_u / target * 100.0) if target else 0.0
            rows.append({
                "period": str(period),
                "month": period.strftime("%b %Y"),
                "scope": scope,
                "actual_units": int(round(actual)),
                "target_units": int(round(target)),
                "variance_units": int(round(var_u)),
                "variance_pct": round(var_pct, 1),
                "status": _status(var_pct, reg),
            })
        result_df = pd.DataFrame(rows)
        view = "monthly"
    else:
        months = sorted(df["period"].unique())
        actual_ytd = float(df[qty_col].sum())
        target_ytd = 0.0
        for p in months:
            if zone:
                target_ytd += _monthly_zone_target(reg, zone, p)
            else:
                target_ytd += _monthly_national_target(reg, p)
        var_u = actual_ytd - target_ytd
        var_pct = (var_u / target_ytd * 100.0) if target_ytd else 0.0
        result_df = pd.DataFrame([{
            "scope": scope,
            "months_in_scope": len(months),
            "actual_units": int(round(actual_ytd)),
            "target_units": int(round(target_ytd)),
            "variance_units": int(round(var_u)),
            "variance_pct": round(var_pct, 1),
            "status": _status(var_pct, reg),
        }])
        view = "ytd"

    if result_df.empty:
        return None

    return {
        "result_df": result_df,
        "registry": reg,
        "scope": scope,
        "zone": zone,
        "grain": view,
        "fy_label": fy_label,
        "doc_code": reg.get("doc_code", "IND-PV-REG-001"),
        "question": question,
    }


def build_alignment_sql(scope: str, grain: str, fy_label: str) -> str:
    zone_filter = f" AND region_name = '{scope}'" if scope != "National" else ""
    if grain == "monthly":
        return (
            f"-- Target vs actual ({fy_label}) — actuals from data; targets from { 'IND-PV-REG-001' }\n"
            f"SELECT DATE_TRUNC('month', sales_date) AS month,\n"
            f"       SUM(order_qty) AS actual_units\n"
            f"FROM fact_sales JOIN dim_region USING (region_id)\n"
            f"WHERE sales_date >= '2026-04-01' AND sales_date < '2027-04-01'{zone_filter}\n"
            f"GROUP BY 1 ORDER BY 1"
        )
    return (
        f"-- YTD target vs actual ({fy_label})\n"
        f"SELECT SUM(order_qty) AS actual_ytd\n"
        f"FROM fact_sales JOIN dim_region USING (region_id)\n"
        f"WHERE sales_date >= '2026-04-01' AND sales_date < '2027-04-01'{zone_filter}"
    )

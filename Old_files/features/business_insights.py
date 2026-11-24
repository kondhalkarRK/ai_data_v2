"""
features/business_insights.py
Deterministic BI-grade insights from a query result DataFrame (0 LLM tokens).
Insurance-aware heuristics for trend, risk, financial, anomaly, recommendations.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


_TIME_HINTS = (
    "month", "year", "quarter", "period", "date", "week", "accounting_month",
    "reported",
)
_REGION_HINTS = ("region", "territory", "zone", "state", "geo")
_PRODUCT_HINTS = ("product", "lob", "line_of_business", "coverage", "plan")
_CLAIM_HINTS = ("claim", "incurred", "paid", "severity", "loss")
_PREMIUM_HINTS = ("premium", "gwp", "earned", "written")
_RATIO_HINTS = ("ratio", "rate", "pct", "percent", "share")


def _col_lower_map(df: pd.DataFrame) -> dict[str, str]:
    return {str(c).lower(): str(c) for c in df.columns}


def _find_col(df: pd.DataFrame, hints: tuple[str, ...]) -> str | None:
    mapping = _col_lower_map(df)
    for h in hints:
        for low, orig in mapping.items():
            if h in low:
                return orig
    return None


def _num_cols(df: pd.DataFrame) -> list[str]:
    return df.select_dtypes(include="number").columns.tolist()


def _str_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in _num_cols(df)]


def _fmt(v: float) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(x) >= 1_000_000:
        return f"{x / 1_000_000:.2f}M"
    if abs(x) >= 10_000:
        return f"{x / 1_000:.1f}K"
    if abs(x) >= 100:
        return f"{x:,.0f}"
    if abs(x) < 1 and abs(x) > 0:
        return f"{x:.2%}" if abs(x) <= 1.5 else f"{x:.3f}"
    return f"{x:,.2f}"


def _metric_label(col: str) -> str:
    return str(col).replace("_", " ")


def _primary_metric(df: pd.DataFrame) -> str | None:
    nums = _num_cols(df)
    if not nums:
        return None
    # Prefer business metrics over rank/id
    skip = ("rank", "id", "key", "index", "row_number")
    preferred = []
    for c in nums:
        low = str(c).lower()
        if any(s in low for s in skip):
            continue
        preferred.append(c)
    pool = preferred or nums
    for hints in (_RATIO_HINTS, _CLAIM_HINTS, _PREMIUM_HINTS):
        hit = _find_col(df, hints)
        if hit and hit in pool:
            return hit
    # Largest variance as signal
    best, best_std = pool[0], -1.0
    for c in pool:
        s = pd.to_numeric(df[c], errors="coerce").dropna()
        if s.empty:
            continue
        std = float(s.std()) if len(s) > 1 else float(abs(s.iloc[0]))
        if std > best_std:
            best, best_std = c, std
    return best


def _trend_findings(df: pd.DataFrame, metric: str, time_col: str) -> list[str]:
    out: list[str] = []
    work = df[[time_col, metric]].copy()
    work[metric] = pd.to_numeric(work[metric], errors="coerce")
    work = work.dropna().sort_values(time_col)
    if len(work) < 2:
        return out
    first = float(work[metric].iloc[0])
    last = float(work[metric].iloc[-1])
    if first == 0:
        direction = "changed" if last != 0 else "flat"
        pct = None
    else:
        pct = (last - first) / abs(first)
        if pct > 0.05:
            direction = "grew"
        elif pct < -0.05:
            direction = "declined"
        else:
            direction = "stayed roughly flat"
    label = _metric_label(metric)
    if pct is None:
        out.append(
            f"Trend: {label} moved from {_fmt(first)} to {_fmt(last)} across the series."
        )
    else:
        out.append(
            f"Trend: {label} {direction} {_fmt(abs(pct))} "
            f"({_fmt(first)} → {_fmt(last)}) over the period."
        )
    # Simple seasonality: peak vs trough
    peak_i = work[metric].idxmax()
    trough_i = work[metric].idxmin()
    out.append(
        f"Seasonality signal: peak at {work.loc[peak_i, time_col]} "
        f"({_fmt(work.loc[peak_i, metric])}); "
        f"low at {work.loc[trough_i, time_col]} "
        f"({_fmt(work.loc[trough_i, metric])})."
    )
    return out


def _concentration_findings(df: pd.DataFrame, metric: str, dim: str) -> list[str]:
    out: list[str] = []
    work = df[[dim, metric]].copy()
    work[metric] = pd.to_numeric(work[metric], errors="coerce").fillna(0)
    g = work.groupby(dim, dropna=False)[metric].sum().sort_values(ascending=False)
    if g.empty or float(g.sum()) == 0:
        return out
    total = float(g.sum())
    top_name, top_val = g.index[0], float(g.iloc[0])
    share = top_val / total
    label = _metric_label(metric)
    out.append(
        f"Risk / concentration: {top_name} accounts for {share:.0%} of {label} "
        f"({_fmt(top_val)} of {_fmt(total)})."
    )
    if len(g) >= 3:
        top3 = float(g.iloc[:3].sum()) / total
        out.append(
            f"Top 3 {_metric_label(dim)} groups hold {top3:.0%} of {label} — "
            f"{'elevated concentration' if top3 >= 0.7 else 'moderately diversified'}."
        )
    return out


def _financial_findings(df: pd.DataFrame) -> list[str]:
    out: list[str] = []
    ratio = _find_col(df, ("loss_ratio", "loss ratio")) or _find_col(df, _RATIO_HINTS)
    incurred = _find_col(df, ("incurred", "claims_incurred", "claims incurred"))
    earned = _find_col(df, ("earned", "earned_premium", "premium"))
    paid = _find_col(df, ("paid", "claims_paid"))

    if ratio and ratio in df.columns:
        s = pd.to_numeric(df[ratio], errors="coerce").dropna()
        if not s.empty:
            out.append(
                f"Financial: loss/ratio metric averages {s.mean():.2f} "
                f"(min {s.min():.2f}, max {s.max():.2f}). "
                f"{'Watch ratios above 1.0 for underwriting pressure.' if s.max() >= 1 else 'Ratios remain within a manageable band in this cut.'}"
            )
    if incurred and earned and incurred in df.columns and earned in df.columns:
        inc = float(pd.to_numeric(df[incurred], errors="coerce").fillna(0).sum())
        ear = float(pd.to_numeric(df[earned], errors="coerce").fillna(0).sum())
        if ear > 0:
            lr = inc / ear
            out.append(
                f"Financial: implied claims-to-premium ratio is {lr:.2f} "
                f"(incurred {_fmt(inc)} / earned {_fmt(ear)})."
            )
    elif incurred and paid and incurred in df.columns and paid in df.columns:
        inc = float(pd.to_numeric(df[incurred], errors="coerce").fillna(0).sum())
        pd_ = float(pd.to_numeric(df[paid], errors="coerce").fillna(0).sum())
        if inc > 0:
            out.append(
                f"Financial: paid is {pd_ / inc:.0%} of incurred "
                f"({_fmt(pd_)} / {_fmt(inc)}) — remainder sits in reserve/outstanding."
            )
    return out


def _anomaly_findings(df: pd.DataFrame, metric: str, dim: str | None) -> list[str]:
    out: list[str] = []
    s = pd.to_numeric(df[metric], errors="coerce").dropna()
    if len(s) < 4:
        return out
    q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
    iqr = q3 - q1
    if iqr <= 0:
        return out
    hi, lo = q3 + 1.5 * iqr, q1 - 1.5 * iqr
    mask = (pd.to_numeric(df[metric], errors="coerce") > hi) | (
        pd.to_numeric(df[metric], errors="coerce") < lo
    )
    outliers = df.loc[mask.fillna(False)]
    if outliers.empty:
        out.append(
            f"Anomaly: no IQR outliers detected for {_metric_label(metric)} in this result."
        )
        return out
    row = outliers.iloc[0]
    who = str(row[dim]) if dim and dim in outliers.columns else "One row"
    out.append(
        f"Anomaly: {who} is an outlier on {_metric_label(metric)} "
        f"at {_fmt(row[metric])} (IQR fences {_fmt(lo)}–{_fmt(hi)})."
    )
    return out


def _recommendations(
    findings: list[str],
    *,
    region_dim: str | None,
    product_dim: str | None,
    has_ratio: bool,
) -> str:
    bits: list[str] = []
    joined = " ".join(findings).lower()
    if "concentration" in joined or "elevated concentration" in joined:
        if region_dim:
            bits.append(
                "Prioritise a claims deep-dive on the top region and validate reserve adequacy."
            )
        if product_dim:
            bits.append(
                "Review pricing and underwriting guidelines for the highest-share product/LOB."
            )
    if "declined" in joined:
        bits.append(
            "Investigate drivers of the decline (mix shift, seasonality, or one-off large losses)."
        )
    if "grew" in joined and any(h in joined for h in ("claim", "incurred", "loss")):
        bits.append(
            "Pair volume growth with severity and frequency to confirm whether risk is deteriorating."
        )
    if has_ratio or "ratio" in joined:
        bits.append(
            "Track loss ratio monthly by region and LOB; escalate any sustained move above plan."
        )
    if not bits:
        bits.append(
            "Drill into the leading dimension with a monthly trend and compare against prior period."
        )
    return " ".join(bits[:3])


def generate_business_insights(
    result_df: pd.DataFrame | None,
    question: str = "",
) -> dict[str, Any]:
    """
    Return narration-compatible dict with BI-structured findings.
    """
    q_hint = (question or "").strip()
    if result_df is None or result_df.empty:
        return {
            "headline": "No results to analyse",
            "narrative_text": "The query returned no rows, so no business insight could be formed.",
            "key_findings": [],
            "recommendation": "Refine filters or time range and ask again.",
            "result_summary": "No rows returned",
            "summary": "No rows returned",
            "word_count": 0,
            "knowledge_citations": [],
            "insight_source": "business_insights",
            "sections": {},
        }

    df = result_df.copy()
    metric = _primary_metric(df)
    time_col = _find_col(df, _TIME_HINTS)
    region_dim = _find_col(df, _REGION_HINTS)
    product_dim = _find_col(df, _PRODUCT_HINTS)
    strs = _str_cols(df)
    dim = region_dim or product_dim or (strs[0] if strs else None)

    sections: dict[str, list[str]] = {
        "trend": [],
        "risk": [],
        "financial": [],
        "anomaly": [],
        "customer": [],
    }
    findings: list[str] = []

    if metric and time_col and time_col in df.columns:
        sections["trend"] = _trend_findings(df, metric, time_col)
        findings.extend(sections["trend"])

    if metric and dim and dim in df.columns and len(df) >= 2:
        sections["risk"] = _concentration_findings(df, metric, dim)
        findings.extend(sections["risk"])

    sections["financial"] = _financial_findings(df)
    findings.extend(sections["financial"])

    if metric:
        sections["anomaly"] = _anomaly_findings(df, metric, dim)
        findings.extend(sections["anomaly"])

    # Customer / policyholder signal when column present
    cust = _find_col(df, ("customer", "policyholder", "insured"))
    if cust and metric and cust in df.columns:
        n_cust = df[cust].nunique(dropna=True)
        sections["customer"] = [
            f"Customer view: {n_cust:,} distinct {_metric_label(cust)} values in this cut."
        ]
        findings.extend(sections["customer"])

    if not findings and metric:
        s = pd.to_numeric(df[metric], errors="coerce").dropna()
        if not s.empty:
            findings.append(
                f"Snapshot: {_metric_label(metric)} total {_fmt(float(s.sum()))}, "
                f"average {_fmt(float(s.mean()))} across {len(df):,} rows."
            )

    has_ratio = bool(_find_col(df, _RATIO_HINTS))
    rec = _recommendations(
        findings,
        region_dim=region_dim,
        product_dim=product_dim,
        has_ratio=has_ratio,
    )

    # Headline
    if sections["risk"]:
        headline = "Concentration and performance signals in this cut"
    elif sections["trend"]:
        headline = "Trend and seasonality in the returned series"
    elif sections["financial"]:
        headline = "Financial ratio view of the result"
    else:
        headline = "Business insight from the query result"

    body_parts = []
    if q_hint:
        body_parts.append(f'For "{q_hint}", the result supports the following analysis.')
    for key, title in (
        ("trend", "Trend"),
        ("risk", "Risk"),
        ("financial", "Financial"),
        ("anomaly", "Anomaly"),
        ("customer", "Customer"),
    ):
        if sections.get(key):
            body_parts.append(f"{title}: " + " ".join(sections[key]))
    if not body_parts and findings:
        body_parts = findings[:]

    narrative = "\n\n".join(body_parts)
    summary = findings[0] if findings else headline

    return {
        "headline": headline,
        "narrative_text": narrative,
        "key_findings": findings[:8],
        "recommendation": rec,
        "result_summary": summary[:160],
        "summary": summary,
        "word_count": len(narrative.split()),
        "knowledge_citations": [],
        "insight_source": "business_insights",
        "sections": sections,
    }

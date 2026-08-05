"""
features/okf_knowledge/target_narration.py
Leadership narration for target vs actual alignment answers.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def _fmt_units(n: float | int) -> str:
    return f"{int(round(n)):,}"


def _fmt_pct(n: float) -> str:
    sign = "+" if n > 0 else ""
    return f"{sign}{n:.1f}%"


def generate_target_alignment_narration(
    payload: dict[str, Any],
    citations: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Build headline + multi-paragraph executive summary from alignment payload.
    """
    result_df: pd.DataFrame = payload.get("result_df")
    reg = payload.get("registry") or {}
    if not reg:
        try:
            from features.okf_knowledge.target_alignment import _load_registry
            reg = _load_registry()
        except Exception:
            reg = {}
    scope = payload.get("scope", "National")
    grain = payload.get("grain", "monthly")
    fy_label = payload.get("fy_label", "FY2026")
    doc_code = payload.get("doc_code", "IND-PV-REG-001")
    question = payload.get("question") or "target alignment"

    th = reg.get("thresholds") or {}
    esc_pct = float(th.get("escalation_behind_pct", -15.0))
    citations = citations or []

    if result_df is None or result_df.empty:
        return {
            "headline": "Unable to assess target alignment",
            "narrative_text": "No FY2026 actuals were found in the loaded dataset for this scope.",
            "summary": "No FY2026 data for alignment.",
            "key_findings": [],
            "recommendation": "Confirm data includes sales from Apr-2026 onward and region dimension is joined.",
            "result_summary": "No alignment data",
            "knowledge_citations": citations,
        }

    if grain == "ytd":
        row = result_df.iloc[0]
        actual = int(row["actual_units"])
        target = int(row["target_units"])
        var_pct = float(row["variance_pct"])
        status = str(row["status"])
        months_n = int(row.get("months_in_scope", 0))

        if status == "Ahead":
            headline = f"{scope} is ahead of {fy_label} plan ({_fmt_pct(var_pct)})"
        elif status == "On Track":
            headline = f"{scope} is on track vs {fy_label} plan ({_fmt_pct(var_pct)})"
        else:
            headline = f"{scope} is behind {fy_label} plan ({_fmt_pct(var_pct)})"

        paras = [
            (
                f"Through {months_n} month(s) of {fy_label}, {scope} delivered "
                f"{_fmt_units(actual)} retail units against a prorated plan of "
                f"{_fmt_units(target)} — a gap of {_fmt_units(row['variance_units'])} units "
                f"({_fmt_pct(var_pct)}). Targets are sourced from **{doc_code}**; "
                f"actuals are from your uploaded sales data."
            ),
        ]

        if var_pct <= esc_pct:
            paras.append(
                f"The variance exceeds the **{esc_pct:.0f}% escalation threshold** defined in "
                f"IND-PV-SOP-004 — this warrants a corrective plan with Regional Sales Excellence, "
                f"not just a dashboard note."
            )
        elif status == "Behind":
            paras.append(
                "Performance is below plan but not yet at formal escalation. Focus on city-hub "
                "contribution within the zone and verify stock / lead conversion before month-end."
            )
        else:
            paras.append(
                "Current run-rate supports the annual plan. Protect momentum in top hubs and "
                "document any one-off campaign effects so H2 festive targets stay credible."
            )

        paras.append(
            f"**Executive read:** treat YTD variance as the control metric for MBR; "
            f"drill to monthly and make level if {scope} status changes next month."
        )

        recommendation = (
            f"Next: ask *monthly units vs target for {scope}* or *top makes behind plan in {scope}*."
        )
        result_summary = f"{scope} YTD: {_fmt_units(actual)} vs {_fmt_units(target)} target ({status})"

    else:
        total_actual = int(result_df["actual_units"].sum())
        total_target = int(result_df["target_units"].sum())
        total_var_pct = (
            (total_actual - total_target) / total_target * 100.0 if total_target else 0.0
        )
        overall_status = (
            "Ahead" if total_var_pct >= float(th.get("ahead_min_pct", 5))
            else "On Track" if total_var_pct >= float(th.get("on_track_min_pct", -5))
            else "Behind"
        )

        best = result_df.loc[result_df["variance_pct"].idxmax()]
        worst = result_df.loc[result_df["variance_pct"].idxmin()]
        behind_months = int((result_df["status"] == "Behind").sum())
        n_months = len(result_df)

        if overall_status == "Behind":
            headline = (
                f"{scope} monthly sales are not fully aligned with {fy_label} targets "
                f"({_fmt_pct(total_var_pct)} cumulative)"
            )
        elif overall_status == "Ahead":
            headline = f"{scope} is running ahead of {fy_label} monthly plan ({_fmt_pct(total_var_pct)})"
        else:
            headline = f"{scope} monthly sales are broadly aligned with {fy_label} plan"

        paras = [
            (
                f"Across {n_months} month(s) in {fy_label}, {scope} recorded "
                f"{_fmt_units(total_actual)} units vs a phased plan of {_fmt_units(total_target)} "
                f"({_fmt_pct(total_var_pct)} overall). Plan numbers come from **{doc_code}** "
                f"(H1/H2 phasing applied at national level; zones scaled consistently)."
            ),
            (
                f"Strongest month: **{best['month']}** ({_fmt_units(best['actual_units'])} actual vs "
                f"{_fmt_units(best['target_units'])} target, {_fmt_pct(float(best['variance_pct']))}). "
                f"Softest month: **{worst['month']}** ({_fmt_pct(float(worst['variance_pct']))}). "
                f"{behind_months} of {n_months} month(s) flagged **Behind** vs plan."
            ),
        ]

        if worst["variance_pct"] <= esc_pct:
            paras.append(
                f"{worst['month']} breached the {esc_pct:.0f}% escalation band — align with "
                f"IND-PV-SOP-004 territory review and assign owners for recovery actions."
            )
        elif behind_months >= max(2, n_months // 2):
            paras.append(
                "Multiple consecutive behind-plan months suggest a structural gap (stock, mix, or "
                "network productivity) rather than a single bad fortnight — avoid averaging it away."
            )
        else:
            paras.append(
                "Most months are within tolerance; use the soft month to test whether the gap is "
                "festive timing, EV mix, or a specific city hub under-delivering."
            )

        paras.append(
            "**Leadership takeaway:** monthly alignment is the early-warning system for annual "
            f"{fy_label} delivery — pair this view with zone EV share vs REG-001 mix targets in the next review."
        )

        recommendation = (
            f"Drill {worst['month']} by make and city hub, or ask *are we on track for {scope} EV share*."
        )
        result_summary = (
            f"{scope} monthly: {_fmt_units(total_actual)} vs {_fmt_units(total_target)} "
            f"({overall_status}, {behind_months}/{n_months} months behind)"
        )

    narrative_text = "\n\n".join(paras)

    if grain == "ytd":
        align_status = str(result_df.iloc[0]["status"])
    else:
        align_status = overall_status

    return {
        "headline": headline,
        "narrative_text": narrative_text,
        "summary": headline,
        "key_findings": [],
        "recommendation": recommendation,
        "result_summary": result_summary,
        "knowledge_citations": citations,
        "alignment_status": align_status,
    }

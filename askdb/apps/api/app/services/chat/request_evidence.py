"""Deterministic, result-bound Chat prose. No provider sees result rows here."""

import math
from decimal import Decimal

from app.services.chat.narration import _fmt


def number(value):
    return (
        isinstance(value, (int, float, Decimal))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def render(request, pack, rows, raw=None, *, investigation=False, total=None):
    if not rows:
        return "No matching records for this selection. This is not a verified zero."
    raw = raw or {}
    parts = []
    for measure in request.measures:
        spec = pack.model.measures[measure.id]
        kind = "currency" if spec.format == "currency" else "number"

        def fmt(value, kind=kind):
            return _fmt(float(value), kind) if number(value) else "unavailable"

        current = raw.get("__headline_current_" + measure.id)
        baseline = raw.get("__headline_baseline_" + measure.id)
        if investigation and number(current) and number(baseline):
            current, baseline = float(current), float(baseline)
            delta = current - baseline
            parts.append(
                f"{spec.display_name}: current {fmt(current)}, baseline {fmt(baseline)}, change {fmt(delta)}."
            )
            if raw.get("__missing_" + measure.id):
                parts.append(
                    "Contributing factors are unverified: one or more groups have missing comparison observations. Missing is not zero."
                )
                continue
            contributions = []
            for row in rows:
                value = row.get("change_" + measure.id)
                if not number(value):
                    continue
                label = ", ".join(
                    str(row.get(f.split(".")[-1], "Unknown")) for f in request.group_by
                )
                contributions.append((label, value))
            shown = sorted(contributions, key=lambda item: abs(item[1]), reverse=True)[:5]
            parts.append(
                "Contributing factors: "
                + "; ".join(f"{label}: {fmt(value)}" for label, value in shown)
                + "."
            )
            residual = delta - sum(value for _, value in shown)
            parts.append(
                f"Other / remaining groups: {fmt(residual)}. Contributions reconcile to the headline change."
            )
            parts.append("These are measured contributions, not proof of causation.")
        else:
            for row in rows[:3]:
                label = ", ".join(
                    str(row.get(field.split(".")[-1], row.get(field.replace(".", "__"), "Unknown")))
                    for field in request.group_by
                )
                for key in (
                    measure.id,
                    "current_" + measure.id,
                    "baseline_" + measure.id,
                    "change_" + measure.id,
                    measure.id + "_change_pct",
                ):
                    if key in row:
                        value = row[key]
                        display = (
                            _fmt(float(value), "percent")
                            if key.endswith("_pct") and number(value)
                            else fmt(value)
                        )
                        parts.append(
                            f"{label + ': ' if label else ''}{key.replace('_', ' ')}: {display}."
                        )
    if total is not None and total > len(rows):
        parts.append(
            f"Showing {len(rows)} of {total} groups; the displayed groups are not the whole result."
        )
    return " ".join(parts) or "Verified results are available in the table."

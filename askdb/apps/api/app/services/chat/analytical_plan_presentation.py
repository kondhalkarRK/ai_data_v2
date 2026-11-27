"""Local, result-bound presentation. No provider calls or new analytical queries."""

from datetime import date

from app.services.chat.narration import _fmt
from app.services.chat.request_dates import comparison_ranges, resolve_period


def _field_label(field, pack):
    table, _, column = field.partition(".")
    spec = pack.model.tables.get(table)
    if not spec or column not in spec.columns:
        return column.replace("_", " ").capitalize()
    label = spec.columns[column].display_name
    count = sum(
        c.display_name == label
        for table in pack.model.tables.values()
        for c in table.columns.values()
    )
    return f"{spec.display_name} · {label}" if count > 1 else label


def step_title(step, pack):
    measures = ", ".join(pack.model.measures[m.id].display_name for m in step.request.measures)
    grouping = ", ".join(_field_label(f, pack).lower() for f in step.request.group_by)
    grouping = grouping or step.request.time_grain or "selection"
    if step.operation == "select_extreme":
        return f"{'Lowest' if step.request.ranking.direction == 'asc' else 'Highest'} {measures.lower()} {grouping}"
    if step.operation == "select_ranked":
        return f"Select ranked {grouping}"
    if step.operation == "contributors":
        return f"Contributing factors by {grouping}"
    if step.operation == "history":
        return "Compare selected members with their history"
    if step.operation == "compare":
        return f"Compare {measures.lower()}" + (
            f" by {grouping}" if step.request.group_by else " with baseline"
        )
    return measures + (
        f" by {grouping}" if step.request.group_by or step.request.time_grain else " totals"
    )


def progress_payload(plan, pack, *, completed=0, result=None):
    statuses = {s.id: s.status for s in result.steps} if result else {}
    return {
        "version": 1,
        "planId": plan.plan_id,
        "total": len(plan.steps),
        "completed": completed,
        "phase": "checking" if completed else "running",
        "message": f"Reviewed step {completed} of {len(plan.steps)}"
        if completed
        else f"Running {len(plan.steps)} linked steps. Results will be checked before they are shown.",
        "steps": [
            {
                "id": s.id,
                "label": step_title(s, pack),
                "status": statuses.get(s.id, "pending") if index < completed else "pending",
            }
            for index, s in enumerate(plan.steps)
        ],
    }


def _column(output, pack):
    if output.role in {"dimension", "period_start", "period_end"}:
        return {
            "key": output.name,
            "label": _field_label(output.semantic_id, pack)
            if output.role == "dimension"
            else "Period start"
            if output.role == "period_start"
            else "Period end (exclusive)",
            "kind": "date" if output.value_type == "date" else "text",
        }
    spec = pack.model.measures[output.semantic_id]
    suffix = {
        "current": "current",
        "baseline": "baseline",
        "change": "change",
        "percent_change": "change %",
        "rank": "rank",
        "group_count": "group count",
    }.get(output.role)
    return {
        "key": output.name,
        "label": spec.display_name + (f" — {suffix}" if suffix else ""),
        "kind": "percent"
        if output.role == "percent_change"
        else "number"
        if output.role in {"rank", "group_count"}
        else "currency"
        if spec.format == "currency"
        else "number",
    }


def _format(value, column):
    if value is None:
        return "Unavailable"
    if column["kind"] in {"currency", "percent", "number"}:
        return _fmt(float(value), column["kind"])
    return str(value)


def _summary(step, result, columns):
    if result.status == "skipped":
        return "Not answered because a required earlier result is unavailable."
    if result.status == "clarification":
        return "Narrow the selection so every tied member can be retained safely."
    if result.status == "empty":
        return "No matching records. This does not establish a zero result."
    if not result.verified:
        return (
            "Contributing factors could not be verified."
            if step.operation == "contributors"
            else "This part could not be verified."
        )
    if not result.rows:
        return "No verified observations are available."
    defs = {c["key"]: c for c in columns}
    metric_outputs = [
        o
        for o in step.outputs
        if o.role in {"value", "current", "baseline", "change", "percent_change"}
    ]
    labels = [o for o in step.outputs if o.role in {"dimension", "period_start"}]
    if step.operation == "contributors":
        mid = step.request.ranking.measure_id
        change = next(o.name for o in metric_outputs if o.role == "change" and o.semantic_id == mid)
        negative = [r for r in result.rows if r[change] is not None and r[change] < 0][:3]
        if negative:
            return (
                "Contributing factors: "
                + "; ".join(
                    ", ".join(
                        str(row[o.name]) if row[o.name] is not None else "Unavailable"
                        for o in labels
                    )
                    + f" ({_format(row[change], defs[change])})"
                    for row in negative
                )
                + ". These are measured changes, not proof of causation."
            )
        return "No verified negative contributor appears in the returned observations."
    if step.operation in {"select_extreme", "select_ranked"}:
        lead = (
            f"{result.selected_groups} tied or selected members. "
            if result.selected_groups > 1
            else ""
        )
        shown = result.rows[:3]
        return (
            lead
            + "; ".join(
                ", ".join(
                    _format(row[o.name], defs[o.name])
                    for o in [*labels, *metric_outputs]
                    if o.name in row
                )
                for row in shown
            )
            + (". See all selected members below." if len(result.rows) > 3 else ".")
        )
    if step.baseline:
        row = result.rows[0]
        values = "; ".join(
            f"{defs[o.name]['label']}: {_format(row[o.name], defs[o.name])}" for o in metric_outputs
        )
        return ("First returned comparison: " if len(result.rows) > 1 else "") + values + "."
    if len(result.rows) == 1:
        return (
            "; ".join(
                f"{defs[o.name]['label']}: {_format(result.rows[0][o.name], defs[o.name])}"
                for o in metric_outputs
            )
            + "."
        )
    return f"{result.total_groups} matching groups. All requested columns are retained below."


def presentation(plan, result, pack, *, today: date, context=None):
    """Store a versioned display snapshot; history never recomputes relative dates."""
    by_id = {s.id: s for s in result.steps}
    steps = []
    extras = {
        "selected_period_start": "Selected period start",
        "selected_period_end": "Selected period end (exclusive)",
        "baseline_period_start": "Baseline period start",
        "baseline_period_end": "Baseline period end (exclusive)",
    }
    titles = {s.id: step_title(s, pack) for s in plan.steps}
    entities = {e["id"]: e["value"] for e in context.payload["entities"]} if context else {}
    for step in plan.steps:
        observed = by_id.get(step.id)
        if observed is None:
            # Denial/cancellation/failure must not synthesize step results.
            continue
        columns = [{**_column(o, pack), "role": o.role, "semanticId": o.semantic_id} for o in step.outputs]
        columns += [
            {"key": key, "label": extras[key], "kind": "date"}
            for key in observed.columns
            if key in extras
        ]
        search = resolve_period(step.request.period, today, pack.model.query_policy)
        periods = []
        if step.baseline and not any(b.kind == "period" for b in step.bindings):
            current, baseline = comparison_ranges(
                step.request.comparisons[0], step.request.period, today, pack.model.query_policy
            )
            periods.append(
                {
                    "currentStart": str(current.start),
                    "currentEnd": str(current.end),
                    "baselineStart": str(baseline.start),
                    "baselineEnd": str(baseline.end),
                }
            )
        elif step.baseline:
            periods = [
                dict(
                    zip(
                        ("currentStart", "currentEnd", "baselineStart", "baselineEnd"),
                        values,
                        strict=True,
                    )
                )
                for values in dict.fromkeys(
                    tuple(row.get(k) for k in extras) for row in observed.rows
                )
            ]
        notes = list(observed.notes)
        for dep in step.depends_on:
            notes = [
                n.replace(f"prerequisite {dep} is", f"prerequisite '{titles[dep]}' is")
                for n in notes
            ]
        steps.append(
            {
                "id": step.id,
                "title": titles[step.id],
                "operation": step.operation,
                "dependsOn": step.depends_on,
                "status": observed.status,
                "verified": observed.verified,
                "completenessVerified": observed.completeness_verified,
                "summary": _summary(step, observed, columns),
                "columns": columns,
                "displayedRows": len(observed.rows),
                "totalGroups": observed.total_groups,
                "selectedGroups": observed.selected_groups,
                "notes": notes,
                "searchPeriod": {
                    "label": search.label,
                    "start": str(search.start) if search.start else None,
                    "endExclusive": str(search.end) if search.end else None,
                },
                "comparisonPeriods": periods,
                "filters": [
                    {
                        "field": f.field,
                        "label": _field_label(f.field, pack),
                        "operator": f.operator,
                        "values": [str(entities.get(e, "Approved entity")) for e in f.entity_ids]
                        if f.entity_ids
                        else [str(v) for v in f.values],
                    }
                    for f in step.request.filters
                ],
                "baseline": {
                    "kind": step.baseline.kind,
                    "origin": "approved_default"
                    if step.baseline.source == "approved_default"
                    else "interpreted_request",
                }
                if step.baseline
                else None,
            }
        )
    selectors = [
        s for s in steps if s["operation"] in {"select_extreme", "select_ranked"} and s["verified"]
    ]
    headlines = [
        s
        for s in steps
        if s["operation"] == "compare"
        and not next(p for p in plan.steps if p.id == s["id"]).request.group_by
        and s["verified"]
    ]
    primary = [*selectors[-1:], *headlines[:1]]
    summary = " ".join(f"{s['title']}: {s['summary']}" for s in primary)
    if result.status in {"denied", "failed", "cancelled", "disabled"}:
        summary = result.message
        steps = []
    elif result.status == "clarification":
        summary = "The selection needs a narrower scope before dependent answers can be produced."
    elif result.status == "empty":
        summary = (
            "No matching records were found in your permitted scope. This is not a verified zero."
        )
    elif result.status == "partial":
        summary = "Some parts could not be verified. " + summary
    if not summary:
        summary = "The requested analysis is shown in order below."
    return {
        "version": 1,
        "status": result.status,
        "summary": summary.strip(),
        "scope": result.scope_labels or ["Your permitted regions"],
        "steps": steps,
        "unanswered": [
            {"id": u.requirement_id, "reason": u.reason, "status": u.status}
            for u in plan.unanswered
        ],
        "notes": [result.message] if result.message else [],
        "checks": result.checks,
    }


def narrative(view):
    parts = [view["summary"], "Scope: " + ", ".join(view["scope"]) + "."]
    for step in view["steps"]:
        parts += [step["title"] + ": " + step["summary"]]
        p = step["searchPeriod"]
        parts.append(f"Search period: {p['start']} to {p['endExclusive']} (exclusive).")
        for pair in step["comparisonPeriods"]:
            parts.append(
                f"Current: {pair['currentStart']} to {pair['currentEnd']}; baseline: {pair['baselineStart']} to {pair['baselineEnd']} (ends exclusive)."
            )
        parts.extend(step["notes"])
    parts.extend("Not answered: " + item["reason"] for item in view["unanswered"])
    parts.extend(view["notes"])
    return "\n".join(parts)

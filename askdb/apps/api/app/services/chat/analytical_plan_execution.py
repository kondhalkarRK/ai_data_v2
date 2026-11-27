"""Bounded execution and result checks for reviewed dependent analytics."""

from __future__ import annotations

import asyncio
import hashlib
import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field
from sqlalchemy import text

from app.analytics.sql_guardrails import sql_is_safe
from app.services.chat.analytical_plan_compiler import compile_analysis
from app.services.chat.request_contract import ContractModel
from app.services.chat.request_dates import add_months
from app.services.security.region_scope import for_current_scope


class AnalyticalStepResult(ContractModel):
    id: str
    status: Literal["completed", "empty", "partial", "skipped", "clarification"]
    columns: list[str]
    rows: list[dict[str, Any]] = Field(default_factory=list)
    total_groups: int = 0
    selected_groups: int = 0
    notes: list[str] = Field(default_factory=list)
    verified: bool = False
    completeness_verified: bool | None = None


class AnalyticalExecution(ContractModel):
    status: Literal[
        "completed",
        "partial",
        "clarification",
        "empty",
        "denied",
        "cancelled",
        "failed",
        "disabled",
    ]
    steps: list[AnalyticalStepResult] = Field(default_factory=list)
    message: str = ""
    analytical_queries: int = 0
    sql: str | None = None
    sql_fingerprint: str | None = None
    scope_fingerprint: str | None = None
    checks: list[dict[str, Any]] = Field(default_factory=list)
    scope_labels: list[str] = Field(default_factory=list)


def _typed(value, output):
    if value is None:
        if not output.nullable:
            raise ValueError("Nonnullable output is missing")
        return None
    if output.value_type in {"integer", "decimal"}:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float, Decimal))
            or not math.isfinite(value)
        ):
            raise ValueError("Result is not a finite numeric value")
        if output.value_type == "integer" and int(value) != value:
            raise ValueError("Integer output has a fraction")
        return value
    if output.value_type == "date":
        if isinstance(value, datetime):
            value = value.date()
        return (
            value.isoformat() if isinstance(value, date) else date.fromisoformat(value).isoformat()
        )
    if output.value_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("Boolean output has another type")
    elif not isinstance(value, str):
        raise ValueError("Text output has another type")
    return value


def check_results(compiled, records):
    """Check the typed envelope before any answer or result is published."""
    plan = compiled.plan
    by_id = {s.id: s for s in plan.steps}
    if not records or len(records) > len(plan.steps) * compiled.display_limit:
        raise ValueError("Incomplete or oversized analytical result envelope")
    grouped = {s.id: [] for s in plan.steps}
    expected_columns = {
        "__step",
        "__present",
        "__count",
        "__total",
        "__period_start",
        "__period_end",
        *(f"__check_{j}" for j in range(len(compiled.checks))),
    }
    expected_columns |= {f"s{i}_{o.name}" for i, s in enumerate(plan.steps) for o in s.outputs}
    for record in records:
        if set(record) != expected_columns or record["__step"] not in by_id:
            raise ValueError("Result columns do not match the planned outputs")
        grouped[record["__step"]].append(record)
    results = {}
    for i, step in enumerate(plan.steps):
        rows = grouped[step.id]
        if not rows:
            raise ValueError("A planned step is missing from the result")
        counts = {r["__count"] for r in rows}
        if len(counts) != 1:
            raise ValueError("Inconsistent step result counts")
        count = counts.pop()
        totals = {r["__total"] for r in rows}
        if len(totals) != 1:
            raise ValueError("Inconsistent total group counts")
        total = totals.pop()
        if isinstance(total, bool) or not isinstance(total, int) or total < count:
            raise ValueError("Invalid total group count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("Invalid group count")
        result = AnalyticalStepResult(
            id=step.id,
            status="completed",
            columns=[o.name for o in step.outputs],
            total_groups=total,
            selected_groups=count,
        )
        results[step.id] = result
        blockers = [
            results[d] for d in step.depends_on if results[d].status not in {"completed", "partial"}
        ]
        if blockers:
            result.status = "skipped"
            result.notes = [f"Not answered: prerequisite {b.id} is {b.status}." for b in blockers]
            continue
        if step.selection and total > min(step.selection.cohort_cap, compiled.display_limit):
            result.status = "clarification"
            result.notes = [
                f"Selection contains {total} tied/cohort members; narrow the scope to preserve every member within the safe limit."
            ]
            continue
        for binding in step.bindings:
            source = results[binding.source_step]
            if source.selected_groups > min(binding.max_items, compiled.display_limit):
                result.status = "clarification"
                result.notes = [
                    "The selected result exceeds the safe binding limit. Please narrow the scope."
                ]
            if any(any(row[c] is None for c in binding.source_columns) for row in source.rows):
                result.status = "skipped"
                result.notes = [
                    "The selected result has a missing binding value; no substitute was guessed."
                ]
        if result.status in {"clarification", "skipped"}:
            continue
        present = [r for r in rows if r["__present"] is not None]
        if len(present) != min(count, compiled.display_limit):
            raise ValueError("Step rows were silently omitted")
        ordinals = {r["__present"] for r in present}
        if ordinals != set(range(1, len(present) + 1)):
            raise ValueError("Step ordering is incomplete")
        for record in sorted(present, key=lambda r: r["__present"]):
            output_row = {o.name: _typed(record[f"s{i}_{o.name}"], o) for o in step.outputs}
            if any(b.kind == "period" for b in step.bindings):
                start, end = record["__period_start"], record["__period_end"]
                start = start.date() if isinstance(start, datetime) else start
                end = end.date() if isinstance(end, datetime) else end
                start = start if isinstance(start, date) else date.fromisoformat(start)
                end = end if isinstance(end, date) else date.fromisoformat(end)
                if start >= end:
                    raise ValueError("Bound period is invalid")
                binding = next(b for b in step.bindings if b.kind == "period")
                source = results[binding.source_step]
                allowed = {
                    (r[binding.source_columns[0]], r[binding.source_columns[1]])
                    for r in source.rows
                }
                if (start.isoformat(), end.isoformat()) not in allowed:
                    raise ValueError("The executed period is not a selected period")
                output_row.update(
                    selected_period_start=start.isoformat(), selected_period_end=end.isoformat()
                )
                if step.baseline:
                    grain = by_id[binding.source_step].request.time_grain
                    months = (
                        12
                        if step.baseline.kind == "same_period_last_year"
                        else {"month": 1, "quarter": 3, "year": 12}.get(grain)
                    )
                    baseline_start = (
                        add_months(start, -months)
                        if months
                        else start - timedelta(days=7 if grain == "week" else 1)
                    )
                    baseline_end = (
                        add_months(end, -months)
                        if months
                        else end - timedelta(days=7 if grain == "week" else 1)
                    )
                    output_row.update(
                        baseline_period_start=baseline_start.isoformat(),
                        baseline_period_end=baseline_end.isoformat(),
                    )
                    for col in ("baseline_period_start", "baseline_period_end"):
                        if col not in result.columns:
                            result.columns.append(col)
                for col in ("selected_period_start", "selected_period_end"):
                    if col not in result.columns:
                        result.columns.append(col)
            result.rows.append(output_row)
        result.status = "completed" if count else "empty"
        result.verified = True
        if step.baseline and any(b.kind == "period" for b in step.bindings) and result.rows:
            result.completeness_verified = all(
                any(
                    source.loaded_data_verified
                    and source.kind in {"combined", "load_status"}
                    and source.scope_fingerprint == plan.scope_fingerprint
                    and source.revision
                    and source.start
                    and source.end_exclusive
                    and source.start
                    <= date.fromisoformat(row["baseline_period_start"])
                    < date.fromisoformat(row["baseline_period_end"])
                    <= source.end_exclusive
                    for source in compiled.completeness_sources
                )
                for row in result.rows
            )
            if not result.completeness_verified:
                result.status = "partial"
                if step.operation == "contributors":
                    result.verified = False
                result.notes.append(
                    "Baseline loaded-period completeness is unverified; available observations do not prove a complete comparison."
                )
        if not count:
            result.notes.append("No matching records. This is not a verified zero.")
        if total > len(present):
            result.notes.append(
                f"Showing {len(present)} of {total} groups; selection and reconciliation used the complete eligible relation."
            )
    checks = []
    for j, (head, detail, measure) in enumerate(compiled.checks):
        values = {r[f"__check_{j}"] for r in records}
        if len(values) != 1 or any(
            isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values
        ):
            raise ValueError("Reconciliation control is missing or inconsistent")
        passed = values == {0}
        checks.append(
            {"headlineStep": head, "contributorStep": detail, "measure": measure, "passed": passed}
        )
        if not passed and results[detail].status in {"completed", "empty"}:
            results[detail].status = "partial"
            results[detail].verified = False
            results[detail].notes.append(
                "Contributor changes did not reconcile independently, or a comparison side is missing. Attribution is unverified."
            )
        elif passed and results[detail].status == "completed":
            change = next(
                o.name
                for o in by_id[head].outputs
                if o.role == "change" and o.semantic_id == measure
            )
            if any(row[change] is not None and row[change] >= 0 for row in results[head].rows):
                results[detail].status = "partial"
                results[detail].verified = False
                results[detail].notes.append(
                    "At least one selected period did not decline against the baseline; a lowest value is not proof of a dip."
                )
            results[detail].notes.append(
                "These are measured contributing factors, not proof of causation."
            )
    states = [s.status for s in results.values()]
    status = (
        "partial"
        if any(s in {"partial", "skipped", "clarification"} for s in states)
        else "empty"
        if all(s == "empty" for s in states)
        else "completed"
    )
    if "clarification" in states:
        status = "clarification"
    elif not any(s.rows for s in results.values()):
        status = "empty"
    return AnalyticalExecution(status=status, steps=list(results.values()), checks=checks)


def render_execution(result, plan, pack):
    """Minimal local result summary. Rich all-step UI/narration is a later batch."""
    from app.services.chat.narration import _fmt

    lines = [result.message] if result.message else []
    steps = {s.id: s for s in plan.steps}
    for step_result in result.steps:
        step = steps[step_result.id]
        lines.append(
            f"{step.label}: {step_result.status}; {step_result.total_groups} matching groups."
        )
        if step.request.period:
            p = step.request.period
            lines.append(
                f"Search period: {p.start} to {p.end_exclusive} (exclusive)."
                if p.start
                else p.label
            )
        if step.baseline:
            lines.append("Baseline: " + step.baseline.kind.replace("_", " ") + ".")
        lines.append(
            "Scope: "
            + (", ".join(result.scope_labels) if result.scope_labels else "your permitted regions")
            + "."
        )
        if step_result.verified:
            for row in step_result.rows[:5]:
                values = []
                outputs = {o.name: o for o in step.outputs}
                for key, value in row.items():
                    out = outputs.get(key)
                    if value is None:
                        shown = "unavailable"
                    elif (
                        out
                        and out.semantic_id in pack.model.measures
                        and out.role not in {"rank", "group_count"}
                    ):
                        kind = (
                            "percent"
                            if out.role == "percent_change"
                            else "currency"
                            if pack.model.measures[out.semantic_id].format == "currency"
                            else "number"
                        )
                        shown = _fmt(float(value), kind)
                    else:
                        shown = str(value)
                    values.append(f"{key.replace('_', ' ')}: {shown}")
                lines.append(", ".join(values))
        lines.extend(step_result.notes)
    return "\n".join(lines) or "No verified answer is available for the complete request."


async def execute_analysis(plan, review, *, connection, settings, today, authorize, cancelled):
    """One statement provides a coherent snapshot without changing isolation late.

    authorize is a SERVER callback rechecking identity, scope and semantic version.
    No caller-supplied permissions or provider endpoint are accepted here.
    """
    if not settings.chat_dependent_analysis_enabled or not settings.chat_typed_execution_enabled:
        return AnalyticalExecution(status="disabled", message="Dependent analysis is disabled.")
    if await cancelled():
        return AnalyticalExecution(status="cancelled", message="The request was cancelled.")
    if not await authorize():
        return AnalyticalExecution(
            status="denied", message="Your access or semantic model changed. Please ask again."
        )
    max_rows = min(50, settings.sql_max_result_rows // max(1, len(plan.steps)))
    compiled = compile_analysis(plan, review, today=today, display_limit=max_rows)
    scope = review.principal.scope
    sql = scope.apply_sql(compiled.sql, review.principal.industry)
    safe, reason = sql_is_safe(sql)
    if not safe:
        raise ValueError(reason)
    scoped = for_current_scope(connection, review.principal.industry, scope)
    output = AnalyticalExecution(
        status="failed", message="The dependent analysis could not be verified."
    )
    task = None
    try:
        async with asyncio.timeout(settings.chat_dependent_timeout_seconds):
            # The registry establishes read-only mode before metadata reads. Verify
            # that mode rather than changing transaction characteristics mid-flow.
            read_only = await scoped.execute(text("SHOW transaction_read_only"))
            if str(read_only.scalar_one()).casefold() != "on":
                raise ValueError("A read-only analytics transaction is required")
            await scoped.execute(
                text(
                    f"SET LOCAL statement_timeout = {int(settings.chat_dependent_timeout_seconds * 1000)}"
                )
            )
            await scoped.execute(text("EXPLAIN " + compiled.sql))
            if await cancelled():
                return AnalyticalExecution(status="cancelled", message="The request was cancelled.")
            if not await authorize():
                return AnalyticalExecution(
                    status="denied", message="Your access changed before execution."
                )
            output.analytical_queries = 1
            task = asyncio.create_task(scoped.execute(text(compiled.sql)))
            while not task.done():
                await asyncio.wait({task}, timeout=0.05)
                if await cancelled():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    return AnalyticalExecution(
                        status="cancelled",
                        analytical_queries=1,
                        message="The request was cancelled; no results were published.",
                    )
            result = await task
            records = [dict(row) for row in result.mappings().all()]
            if await cancelled():
                return AnalyticalExecution(
                    status="cancelled", analytical_queries=1, message="The request was cancelled."
                )
            if not await authorize():
                return AnalyticalExecution(
                    status="denied",
                    analytical_queries=1,
                    message="Access changed during execution; results were discarded.",
                )
            output = check_results(compiled, records)
            output.analytical_queries = 1
            output.sql = sql
            output.sql_fingerprint = hashlib.sha256(sql.encode()).hexdigest()
            output.scope_fingerprint = plan.scope_fingerprint
            output.scope_labels = (
                ["All permitted regions"] if scope.unrestricted else list(scope.zones)
            )
            return output
    except asyncio.CancelledError:
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        raise
    except Exception:
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        # No raw SQL/provider/driver exceptions are exposed to the user.
        return output

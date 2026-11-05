"""Finite report turn coordinator. No autonomous or tool-calling loop."""

import hashlib
import re
import time
import uuid
from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.exceptions import AuthorizationError, ConflictError, ValidationError
from app.schemas.bi import BiPending, BiPlan, BiReport, BiState, BiTurn, BiTurnRequest
from app.services.analytics.bi.advanced import prepare
from app.services.analytics.bi.execution import validate_values
from app.services.analytics.bi.llm import BiCompletion, BiProviderError
from app.services.analytics.bi.planning import propose, refresh_dates, validate, validate_chart
from app.services.analytics.bi.repository import context, owned, persist, view
from app.services.analytics.runner import AnalyticsService
from app.services.executive.dashboard import QueryMeter
from app.services.security.region_scope import forbidden_zones


def visual_change(plan: BiPlan, target: str | None, viz: str) -> BiPlan:
    changed = plan.model_copy(deep=True)
    panel = next((p for p in changed.panels if p.id == target), None)
    if not panel:
        raise ValidationError("Select the chart you want to change.")
    if viz not in {"bar", "line", "area", "pie", "table", "kpi", "heatmap", "treemap", "auto"}:
        raise ValidationError("That visualization is not supported for this report.")
    if not panel.spec.dimensions and viz not in {"kpi", "table"}:
        raise ValidationError("A single value needs a breakdown before it can become a chart.")
    panel.spec.viz = viz  # type: ignore[assignment]
    panel.kind = "table" if viz == "table" else "kpi" if viz == "kpi" else "chart"
    changed.answer_kind = "analysis"
    validate_chart(panel)
    return changed


def local_visual(
    question: str, plan: BiPlan | None, selected: str | None
) -> tuple[BiPlan, str] | None:
    if not plan:
        return None
    match = re.fullmatch(
        r"(?:change|make|switch|turn) (?:the )?(this chart|selected chart|chart [1-6]|(?:first|second|third|fourth|fifth|sixth) chart) (?:to |into |a |an )*(bar|line|area|pie|table)(?: chart)?[.!]?",
        question.strip().casefold(),
    )
    if not match:
        return None
    target, viz = match.groups()
    numbers = ["first", "second", "third", "fourth", "fifth", "sixth"]
    index = next((i for i, word in enumerate(numbers) if word in target), None)
    if target[-1:].isdigit():
        index = int(target[-1]) - 1
    if index is not None:
        selected = plan.panels[index].id if index < len(plan.panels) else None
    if selected is None and len(plan.panels) == 1:
        selected = plan.panels[0].id
    return visual_change(
        plan, selected, viz
    ), f"Changed the selected chart to {viz}. Its data scope is unchanged."


async def turn(base: AnalyticsService, report_id: uuid.UUID, body: BiTurnRequest) -> BiReport:
    started = time.perf_counter()
    catalog, scope = await context(base)
    row = await owned(base, report_id, scope)
    request_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    for receipt in row.requests:
        if receipt["id"] == str(body.request_id):
            if receipt["hash"] != request_hash:
                raise ConflictError("A request ID cannot be reused for a different edit.")
            return view(row, base)
    if row.revision != body.revision:
        raise ConflictError(
            "This report changed. Reload it before editing; your question has not been applied."
        )
    if forbidden_zones(body.question, scope):
        raise AuthorizationError("The requested geography is outside your access.")
    state = BiState.model_validate(row.state)
    original_state = state.model_copy(deep=True)
    previous = state.plan.model_copy(deep=True) if state.plan else None
    selected = body.selected_panel_id or (
        state.pending.selected_panel_id if state.pending else None
    )
    if selected and (not state.plan or selected not in {p.id for p in state.plan.panels}):
        raise ValidationError("The selected panel is no longer in this report.")
    now = datetime.now(ZoneInfo(base._settings.askwiz_timezone))
    llm = BiCompletion(base, limit=3)
    original_sql = dict(state.advanced_sql)
    answer = ""
    kind = "edit"
    code = None
    saved = row.saved
    try:
        if body.action == "ask":
            if not body.question.strip():
                raise ValidationError("Enter a question.")
            visual = (
                local_visual(body.question, state.plan, selected) if not state.pending else None
            )
            if visual:
                state.plan, answer = visual
            else:
                proposal = await propose(state, body.question, selected, now, catalog, scope, llm)
                kind, answer = proposal.kind, proposal.message
                if proposal.kind == "answer":
                    assert proposal.plan
                    if any(p.spec.filters for p in proposal.plan.panels):
                        original_connection = base._analytics
                        meter = QueryMeter(original_connection)
                        base._analytics = cast(AsyncConnection, meter)
                        try:
                            await validate_values(base, proposal.plan.panels)
                        finally:
                            base._analytics = original_connection
                            llm.usage.validation_queries += meter.count
                    state.plan = proposal.plan
                    state.pending = None
                elif proposal.kind == "clarification":
                    original = (
                        (state.pending.question + "\nAnswer: " + body.question)
                        if state.pending
                        else body.question
                    )
                    state.pending = BiPending(
                        question=original[-6000:], clarification=answer, selected_panel_id=selected
                    )
                else:
                    state.pending = None
        elif body.action == "undo":
            if not state.previous:
                raise ValidationError("There is no report edit to undo.")
            state.plan, state.previous = state.previous, state.plan
            state.pending = None
            answer = "Restored the previous report definition. Results will be checked against that scope."
        elif body.action == "save":
            if not state.plan:
                raise ValidationError("Create an analysis before saving.")
            saved, answer = (
                True,
                "Report saved. Reopening preserves these dates; Refresh updates relative dates.",
            )
        elif body.action == "refresh":
            if not state.plan:
                raise ValidationError("There is no report to refresh.")
            state.plan = refresh_dates(state.plan, now)
            state.pending = None
            answer = "Refreshing report data. Relative periods now use the current business date; previous results remain labeled until replaced."
        elif state.plan:
            plan = state.plan.model_copy(deep=True)
            if body.action == "rename":
                if not body.value or not body.value.strip():
                    raise ValidationError("Enter a report title.")
                plan.title = body.value.strip()
                answer = "Report renamed."
            elif body.action == "visualize":
                plan = visual_change(plan, selected, body.value or "")
                answer = "Updated chart presentation; its data selection is unchanged."
            else:
                index = next((i for i, p in enumerate(plan.panels) if p.id == selected), None)
                if index is None:
                    raise ValidationError("Select a panel first.")
                if body.action == "remove":
                    plan.panels.pop(index)
                    answer = "Removed the selected panel. You can undo this edit."
                else:
                    target = index + (-1 if body.action == "move_up" else 1)
                    if 0 <= target < len(plan.panels):
                        plan.panels[index], plan.panels[target] = (
                            plan.panels[target],
                            plan.panels[index],
                        )
                    answer = "Updated panel order."
            state.plan = plan if plan.panels else None
            state.pending = None
        else:
            raise ValidationError("Create a report first.")
        if state.plan:
            validate(state.plan, catalog, scope)
            state.advanced_sql = await prepare(
                state.plan, catalog, llm, base._settings.ask_me_askbi_advanced_enabled, original_sql
            )
    except BiProviderError as exc:
        kind, code, answer = "error", exc.code, str(exc)
        state = original_state
    except ValidationError as exc:
        # Invalid requested edits/values are durable actionable turns, not blank
        # responses or permission exceptions disguised as clarification.
        kind, code, answer = "error", exc.code, exc.message
        state = original_state
    if state.plan != previous and body.action != "undo":
        state.previous = previous
    before = {p.id: p.model_dump() for p in previous.panels} if previous else {}
    after = {p.id: p.model_dump() for p in state.plan.panels} if state.plan else {}
    changed = [key for key in before.keys() | after.keys() if before.get(key) != after.get(key)]
    state.turns.append(
        BiTurn(
            id=body.request_id,
            question=body.question or body.action.replace("_", " ").capitalize(),
            answer=answer,
            kind=kind,
            code=code,
            changed_panel_ids=changed,
        )
    )
    state.turns = state.turns[-50:]
    state.usage = llm.usage
    state.usage.elapsed_ms = (time.perf_counter() - started) * 1000
    receipts = [*row.requests, {"id": str(body.request_id), "hash": request_hash}]
    return await persist(base, row, state, saved, receipts)

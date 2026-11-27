"""Typed Chat -> existing owner/revision-bound AskBI, with no second interpretation."""

import asyncio
import time
import uuid
from datetime import timedelta

from app.core.exceptions import AuthorizationError, ValidationError
from app.schemas.analytics_workspace import WorkspaceFilter, WorkspaceSpec
from app.schemas.bi import BiCreate, BiPanel, BiPlan, BiRunRequest
from app.services.analytics.bi import execution, repository
from app.services.analytics.bi.planning import validate
from app.services.analytics.runner import AnalyticsService
from app.services.chat.request_dates import resolve_period
from app.services.chat.request_state import save_request
from app.services.executive.dashboard import QueryMeter


def report_plan(request, pack, context, catalog, today, previous=None):
    if (
        request.comparisons
        or request.windows
        or request.operations
        or request.measure_filters
        or request.ranking
    ):
        raise ValidationError(
            "This report transformation is not supported by the typed handoff yet."
        )
    if not request.period:
        raise ValidationError("Which date range should the report use?")
    period = resolve_period(request.period, today, pack.model.query_policy)
    if not period.start or not period.end:
        raise ValidationError("Choose a bounded report period.")
    entities = {e["id"]: e for e in context.payload["entities"]}
    filters = []
    for item in request.filters:
        domain = next(
            (d for d in catalog.domains if d.qualified_column == "automotive." + item.field), None
        )
        if domain is None or item.operator not in {"eq", "in"}:
            raise ValidationError(
                "A requested report filter is unsupported; it has not been discarded."
            )
        values = (
            [str(entities[k]["value"]) for k in item.entity_ids]
            if item.entity_ids
            else [str(v) for v in item.values]
        )
        filters.append(WorkspaceFilter(domain=domain.name, operator="IN", values=values))
    if not set(request.entity_ids) <= {key for item in request.filters for key in item.entity_ids}:
        raise ValidationError("Every requested entity must have an explicit report filter.")
    measures = [m.id for m in request.measures] or ["revenue", "units_sold"]
    if len(measures) > 3:
        raise ValidationError("Choose up to three report measures for this report layout.")
    if previous:
        plan = previous.model_copy(deep=True)
    else:
        panels = [
            BiPanel(
                id="kpi-" + m,
                title=m.replace("_", " ").title(),
                kind="kpi",
                spec=WorkspaceSpec(metrics=[m], viz="kpi"),
            )
            for m in measures
        ]
        dimensions = []
        for field in request.group_by:
            dim = next(
                (
                    d.id
                    for d in catalog.dimensions
                    if (spec := catalog._dimension_spec(d.id))
                    and field == spec.table + "." + spec.column
                ),
                None,
            )
            if not dim:
                raise ValidationError("A requested report grouping is unsupported.")
            dimensions.append(dim)
        if len(dimensions) > 6 - len(panels):
            raise ValidationError("The requested groupings exceed the report panel limit.")
        choices = list(
            dict.fromkeys([*dimensions, request.time_grain or "month", "make", "region", "model"])
        )
        for dim in choices[: 6 - len(panels)]:
            panels.append(
                BiPanel(
                    id="chart-" + dim,
                    title="By " + dim,
                    kind="chart",
                    spec=WorkspaceSpec(
                        metrics=[measures[0]],
                        dimensions=[dim],
                        viz="line" if dim == "month" else "bar",
                    ),
                )
            )
        plan = BiPlan(title=request.summary[:160], answer_kind="report", panels=panels)
    for panel in plan.panels:
        panel.spec.date_preset = "custom"
        panel.spec.date_from = period.start.isoformat()
        panel.spec.date_to = (period.end - timedelta(days=1)).isoformat()
        panel.spec.filters = filters
    return plan


async def handoff_report(chat, typed, memory, *, cancel_check=None, usage_callback=None):
    from app.services.chat.request_dates import business_today

    base = AnalyticsService(
        app_session=chat._app,
        analytics=chat._analytics,
        settings=chat._settings,
        user=chat._user,
        industry=chat._industry,
        semantic_service=chat._semantic,
    )
    catalog, scope = await repository.context(base)
    request = typed.preview.request
    previous = (memory.typed_request or {}).get("report") if request.followup else None
    if previous:
        row = await repository.owned(base, uuid.UUID(previous["id"]), scope)
        if row.revision != previous["revision"]:
            raise ValidationError("The report changed in Builder. Reload it before refining it.")
        report = repository.view(row, base)
    else:
        report = None
    pack = await chat._semantic.get_pack(chat._industry)
    plan = report_plan(
        request,
        pack,
        typed.context,
        catalog,
        business_today(pack.model.query_policy),
        report.state.plan if report and "measures" not in request.changed_fields else None,
    )
    validate(plan, catalog, scope)
    if report is None:
        report = await repository.create(base, BiCreate(id=uuid.uuid4()))
        row = await repository.owned(base, report.id, scope)
    state = report.state.model_copy(deep=True)
    state.plan = plan
    state.advanced_sql = {}
    report = await repository.persist(base, row, state, False, row.requests)
    panels = []
    meter = QueryMeter(base._analytics)
    base._analytics = meter
    deadline = time.monotonic() + chat._settings.chat_report_workflow_timeout_seconds
    for panel in plan.panels:
        if cancel_check and await cancel_check():
            raise asyncio.CancelledError
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            panels.append({"id": panel.id, "status": "unavailable"})
            continue
        try:
            value = await asyncio.wait_for(
                execution.run(
                    base, report.id, BiRunRequest(revision=report.revision, panel_id=panel.id)
                ),
                timeout=remaining,
            )
            panels.append(
                {
                    "id": panel.id,
                    "title": panel.title,
                    "kind": panel.kind,
                    "status": "verified",
                    "result": value.model_dump(mode="json"),
                }
            )
        except AuthorizationError:
            raise
        except Exception:
            await base._analytics.rollback()
            panels.append({"id": panel.id, "status": "unavailable"})
        finally:
            if usage_callback:
                usage_callback(base.analytical_query_count, meter.count)
    _, fresh_scope = await repository.context(base)
    await repository.owned(base, report.id, fresh_scope)
    failed = sum(p["status"] != "verified" for p in panels)
    briefing = f"Report prepared with {len(panels) - failed} verified panels."
    if failed:
        briefing += f" Partial report: {failed} panels unavailable; no values were invented."
    memory.typed_request = save_request(
        memory.typed_request, request, typed.context, str(report.id), pending=False
    )
    memory.typed_request["report"] = {"id": str(report.id), "revision": report.revision}
    return {
        "reportId": str(report.id),
        "revision": report.revision,
        "panels": panels,
        "briefing": briefing,
        "url": f"/analytics-builder?askbiReport={report.id}",
        "partial": bool(failed),
        "queryCount": meter.count,
        "analyticalQueries": base.analytical_query_count,
    }

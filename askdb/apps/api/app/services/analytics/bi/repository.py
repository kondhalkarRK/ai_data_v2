"""Ownership, scope binding, optimistic revisions and legacy read adapters."""

import uuid
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult

from app.core.config import Industry
from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.models import AnalyticsWorkspace, AutoDashboard, SavedAnalysis
from app.models.bi_report import BiReportRecord
from app.schemas.analytics_workspace import WorkspaceSpec
from app.schemas.askwiz import BoardDefinition
from app.schemas.bi import BiCreate, BiPanel, BiPlan, BiReport, BiState
from app.services.analytics.bi.planning import validate
from app.services.analytics.catalog import Catalog
from app.services.analytics.runner import AnalyticsService, catalog_for
from app.services.executive.dashboard import semantic_revision
from app.services.security.region_scope import RegionScope, load_region_scope


async def context(base: AnalyticsService) -> tuple[Catalog, RegionScope]:
    if base._industry != Industry.AUTOMOTIVE:
        raise AuthorizationError("AskBI is available for automotive only.")
    if not base._settings.ask_me_askbi_enabled:
        raise NotFoundError(
            "AskBI is disabled on the API. Enable ASK_ME_ASKBI_ENABLED and restart the API."
        )
    return await catalog_for(base._semantic, base._industry), await load_region_scope(
        base._app, base._user
    )


def scope_key(base: AnalyticsService, scope: RegionScope) -> str:
    return f"{base._user.role}:{scope.cache_key()}"


def view(row: BiReportRecord, base: AnalyticsService) -> BiReport:
    warning = (
        None
        if row.semantic_revision == semantic_revision(base._settings, Industry.AUTOMOTIVE)
        else "Semantic definitions changed; execution revalidates all queries. Refresh before interpreting results."
    )
    return BiReport(
        id=row.id,
        revision=row.revision,
        title=row.title,
        saved=row.saved,
        state=BiState.model_validate(row.state),
        warning=warning,
    )


async def owned(base: AnalyticsService, report_id: uuid.UUID, scope: RegionScope) -> BiReportRecord:
    row = await base._app.scalar(
        select(BiReportRecord)
        .where(BiReportRecord.id == report_id, BiReportRecord.user_id == base._user.id)
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise NotFoundError("Report not found.")
    if row.scope_key != scope_key(base, scope):
        raise AuthorizationError("Your access changed. Start a new report for your current scope.")
    return row


async def imported(base: AnalyticsService, body: BiCreate, scope: RegionScope) -> BiPlan | None:
    if not body.source:
        return None
    if body.source == "analysis":
        analysis = await base._app.scalar(
            select(SavedAnalysis).where(
                SavedAnalysis.id == body.source_id,
                SavedAnalysis.user_id == base._user.id,
                SavedAnalysis.industry == "automotive",
            )
        )
        if not analysis:
            raise NotFoundError("Saved analysis not found.")
        spec = WorkspaceSpec.model_validate(analysis.spec)
        if spec.date_preset != "custom":
            raise ValidationError(
                "Open this Custom report and save exact dates before importing it into AskBI."
            )
        panel = BiPanel(
            id="imported",
            title=analysis.title[:160],
            spec=spec,
            kind="table" if spec.viz == "table" else "chart" if spec.dimensions else "kpi",
        )
        if panel.kind == "kpi":
            panel.spec.viz = "kpi"
        return BiPlan(title=analysis.title[:160], panels=[panel])
    if body.source == "workspace":
        workspace = await base._app.scalar(
            select(AnalyticsWorkspace).where(
                AnalyticsWorkspace.id == body.source_id, AnalyticsWorkspace.user_id == base._user.id
            )
        )
        if not workspace:
            raise NotFoundError("Workspace not found.")
        if workspace.scope_key != scope.cache_key():
            raise AuthorizationError("The workspace belongs to a different access scope.")
        data = {**workspace.definition, "version": 2}
        data.pop("clarification", None)
        return BiPlan.model_validate(data)
    board = await base._app.scalar(
        select(AutoDashboard).where(
            AutoDashboard.id == body.source_id, AutoDashboard.user_id == base._user.id
        )
    )
    if not board:
        raise NotFoundError("Board not found.")
    if board.scope_key != scope.cache_key():
        raise AuthorizationError("The board belongs to a different access scope.")
    definition = BoardDefinition.model_validate(board.definition)
    panels = []
    for chart in definition.charts:
        time = chart.dimension in {"day", "month"}
        panels.append(
            BiPanel(
                id=chart.id,
                title=chart.title,
                kind="table" if chart.viz == "table" else "chart",
                grain="day" if chart.dimension == "day" else None,
                spec=WorkspaceSpec(
                    metrics=[chart.metric],
                    dimensions=["month" if chart.dimension == "day" else chart.dimension],
                    analysis="trend" if time else "basic",
                    viz=chart.viz,
                    date_preset="custom",
                    date_from=definition.start,
                    date_to=definition.end,
                    filters=[
                        {"domain": k, "values": v, "operator": "IN"}
                        for k, v in definition.filters.items()
                    ],
                ),
            )
        )
    return BiPlan(title=board.title[:160], panels=panels, answer_kind="report")


async def create(base: AnalyticsService, body: BiCreate) -> BiReport:
    catalog, scope = await context(base)
    existing = await base._app.scalar(select(BiReportRecord).where(BiReportRecord.id == body.id))
    if existing:
        return view(await owned(base, body.id, scope), base)
    plan = await imported(base, body, scope)
    if plan:
        validate(plan, catalog, scope)
    row = BiReportRecord(
        id=body.id,
        user_id=base._user.id,
        title=plan.title if plan else "Untitled report",
        revision=1,
        saved=False,
        scope_key=scope_key(base, scope),
        semantic_revision=semantic_revision(base._settings, Industry.AUTOMOTIVE),
        state=BiState(plan=plan).model_dump(mode="json"),
        requests=[],
    )
    base._app.add(row)
    await base._app.flush()
    return view(row, base)


async def persist(
    base: AnalyticsService,
    row: BiReportRecord,
    state: BiState,
    saved: bool,
    receipts: list[dict[str, Any]],
) -> BiReport:
    revision = row.revision
    title = state.plan.title if state.plan else row.title
    changed = await base._app.execute(
        update(BiReportRecord)
        .where(
            BiReportRecord.id == row.id,
            BiReportRecord.user_id == base._user.id,
            BiReportRecord.revision == revision,
        )
        .values(
            revision=revision + 1,
            title=title,
            saved=saved,
            state=state.model_dump(mode="json"),
            requests=receipts[-12:],
            semantic_revision=semantic_revision(base._settings, Industry.AUTOMOTIVE),
        )
        .execution_options(synchronize_session=False)
    )
    if cast(CursorResult[Any], changed).rowcount != 1:
        raise ConflictError("This report changed in another request. Reload it before editing.")
    await base._app.refresh(row)
    return view(row, base)

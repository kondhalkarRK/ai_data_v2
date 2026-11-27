"""Batch 2 typed preparation feeding the existing shared Chat executor."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import text

from app.core.cache import TTLCache
from app.core.config import Industry, Settings
from app.core.exceptions import AuthorizationError
from app.schemas.semantic import SemanticPackResponse
from app.services.chat.message_classifier import MessageRoute, classify_message
from app.services.chat.pipeline import TurnPlan
from app.services.chat.question_understanding import ExtractedFilter, QuestionPlan
from app.services.chat.request_compiler import CompiledRequest, TypedCompileError, compile_request
from app.services.chat.request_context import (
    RequestContext,
    RequestPrincipal,
    ScopedCatalog,
    build_request_context,
    pack_fingerprint,
)
from app.services.chat.request_dates import RequestClarificationError, business_today
from app.services.chat.request_interpreter import (
    InterpretationInput,
    RoutePreview,
    is_greeting,
    preview_request,
)
from app.services.chat.request_state import previous_request
from app.services.chat.semantic_query_planner import SemanticQuery
from app.services.chat.time_periods import Period
from app.services.chat.value_dictionary import load_value_dictionary
from app.services.security.region_scope import for_current_scope

if TYPE_CHECKING:
    from app.services.chat.analytical_plan import AnalyticalPlan
    from app.services.chat.analytical_plan_validation import PlanReviewContext

_CATALOGS: TTLCache[tuple[ScopedCatalog, date | None]] = TTLCache(ttl_seconds=300, max_entries=256)


async def scoped_catalog(connection, pack, principal, timeout_seconds=10):
    """Every cache key is owner/scope/industry/semantic-version specific."""
    key = (principal.binding, pack_fingerprint(pack))

    async def load():
        scoped = for_current_scope(connection, principal.industry, principal.scope)
        await scoped.execute(text(f"SET LOCAL statement_timeout = {int(timeout_seconds * 1000)}"))
        snapshot = await load_value_dictionary(scoped, principal.industry, pack=pack)
        result = await scoped.execute(
            text(
                "SELECT DISTINCT v.model, v.make FROM automotive.fact_sales f "
                "JOIN automotive.dim_carline v ON v.carline_id = f.carline_id "
                "ORDER BY v.model, v.make LIMIT 2000"
            )
        )
        links = tuple((str(r.model), str(r.make)) for r in result)
        result = await scoped.execute(text("SELECT MAX(f.sales_date) FROM automotive.fact_sales f"))
        latest = result.scalar()
        return ScopedCatalog(principal.binding, snapshot, links), latest

    return await _CATALOGS.get_or_set(key, load)


@dataclass
class TypedPreparation:
    preview: RoutePreview
    context: RequestContext
    compiled: CompiledRequest | None
    turn: TurnPlan | None
    prior_sql: str | None = None
    data_as_of: str | None = None
    analysis_plan: AnalyticalPlan | None = None
    analysis_review: PlanReviewContext | None = None
    analysis_date: date | None = None
    analysis_issue_codes: list[str] = field(default_factory=list)


async def prepare_typed_request(
    *,
    settings: Settings,
    user,
    scope,
    pack: SemanticPackResponse,
    analytics,
    question: str,
    memory,
    today: date | None = None,
    completeness_sources=(),
    cancel_requested=None,
) -> TypedPreparation:
    principal = RequestPrincipal(user.id, scope, Industry.AUTOMOTIVE)
    if pack.model.query_policy is None:
        raise ValueError("No approved typed-query policy")
    today = today or business_today(pack.model.query_policy)
    greeting = is_greeting(question)
    skip_metadata = (
        greeting
        or classify_message(question, Industry.AUTOMOTIVE, enabled=True).route
        == MessageRoute.UNSUPPORTED
    )
    catalog, as_of = None, None
    if analytics is not None and not skip_metadata:
        async with asyncio.timeout(settings.nlq_sql_timeout_seconds):
            catalog, as_of = await scoped_catalog(
                analytics, pack, principal, settings.nlq_sql_timeout_seconds
            )
    try:
        prior = previous_request(
            memory.typed_request,
            principal,
            pack_fingerprint(pack),
            ttl_seconds=settings.chat_analytical_context_ttl_seconds,
            max_turns=settings.chat_analytical_context_max_turns,
        )
    except (AuthorizationError, ValueError, KeyError, TypeError):
        # Revocation/model changes invalidate old context, never the new user's scope.
        memory.typed_request = None
        prior = None
    if skip_metadata:
        prior = None
    context = build_request_context(
        question,
        pack=pack,
        principal=principal,
        catalog=catalog,
        previous=prior,
        current_date=today,
        data_as_of=as_of,
    )
    result = await preview_request(
        settings=settings.model_copy(update={"chat_request_preview_enabled": True}),
        incoming=InterpretationInput(
            question, principal, context, user.full_name, cancel_requested
        ),
    )
    if result.request and result.request.outcome == "documents" and result.status == "partial":
        request = result.request
        supported = next(
            (
                outcome
                for outcome in ("analytics", "report")
                if outcome in request.additional_outcomes
            ),
            None,
        )
        if supported and (request.measures or supported == "report"):
            result.request = request.model_copy(
                update={
                    "outcome": supported,
                    "additional_outcomes": [
                        "documents",
                        *(o for o in request.additional_outcomes if o != supported),
                    ],
                }
            )
    if (
        result.request
        and result.request.analysis_tasks
        and not result.request.clarification
        and result.status in {"ready", "partial"}
    ):
        from app.services.chat.analytical_plan_factory import materialize_plan
        from app.services.chat.analytical_plan_validation import PlanReviewContext, review_plan

        if not settings.chat_dependent_analysis_enabled or result.usage.verification_calls != 1:
            result.status, result.reason = (
                "unsupported",
                "Dependent analysis was not independently checked; no query ran.",
            )
            return TypedPreparation(result, context, None, None)
        try:
            review = PlanReviewContext(
                request_id=result.request_id,
                principal=principal,
                context=context,
                pack=pack,
                requirements=(),
                completeness_sources=tuple(completeness_sources),
                model_calls_used=result.usage.calls,
            )
            plan, review = materialize_plan(result.request, review, today=today)
            checked = review_plan(plan, review)
            if checked.status != "valid":
                issue_codes = [i.code for i in checked.issues]
                if set(issue_codes) & {
                    "loaded_completeness",
                    "completeness_source",
                    "completeness_coverage",
                    "completeness_inventory",
                }:
                    result.status = "unavailable"
                    result.reason = "Reporting-period completeness has not been verified for this selection. An administrator needs to connect approved load-status evidence. No analytical query ran."
                    result.request = result.request.model_copy(update={"clarification": None})
                    return TypedPreparation(
                        result,
                        context,
                        None,
                        None,
                        analysis_review=review,
                        analysis_date=today,
                        analysis_issue_codes=issue_codes,
                    )
                result.status = (
                    "clarification" if checked.status == "clarification" else "unsupported"
                )
                result.reason = (
                    "; ".join(i.message for i in checked.issues)
                    or "The complete request is not supported."
                )
                if result.status == "clarification":
                    result.request = result.request.model_copy(
                        update={"clarification": result.reason[:240]}
                    )
                return TypedPreparation(
                    result,
                    context,
                    None,
                    None,
                    analysis_review=review,
                    analysis_date=today,
                    analysis_issue_codes=issue_codes,
                )
            return TypedPreparation(
                result,
                context,
                None,
                None,
                analysis_plan=plan,
                analysis_review=review,
                analysis_date=today,
            )
        except RequestClarificationError as exc:
            result.status, result.reason = "clarification", str(exc)
            result.request = result.request.model_copy(update={"clarification": str(exc)})
        except (TypedCompileError, ValueError, KeyError):
            result.status, result.reason = (
                "unsupported",
                "This dependent operation combination needs a supported, complete analytical plan. No query ran.",
            )
        return TypedPreparation(result, context, None, None)
    if (
        result.request
        and result.request.outcome == "investigation"
        and not result.request.clarification
    ):
        request = result.request
        context.payload["requested_outcome"] = "investigation"
        if (
            any(pack.model.measures[m.id].aggregation != "sum" for m in request.measures)
            or request.windows
            or request.operations
            or request.measure_filters
            or request.ranking
            or any(c.kind != "period" for c in request.comparisons)
        ):
            result.status, result.reason = (
                "unsupported",
                "This investigation needs an approved additive decomposition. Ask for the underlying values instead.",
            )
            return TypedPreparation(result, context, None, None)
        from app.services.chat.request_contract import RequestedComparison

        period = request.period or next((c.current for c in request.comparisons if c.current), None)
        if period is None:
            result.status = "clarification"
            result.request = request.model_copy(
                update={"clarification": "Which period should I investigate?"}
            )
            return TypedPreparation(result, context, None, None)
        request = request.model_copy(
            update={
                "outcome": "analytics",
                "period": period,
                "group_by": request.group_by or ["dim_region.region_name"],
                "comparisons": request.comparisons
                or [RequestedComparison(kind="period", baseline_reference="previous_period")],
            }
        )
        result.request = request
    if (
        result.request
        and result.request.outcome == "report"
        and result.status in {"ready", "partial"}
        and not result.request.period
        and not result.request.clarification
    ):
        result.status = "clarification"
        result.request = result.request.model_copy(
            update={"clarification": "Which date range should the report use?"}
        )
    compiled = turn = None
    if (
        result.request
        and result.request.outcome == "analytics"
        and not result.request.clarification
        and result.status in {"ready", "partial"}
    ):
        try:
            compiled = compile_request(
                result.request,
                pack=pack,
                context=context,
                principal=principal,
                today=today,
                row_limit=min(settings.nlq_default_result_limit, settings.sql_max_result_rows),
            )
        except RequestClarificationError as exc:
            result.status, result.reason = "clarification", str(exc)
            result.request = result.request.model_copy(update={"clarification": str(exc)})
            return TypedPreparation(result, context, None, None)
        except (TypedCompileError, ValueError) as exc:
            result.status, result.reason = "unsupported", str(exc)
            return TypedPreparation(result, context, None, None)
        if result.status == "partial":
            compiled.notes.append(result.reason)
        if "documents_gated" in result.routes:
            compiled.notes.append(
                "Document evidence is unavailable; policy compliance is unverified."
            )
        if "askbi" in result.routes:
            compiled.notes.append(
                "The database part is verified separately; report creation is not enabled in typed Chat yet."
            )
        period = next(iter(compiled.periods.values()))
        primary = result.request.measures[0].id
        metric = {"units_sold": "units", "target_units": "units", "target_revenue": "revenue"}.get(
            primary, primary
        )
        filters = []
        entities = {e["id"]: e for e in context.payload["entities"]}
        for filt in result.request.filters:
            values = (
                [str(entities[key]["value"]) for key in filt.entity_ids]
                if filt.entity_ids
                else [str(v) for v in filt.values]
            )
            if values:
                filters.append(
                    ExtractedFilter(
                        column="automotive." + filt.field,
                        operator={
                            "eq": "=",
                            "ne": "<>",
                            "in": "IN",
                            "not_in": "NOT IN",
                            "gt": ">",
                            "gte": ">=",
                            "lt": "<",
                            "lte": "<=",
                        }.get(filt.operator, "="),
                        value=values[0],
                        values=tuple(values),
                        label=f"{filt.field}: {', '.join(values)}",
                    )
                )
        # Legacy plan is a presentation adapter ONLY. SQL was compiled from the full request.
        plan = QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="ranking"
            if result.request.ranking
            else "trend"
            if result.request.time_grain
            else "aggregation",
            entity="metric_only",
            metric=metric,
            filters=filters,
            dimensions=list(compiled.group_aliases.values()),
            time_grain=result.request.time_grain,
            notes=compiled.notes,
            period=Period(period.label, period.start, period.end),
        )
        planned = SemanticQuery(
            original=question,
            rewritten=question,
            plan=plan,
            sql=compiled.sql,
            title=result.request.summary,
            path="typed_semantic",
            glossary_matches=len(result.request.measures),
            chart_type="line" if result.request.time_grain else "bar",
            contextual=result.request.followup,
        )
        turn = TurnPlan(
            original=question,
            question=question,
            plan=plan,
            planned=planned,
            contextual=result.request.followup,
            governed_sql=compiled.sql,
        )
    stored = (memory.typed_request or {}).get("confirmed") or {}
    return TypedPreparation(
        result,
        context,
        compiled,
        turn,
        stored.get("sql") if prior else None,
        as_of.isoformat() if as_of else None,
    )

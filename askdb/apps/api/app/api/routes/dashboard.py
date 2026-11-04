"""On-demand dashboard explanations and bounded contextual conversation."""

from __future__ import annotations

import json
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import (
    ActiveIndustry,
    AppSession,
    RegionScopeDep,
    RequireUser,
    get_app_settings,
    get_scoped_analytics,
    verify_csrf,
)
from app.core.config import Settings
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.activity import Conversation, QueryHistory
from app.models.enums import ExecutionMode
from app.schemas.dashboard import DashboardAskRequest, DashboardExplainRequest, DashboardExplanation
from app.services.executive.dashboard import (
    explain_dashboard,
    question_intent,
    resolve_snapshot,
    select_metric,
)
from app.services.governance import enforce_quota, record_question_usage, sync_llm_config
from app.services.llm import complete_text, llm_configured
from app.services.security.region_scope import forbidden_zones

router = APIRouter(prefix="/executive", tags=["executive"], dependencies=[Depends(verify_csrf)])
Analytics = Annotated[AsyncConnection, Depends(get_scoped_analytics)]
Config = Annotated[Settings, Depends(get_app_settings)]


@router.post("/explain", response_model=DashboardExplanation)
async def explain(
    body: DashboardExplainRequest,
    user: RequireUser,
    industry: ActiveIndustry,
    scope: RegionScopeDep,
    analytics: Analytics,
    settings: Config,
) -> DashboardExplanation:
    snapshot = resolve_snapshot(
        body.snapshot_token, settings=settings, user=user, industry=industry, scope=scope
    )
    return await explain_dashboard(
        snapshot, body.metric_id, body.dimension, analytics, settings, scope
    )


@router.post("/ask", response_model=DashboardExplanation)
async def ask(
    body: DashboardAskRequest,
    user: RequireUser,
    industry: ActiveIndustry,
    scope: RegionScopeDep,
    analytics: Analytics,
    settings: Config,
    session: AppSession,
) -> DashboardExplanation:
    started = time.perf_counter()
    snapshot = resolve_snapshot(
        body.snapshot_token, settings=settings, user=user, industry=industry, scope=scope
    )
    if forbidden_zones(body.question, scope):
        raise AuthorizationError(
            "This question asks about a region outside your access. Use your "
            "permitted dashboard selection."
        )
    metric = select_metric(snapshot, body.metric_id)
    conversation = None
    if body.conversation_id:
        conversation = await session.get(Conversation, body.conversation_id)
        if (
            conversation is None
            or conversation.user_id != user.id
            or conversation.industry != industry.value
        ):
            raise NotFoundError("Dashboard conversation not found.")
        memory = (conversation.session_memory or {}).get("dashboard", {})
        if (
            memory.get("result_id") != snapshot.context.result_id
            or memory.get("scope") != scope.cache_key()
        ):
            raise AuthorizationError(
                "This conversation belongs to an earlier dashboard context. Start"
                " a new question for the current selection."
            )
    await enforce_quota(session, user)
    metric_id, dimension, operation = question_intent(
        body.question, snapshot, metric.id, body.dimension
    )
    tokens_in = tokens_out = 0
    model = "none"
    assisted = False
    if operation == "unknown":
        await sync_llm_config(session, settings)
        if llm_configured(settings):
            assisted = True
            result = await complete_text(
                settings=settings,
                system=(
                    "Classify a dashboard question. Return only JSON with metricId, "
                    "dimension, operation. "
                    "operation must be explain, definition or unsupported. Never "
                    "write SQL, numbers or advice. "
                    "Do not change periods or filters. Questions requiring different "
                    "filters/periods are unsupported. "
                    "Allowed metrics/dimensions: "
                    f"{json.dumps({m.id: m.dimensions for m in snapshot.metrics})}. "
                    f"Current metric={metric_id}; dimension={dimension}."
                ),
                user=body.question,
                max_tokens=120,
            )
            tokens_in, tokens_out, model = (
                result.prompt_tokens,
                result.completion_tokens,
                result.model,
            )
            try:
                parsed = json.loads(result.content)
                candidate = select_metric(snapshot, parsed["metricId"])
                dim = parsed.get("dimension")
                op = parsed.get("operation")
                if op in {"explain", "definition"} and (dim is None or dim in candidate.dimensions):
                    metric_id, dimension, operation = candidate.id, dim, op
            except (ValueError, KeyError, TypeError, ValidationError):
                pass  # A malformed classifier result is never executed or shown as an answer.
    metric = select_metric(snapshot, metric_id)
    if operation == "explain":
        answer = await explain_dashboard(snapshot, metric_id, dimension, analytics, settings, scope)
    else:
        narrative = {
            "definition": f"{metric.label}: {metric.definition}. "
            "This definition applies to the captured dashboard period and filters.",
            "scope": "This question changes the period or geography. Apply that "
            "selection on the dashboard, then ask again so the charts and "
            "explanation remain aligned.",
        }.get(
            operation,
            "I can explain a displayed metric, show its definition, or "
            "compare supported contributors. Try one of the suggestions "
            "below. Broader questions are available in AI Chat.",
        )
        answer = DashboardExplanation(
            context=snapshot.context,
            metric=metric,
            dimension=dimension or metric.dimensions[0],
            narrative=narrative,
            caveats=list(snapshot.caveats),
            source_tables=snapshot.source.get("tables", []),
            suggested_questions=[f"Explain {metric.label} by {d}" for d in metric.dimensions]
            + [f"What is {metric.label}?"],
        )
    if conversation is None:
        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=user.id,
            industry=industry.value,
            title=f"Dashboard: {snapshot.context.period_label}"[:240],
        )
        session.add(conversation)
        await session.flush()
    old = (conversation.session_memory or {}).get("dashboard", {})
    turns = [
        *old.get("turns", [])[-5:],
        {"question": body.question, "metric": metric_id, "dimension": answer.dimension},
    ]
    conversation.session_memory = {
        "dashboard": {
            "result_id": snapshot.context.result_id,
            "scope": scope.cache_key(),
            "turns": turns,
        }
    }
    answer.conversation_id = conversation.id
    history = QueryHistory(
        id=uuid.uuid4(),
        user_id=user.id,
        conversation_id=conversation.id,
        industry=industry.value,
        question=body.question,
        sql_text=answer.sql,
        status="completed",
        row_count=len(answer.contributors),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    session.add(history)
    await session.flush()
    await record_question_usage(
        session,
        user_id=user.id,
        question=body.question,
        industry=industry.value,
        mode=ExecutionMode.HYBRID if assisted else ExecutionMode.SCHEMA,
        model_name=model,
        prompt_tokens=tokens_in,
        completion_tokens=tokens_out,
        response_time_ms=int((time.perf_counter() - started) * 1000),
        query_history_id=history.id,
    )
    return answer

"""Chat orchestration with SSE events."""

from __future__ import annotations

import json
import logging
import secrets
import time
import uuid
from asyncio import Event
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.analytics.sql_guardrails import sql_is_safe
from app.core.config import Industry, Settings
from app.core.exceptions import ValidationError
from app.models.activity import Conversation, LlmUsage, QueryHistory, SavedQuestion
from app.models.user import User
from app.semantic.service import SemanticService
from app.services.catalog import EntityCatalogService
from app.services.chat.clarification import (
    interpretation,
    plan_suggestions,
    recovery_for_failure,
    resolution_notes,
)
from app.services.chat.conversation_context import plan_state
from app.services.chat.decision_engine import (
    Confidence,
    assess_confidence,
    decide_route,
    interpretation_options,
)
from app.services.chat.failures import (
    FailureInfo,
    classify_database,
    classify_llm_failure,
    classify_sql_validation,
    propose_sql_repair,
)
from app.services.chat.intents import (
    is_out_of_bounds,
    is_surprise_me,
    is_whatif,
    parse_whatif,
    suggested_followups,
)
from app.services.chat.llm_assist import (
    generate_validated_sql,
    interpret_question,
    interpretation_vocabulary,
)
from app.services.chat.pipeline import TurnPlan, plan_turn
from app.services.chat.profiler import PROFILER, QueryProfile
from app.services.chat.query_cache import QUERY_CACHE, CachedAnswer
from app.services.chat.query_router import knowledge_narrative, plan_entities, route_question
from app.services.chat.question_understanding import QuestionPlan
from app.services.chat.response_meta import (
    QueryTimings,
    build_insights,
    detect_anomalies,
    extract_query_meta,
    merge_hybrid_evidence,
    resolve_grounded_on,
    semantic_followups,
    source_database_label,
    sql_diff_lines,
)
from app.services.chat.semantic_context import (
    build_allowed_schema,
    build_domain_sql_hints,
    validate_sql_against_plan,
)
from app.services.chat.semantic_query_planner import PIPELINE_STAGES, recommend_chart
from app.services.chat.sql_limits import ensure_result_limit
from app.services.chat.templates import list_templates
from app.services.chat.trust import compute_trust_score
from app.services.chat.value_dictionary import (
    ValueDictionarySnapshot,
    cached_value_dictionary,
    get_value_dictionary,
    resolver_for,
)
from app.services.knowledge import KnowledgeService
from app.services.llm import llm_configured
from app.services.web_retrieval import WebRetrievalService

logger = logging.getLogger(__name__)


def _worth_reinterpreting(turn: TurnPlan) -> bool:
    """The AI may restate names/phrasing we could not read; curated clarifications stay."""
    if turn.clarify_reason in {"needs_clarification", "unresolved"}:
        return True
    return turn.clarification is None and not turn.governed_sql


def _needs_clarification() -> Confidence:
    return Confidence("needs_clarification", 0, ["Asked for clarification instead of guessing"])


RECOVERY_OPTIONS: dict[Industry, list[str]] = {
    Industry.AUTOMOTIVE: [
        "Revenue by month",
        "Top brand by revenue",
        "Maruti Suzuki sales by year",
        "SUV sales by state",
    ],
    Industry.INSURANCE: [
        "Written premium by month",
        "Loss ratio by month",
        "Claim count by status",
        "Top agents by premium",
    ],
}


def recovery_frames(industry: Industry) -> list[str]:
    """Last-resort answer when anything unexpected breaks: suggestions, never a stack trace."""
    options = RECOVERY_OPTIONS.get(industry, RECOVERY_OPTIONS[Industry.AUTOMOTIVE])
    message = "I couldn't finish that one. These questions answer instantly:"
    return [
        _sse(
            "clarification",
            {
                "kind": "recovery",
                "title": "Here's what I can answer",
                "question": message,
                "options": options,
            },
        ),
        _sse("followups", {"items": []}),
        _sse("done", {"recovered": True, "confidence": _needs_clarification().to_dict()}),
    ]

PROGRESS_STEPS = PIPELINE_STAGES
_DIMENSION_COLUMNS = frozenset(
    {
        "year",
        "quarter",
        "month",
        "make",
        "model",
        "car_type",
        "engine_type",
        "city",
        "region_name",
        "colour_name",
        "dealer_name",
        "dealer_grade",
        "salesperson_name",
        "state_code",
    }
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _citation_payload(citation: Any) -> dict[str, Any]:
    return {
        "documentId": citation.document_id,
        "title": citation.title,
        "chunkId": citation.chunk_id,
        "snippet": citation.snippet,
        "locator": citation.locator,
        "untrusted": citation.untrusted,
        "confidence": getattr(citation, "confidence", None),
        "collection": getattr(citation, "collection", None),
    }


def _progress(
    current: str,
    completed: list[str],
    *,
    slow: bool = False,
    steps: list[dict[str, str]] | None = None,
) -> str:
    active = steps if steps is not None else PROGRESS_STEPS
    label = next((s["label"] for s in active if s["id"] == current), current)
    payload: dict[str, Any] = {
        "steps": active,
        "current": current,
        "currentLabel": label,
        "completed": [step for step in completed if any(s["id"] == step for s in active)],
    }
    if slow:
        payload["slowWarning"] = True
        payload["message"] = (
            f"This query is taking longer than expected. Current stage: {label}"
        )
    return _sse("progress", payload)


class ChatService:
    def __init__(
        self,
        *,
        app_session: AsyncSession,
        analytics: AsyncConnection,
        settings: Settings,
        user: User,
        industry: Industry,
        semantic_service: SemanticService | None = None,
    ) -> None:
        self._app = app_session
        self._analytics = analytics
        self._settings = settings
        self._user = user
        self._industry = industry
        self._semantic = semantic_service or SemanticService(settings)
        self.usage_model = ""
        self.usage_prompt_tokens = 0
        self.usage_completion_tokens = 0
        self.usage_llm_steps = 0
        self.last_profile: QueryProfile | None = None
        self.last_history: QueryHistory | None = None

    async def _recover_analytics(self) -> None:
        """Clear an aborted Postgres transaction so later statements can run.

        Read-only analytics work shares one connection for the request. A failed
        EXPLAIN/probe leaves the transaction in ``InFailedSqlTransaction`` until
        rollback — without this, valid SQL looks broken.
        """
        try:
            await self._analytics.rollback()
            await self._analytics.execute(text("SET TRANSACTION READ ONLY"))
        except Exception:
            logger.debug("Analytics connection recovery failed", exc_info=True)

    async def _discover_unknown_values(self, terms: list[str]) -> ValueDictionarySnapshot | None:
        """Targeted catalog lookup for names the dictionary does not know (e.g. a new brand).

        Returns the refreshed dictionary when something was found; never raises.
        """
        service = EntityCatalogService(
            self._app, self._semantic, self._industry, analytics=self._analytics
        )
        try:
            async with self._app.begin_nested():
                found = await service.targeted_lookup(terms)
        except Exception:
            await self._recover_analytics()
            logger.warning("catalog lookup failed for %s", terms[:3], exc_info=True)
            return None
        if not found:
            return None
        logger.info("catalog_lookup found=%s", found[:5])
        return cached_value_dictionary(self._industry)

    async def ask_stream(
        self,
        question: str,
        conversation_id: uuid.UUID | None,
        *,
        cancel_event: Event | None = None,
        cancel_requested: set[uuid.UUID] | None = None,
        web_retrieval: bool = False,
        model_override: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
    ) -> AsyncIterator[str]:
        started = time.perf_counter()
        wall_started = time.time()
        timings = QueryTimings()
        question = (question or "").strip()
        if not question:
            raise ValidationError("Question is required.")

        profile = QueryProfile(
            question=question,
            industry=self._industry.value,
            started_at=wall_started,
        )
        history_id = uuid.uuid4()
        profile.history_id = str(history_id)
        self.last_profile = profile
        completed_steps: list[str] = ["question"]

        yield _sse("stage", {"stage": "accepted", "historyId": str(history_id)})
        yield _progress("rewrite", completed_steps)

        conversation = await self._ensure_conversation(conversation_id, question)
        history = await self._create_running_history(history_id, conversation.id, question)
        self.last_history = history
        await self._app.flush()
        await self._app.commit()

        async def cancelled() -> bool:
            if (cancel_event is not None and cancel_event.is_set()) or (
                cancel_requested is not None and history_id in cancel_requested
            ):
                history.status = "cancelled"
                history.latency_ms = int((time.perf_counter() - started) * 1000)
                await self._app.flush()
                await self._app.commit()
                if cancel_requested is not None:
                    cancel_requested.discard(history_id)
                profile.error_category = "cancelled"
                profile.error_reason = "Cancelled"
                profile.timings = timings.to_dict()
                PROFILER.record(profile)
                return True
            return False

        def maybe_slow() -> bool:
            return (time.perf_counter() - started) > 15.0

        current_plan: QuestionPlan | None = None

        async def emit_failure(info: FailureInfo, *, sql: str | None = None) -> AsyncIterator[str]:
            """Recover with suggestions; the technical reason stays in history/profiling."""
            logger.info("nlq_recovery category=%s reason=%s", info.category, info.reason[:240])
            profile.error_category = info.category
            profile.error_reason = info.reason
            profile.sql = sql
            history.sql_text = sql
            recovery = recovery_for_failure(
                info.category,
                current_plan,
                industry=self._industry,
                question=question,
            )
            recovery.options = interpretation_options(
                current_plan, industry=self._industry, question=question
            )
            async for frame in finish_without_sql(
                path="recovery",
                narrative=recovery.message,
                event="clarification",
                payload=recovery.payload(historyId=str(history_id)),
                alternates=recovery.options,
                history_status="failed",
                extra_breakdown={"failure": info.to_dict()},
                done_extra={
                    "recovered": True,
                    "failureCategory": info.category,
                    "confidence": _needs_clarification().to_dict(),
                },
            ):
                yield frame

        async def finish_without_sql(
            *,
            path: str,
            narrative: str,
            event: str | None = None,
            payload: dict[str, Any] | None = None,
            ambiguity: bool = False,
            alternates: list[str] | None = None,
            history_status: str = "completed",
            extra_breakdown: dict[str, Any] | None = None,
            done_extra: dict[str, Any] | None = None,
        ) -> AsyncIterator[str]:
            if event:
                yield _sse(event, payload or {})
            insights = build_insights(narrative=narrative, columns=[], rows=[], path=path)
            yield _sse(
                "meta",
                {
                    "groundedOn": resolve_grounded_on(
                        path=path,
                        glossary_matches=0,
                        has_sql=False,
                        dq_checked=False,
                    ),
                    "ambiguityFlag": ambiguity,
                    "validationStatus": "skipped",
                    "rowCount": 0,
                    "executionTimeMs": 0,
                    "sourceDatabase": source_database_label(self._industry),
                    "dataAsOf": None,
                    "timings": timings.to_dict(),
                    "queryMeta": extract_query_meta(None).to_dict(),
                    "insights": insights,
                    "anomalies": [],
                    "alternateInterpretations": alternates or [],
                    "cacheHit": False,
                },
            )
            for token in narrative.split():
                yield _sse("token", {"token": token + " "})
            history.status = history_status
            history.row_count = 0
            history.trust_score = 0
            history.trust_breakdown = {
                "path": path,
                "ambiguityFlag": ambiguity,
                **(extra_breakdown or {}),
            }
            history.latency_ms = int((time.perf_counter() - started) * 1000)
            await self._app.flush()
            if history_status == "failed":
                await self._app.commit()
            profile.path = path
            profile.timings = timings.to_dict()
            PROFILER.record(profile)
            options = (payload or {}).get("options") or []
            yield _sse(
                "followups",
                {
                    "items": [
                        item
                        for item in suggested_followups(self._industry, path)
                        if item not in options
                    ]
                    if path not in {"clarification", "recovery"}
                    else []
                },
            )
            yield _sse(
                "done",
                {
                    "historyId": str(history_id),
                    "conversationId": str(conversation.id),
                    "latencyMs": history.latency_ms,
                    "trustScore": 0,
                    "ambiguityFlag": ambiguity,
                    **(done_extra or {}),
                },
            )

        if is_out_of_bounds(question, self._industry):
            yield _sse("badge", {"path": "out_of_bounds", "label": "Out of scope"})
            async for frame in finish_without_sql(
                path="out_of_bounds",
                narrative=(
                    f"I can only answer governed {self._industry.value} analytics questions. "
                    "Try asking about a business metric in the available data."
                ),
            ):
                yield frame
            return

        try:
            semantic_pack = await self._semantic.get_pack(self._industry)
        except Exception:
            logger.warning("Semantic pack unavailable; using fallback hints", exc_info=True)
            semantic_pack = None
        try:
            value_dictionary = await get_value_dictionary(
                self._analytics,
                self._industry,
                pack=semantic_pack,
            )
        except Exception:
            await self._recover_analytics()
            logger.warning(
                "Value dictionary unavailable; continuing with pack vocabulary", exc_info=True
            )
            value_dictionary = ValueDictionarySnapshot(self._industry, ())
        allowed_schema = build_allowed_schema(semantic_pack)
        resolver = resolver_for(value_dictionary, semantic_pack)
        llm_ready = llm_configured(self._settings)

        prior_sql: str | None = None
        prior_state: dict[str, Any] | None = None
        if conversation_id is not None:
            prior_sql = await self._prior_sql(conversation.id, history_id)
            prior_state = await self._prior_state(conversation.id, history_id)

        surprise_sql = None
        if is_surprise_me(question):
            templates = list_templates(self._industry)
            surprise = secrets.choice(templates) if templates else None
            if surprise is not None:
                surprise_sql = (surprise.sql, surprise.title, surprise.glossary_matches)
            yield _sse("stage", {"stage": "surprise"})

        # Spell correction -> rewrite -> resolver (exact, synonym, fuzzy, alias,
        # glossary) -> intent -> planner -> governed SQL -> plan validation.
        semantic_t0 = time.perf_counter()
        turn = plan_turn(
            self._industry,
            question,
            snapshot=value_dictionary,
            pack=semantic_pack,
            allowed_schema=allowed_schema,
            prior_sql=prior_sql,
            prior_state=prior_state,
            surprise_sql=surprise_sql,
        )
        if turn.clarify_reason == "unresolved" and turn.resolution.unresolved:
            refreshed = await self._discover_unknown_values(
                [item.text for item in turn.resolution.unresolved]
            )
            if refreshed is not None:
                yield _sse("stage", {"stage": "catalog_lookup"})
                value_dictionary = refreshed
                resolver = resolver_for(value_dictionary, semantic_pack)
                turn = plan_turn(
                    self._industry,
                    question,
                    snapshot=value_dictionary,
                    pack=semantic_pack,
                    allowed_schema=allowed_schema,
                    prior_sql=prior_sql,
                    prior_state=prior_state,
                    surprise_sql=surprise_sql,
                )
        reinterpreted: str | None = None
        if llm_ready and self._settings.nlq_llm_interpretation and _worth_reinterpreting(turn):
            # Last step before asking the user: let the AI restate the question in
            # governed vocabulary, then plan the restatement deterministically.
            yield _sse("stage", {"stage": "llm_interpret"})
            llm_t0 = time.perf_counter()
            restated, tokens_in, tokens_out = await interpret_question(
                settings=self._settings,
                industry=self._industry,
                question=turn.question,
                vocabulary=interpretation_vocabulary(self._industry, resolver),
                model_override=model_override,
            )
            timings.llm_generation_ms += int((time.perf_counter() - llm_t0) * 1000)
            profile.llm_calls += 1
            profile.prompt_tokens += tokens_in
            profile.completion_tokens += tokens_out
            if tokens_in or tokens_out:
                await self._record_usage(
                    model_override or self._settings.llm_default_model, tokens_in, tokens_out
                )
            if restated:
                second = plan_turn(
                    self._industry,
                    restated,
                    snapshot=value_dictionary,
                    pack=semantic_pack,
                    allowed_schema=allowed_schema,
                )
                if second.clarification is None and second.governed_sql:
                    logger.info("nlq_reinterpreted question=%r as=%r", question[:180], restated)
                    turn, reinterpreted = second, restated
        timings.semantic_lookup_ms = int((time.perf_counter() - semantic_t0) * 1000)

        plan = turn.plan
        current_plan = plan
        completed_steps.extend(["rewrite", "intent"])
        yield _progress("ambiguity", completed_steps, slow=maybe_slow())
        if plan is not None:
            logger.info(
                "nlq_plan question=%r corrected=%r intent=%s entity=%s metric=%s analysis=%s "
                "dimensions=%s filters=%s contextual=%s",
                question[:180],
                turn.question[:180],
                plan.intent,
                plan.entity,
                plan.metric,
                plan.analysis,
                plan.dimensions,
                [f"{item.column}={item.value}" for item in plan.filters],
                turn.contextual,
            )

        if turn.clarification is not None or plan is None:
            clar = turn.clarification
            assert clar is not None
            options = clar.options or interpretation_options(
                plan, industry=self._industry, question=question
            )
            logger.info(
                "nlq_clarify reason=%s unresolved=%s unsupported=%s",
                turn.clarify_reason,
                [item.text for item in turn.resolution.unresolved],
                [item.term for item in turn.resolution.unsupported],
            )
            async for frame in finish_without_sql(
                path="clarification",
                narrative=clar.message,
                event="clarification",
                payload={**clar.payload(), "options": options},
                ambiguity=True,
                alternates=options,
                done_extra={"confidence": _needs_clarification().to_dict()},
            ):
                yield frame
            return

        knowledge_service = KnowledgeService(self._settings, self._industry)
        decision = route_question(
            question,
            plan,
            has_documents=bool(knowledge_service.list_documents()),
        )
        yield _sse(
            "stage",
            {"stage": "route", "route": decision.route, "reason": decision.reason},
        )

        if decision.route == "knowledge":
            completed_steps.extend(
                step for step in ("rewrite", "intent", "ambiguity") if step not in completed_steps
            )
            yield _progress("narration", completed_steps, slow=maybe_slow())
            try:
                citations = knowledge_service.search(
                    question,
                    top_k=min(5, self._settings.rag_top_k),
                    user_id=str(self._user.id),
                )
            except Exception:
                logger.debug("Knowledge search failed", exc_info=True)
                citations = []
            for citation in citations:
                yield _sse("citation", _citation_payload(citation))
            narrative = knowledge_narrative(citations)
            insights = build_insights(
                narrative=narrative,
                columns=[],
                rows=[],
                path="knowledge",
            )
            followups: list[str] = []
            for doc in knowledge_service.list_documents():
                for item in doc.get("suggestedQuestions") or []:
                    if item not in followups:
                        followups.append(str(item))
                if len(followups) >= 4:
                    break
            if not followups:
                followups = suggested_followups(self._industry, "knowledge")
            yield _sse(
                "meta",
                {
                    "groundedOn": [],
                    "ambiguityFlag": False,
                    "validationStatus": "skipped",
                    "rowCount": 0,
                    "executionTimeMs": 0,
                    "sourceDatabase": "Knowledge base",
                    "dataAsOf": None,
                    "timings": timings.to_dict(),
                    "queryMeta": extract_query_meta(None).to_dict(),
                    "insights": insights,
                    "anomalies": [],
                    "alternateInterpretations": [],
                    "cacheHit": False,
                    "route": "knowledge",
                    "routeReason": decision.reason,
                },
            )
            for token in narrative.split():
                yield _sse("token", {"token": token + " "})
            history.status = "completed"
            history.row_count = 0
            history.trust_score = 0
            history.trust_breakdown = {"path": "knowledge", "route": "knowledge"}
            history.latency_ms = int((time.perf_counter() - started) * 1000)
            await self._app.flush()
            profile.path = "knowledge"
            profile.timings = timings.to_dict()
            PROFILER.record(profile)
            yield _sse("followups", {"items": followups})
            yield _sse(
                "done",
                {
                    "historyId": str(history_id),
                    "conversationId": str(conversation.id),
                    "latencyMs": history.latency_ms,
                    "trustScore": 0,
                    "ambiguityFlag": False,
                    "route": "knowledge",
                },
            )
            return

        if await cancelled():
            yield _sse("cancelled", {"historyId": str(history_id)})
            return

        completed_steps.append("ambiguity")
        yield _progress("context", completed_steps, slow=maybe_slow())

        data_as_of_hint = await self._industry_data_as_of()

        cached = QUERY_CACHE.get(
            industry=self._industry.value,
            question=question,
            current_data_as_of=data_as_of_hint,
        )
        if cached is not None:
            profile.cache_hit = True
            profile.path = cached.path
            profile.sql = cached.sql
            profile.row_count = len(cached.rows)
            profile.tables = list(cached.tables)
            profile.timings = timings.to_dict()
            PROFILER.record(profile)
            yield _sse("stage", {"stage": "cache_hit"})
            for step in (
                "rewrite",
                "intent",
                "ambiguity",
                "context",
                "semantic",
                "joins",
                "formula",
                "sql",
                "validate",
                "repair",
                "execute",
                "chart",
            ):
                if step not in completed_steps:
                    completed_steps.append(step)
            yield _progress("narration", completed_steps)
            if cached.sql:
                yield _sse(
                    "sql",
                    {
                        "sql": cached.sql,
                        "path": cached.path,
                        "priorSql": None,
                        "diff": [],
                        "validationStatus": "passed",
                        "cacheHit": True,
                    },
                )
            if cached.columns:
                yield _sse("columns", {"columns": cached.columns})
                yield _sse(
                    "rows",
                    {"rows": cached.rows, "rowCount": len(cached.rows), "truncated": False},
                )
            if cached.chart:
                yield _sse("chart", cached.chart)
            meta = {
                **cached.meta,
                "cacheHit": True,
                "timings": timings.to_dict(),
                "route": decision.route,
            }
            yield _sse("meta", meta)
            for token in cached.narrative.split(" "):
                yield _sse("token", {"token": token + " "})
            yield _sse("followups", {"items": cached.followups})
            latency_ms = int((time.perf_counter() - started) * 1000)
            history.sql_text = cached.sql
            history.row_count = len(cached.rows)
            history.status = "completed"
            history.latency_ms = latency_ms
            history.trust_breakdown = {"path": cached.path, "cacheHit": True}
            await self._app.flush()
            yield _sse(
                "done",
                {
                    "historyId": str(history_id),
                    "conversationId": str(conversation.id),
                    "latencyMs": latency_ms,
                    "cacheHit": True,
                    "rowCount": len(cached.rows),
                },
            )
            return

        yield _sse(
            "stage",
            {
                "stage": "planning",
                "conversationId": str(conversation.id),
            },
        )

        followup_note = ""
        if turn.contextual:
            yield _sse("stage", {"stage": "followup"})
            followup_note = "Using the previous question's metric, filters, and grain. "
        else:
            prior_sql = None

        planned = turn.planned
        assert planned is not None
        logger.info("nlq_structured_plan %s", json.dumps(planned.structured_plan(), default=str))
        yield _sse("stage", {"stage": "semantic_plan", **planned.trace()})
        for step in ("context", "semantic", "joins", "formula"):
            if step not in completed_steps:
                completed_steps.append(step)
        yield _progress("sql", completed_steps, slow=maybe_slow())

        governed_sql = turn.governed_sql
        sql_text: str | None = governed_sql
        path = planned.path
        glossary_matches = planned.glossary_matches
        narrative = followup_note
        scenario = parse_whatif(question) if is_whatif(question) else None
        ambiguity_flag = False
        alternate_interpretations: list[str] = []
        ai_generated = False
        notes = [*turn.spelling_notes, *resolution_notes(turn.resolution)]
        if reinterpreted:
            notes.insert(0, f"I read this as \u201c{reinterpreted}\u201d.")
        if turn.validation_error:
            logger.warning("Governed SQL failed plan validation: %s", turn.validation_error)

        route_decision = decide_route(
            plan,
            has_governed_sql=bool(governed_sql),
            llm_available=llm_ready,
            mode=self._settings.nlq_llm_reasoning_mode,
        )
        yield _sse("stage", {"stage": "decision", **route_decision.to_dict()})

        if route_decision.path == "clarify":
            async for frame in emit_failure(
                FailureInfo(
                    "semantic" if plan.metric == "unknown" else "sql_generation",
                    "No governed query",
                    turn.validation_error
                    or "No governed template matched and no language model is configured.",
                )
            ):
                yield frame
            return

        if route_decision.path == "llm_reasoning":
            yield _sse("stage", {"stage": "llm", "reason": route_decision.reason})
            llm_t0 = time.perf_counter()

            def _validate(candidate: str) -> tuple[bool, str | None]:
                safe, why = sql_is_safe(candidate)
                if not safe:
                    return safe, why
                return validate_sql_against_plan(candidate, plan, allowed_schema=allowed_schema)

            outcome = await generate_validated_sql(
                settings=self._settings,
                industry=self._industry,
                question=turn.question,
                plan=plan,
                schema_hints=await self._domain_sql_hints(turn.question, plan),
                validate=_validate,
                prior_sql=prior_sql,
                model_override=model_override,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
            )
            timings.llm_generation_ms += int((time.perf_counter() - llm_t0) * 1000)
            profile.llm_calls += outcome.attempts
            profile.prompt_tokens += outcome.prompt_tokens
            profile.completion_tokens += outcome.completion_tokens
            if outcome.prompt_tokens or outcome.completion_tokens:
                await self._record_usage(
                    outcome.model, outcome.prompt_tokens, outcome.completion_tokens
                )
            if outcome.sql:
                sql_text = outcome.sql
                path = "semantic_llm"
                glossary_matches = max(glossary_matches, 1)
                ai_generated = True
                if outcome.repaired:
                    notes.append("The AI's first draft was corrected in the validation loop.")
            elif governed_sql:
                logger.info(
                    "nlq_llm_fallback reason=%s rejected=%s", outcome.error, outcome.rejected
                )
                route_decision.governed_fallback = True
            else:
                logger.info("nlq_llm_failed reason=%s rejected=%s", outcome.error, outcome.rejected)
                info = (
                    classify_llm_failure(outcome.error or "degraded")
                    if outcome.circuit_open or not outcome.rejected
                    else classify_sql_validation(outcome.error or "rejected")
                )
                async for frame in emit_failure(info):
                    yield frame
                return

        confidence = assess_confidence(
            plan,
            resolution=turn.resolution,
            corrections=turn.corrections,
            has_sql=bool(sql_text),
            contextual=turn.contextual,
            reinterpreted=bool(reinterpreted),
            ai_generated=ai_generated,
        )
        if confidence.level == "needs_clarification":
            # A safe clarification beats a confident wrong number.
            options = list(
                dict.fromkeys(
                    [
                        interpretation(plan),
                        *interpretation_options(plan, industry=self._industry, question=question),
                    ]
                )
            )[:5]
            message = "I found more than one way to read this. Choose one:"
            async for frame in finish_without_sql(
                path="clarification",
                narrative=message,
                event="clarification",
                payload={
                    "kind": "clarify",
                    "title": "I found multiple interpretations",
                    "question": message,
                    "options": options,
                },
                ambiguity=True,
                alternates=options,
                extra_breakdown={"confidence": confidence.to_dict()},
                done_extra={"confidence": confidence.to_dict()},
            ):
                yield frame
            return

        if planned.defaulted_grain and not ai_generated:
            notes.append(
                "No period was given, so this is the monthly trend for the latest 24 months."
            )
            alternate_interpretations = plan_suggestions(
                plan, industry=self._industry, question=question
            )
        if confidence.level == "medium" and not alternate_interpretations:
            alternate_interpretations = interpretation_options(
                plan, industry=self._industry, question=question, limit=3
            )
        if ai_generated:
            notes.append(
                "Planner + AI reasoning: SQL drafted by the AI from the query plan and "
                "approved by the validator."
            )
        else:
            notes.append(f"Answered with governed template: {planned.title}.")
            yield _sse("stage", {"stage": "template", "title": planned.title})
        narrative += " ".join(notes)

        if scenario is not None:
            direction = str(scenario["direction"])
            raw_value = scenario["change_value"]
            value = float(raw_value) if isinstance(raw_value, (int, float, str)) else 0.0
            unit = "%" if scenario["change_type"] == "percent" else " units"
            narrative += (
                f" Scenario: an illustrative {direction} change of {value:g}{unit} "
                "is applied conceptually; source data is not modified."
            )

        if await cancelled():
            yield _sse("cancelled", {"historyId": str(history_id)})
            return

        rows: list[dict[str, Any]] = []
        columns: list[str] = []
        validation_status = "skipped"
        data_as_of: str | None = data_as_of_hint
        dq_failed = False
        execution_error: str | None = None
        explain_plan: str | None = None
        chart_payload: dict[str, Any] | None = None

        if sql_text:
            sql_text = ensure_result_limit(sql_text, self._settings.nlq_default_result_limit)
            completed_steps.append("sql")
            yield _progress("validate", completed_steps, slow=maybe_slow())
            val_t0 = time.perf_counter()
            ok, reason = sql_is_safe(sql_text)
            if not ok:
                timings.sql_validation_ms = int((time.perf_counter() - val_t0) * 1000)
                async for frame in emit_failure(classify_sql_validation(reason), sql=sql_text):
                    yield frame
                return

            validation_status = "passed"
            try:
                await self._analytics.execute(text(f"EXPLAIN {sql_text}"))
            except Exception as exc:
                await self._recover_analytics()
                repair_t0 = time.perf_counter()
                candidate = sql_text
                last_exc: Exception = exc
                repaired_ok = False
                for _attempt in range(3):
                    proposal = propose_sql_repair(candidate, str(last_exc), semantic_pack)
                    if not proposal:
                        break
                    try:
                        await self._analytics.execute(text(f"EXPLAIN {proposal}"))
                        sql_text = proposal
                        validation_status = "auto_repaired"
                        repaired_ok = True
                        break
                    except Exception as repair_exc:
                        await self._recover_analytics()
                        last_exc = repair_exc
                        candidate = proposal
                if not repaired_ok and llm_ready:
                    repaired = await self._llm_repair(
                        question=turn.question,
                        plan=plan,
                        failed_sql=candidate,
                        error=str(last_exc),
                        allowed_schema=allowed_schema,
                        model_override=model_override,
                    )
                    if repaired:
                        sql_text, validation_status, repaired_ok = repaired, "auto_repaired", True
                        ai_generated = True
                        path = "semantic_llm"
                if not repaired_ok and governed_sql and sql_text != governed_sql:
                    fallback = ensure_result_limit(
                        governed_sql, self._settings.nlq_default_result_limit
                    )
                    try:
                        await self._analytics.execute(text(f"EXPLAIN {fallback}"))
                        sql_text, path, repaired_ok = fallback, planned.path, True
                        ai_generated = False
                        route_decision.governed_fallback = True
                    except Exception:
                        await self._recover_analytics()
                timings.sql_auto_repair_ms = int((time.perf_counter() - repair_t0) * 1000)
                if not repaired_ok:
                    validation_status = "failed"
                    timings.sql_validation_ms = int((time.perf_counter() - val_t0) * 1000)
                    detail = str(last_exc)[:240]
                    if "InFailedSqlTransaction" in detail:
                        detail = str(exc)[:240]
                    async for frame in emit_failure(
                        classify_database(detail),
                        sql=sql_text,
                    ):
                        yield frame
                    return
            timings.sql_validation_ms = int((time.perf_counter() - val_t0) * 1000)
            completed_steps.append("validate")
            if "repair" not in completed_steps:
                completed_steps.append("repair")
            yield _progress("execute", completed_steps, slow=maybe_slow())

            yield _sse(
                "sql",
                {
                    "sql": sql_text,
                    "path": path,
                    "priorSql": prior_sql,
                    "diff": sql_diff_lines(prior_sql, sql_text),
                    "validationStatus": validation_status,
                },
            )

            try:
                plan_result = await self._analytics.execute(
                    text(f"EXPLAIN (FORMAT TEXT) {sql_text}")
                )
                explain_plan = "\n".join(str(row[0]) for row in plan_result.fetchall())
            except Exception:
                await self._recover_analytics()
                explain_plan = None

            exec_t0 = time.perf_counter()
            try:
                timeout_ms = int(self._settings.nlq_sql_timeout_seconds * 1000)
                await self._analytics.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
                result = await self._analytics.execute(text(sql_text))
                mappings = result.mappings().all()
                cap = min(
                    self._settings.nlq_default_result_limit,
                    self._settings.sql_max_result_rows,
                )
                capped = mappings[:cap]
                columns = list(capped[0].keys()) if capped else list(result.keys())
                rows = [{key: _jsonable(value) for key, value in row.items()} for row in capped]
                timings.execution_ms = int((time.perf_counter() - exec_t0) * 1000)
                probed = await self._probe_data_as_of(sql_text)
                if probed:
                    data_as_of = probed
            except Exception as exc:
                await self._recover_analytics()
                timings.execution_ms = int((time.perf_counter() - exec_t0) * 1000)
                async for frame in emit_failure(classify_database(str(exc)), sql=sql_text):
                    yield frame
                return

            completed_steps.append("execute")
            yield _progress("chart", completed_steps, slow=maybe_slow())

            if rows or columns:
                yield _sse("columns", {"columns": columns})
                yield _sse(
                    "rows",
                    {
                        "rows": rows,
                        "rowCount": len(rows),
                        "truncated": False,
                    },
                )
            render_t0 = time.perf_counter()
            chart_type = recommend_chart(plan, columns)
            if rows and len(columns) >= 2 and chart_type != "table":
                measures = [
                    column
                    for column in columns[1:]
                    if column not in _DIMENSION_COLUMNS
                    and isinstance(rows[0].get(column), (int, float))
                ]
                series = [column for column in planned.chart_series if column in columns]
                chart_payload = {
                    "type": chart_type,
                    "x": columns[0],
                    "y": (series or measures or columns[1:])[0],
                    "series": series,
                    "points": rows[:60],
                    "anomalies": detect_anomalies(columns, rows),
                }
                yield _sse("chart", chart_payload)
            timings.render_ms = int((time.perf_counter() - render_t0) * 1000)
            completed_steps.append("chart")
            yield _progress("narration", completed_steps, slow=maybe_slow())

            score, breakdown = compute_trust_score(
                glossary_matches=glossary_matches,
                glossary_hints_are_sql=True,
                resolution_path=path,
                row_count=len(rows),
            )
        else:
            score, breakdown = compute_trust_score(
                glossary_matches=0,
                glossary_hints_are_sql=False,
                resolution_path=path,
                row_count=0,
            )
            completed_steps.extend(
                step
                for step in ("sql", "validate", "repair", "execute", "chart")
                if step not in completed_steps
            )
            yield _progress("narration", completed_steps, slow=maybe_slow())

        if await cancelled():
            yield _sse("cancelled", {"historyId": str(history_id)})
            return

        try:
            citations = []
            if decision.route == "hybrid":
                citations = KnowledgeService(self._settings, self._industry).search(
                    question,
                    top_k=min(2, self._settings.rag_top_k),
                    user_id=str(self._user.id),
                    entities=plan_entities(plan),
                )
                for citation in citations:
                    yield _sse("citation", _citation_payload(citation))
            if web_retrieval and question.startswith(("http://", "https://")):
                web_hits = await WebRetrievalService(self._settings).retrieve(
                    question, opted_in=True
                )
                for citation in web_hits:
                    yield _sse(
                        "citation",
                        {
                            **_citation_payload(citation),
                            "untrusted": True,
                        },
                    )
        except Exception:
            logger.debug("Supplementary knowledge retrieval failed", exc_info=True)
            citations = []

        query_meta = extract_query_meta(sql_text)
        insights = build_insights(
            narrative=narrative,
            columns=columns,
            rows=rows,
            path=path,
        )
        if decision.route == "hybrid" and citations:
            insights = merge_hybrid_evidence(
                insights,
                [citation.snippet for citation in citations],
                entities=plan_entities(plan),
            )
        grounded = resolve_grounded_on(
            path=path,
            glossary_matches=glossary_matches,
            has_sql=bool(sql_text),
            dq_checked=False,
        )
        if "chart" not in completed_steps:
            completed_steps.append("chart")
        if "narration" not in completed_steps:
            completed_steps.append("narration")

        confidence = assess_confidence(
            plan,
            resolution=turn.resolution,
            corrections=turn.corrections,
            has_sql=bool(sql_text),
            contextual=turn.contextual,
            reinterpreted=bool(reinterpreted),
            ai_generated=ai_generated,
        )
        meta_payload = {
            "confidence": confidence.to_dict(),
            "decision": {
                **route_decision.to_dict(),
                "answeredBy": "llm" if ai_generated else "semantic",
            },
            "corrections": [
                {"from": wrong, "to": right} for wrong, right in turn.corrections
            ],
            "reinterpretedAs": reinterpreted,
            "groundedOn": grounded,
            "ambiguityFlag": ambiguity_flag,
            "validationStatus": validation_status,
            "rowCount": len(rows),
            "executionTimeMs": timings.execution_ms,
            "sourceDatabase": source_database_label(self._industry),
            "dataAsOf": data_as_of,
            "timings": timings.to_dict(),
            "queryMeta": query_meta.to_dict(),
            "insights": insights,
            "anomalies": detect_anomalies(columns, rows) if rows else [],
            "alternateInterpretations": alternate_interpretations,
            "queryPlan": planned.trace(),
            "dqFailed": dq_failed,
            "executionError": execution_error,
            "autoRepaired": validation_status == "auto_repaired",
            "cacheHit": False,
            "route": decision.route,
            "routeReason": decision.reason,
        }
        yield _sse("meta", meta_payload)

        for token in narrative.split(" "):
            yield _sse("token", {"token": token + " "})

        yield _sse("trust", {"score": score, "breakdown": breakdown})
        latency_ms = int((time.perf_counter() - started) * 1000)
        history.sql_text = sql_text
        history.row_count = len(rows)
        history.trust_score = score
        history.trust_breakdown = {
            **breakdown,
            "path": path,
            "groundedOn": grounded,
            "ambiguityFlag": ambiguity_flag,
            "validationStatus": validation_status,
            "queryState": plan_state(plan),
            "confidence": confidence.to_dict(),
            "decision": route_decision.to_dict(),
        }
        history.latency_ms = latency_ms
        history.status = "completed"
        await self._app.flush()

        scoped = (
            plan_suggestions(plan, industry=self._industry, question=question, limit=3)
            if plan.filters
            else []
        )
        followups = list(
            dict.fromkeys(
                [
                    *(item for item in scoped if item not in alternate_interpretations),
                    *semantic_followups(
                        self._industry,
                        dimensions=query_meta.dimensions_used,
                        metrics=query_meta.metrics_used,
                        tables=query_meta.tables_used,
                        path=path,
                    ),
                ]
            )
        )[:5]
        yield _sse("followups", {"items": followups})

        if sql_text and path != "fallback" and not turn.contextual:
            QUERY_CACHE.put(
                industry=self._industry.value,
                question=question,
                answer=CachedAnswer(
                    sql=sql_text,
                    columns=columns,
                    rows=rows,
                    chart=chart_payload,
                    meta=meta_payload,
                    narrative=narrative,
                    followups=followups,
                    path=path,
                    data_as_of=data_as_of,
                    created_at=time.time(),
                    tables=query_meta.tables_used,
                ),
            )

        profile.sql = sql_text
        profile.tables = query_meta.tables_used
        profile.row_count = len(rows)
        profile.path = path
        profile.timings = timings.to_dict()
        profile.explain_plan = explain_plan
        PROFILER.record(profile)

        yield _sse(
            "done",
            {
                "historyId": str(history_id),
                "conversationId": str(conversation.id),
                "latencyMs": latency_ms,
                "trustScore": score,
                "ambiguityFlag": ambiguity_flag,
                "validationStatus": validation_status,
                "rowCount": len(rows),
                "timings": timings.to_dict(),
                "confidence": confidence.to_dict(),
            },
        )

    async def _llm_repair(
        self,
        *,
        question: str,
        plan: QuestionPlan,
        failed_sql: str,
        error: str,
        allowed_schema: dict[str, set[str]],
        model_override: str | None,
    ) -> str | None:
        """One AI repair of SQL the database rejected; it must pass validation and EXPLAIN."""

        def _validate(candidate: str) -> tuple[bool, str | None]:
            safe, why = sql_is_safe(candidate)
            if not safe:
                return safe, why
            return validate_sql_against_plan(candidate, plan, allowed_schema=allowed_schema)

        outcome = await generate_validated_sql(
            settings=self._settings,
            industry=self._industry,
            question=question,
            plan=plan,
            schema_hints=await self._domain_sql_hints(question, plan),
            validate=_validate,
            model_override=model_override,
            initial_feedback=f"Database error: {error[:400]}\nFailed SQL:\n{failed_sql}",
        )
        if outcome.prompt_tokens or outcome.completion_tokens:
            await self._record_usage(outcome.model, outcome.prompt_tokens, outcome.completion_tokens)
        if not outcome.sql:
            return None
        candidate = ensure_result_limit(outcome.sql, self._settings.nlq_default_result_limit)
        try:
            await self._analytics.execute(text(f"EXPLAIN {candidate}"))
        except Exception:
            await self._recover_analytics()
            return None
        return candidate

    async def _domain_sql_hints(self, question: str, plan: QuestionPlan) -> str:
        pack = None
        try:
            pack = await self._semantic.get_pack(self._industry)
        except Exception:
            logger.debug("Semantic pack unavailable; using fallback schema hints", exc_info=True)
        return build_domain_sql_hints(
            industry=self._industry,
            question=question,
            plan=plan,
            pack=pack,
        )

    async def _industry_data_as_of(self) -> str | None:
        probes = {
            Industry.AUTOMOTIVE: ("automotive.fact_sales", "sales_date"),
            Industry.INSURANCE: ("insurance.fact_claims", "reported_date"),
        }
        table, col = probes[self._industry]
        try:
            result = await self._analytics.execute(text(f"SELECT MAX({col}) AS as_of FROM {table}"))
            value = result.scalar_one_or_none()
            if value is not None:
                return value.isoformat() if hasattr(value, "isoformat") else str(value)
        except Exception:
            await self._recover_analytics()
            return None
        return None

    async def _probe_data_as_of(self, sql: str) -> str | None:
        meta = extract_query_meta(sql)
        date_cols = {
            "insurance.fact_claims": "reported_date",
            "fact_claims": "reported_date",
            "insurance.fact_policy_monthly": "accounting_month",
            "fact_policy_monthly": "accounting_month",
            "automotive.fact_sales": "sales_date",
            "fact_sales": "sales_date",
        }
        for table in meta.tables_used:
            col = date_cols.get(table.lower()) or date_cols.get(table.split(".")[-1].lower())
            if not col:
                continue
            try:
                result = await self._analytics.execute(
                    text(f"SELECT MAX({col}) AS as_of FROM {table}")
                )
                value = result.scalar_one_or_none()
                if value is not None:
                    return value.isoformat() if hasattr(value, "isoformat") else str(value)
            except Exception:
                await self._recover_analytics()
                logger.debug("Could not probe data freshness for %s", table, exc_info=True)
                continue
        return None

    async def cancel(self, history_id: uuid.UUID) -> bool:
        result = await self._app.execute(
            update(QueryHistory)
            .where(QueryHistory.id == history_id)
            .where(QueryHistory.user_id == self._user.id)
            .values(status="cancelled")
        )
        await self._app.flush()
        return bool(getattr(result, "rowcount", 0))

    async def _prior_sql(
        self, conversation_id: uuid.UUID, current_history_id: uuid.UUID
    ) -> str | None:
        result = await self._app.execute(
            select(QueryHistory.sql_text)
            .where(QueryHistory.conversation_id == conversation_id)
            .where(QueryHistory.id != current_history_id)
            .where(QueryHistory.sql_text.is_not(None))
            .order_by(QueryHistory.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _prior_state(
        self, conversation_id: uuid.UUID, current_history_id: uuid.UUID
    ) -> dict[str, Any] | None:
        result = await self._app.execute(
            select(QueryHistory.trust_breakdown)
            .where(QueryHistory.conversation_id == conversation_id)
            .where(QueryHistory.id != current_history_id)
            .where(QueryHistory.status == "completed")
            .order_by(QueryHistory.created_at.desc())
            .limit(1)
        )
        breakdown = result.scalar_one_or_none()
        if not isinstance(breakdown, dict):
            return None
        state = breakdown.get("queryState")
        return state if isinstance(state, dict) else None

    async def list_history(self, *, limit: int = 50) -> list[QueryHistory]:
        result = await self._app.execute(
            select(QueryHistory)
            .where(QueryHistory.user_id == self._user.id)
            .where(QueryHistory.industry == self._industry.value)
            .order_by(QueryHistory.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_saved(self) -> list[SavedQuestion]:
        result = await self._app.execute(
            select(SavedQuestion)
            .where(SavedQuestion.user_id == self._user.id)
            .where(SavedQuestion.industry == self._industry.value)
            .order_by(SavedQuestion.created_at.desc())
        )
        return list(result.scalars().all())

    async def save_question(
        self, *, title: str, question: str, sql_text: str | None
    ) -> SavedQuestion:
        row = SavedQuestion(
            id=uuid.uuid4(),
            user_id=self._user.id,
            industry=self._industry.value,
            title=title[:240],
            question=question,
            sql_text=sql_text,
        )
        self._app.add(row)
        await self._app.flush()
        return row

    async def cost_summary(self) -> dict[str, Any]:
        result = await self._app.execute(
            select(LlmUsage)
            .where(LlmUsage.user_id == self._user.id)
            .order_by(LlmUsage.created_at.desc())
            .limit(500)
        )
        rows = list(result.scalars().all())
        total_tokens = sum(row.total_tokens for row in rows)
        total_cost = float(sum(float(row.estimated_cost_usd) for row in rows))
        avg_cost = (total_cost / len(rows)) if rows else 0.0

        by_model: dict[str, dict[str, float | int]] = {}
        by_domain: dict[str, dict[str, float | int]] = {}
        daily: dict[str, float] = {}
        for row in rows:
            model_bucket = by_model.setdefault(
                row.model_name, {"calls": 0, "tokens": 0, "costUsd": 0.0}
            )
            model_bucket["calls"] = int(model_bucket["calls"]) + 1
            model_bucket["tokens"] = int(model_bucket["tokens"]) + row.total_tokens
            model_bucket["costUsd"] = float(model_bucket["costUsd"]) + float(
                row.estimated_cost_usd
            )

            domain = row.industry or "unknown"
            domain_bucket = by_domain.setdefault(
                domain, {"calls": 0, "tokens": 0, "costUsd": 0.0}
            )
            domain_bucket["calls"] = int(domain_bucket["calls"]) + 1
            domain_bucket["tokens"] = int(domain_bucket["tokens"]) + row.total_tokens
            domain_bucket["costUsd"] = float(domain_bucket["costUsd"]) + float(
                row.estimated_cost_usd
            )

            day = row.created_at.date().isoformat() if row.created_at else "unknown"
            daily[day] = daily.get(day, 0.0) + float(row.estimated_cost_usd)

        budget = float(getattr(self._settings, "llm_monthly_budget_usd", 50.0) or 50.0)
        spend_ratio = (total_cost / budget) if budget > 0 else 0.0
        return {
            "calls": len(rows),
            "totalTokens": total_tokens,
            "estimatedCostUsd": round(total_cost, 6),
            "avgCostPerQueryUsd": round(avg_cost, 6),
            "budgetUsd": budget,
            "budgetUsedPct": round(min(spend_ratio * 100, 999), 1),
            "budgetWarning": spend_ratio >= 0.8,
            "byModel": [
                {
                    "model": model,
                    "calls": int(stats["calls"]),
                    "tokens": int(stats["tokens"]),
                    "costUsd": round(float(stats["costUsd"]), 6),
                }
                for model, stats in sorted(
                    by_model.items(), key=lambda item: float(item[1]["costUsd"]), reverse=True
                )
            ],
            "byDomain": [
                {
                    "domain": domain,
                    "calls": int(stats["calls"]),
                    "tokens": int(stats["tokens"]),
                    "costUsd": round(float(stats["costUsd"]), 6),
                }
                for domain, stats in sorted(
                    by_domain.items(), key=lambda item: float(item[1]["costUsd"]), reverse=True
                )
            ],
            "spendOverTime": [
                {"date": day, "costUsd": round(cost, 6)}
                for day, cost in sorted(daily.items())
            ],
            "recent": [
                {
                    "id": str(row.id),
                    "model": row.model_name,
                    "purpose": row.purpose,
                    "executionMode": row.execution_mode,
                    "totalTokens": row.total_tokens,
                    "estimatedCostUsd": float(row.estimated_cost_usd),
                    "createdAt": row.created_at.isoformat(),
                    "industry": row.industry,
                }
                for row in rows[:20]
            ],
        }

    async def _ensure_conversation(
        self, conversation_id: uuid.UUID | None, question: str
    ) -> Conversation:
        if conversation_id is not None:
            existing = await self._app.get(Conversation, conversation_id)
            if existing and existing.user_id == self._user.id:
                existing.updated_at = datetime.now(UTC)
                return existing
        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=self._user.id,
            industry=self._industry.value,
            title=question[:80],
        )
        self._app.add(conversation)
        await self._app.flush()
        return conversation

    async def _create_running_history(
        self, history_id: uuid.UUID, conversation_id: uuid.UUID, question: str
    ) -> QueryHistory:
        row = QueryHistory(
            id=history_id,
            user_id=self._user.id,
            conversation_id=conversation_id,
            industry=self._industry.value,
            question=question,
            sql_text=None,
            status="running",
            row_count=None,
            trust_score=None,
            trust_breakdown=None,
            latency_ms=None,
        )
        self._app.add(row)
        return row

    async def _record_usage(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Accumulate LLM tokens; the chat route stores one ``llm_usage`` row per question."""
        self.usage_model = model or self.usage_model
        self.usage_prompt_tokens += max(0, prompt_tokens)
        self.usage_completion_tokens += max(0, completion_tokens)
        self.usage_llm_steps += 1

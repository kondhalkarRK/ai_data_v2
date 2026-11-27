"""Chat orchestration with SSE events."""

from __future__ import annotations

import json
import logging
import re
import secrets
import time
import uuid
from asyncio import CancelledError, Event
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.analytics.sql_guardrails import sql_is_safe
from app.core.config import Industry, Settings
from app.core.exceptions import ValidationError
from app.models.activity import Conversation, LlmUsage, QueryHistory, SavedQuestion
from app.models.enums import Role
from app.models.user import User
from app.rag.feature import rag_enabled
from app.rag.generation import grounded_document_reply
from app.semantic.service import SemanticService
from app.services.catalog import EntityCatalogService
from app.services.chat.clarification import (
    Clarification,
    interpretation,
    plan_suggestions,
    recovery_for_failure,
    resolution_notes,
)
from app.services.chat.conversation_context import plan_state
from app.services.chat.conversation_memory import (
    DocumentContext,
    ResultMeta,
    SessionMemory,
    append_general_chat,
    append_recent_turn,
    assert_memory_scope,
    build_analytical_context,
    clear_pending,
    empty_memory,
    is_refresh_request,
    resolve_incoming_message,
    revalidate_plan_for_scope,
    session_memory_storage_error,
    set_pending_clarification,
)
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
from app.services.chat.follow_up_guard import data_vocabulary_hit, follow_up_guard_allows_sql
from app.services.chat.intents import (
    is_surprise_me,
    is_whatif,
    parse_whatif,
    suggested_followups,
)
from app.services.chat.llm_assist import (
    classify_and_resolve,
    generate_validated_sql,
    interpret_question,
    interpretation_vocabulary,
)
from app.services.chat.message_classifier import (
    rule_route_interrupts_analytical_context,
    template_out_of_scope_live,
    template_scope_declined,
    template_unsupported,
)
from app.services.chat.narration import describe_result
from app.services.chat.non_data_handlers import (
    LlmReply,
    app_help_reply,
    definition_from_metadata,
    general_chat_reply,
    general_knowledge_reply,
    no_documents_reply,
)
from app.services.chat.pipeline import TurnPlan, plan_turn
from app.services.chat.pre_plan import early_route, plan_with_rewrites, run_pre_plan
from app.services.chat.profiler import PROFILER, QueryProfile
from app.services.chat.query_cache import QUERY_CACHE, CachedAnswer
from app.services.chat.query_router import (
    RouteDecision as EvidenceRouteDecision,
)
from app.services.chat.query_router import (
    explicit_document_question,
    knowledge_narrative,
    plan_entities,
    route_question,
)
from app.services.chat.question_understanding import QuestionPlan
from app.services.chat.request_context import ContextBudgetError
from app.services.chat.request_evidence import render as render_typed_evidence
from app.services.chat.request_runtime import prepare_typed_request
from app.services.chat.request_state import save_request
from app.services.chat.response_contract import response_kind
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
from app.services.governance.llm_config import active_llm
from app.services.knowledge import KnowledgeService
from app.services.llm import llm_configured
from app.services.security.region_scope import (
    RegionScope,
    deny_if_out_of_scope,
    for_current_scope,
    forbidden_zones,
    load_region_scope,
)
from app.services.web_retrieval import WebRetrievalService

logger = logging.getLogger(__name__)


def _worth_reinterpreting(turn: TurnPlan) -> bool:
    """The AI may restate names/phrasing we could not read; curated clarifications stay."""
    if turn.clarify_reason in {"needs_clarification", "unresolved"}:
        return True
    return turn.clarification is None and not turn.governed_sql


def _force_clarification(turn: TurnPlan, message: str) -> TurnPlan:
    """Ask instead of guessing; keeps any options the planner already offered."""
    options = list(turn.clarification.options) if turn.clarification else []
    return replace(
        turn,
        clarification=Clarification(
            kind="clarify", title="Need detail", message=message, options=options
        ),
        clarify_reason=turn.clarify_reason or "needs_clarification",
        governed_sql=None,
    )


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
        payload["message"] = f"This query is taking longer than expected. Current stage: {label}"
    return _sse("progress", payload)


class ChatService:
    def __init__(
        self,
        *,
        app_session: AsyncSession,
        analytics: AsyncConnection | None,
        settings: Settings,
        user: User,
        industry: Industry,
        semantic_service: SemanticService | None = None,
        region_scope: RegionScope | None = None,
    ) -> None:
        self._app = app_session
        self._analytics = analytics
        self._settings = settings
        self._user = user
        self._industry = industry
        self._semantic = semantic_service or SemanticService(settings)
        self._region_scope = region_scope or RegionScope.all_regions(user)
        self.usage_model = ""
        self.usage_llm_provider = ""
        self.usage_prompt_tokens = 0
        self.usage_completion_tokens = 0
        self.usage_llm_steps = 0
        self._schema_used = False
        self.last_profile: QueryProfile | None = None
        self.last_history: QueryHistory | None = None
        self.session_memory_persisted: bool = True

    def _cache_scope(self) -> str:
        governed = active_llm(self._settings)
        return f"rag-mode-v1|user:{self._user.id}|{self._region_scope.cache_key()}|llm:{governed.provider}:{governed.model}"

    def _llm_runtime_meta(self) -> dict[str, Any]:
        governed = active_llm(self._settings)
        return {
            "invoked": self.usage_llm_steps > 0,
            "provider": self.usage_llm_provider or governed.provider,
            "model": self.usage_model or governed.model,
            "configuredProvider": governed.provider,
            "configuredModel": governed.model,
        }

    def _result_profile(
        self, columns: list[str], rows: list[dict[str, Any]], plan: Any
    ) -> dict[str, Any] | None:
        """Presentation hints from the executed result; never blocks or alters the answer."""
        try:
            return describe_result(
                columns,
                rows,
                intent=getattr(plan, "intent", None),
                analysis=getattr(plan, "analysis", None),
                row_limit=self._settings.nlq_default_result_limit,
            )
        except Exception:
            logger.debug("result profile unavailable", exc_info=True)
            return None

    async def _general_knowledge_reply(self, question: str) -> LlmReply:
        """Open-domain questions are out of scope unless explicitly enabled; no LLM, no SQL."""
        if self._settings.chat_general_knowledge_enabled:
            return await general_knowledge_reply(
                self._settings, industry=self._industry, question=question
            )
        return LlmReply(template_scope_declined(self._industry))

    async def _recover_analytics(self) -> None:
        """Clear an aborted Postgres transaction so later statements can run.

        Read-only analytics work shares one connection for the request. A failed
        EXPLAIN/probe leaves the transaction in ``InFailedSqlTransaction`` until
        rollback â€” without this, valid SQL looks broken.
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
        use_documents: bool = False,
        model_override: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
    ) -> AsyncIterator[str]:
        started = time.perf_counter()
        wall_started = time.time()
        timings = QueryTimings()
        question = (question or "").strip()
        typed_mode = (
            self._industry == Industry.AUTOMOTIVE and self._settings.chat_typed_execution_enabled
        )
        typed = None
        planning_ms = 0
        narration_ms = 0
        analytical_queries = 0
        warehouse_queries = None
        report_partial = False
        dependent_result = None
        dependent_view = None
        if not question:
            raise ValidationError("Question is required.")
        self._region_scope = await load_region_scope(self._app, self._user)
        if typed_mode and self._analytics is not None:
            self._analytics = for_current_scope(self._analytics, self._industry, self._region_scope)
        self.usage_model = ""
        self.usage_llm_provider = ""
        self.usage_prompt_tokens = 0
        self.usage_completion_tokens = 0
        self.usage_llm_steps = 0
        self._schema_used = False

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
        session_memory = await self._load_session_memory(conversation.id)
        # Legacy summaries have no evidence/ACL provenance. Never reuse them.
        if session_memory.document is not None or use_documents:
            session_memory.recent_turns = ()
            session_memory.general_chat_turns = ()
        session_memory.document = None
        documents_allowed = use_documents and rag_enabled(self._settings) and not typed_mode
        raw_question = question
        if not typed_mode:
            question, _completed_pending = resolve_incoming_message(session_memory, question)
        bypass_query_cache = (
            typed_mode
            or is_refresh_request(raw_question)
            or is_refresh_request(question)
            or documents_allowed
        )
        append_recent_turn(session_memory, role="user", text=question, settings=self._settings)
        history = await self._create_running_history(history_id, conversation.id, question)
        self.last_history = history
        await self._app.flush()
        await self._app.commit()

        blocked = forbidden_zones(question, self._region_scope)
        if blocked:
            attempted = " and ".join(blocked)
            try:
                await deny_if_out_of_scope(
                    self._app,
                    self._region_scope,
                    attempted=attempted,
                    action="AI Chat",
                )
            except Exception as exc:
                narrative = getattr(exc, "message", None) or str(exc)
                history.status = "completed"
                history.error_message = narrative[:500]
                await self._app.flush()
                await self._app.commit()
                yield _sse(
                    "clarification",
                    {
                        "kind": "denied",
                        "title": "Access denied",
                        "message": narrative,
                        "historyId": str(history_id),
                    },
                )
                insights = build_insights(narrative=narrative, columns=[], rows=[], path="denied")
                yield _sse(
                    "meta",
                    {"insights": insights, "responseKind": "denied", "runId": str(history_id)},
                )
                yield _sse("done", {"ok": False, "code": "region_forbidden"})
                return

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

        def run_usage(fallback=None):
            return {
                "initialModelCalls": self.usage_llm_steps
                - (typed.preview.usage.verification_calls if typed else 0),
                "verificationModelCalls": typed.preview.usage.verification_calls if typed else 0,
                "correctionModelCalls": 0,
                "inputTokens": self.usage_prompt_tokens,
                "outputTokens": self.usage_completion_tokens,
                "tokensEstimated": bool(profile.tokens_estimated),
                **({
                    "modelsUsed": [c.model for c in typed.preview.usage.call_records],
                    "modelUsageComplete": len(typed.preview.usage.call_records) == self.usage_llm_steps
                        and all(c.completed and c.model for c in typed.preview.usage.call_records),
                    "initialInputTokens": sum(c.input_tokens for c in typed.preview.usage.call_records if c.kind == "interpretation"),
                    "initialOutputTokens": sum(c.output_tokens for c in typed.preview.usage.call_records if c.kind == "interpretation"),
                    "verificationInputTokens": sum(c.input_tokens for c in typed.preview.usage.call_records if c.kind == "inventory"),
                    "verificationOutputTokens": sum(c.output_tokens for c in typed.preview.usage.call_records if c.kind == "inventory"),
                } if typed else {}),
                "interpretationMs": typed.preview.usage.elapsed_ms if typed else 0,
                "planningMs": planning_ms,
                "executionMs": timings.execution_ms,
                "narrationMs": narration_ms,
                "analyticalQueries": analytical_queries,
                "cacheHit": False,
                "fallbackReason": fallback,
                "warehouseQueries": warehouse_queries,
            }

        def dependent_audit(status):
            if not typed or not typed.preview.request or not typed.preview.request.analysis_tasks:
                return None
            from app.services.chat.analytical_plan_audit import build_audit

            return build_audit(run_id=history_id, typed=typed, result=dependent_result,
                status=status, usage=run_usage())

        def retain_dependent_audit(status):
            audit = dependent_audit(status)
            if audit:
                history.trust_breakdown = {**(history.trust_breakdown or {}), "analyticalAudit": audit}
            return audit

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
            if dependent_result:
                insights = {"executive": narrative, "analyst": narrative}
            audit = dependent_audit(dependent_result.status if dependent_result else typed.preview.status if typed else path)
            yield _sse(
                "meta",
                {
                    "executionMode": "typed" if typed_mode else "legacy",
                    **(
                        {
                            "analyticalExecution": dependent_result.model_dump(mode="json"),
                            "analyticalPlan": typed.analysis_plan.model_dump(mode="json"),
                            "analyticalPresentation": dependent_view,
                        }
                        if dependent_result
                        else {}
                    ),
                    "responseKind": response_kind(
                        path,
                        failed=history_status == "failed",
                        partial=report_partial,
                        sql=bool(dependent_result and dependent_result.sql),
                        rows=sum(len(s.rows) for s in dependent_result.steps)
                        if dependent_result
                        else 0,
                    ),
                    "runId": str(history_id),
                    **({"analyticalAudit": audit} if audit else {}),
                    "runUsage": run_usage(
                        path
                        if "unavailable" in path
                        or "unsupported" in path
                        or history_status == "failed"
                        else None
                    )
                    if typed_mode
                    else None,
                    "typedRequest": typed.preview.request.model_dump(mode="json")
                    if typed and typed.preview.request
                    else None,
                    "limitations": [typed.preview.reason]
                    if typed and typed.preview.status != "ready"
                    else [],
                    "groundedOn": resolve_grounded_on(
                        path=path,
                        glossary_matches=len(typed.preview.request.measures)
                        if dependent_result and typed and typed.preview.request
                        else 0,
                        has_sql=bool(dependent_result and dependent_result.sql),
                        dq_checked=False,
                        llm_invoked=self.usage_llm_steps > 0,
                        schema_used=self._schema_used,
                    ),
                    "ambiguityFlag": ambiguity,
                    "validationStatus": "passed"
                    if dependent_result and dependent_result.sql
                    else "skipped",
                    "rowCount": sum(len(s.rows) for s in dependent_result.steps)
                    if dependent_result
                    else 0,
                    "executionTimeMs": timings.execution_ms if dependent_result else 0,
                    "sourceDatabase": source_database_label(self._industry),
                    "dataAsOf": None,
                    "timings": timings.to_dict(),
                    "queryMeta": extract_query_meta(dependent_result.sql if dependent_result else None).to_dict(),
                    "insights": insights,
                    "anomalies": [],
                    "alternateInterpretations": alternates or [],
                    "cacheHit": False,
                    "llmRuntime": self._llm_runtime_meta(),
                },
            )
            for token in re.findall(r"\S+\s*", narrative):
                yield _sse("token", {"token": token})
            history.status = history_status
            history.row_count = (
                sum(len(s.rows) for s in dependent_result.steps) if dependent_result else 0
            )
            if dependent_result:
                history.sql_text = dependent_result.sql
            history.trust_score = 0
            history.trust_breakdown = {
                "path": path,
                "ambiguityFlag": ambiguity,
                **(extra_breakdown or {}),
                **({"analyticalAudit": audit} if audit else {}),
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

        async def record_reply(reply: LlmReply) -> None:
            if not reply.used_llm:
                return
            profile.llm_calls += 1
            profile.prompt_tokens += reply.prompt_tokens
            profile.completion_tokens += reply.completion_tokens
            profile.llm_model = reply.model
            profile.tokens_estimated = profile.tokens_estimated or reply.tokens_estimated
            profile.llm_latency_ms += reply.latency_ms
            timings.llm_generation_ms += reply.latency_ms
            await self._record_usage(reply.model, reply.prompt_tokens, reply.completion_tokens)

        def log_route(route: str, source: str) -> None:
            profile.route, profile.route_source = route, source
            logger.info(
                "chat_route route=%s source=%s llm_calls=%d prompt_tokens=%d "
                "completion_tokens=%d tokens_estimated=%s llm_latency_ms=%d",
                route,
                source,
                profile.llm_calls,
                profile.prompt_tokens,
                profile.completion_tokens,
                profile.tokens_estimated,
                profile.llm_latency_ms,
            )

        async def answer_from_documents(reason: str) -> AsyncIterator[str]:
            if not documents_allowed:
                async for frame in finish_without_sql(
                    path="documents_disabled",
                    narrative="Knowledge documents are off or unavailable. Enable Use knowledge documents when the server supports it to answer from uploaded sources.",
                ):
                    yield frame
                return
            knowledge = KnowledgeService(
                self._settings,
                self._industry,
                session=self._app if rag_enabled(self._settings) else None,
            )
            if rag_enabled(self._settings):
                documents = await knowledge.list_documents_authorized(
                    user=self._user, region_scope=self._region_scope
                )
            else:
                documents = knowledge.list_documents()
            if not documents:
                async for frame in finish_without_sql(
                    path="knowledge", narrative=no_documents_reply()
                ):
                    yield frame
                return
            completed_steps.extend(
                step for step in ("rewrite", "intent", "ambiguity") if step not in completed_steps
            )
            yield _progress("narration", completed_steps, slow=maybe_slow())
            try:
                citations = await knowledge.search_authorized(
                    question,
                    user=self._user,
                    region_scope=self._region_scope,
                    top_k=min(5, self._settings.rag_top_k),
                )
            except Exception:
                logger.debug("Knowledge search failed", exc_info=True)
                async for frame in finish_without_sql(
                    path="documents_unavailable",
                    narrative="Document search is unavailable. Please retry; this is not a no-matches result.",
                ):
                    yield frame
                return
            for citation in citations:
                yield _sse("citation", _citation_payload(citation))
            doc_followup = ""
            if rag_enabled(self._settings):
                reply = await grounded_document_reply(
                    self._settings,
                    question=question,
                    passages=citations,
                    conversation_context=doc_followup or None,
                )
                narrative = reply.text
                if reply.used_llm:
                    await record_reply(reply)
            else:
                narrative = knowledge_narrative(citations)
            session_memory.document = DocumentContext(
                question=question,
                summary=narrative[:500],
                citation_titles=tuple(
                    dict.fromkeys(str(c.title) for c in citations if getattr(c, "title", None))
                ),
                updated_at=datetime.now(UTC),
            )
            await self._save_session_memory(conversation, session_memory)
            insights = build_insights(narrative=narrative, columns=[], rows=[], path="knowledge")
            followups: list[str] = []
            for doc in documents:
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
                    "groundedOn": ["documents"] if citations else [],
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
                    "routeReason": reason,
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

        if typed_mode:
            try:
                semantic_pack = await self._semantic.get_pack(self._industry)
                preparation_started = time.perf_counter()
                typed = await prepare_typed_request(
                    settings=self._settings,
                    user=self._user,
                    scope=self._region_scope,
                    pack=semantic_pack,
                    analytics=self._analytics,
                    question=question,
                    memory=session_memory,
                    cancel_requested=lambda: bool(
                        (cancel_event is not None and cancel_event.is_set())
                        or (cancel_requested is not None and history_id in cancel_requested)
                    ),
                )
            except (ContextBudgetError, ValueError) as exc:
                async for frame in finish_without_sql(path="typed_unavailable", narrative=str(exc)):
                    yield frame
                return
            except Exception:
                logger.warning("Typed request preparation unavailable")
                async for frame in finish_without_sql(
                    path="typed_unavailable",
                    narrative="Approved analytical context is unavailable. Please retry.",
                ):
                    yield frame
                return
            planning_ms = max(
                0,
                int((time.perf_counter() - preparation_started) * 1000)
                - typed.preview.usage.elapsed_ms,
            )
            usage = typed.preview.usage
            if usage.calls:
                await record_reply(
                    LlmReply(
                        text="",
                        model=usage.model,
                        used_llm=True,
                        prompt_tokens=usage.input_tokens,
                        completion_tokens=usage.output_tokens,
                        tokens_estimated=usage.tokens_estimated,
                        latency_ms=usage.elapsed_ms,
                    )
                )
                self.usage_llm_steps += max(0, usage.calls - 1)
                profile.llm_calls += max(0, usage.calls - 1)
            request = typed.preview.request
            if await cancelled():
                retain_dependent_audit("cancelled")
                yield _sse(
                    "cancelled",
                    {
                        "historyId": str(history_id),
                        "responseKind": "cancelled",
                        "runUsage": run_usage(),
                    },
                )
                return
            yield _sse(
                "stage",
                {
                    "stage": "typed_interpretation",
                    "route": request.outcome if request else typed.preview.status,
                    "requestId": typed.preview.request_id,
                },
            )
            if typed.analysis_plan is not None:
                from app.services.chat.analytical_plan_execution import (
                    AnalyticalExecution,
                    execute_analysis,
                )
                from app.services.chat.analytical_plan_presentation import (
                    narrative as analysis_narrative,
                )
                from app.services.chat.analytical_plan_presentation import (
                    presentation,
                    progress_payload,
                )
                from app.services.chat.request_context import pack_fingerprint
                from app.services.chat.request_dates import (
                    RequestClarificationError,
                    business_today,
                )

                async def authorized_analysis():
                    current_user = await self._app.get(User, self._user.id, populate_existing=True)
                    if current_user is None or not current_user.is_active:
                        return False
                    current_scope = await load_region_scope(self._app, current_user)
                    current_pack = await self._semantic.get_pack(self._industry)
                    return (
                        current_scope.cache_key() == self._region_scope.cache_key()
                        and pack_fingerprint(current_pack) == typed.context.semantic_version
                    )

                async def analysis_cancelled():
                    return bool(
                        (cancel_event is not None and cancel_event.is_set())
                        or (cancel_requested is not None and history_id in cancel_requested)
                    )

                if self._analytics is None:
                    async for frame in finish_without_sql(
                        path="typed_unavailable", narrative="The analytics database is unavailable."
                    ):
                        yield frame
                    return
                execution_start = time.perf_counter()
                yield _sse("analysis_progress", progress_payload(typed.analysis_plan, semantic_pack))
                try:
                    dependent_result = await execute_analysis(
                        typed.analysis_plan,
                        typed.analysis_review,
                        connection=self._analytics,
                        settings=self._settings,
                        today=typed.analysis_date or business_today(semantic_pack.model.query_policy),
                        authorize=authorized_analysis,
                        cancelled=analysis_cancelled,
                    )
                except CancelledError:
                    history.status = "cancelled"
                    retain_dependent_audit("cancelled")
                    raise
                except RequestClarificationError as exc:
                    typed.preview.status = "clarification"
                    typed.preview.request = request.model_copy(update={"clarification": str(exc)})
                    session_memory.typed_request = save_request(
                        session_memory.typed_request,
                        typed.preview.request,
                        typed.context,
                        typed.preview.request_id,
                        pending=True,
                    )
                    await self._save_session_memory(conversation, session_memory)
                    async for frame in finish_without_sql(path="clarification", narrative=str(exc)):
                        yield frame
                    return
                except (ValueError, KeyError):
                    async for frame in finish_without_sql(
                        path="typed_unsupported",
                        narrative="The dependent plan could not be compiled completely. No query ran.",
                    ):
                        yield frame
                    return
                timings.execution_ms = int((time.perf_counter() - execution_start) * 1000)
                analytical_queries = dependent_result.analytical_queries
                self._schema_used = dependent_result.analytical_queries > 0
                if (
                    dependent_result.status in {"completed", "partial"}
                    and "documents_gated" in typed.preview.routes
                ):
                    dependent_result.status = "partial"
                    dependent_result.message = "The database part is shown below. Document evidence is unavailable; policy compliance is unverified."
                if (
                    dependent_result.status in {"completed", "partial"}
                    and "report" in request.additional_outcomes
                ):
                    dependent_result.status = "partial"
                    dependent_result.message += " The database part is shown; report creation was not performed for this compound request."
                if dependent_result.status == "completed" and typed.preview.status == "partial":
                    dependent_result.status = "partial"
                    dependent_result.message += " " + typed.preview.reason
                if dependent_result.status == "cancelled":
                    await cancelled()
                    retain_dependent_audit("cancelled")
                    yield _sse(
                        "cancelled",
                        {
                            "historyId": str(history_id),
                            "responseKind": "cancelled",
                            "runUsage": run_usage(),
                        },
                    )
                    return
                for checked_index, _step in enumerate(dependent_result.steps, start=1):
                    if await analysis_cancelled():
                        await cancelled()
                        retain_dependent_audit("cancelled")
                        yield _sse("cancelled", {"historyId": str(history_id), "responseKind": "cancelled", "runUsage": run_usage()})
                        return
                    yield _sse("analysis_progress", progress_payload(typed.analysis_plan, semantic_pack,
                        completed=checked_index, result=dependent_result))
                if dependent_result.steps and not await authorized_analysis():
                    dependent_result = AnalyticalExecution(status="denied",
                        analytical_queries=analytical_queries,
                        message="Your access changed before publication. Results were discarded.")
                if dependent_result.sql:
                    yield _sse(
                        "sql",
                        {
                            "sql": dependent_result.sql,
                            "path": "dependent_analysis",
                            "validationStatus": "passed",
                        },
                    )
                # Verified step results, display snapshot and audit are shared by both layouts.
                report_partial = dependent_result.status == "partial"
                path = {
                    "denied": "denied",
                    "clarification": "clarification",
                    "failed": "typed_error",
                    "disabled": "typed_disabled",
                }.get(dependent_result.status, "dependent_analysis")
                local_narration_started = time.perf_counter()
                dependent_view = presentation(typed.analysis_plan, dependent_result, semantic_pack,
                    today=typed.analysis_date or business_today(semantic_pack.model.query_policy), context=typed.context)
                if dependent_result.status in {"completed", "partial"} and request.definition_terms:
                    dependent_view["notes"].extend(
                        "Approved glossary: " + definition_from_metadata(t, semantic_pack, self._industry)
                        for t in request.definition_terms
                    )
                summary = analysis_narrative(dependent_view)
                narration_ms = int((time.perf_counter() - local_narration_started) * 1000)
                if dependent_result.status in {"completed", "partial"} and dependent_result.sql:
                    session_memory.typed_request = save_request(
                        session_memory.typed_request,
                        request,
                        typed.context,
                        typed.preview.request_id,
                        pending=False,
                        sql=dependent_result.sql,
                    )
                    session_memory.typed_request["confirmed"]["evidence_summary"] = summary
                    await self._save_session_memory(conversation, session_memory)
                async for frame in finish_without_sql(
                    path=path,
                    narrative=summary,
                    history_status="failed" if dependent_result.status == "failed" else "completed",
                ):
                    yield frame
                return
            if typed.turn is None:
                narrative = typed.preview.reason
                path = (
                    "clarification"
                    if typed.preview.status == "clarification"
                    else "typed_" + typed.preview.status
                )
                if request and request.clarification:
                    narrative = request.clarification
                    session_memory.typed_request = save_request(
                        session_memory.typed_request,
                        request,
                        typed.context,
                        str(history_id),
                        pending=True,
                    )
                elif request and request.outcome == "definition":
                    narrative = "\n\n".join(
                        definition_from_metadata(t, semantic_pack, self._industry)
                        for t in request.definition_terms
                    )
                    narrative += (
                        "\nSource: approved Automotive semantic model and business glossary."
                    )
                    path = "definition"
                elif request and request.reply and typed.preview.status == "ready":
                    narrative, path = request.reply, request.outcome
                elif request and request.outcome == "previous_sql":
                    previous = (
                        ((session_memory.typed_request or {}).get("confirmed") or {})
                        if typed.context.payload.get("previous")
                        else {}
                    )
                    if previous.get("sql"):
                        yield _sse("sql", {"sql": previous["sql"], "path": "previous_sql"})
                        narrative = "SQL from the previous authorized answer. No new analytical query was run."
                        path = "previous_sql"
                    else:
                        narrative = "There is no authorized previous SQL to display."
                        path = "typed_unavailable"
                elif request and request.outcome == "data_quality":
                    narrative = "Data completeness has not been verified for this request. Open Data Trust to review its checks; observed date coverage alone does not prove completeness."
                    path = "typed_unavailable"
                elif request and request.outcome == "implications":
                    evidence = (
                        ((session_memory.typed_request or {}).get("confirmed") or {}).get(
                            "evidence_summary"
                        )
                        if typed.context.payload.get("previous")
                        else None
                    )
                    narrative = (
                        (
                            "Observations: "
                            + evidence
                            + " Implications: assess whether the verified movement is material against your approved business goals. Suggested actions: review the contributing groups and data completeness before acting. These are suggestions, not operational changes."
                        )
                        if evidence
                        else "Which verified analysis should I interpret? Ask a data question first."
                    )
                elif (
                    request
                    and request.outcome == "report"
                    and typed.preview.status in {"ready", "partial"}
                ):
                    from app.services.chat.request_report import handoff_report

                    try:

                        def report_usage(analytical, warehouse):
                            nonlocal analytical_queries, warehouse_queries
                            analytical_queries, warehouse_queries = analytical, warehouse

                        report_started = time.perf_counter()
                        report = await handoff_report(
                            self,
                            typed,
                            session_memory,
                            cancel_check=cancelled,
                            usage_callback=report_usage,
                        )
                        timings.execution_ms = int((time.perf_counter() - report_started) * 1000)
                        report_partial = report["partial"]
                        analytical_queries = report.get("analyticalQueries", 0)
                        warehouse_queries = report.get("queryCount", 0)
                        path = "report"
                        yield _sse("report", report)
                        report["briefing"] += f" [Open in Analytics Builder]({report['url']})."
                        narrative = report["briefing"] + (
                            " Document evidence is unavailable; policy compliance is unverified."
                            if "documents_gated" in typed.preview.routes
                            else ""
                        )
                    except CancelledError:
                        yield _sse(
                            "cancelled",
                            {
                                "historyId": str(history_id),
                                "responseKind": "cancelled",
                                "runUsage": run_usage() if typed_mode else None,
                            },
                        )
                        return
                    except Exception as exc:
                        logger.warning("Typed report handoff failed")
                        path = "typed_unavailable"
                        narrative = (
                            getattr(exc, "message", None)
                            or "Report preparation could not complete. Reopen Builder to inspect the latest revision."
                        )
                elif (
                    request
                    and request.outcome
                    in {
                        "investigation",
                        "implications",
                        "report",
                        "data_quality",
                        "previous_sql",
                    }
                    and typed.preview.status == "ready"
                ):
                    narrative = "This workflow is not enabled in typed Chat yet. Ask a direct data question, or use the existing application module."
                if (
                    request
                    and not request.followup
                    and not request.clarification
                    and session_memory.typed_request
                ):
                    session_memory.typed_request["pending"] = None
                clear_pending(session_memory)
                await self._save_session_memory(conversation, session_memory)
                log_route(request.outcome if request else typed.preview.status, "typed_interpreter")
                async for frame in finish_without_sql(
                    path=path,
                    narrative=narrative,
                    event="clarification" if path == "clarification" else None,
                    payload={
                        "kind": "clarify",
                        "title": "Need detail",
                        "message": narrative,
                        "options": [],
                    }
                    if path == "clarification"
                    else None,
                    ambiguity=path == "clarification",
                ):
                    yield frame
                return
            if self._analytics is None:
                async for frame in finish_without_sql(
                    path="typed_unavailable", narrative="The analytics database is unavailable."
                ):
                    yield frame
                return
            turn = typed.turn
            reinterpreted = follow_up_interpretation = None
            prior_sql, prior_state, surprise_sql = typed.prior_sql, None, None
            allowed_schema = build_allowed_schema(semantic_pack)
            llm_ready = False  # Never ask the model to rewrite compiled typed SQL.
            profile.route_source = "typed_interpreter"
            clear_pending(session_memory)
        else:
            if explicit_document_question(question):
                if re.search(r"\b(?:and|also)\b", question, re.IGNORECASE) and re.search(
                    r"\b(?:sales|revenue|units|claims|premium)\b", question, re.IGNORECASE
                ):
                    async for frame in finish_without_sql(
                        path="clarification",
                        narrative="Please ask the measured business result and the document procedure separately so each answer has the correct evidence.",
                    ):
                        yield frame
                else:
                    async for frame in answer_from_documents("explicit document request"):
                        yield frame
                return

            early = early_route(
                industry=self._industry,
                message=question,
                scope=self._region_scope,
                router_enabled=self._settings.chat_router_enabled,
            )
            if early is not None:
                stop = early.stop
                log_route(stop or "unknown", "rules")
                if stop == "general_chat":
                    reply = await general_chat_reply(
                        self._settings,
                        industry=self._industry,
                        question=question,
                        reason=early.stop_detail,
                        last_turn_failed=await self._last_turn_failed(conversation.id, history_id),
                    )
                    await record_reply(reply)
                    append_general_chat(
                        session_memory, role="assistant", text=reply.text, settings=self._settings
                    )
                    await self._save_session_memory(conversation, session_memory)
                    async for frame in finish_without_sql(
                        path="general_chat", narrative=reply.text
                    ):
                        yield frame
                    return
                if stop == "unsupported":
                    async for frame in finish_without_sql(
                        path="unsupported", narrative=template_unsupported()
                    ):
                        yield frame
                    return
                if stop == "out_of_scope_live":
                    async for frame in finish_without_sql(
                        path="out_of_scope_live", narrative=template_out_of_scope_live()
                    ):
                        yield frame
                    return
                if stop == "general_knowledge":
                    reply = await self._general_knowledge_reply(question)
                    await record_reply(reply)
                    async for frame in finish_without_sql(
                        path="general_knowledge", narrative=reply.text
                    ):
                        yield frame
                    return
                if stop == "document_query":
                    async for frame in answer_from_documents("document cue"):
                        yield frame
                    return
                if stop == "app_help":
                    try:
                        help_pack = await self._semantic.get_pack(self._industry)
                    except Exception:
                        logger.warning("Semantic pack unavailable for app help", exc_info=True)
                        help_pack = None
                    narrative = app_help_reply(
                        question,
                        industry=self._industry,
                        pack=help_pack,
                        allowed_schema=build_allowed_schema(help_pack),
                        scope=self._region_scope,
                    )
                    async for frame in finish_without_sql(path="app_help", narrative=narrative):
                        yield frame
                    return
                if stop == "legacy_out_of_bounds":
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
            if allowed_schema:
                self._schema_used = True
            resolver = resolver_for(value_dictionary, semantic_pack)
            llm_ready = llm_configured(self._settings)

            hist_prior = (
                await self._prior_state(conversation.id, history_id)
                if not session_memory.analytical
                else None
            )

            def _follow_up_guard(**kwargs: Any) -> tuple[bool, str | None]:
                if not self._settings.chat_follow_up_guard_enabled:
                    return True, None
                return follow_up_guard_allows_sql(
                    question=kwargs["question"],
                    session_memory=kwargs["session_memory"],
                    settings=self._settings,
                    prior_state=kwargs["prior_state"],
                    snapshot=value_dictionary,
                    pack=semantic_pack,
                    industry=self._industry,
                )

            pre = run_pre_plan(
                industry=self._industry,
                message=question,
                settings=self._settings,
                scope=self._region_scope,
                session_memory=session_memory,
                prior_state=hist_prior,
                router_enabled=self._settings.chat_router_enabled,
                data_vocabulary=lambda text: data_vocabulary_hit(
                    text, value_dictionary, semantic_pack
                ),
                follow_up_guard_check=_follow_up_guard,
                skip_early=True,
            )
            if pre.stop == "general_knowledge":
                log_route("general_knowledge", "rules")
                reply = await self._general_knowledge_reply(question)
                await record_reply(reply)
                async for frame in finish_without_sql(
                    path="general_knowledge", narrative=reply.text
                ):
                    yield frame
                return
            if not pre.proceed:
                if pre.stop == "memory_expired":
                    msg = (
                        "That follow-up refers to an earlier question, but that context "
                        "has expired. Please ask your full question again."
                    )
                    await self._save_session_memory(conversation, session_memory)
                    async for frame in finish_without_sql(
                        path="clarification",
                        narrative=msg,
                        event="clarification",
                        payload={
                            "kind": "clarify",
                            "title": "Context expired",
                            "message": msg,
                            "historyId": str(history_id),
                        },
                        ambiguity=True,
                    ):
                        yield frame
                    return
                if pre.stop == "scope_denied":
                    try:
                        await deny_if_out_of_scope(
                            self._app,
                            self._region_scope,
                            attempted=pre.stop_detail or "region scope",
                            action="AI Chat follow-up",
                        )
                    except Exception as exc:
                        narrative = getattr(exc, "message", None) or str(exc)
                        await self._save_session_memory(conversation, session_memory)
                        async for frame in finish_without_sql(
                            path="denied",
                            narrative=narrative,
                            event="clarification",
                            payload={
                                "kind": "denied",
                                "title": "Access denied",
                                "message": narrative,
                                "historyId": str(history_id),
                            },
                        ):
                            yield frame
                        return
            if pre.follow_up_guard_blocked:
                log_route("clarification", "follow_up_guard")
                msg = (
                    "I'm not sure how that follow-up relates to your data question. "
                    "Try naming a metric, region, or time period from your dataset."
                )
                async for frame in finish_without_sql(
                    path="clarification",
                    narrative=msg,
                    event="clarification",
                    payload={
                        "kind": "clarify",
                        "title": "Need detail",
                        "message": msg,
                        "historyId": str(history_id),
                    },
                    ambiguity=True,
                ):
                    yield frame
                return

            prior_sql: str | None = None
            prior_state = pre.prior_state
            question = pre.question
            follow_up_interpretation = pre.interpretation if prior_state else None
            if follow_up_interpretation:
                yield _sse(
                    "stage", {"stage": "interpretation", "message": follow_up_interpretation}
                )

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
            planned = plan_with_rewrites(
                lambda text: plan_turn(
                    self._industry,
                    text,
                    snapshot=value_dictionary,
                    pack=semantic_pack,
                    allowed_schema=allowed_schema,
                    prior_sql=prior_sql,
                    prior_state=prior_state,
                    surprise_sql=surprise_sql,
                ),
                question,
                enabled=self._settings.chat_question_rewrites_enabled,
            )
            turn = planned.turn
            reinterpreted: str | None = None
            if planned.planned_question != question:
                reinterpreted = planned.planned_question
                logger.info("nlq_rewritten question=%r as=%r", question[:180], reinterpreted)
            if planned.definition_term:
                definition = definition_from_metadata(
                    planned.definition_term, semantic_pack, self._industry
                )
                yield _sse(
                    "definition",
                    {
                        "term": planned.definition_term,
                        "text": definition,
                        "source": "semantic_layer",
                    },
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
            if (
                llm_ready
                and self._settings.nlq_llm_interpretation
                and self._settings.chat_structured_classifier_enabled
                and _worth_reinterpreting(turn)
            ):
                yield _sse("stage", {"stage": "llm_classify"})
                llm_t0 = time.perf_counter()
                outcome = await classify_and_resolve(
                    settings=self._settings,
                    industry=self._industry,
                    question=turn.question,
                    vocabulary=interpretation_vocabulary(self._industry, resolver),
                    previous_question=(
                        session_memory.analytical.previous_question
                        if session_memory.analytical and prior_state
                        else None
                    ),
                    model_override=model_override,
                )
                await record_reply(
                    LlmReply(
                        text="",
                        model=outcome.model,
                        prompt_tokens=outcome.prompt_tokens,
                        completion_tokens=outcome.completion_tokens,
                        latency_ms=int((time.perf_counter() - llm_t0) * 1000),
                        used_llm=True,
                    )
                )
                profile.route_source = "llm_classifier"
                verdict = outcome.verdict
                logger.info(
                    "chat_llm_classifier intent=%s failure=%s",
                    verdict.intent if verdict else None,
                    outcome.failure,
                )
                if verdict is None:
                    turn = _force_clarification(
                        turn,
                        "I couldn't work out what you're asking for. Could you name the metric "
                        "and the period you need?",
                    )
                elif verdict.needs_clarification or verdict.intent == "CLARIFICATION":
                    turn = _force_clarification(
                        turn,
                        verdict.clarification_question
                        or "Could you say which metric and period you mean?",
                    )
                elif verdict.intent in {"DATA_QUERY", "DATA_FOLLOW_UP"}:
                    restated = (verdict.resolved_question or "").strip()
                    second = plan_turn(
                        self._industry,
                        restated,
                        snapshot=value_dictionary,
                        pack=semantic_pack,
                        allowed_schema=allowed_schema,
                        prior_sql=prior_sql,
                        prior_state=prior_state if verdict.intent == "DATA_FOLLOW_UP" else None,
                    )
                    if second.clarification is None and second.governed_sql:
                        logger.info("nlq_reinterpreted question=%r as=%r", question[:180], restated)
                        turn, reinterpreted = second, restated
                    else:
                        turn = _force_clarification(
                            turn,
                            turn.clarification.message
                            if turn.clarification
                            else "I couldn't map that to a governed metric. Which metric do you mean?",
                        )
                else:
                    log_route(verdict.intent.lower(), "llm_classifier")
                    if verdict.intent == "DOCUMENT_QUERY":
                        async for frame in answer_from_documents("llm classifier"):
                            yield frame
                        return
                    if verdict.intent == "GENERAL_KNOWLEDGE":
                        reply = await self._general_knowledge_reply(question)
                        await record_reply(reply)
                        narrative = reply.text
                    elif verdict.intent == "APP_HELP":
                        narrative = app_help_reply(
                            question,
                            industry=self._industry,
                            pack=semantic_pack,
                            allowed_schema=allowed_schema,
                            scope=self._region_scope,
                        )
                    elif verdict.intent == "GENERAL_CHAT":
                        reply = await general_chat_reply(
                            self._settings,
                            industry=self._industry,
                            question=question,
                            reason="default",
                            last_turn_failed=await self._last_turn_failed(
                                conversation.id, history_id
                            ),
                        )
                        await record_reply(reply)
                        append_general_chat(
                            session_memory,
                            role="assistant",
                            text=reply.text,
                            settings=self._settings,
                        )
                        await self._save_session_memory(conversation, session_memory)
                        narrative = reply.text
                    elif verdict.intent == "OUT_OF_SCOPE_LIVE":
                        narrative = template_out_of_scope_live()
                    else:
                        narrative = template_unsupported()
                    async for frame in finish_without_sql(
                        path=verdict.intent.lower(), narrative=narrative
                    ):
                        yield frame
                    return
            elif (
                llm_ready
                and self._settings.nlq_llm_interpretation
                and _worth_reinterpreting(turn)
                and not rule_route_interrupts_analytical_context(question, self._industry)
            ):
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
                        model_override or active_llm(self._settings).model, tokens_in, tokens_out
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
            set_pending_clarification(
                session_memory,
                original_question=question,
                clarifies=clar.message,
                options=clar.options,
            )
            await self._save_session_memory(conversation, session_memory)
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

        decision = (
            EvidenceRouteDecision("sql", "Validated typed analytical request")
            if typed_mode
            else route_question(
                question,
                plan,
                has_documents=documents_allowed,
            )
        )
        if not documents_allowed and decision.route == "hybrid":
            decision = replace(decision, route="sql", reason="documents excluded by request mode")
        yield _sse(
            "stage",
            {"stage": "route", "route": decision.route, "reason": decision.reason},
        )

        if decision.route == "knowledge":
            log_route("knowledge", "query_router")
            async for frame in answer_from_documents(decision.reason):
                yield frame
            return
        log_route("data", profile.route_source or "planner")

        if await cancelled():
            yield _sse(
                "cancelled",
                {
                    "historyId": str(history_id),
                    "responseKind": "cancelled",
                    "runUsage": run_usage() if typed_mode else None,
                },
            )
            return

        completed_steps.append("ambiguity")
        yield _progress("context", completed_steps, slow=maybe_slow())

        data_as_of_hint = typed.data_as_of if typed else await self._industry_data_as_of()

        cached = None
        if not bypass_query_cache:
            cached = QUERY_CACHE.get(
                industry=self._industry.value,
                question=question,
                current_data_as_of=data_as_of_hint,
                scope=self._cache_scope(),
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
        scenario = parse_whatif(question) if not typed_mode and is_whatif(question) else None
        ambiguity_flag = False
        alternate_interpretations: list[str] = []
        ai_generated = False
        notes = [*turn.spelling_notes, *resolution_notes(turn.resolution)]
        if typed and typed.compiled:
            notes += typed.compiled.notes
            notes += [
                f"{label}: {period.start or 'available history'} to {period.end} (end exclusive){'; partial period' if period.partial else ''}."
                for label, period in typed.compiled.periods.items()
            ]
        if reinterpreted:
            notes.insert(0, f"I read this as \u201c{reinterpreted}\u201d.")
        if follow_up_interpretation and turn.contextual:
            notes.insert(0, f"{follow_up_interpretation}.")
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
        if not ai_generated:
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
            yield _sse(
                "cancelled",
                {
                    "historyId": str(history_id),
                    "responseKind": "cancelled",
                    "runUsage": run_usage() if typed_mode else None,
                },
            )
            return

        rows: list[dict[str, Any]] = []
        columns: list[str] = []
        validation_status = "skipped"
        data_as_of: str | None = data_as_of_hint
        dq_failed = False
        execution_error: str | None = None
        explain_plan: str | None = None
        chart_payload: dict[str, Any] | None = None
        typed_coverage: dict[str, Any] = {}

        if sql_text:
            if typed_mode:
                current_scope = await load_region_scope(self._app, self._user)
                if current_scope.cache_key() != self._region_scope.cache_key():
                    async for frame in finish_without_sql(
                        path="denied",
                        narrative="Your access changed while this request was being prepared. Please ask again.",
                    ):
                        yield frame
                    return
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
                if typed_mode:
                    async for frame in emit_failure(classify_database(str(exc)), sql=sql_text):
                        yield frame
                    return
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

            if plan is not None:
                ok_scope, scope_reason = revalidate_plan_for_scope(
                    plan, question, self._region_scope
                )
                if not ok_scope:
                    try:
                        await deny_if_out_of_scope(
                            self._app,
                            self._region_scope,
                            attempted=scope_reason or "region scope",
                            action="AI Chat query",
                        )
                    except Exception as exc:
                        narrative = getattr(exc, "message", None) or str(exc)
                        await self._save_session_memory(conversation, session_memory)
                        async for frame in finish_without_sql(
                            path="denied",
                            narrative=narrative,
                            event="clarification",
                            payload={
                                "kind": "denied",
                                "title": "Access denied",
                                "message": narrative,
                                "historyId": str(history_id),
                            },
                        ):
                            yield frame
                        return

            yield _sse(
                "sql",
                {
                    "sql": self._region_scope.apply_sql(sql_text, self._industry)
                    if typed_mode
                    else sql_text,
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
                timeout_ms = int(
                    (
                        self._settings.chat_investigation_sql_timeout_seconds
                        if typed
                        and typed.context.payload.get("requested_outcome") == "investigation"
                        else self._settings.nlq_sql_timeout_seconds
                    )
                    * 1000
                )
                await self._analytics.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
                analytical_queries += 1
                result = await self._analytics.execute(text(sql_text))
                mappings = result.mappings().all()
                if typed and typed.compiled:
                    typed.compiled.total_groups = (
                        int(mappings[0]["__total_groups"]) if mappings else 0
                    )
                    if mappings:
                        for alias, (
                            period_name,
                            source,
                            boundary,
                        ) in typed.compiled.coverage_columns.items():
                            typed_coverage.setdefault(period_name, {}).setdefault(source, {})[
                                boundary
                            ] = _jsonable(mappings[0].get(alias))
                        for period_name, sources in typed_coverage.items():
                            for source, coverage in sources.items():
                                if coverage.get("start"):
                                    label = {"fact_sales": "sales", "dim_targets": "target"}.get(
                                        source, "source"
                                    )
                                    narrative += f" Observed {label} dates ({period_name}): {coverage['start']} through {coverage.get('through')} (inclusive)."
                cap = min(
                    self._settings.nlq_default_result_limit,
                    self._settings.sql_max_result_rows,
                )
                capped = mappings[:cap]
                columns = list(capped[0].keys()) if capped else list(result.keys())
                if typed_mode:
                    columns = [key for key in columns if not key.startswith("__")]
                rows = [
                    {
                        key: _jsonable(value)
                        for key, value in row.items()
                        if not typed_mode or not key.startswith("__")
                    }
                    for row in capped
                ]
                timings.execution_ms = int((time.perf_counter() - exec_t0) * 1000)
                probed = typed.data_as_of if typed else await self._probe_data_as_of(sql_text)
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
                        "truncated": bool(
                            typed and typed.compiled and typed.compiled.total_groups > len(rows)
                        ),
                    },
                )
            render_t0 = time.perf_counter()
            chart_type = recommend_chart(plan, columns)
            if (
                rows
                and len(columns) >= 2
                and chart_type != "table"
                and (not typed or typed.compiled.group_aliases)
            ):
                measures = [
                    column
                    for column in columns[1:]
                    if column not in _DIMENSION_COLUMNS
                    and isinstance(rows[0].get(column), (int, float))
                ]
                series = [column for column in planned.chart_series if column in columns]
                if typed and typed.compiled:
                    series = [
                        column
                        for column in columns
                        if column not in typed.compiled.group_aliases.values()
                    ]
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
            yield _sse(
                "cancelled",
                {
                    "historyId": str(history_id),
                    "responseKind": "cancelled",
                    "runUsage": run_usage() if typed_mode else None,
                },
            )
            return

        try:
            citations = []
            if decision.route == "hybrid" and documents_allowed:
                knowledge = KnowledgeService(
                    self._settings,
                    self._industry,
                    session=self._app if rag_enabled(self._settings) else None,
                )
                citations = await knowledge.search_authorized(
                    question,
                    user=self._user,
                    region_scope=self._region_scope,
                    top_k=min(2, self._settings.rag_top_k),
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

        narration_started = time.perf_counter()
        if typed and typed.compiled:
            narrative = (
                render_typed_evidence(
                    typed.preview.request,
                    semantic_pack,
                    rows,
                    mappings[0] if mappings else {},
                    investigation=typed.context.payload.get("requested_outcome") == "investigation",
                    total=typed.compiled.total_groups,
                )
                + " "
                + " ".join(notes)
            )
        if typed and typed.preview.request.definition_terms:
            narrative += " " + " ".join(
                definition_from_metadata(term, semantic_pack, self._industry)
                for term in typed.preview.request.definition_terms
            )
        query_meta = extract_query_meta(sql_text)
        insights = build_insights(
            narrative=narrative,
            columns=columns,
            rows=rows,
            path=path,
        )
        if typed and typed.compiled:
            insights["executive"] = narrative
            insights["narration"] = {
                "summary": narrative,
                "highlights": [],
                "insight": None,
                "focus": None,
            }
        if decision.route == "hybrid" and citations:
            insights = merge_hybrid_evidence(
                insights,
                [citation.snippet for citation in citations],
                entities=plan_entities(plan),
            )
        if isinstance(insights.get("narration"), dict):
            context_note = narrative.strip()
            if context_note:
                insights["narration"]["context"] = context_note
            narrative = context_note if typed else f"{context_note} {insights['executive']}".strip()
        grounded = resolve_grounded_on(
            path=path,
            glossary_matches=glossary_matches,
            has_sql=bool(sql_text),
            dq_checked=False,
            llm_invoked=self.usage_llm_steps > 0,
            schema_used=self._schema_used or bool(query_meta.tables_used),
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
            "corrections": [{"from": wrong, "to": right} for wrong, right in turn.corrections],
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
            "resultProfile": self._result_profile(columns, rows, plan),
            "anomalies": detect_anomalies(columns, rows) if rows else [],
            "alternateInterpretations": alternate_interpretations,
            "queryPlan": planned.trace(),
            "dqFailed": dq_failed,
            "executionError": execution_error,
            "autoRepaired": validation_status == "auto_repaired",
            "cacheHit": False,
            "route": decision.route,
            "routeReason": decision.reason,
            "llmRuntime": self._llm_runtime_meta(),
        }
        meta_payload["executionMode"] = "typed" if typed_mode else "legacy"
        if typed and typed.compiled:
            narration_ms = int((time.perf_counter() - narration_started) * 1000)
            meta_payload["responseKind"] = response_kind(
                path,
                sql=True,
                rows=len(rows),
                partial=bool(typed.compiled.unsupported) or typed.preview.status == "partial",
            )
            meta_payload["runId"] = str(history_id)
            meta_payload["runUsage"] = run_usage()
            meta_payload["requestedOutcome"] = typed.context.payload.get("requested_outcome", typed.preview.request.outcome)
            meta_payload["typedRequest"] = typed.preview.request.model_dump(mode="json")
            meta_payload["totalGroups"] = typed.compiled.total_groups
            meta_payload["dataCoverage"] = typed_coverage
            meta_payload["appliedScope"] = self._region_scope.to_api()
            meta_payload["limitations"] = typed.compiled.notes
            meta_payload["unsupportedMeasures"] = typed.compiled.unsupported
            if typed.compiled.total_groups is not None and typed.compiled.total_groups > len(rows):
                notice = (
                    f"Showing {len(rows)} of {typed.compiled.total_groups} groups (safe row limit)."
                )
                meta_payload["insights"]["narration"]["summary"] += " " + notice
                narrative += " " + notice
        yield _sse("meta", meta_payload)

        for token in narrative.split(" "):
            yield _sse("token", {"token": token + " "})

        yield _sse("trust", {"score": score, "breakdown": breakdown})
        latency_ms = int((time.perf_counter() - started) * 1000)
        history.sql_text = (
            self._region_scope.apply_sql(sql_text, self._industry)
            if typed_mode and sql_text
            else sql_text
        )
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

        if plan is not None and sql_text and validation_status == "passed":
            ok_scope, _ = revalidate_plan_for_scope(plan, question, self._region_scope)
            if ok_scope:
                session_memory.analytical = build_analytical_context(
                    plan=plan,
                    question=question,
                    result_meta=ResultMeta(
                        row_count=len(rows),
                        column_names=tuple(columns),
                    ),
                    prior=session_memory.analytical,
                )
                if typed and typed.preview.request:
                    session_memory.typed_request = save_request(
                        session_memory.typed_request,
                        typed.preview.request,
                        typed.context,
                        str(history_id),
                        pending=False,
                        sql=history.sql_text,
                    )
                    session_memory.typed_request["confirmed"]["evidence_summary"] = narrative
        await self._save_session_memory(conversation, session_memory)

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

        if (
            not typed_mode
            and not documents_allowed
            and sql_text
            and path != "fallback"
            and not turn.contextual
        ):
            QUERY_CACHE.put(
                industry=self._industry.value,
                question=question,
                scope=self._cache_scope(),
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
            await self._record_usage(
                outcome.model, outcome.prompt_tokens, outcome.completion_tokens
            )
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

    async def _load_session_memory(self, conversation_id: uuid.UUID) -> SessionMemory:
        self.session_memory_persisted = True
        try:
            result = await self._app.execute(
                select(Conversation.session_memory)
                .where(Conversation.id == conversation_id)
                .where(Conversation.user_id == self._user.id)
            )
            raw = result.scalar_one_or_none()
        except Exception as exc:
            if session_memory_storage_error(exc):
                logger.warning(
                    "conversations.session_memory unavailable; in-request memory only (%s)",
                    exc,
                )
                self.session_memory_persisted = False
                return empty_memory(user_id=self._user.id, conversation_id=conversation_id)
            raise
        memory = (
            SessionMemory.from_dict(raw)
            if isinstance(raw, dict)
            else empty_memory(user_id=self._user.id, conversation_id=conversation_id)
        )
        if memory is None:
            memory = empty_memory(user_id=self._user.id, conversation_id=conversation_id)
        assert_memory_scope(memory, user_id=self._user.id, conversation_id=conversation_id)
        return memory

    async def _save_session_memory(self, conversation: Conversation, memory: SessionMemory) -> None:
        if not self.session_memory_persisted:
            return
        assert_memory_scope(memory, user_id=self._user.id, conversation_id=conversation.id)
        try:
            conversation.session_memory = memory.to_dict()
            await self._app.flush()
        except Exception as exc:
            if session_memory_storage_error(exc):
                logger.warning(
                    "Could not persist session_memory; continuing without cross-request memory"
                )
                self.session_memory_persisted = False
                return
            raise

    async def _prior_sql(
        self, conversation_id: uuid.UUID, current_history_id: uuid.UUID
    ) -> str | None:
        result = await self._app.execute(
            select(QueryHistory.sql_text)
            .where(QueryHistory.user_id == self._user.id)
            .where(QueryHistory.conversation_id == conversation_id)
            .where(QueryHistory.id != current_history_id)
            .where(QueryHistory.sql_text.is_not(None))
            .order_by(QueryHistory.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _last_turn_failed(
        self, conversation_id: uuid.UUID, current_history_id: uuid.UUID
    ) -> bool:
        """True when the previous answer errored, asked to clarify or returned no rows."""
        result = await self._app.execute(
            select(QueryHistory.status, QueryHistory.row_count, QueryHistory.trust_breakdown)
            .where(QueryHistory.user_id == self._user.id)
            .where(QueryHistory.conversation_id == conversation_id)
            .where(QueryHistory.id != current_history_id)
            .order_by(QueryHistory.created_at.desc())
            .limit(1)
        )
        row = result.first()
        if row is None:
            return False
        status, row_count, breakdown = row
        path = (breakdown or {}).get("path") if isinstance(breakdown, dict) else None
        if status != "completed" or path in {"clarification", "recovery", "denied"}:
            return True
        return bool((breakdown or {}).get("queryState")) and not row_count

    async def _prior_state(
        self, conversation_id: uuid.UUID, current_history_id: uuid.UUID
    ) -> dict[str, Any] | None:
        result = await self._app.execute(
            select(QueryHistory.trust_breakdown)
            .where(QueryHistory.user_id == self._user.id)
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
        stmt = (
            select(QueryHistory)
            .where(QueryHistory.industry == self._industry.value)
            .order_by(QueryHistory.created_at.desc())
            .limit(limit)
        )
        if self._user.role != Role.ADMIN:
            stmt = stmt.where(QueryHistory.user_id == self._user.id)
        result = await self._app.execute(stmt)
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
            model_bucket["costUsd"] = float(model_bucket["costUsd"]) + float(row.estimated_cost_usd)

            domain = row.industry or "unknown"
            domain_bucket = by_domain.setdefault(domain, {"calls": 0, "tokens": 0, "costUsd": 0.0})
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
                {"date": day, "costUsd": round(cost, 6)} for day, cost in sorted(daily.items())
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
        governed = active_llm(self._settings)
        self.usage_model = model or governed.model
        self.usage_llm_provider = governed.provider
        self.usage_prompt_tokens += max(0, prompt_tokens)
        self.usage_completion_tokens += max(0, completion_tokens)
        self.usage_llm_steps += 1

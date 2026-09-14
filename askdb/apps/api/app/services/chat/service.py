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
from app.services.chat.failures import (
    FailureInfo,
    classify_database,
    classify_llm_failure,
    classify_semantic,
    classify_sql_validation,
)
from app.services.chat.intents import (
    is_followup,
    is_out_of_bounds,
    is_surprise_me,
    is_whatif,
    needs_clarification,
    parse_whatif,
    suggested_followups,
)
from app.services.chat.profiler import PROFILER, QueryProfile
from app.services.chat.query_cache import QUERY_CACHE, CachedAnswer
from app.services.chat.question_understanding import QuestionPlan, understand_question
from app.services.chat.response_meta import (
    QueryTimings,
    build_insights,
    detect_anomalies,
    extract_query_meta,
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
from app.services.chat.sql_limits import ensure_result_limit
from app.services.chat.templates import list_templates, resolve_template
from app.services.chat.trust import compute_trust_score
from app.services.chat.value_dictionary import (
    ValueDictionarySnapshot,
    get_value_dictionary,
)
from app.services.knowledge import KnowledgeService
from app.services.llm import complete_chat
from app.services.web_retrieval import WebRetrievalService

logger = logging.getLogger(__name__)

PROGRESS_STEPS = [
    {"id": "understanding", "label": "Understanding Question"},
    {"id": "metrics", "label": "Identifying Business Metrics"},
    {"id": "sql", "label": "Generating SQL"},
    {"id": "execute", "label": "Executing Query"},
    {"id": "visualize", "label": "Building Visualization"},
]


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _progress(current: str, completed: list[str], *, slow: bool = False) -> str:
    label = next((s["label"] for s in PROGRESS_STEPS if s["id"] == current), current)
    payload: dict[str, Any] = {
        "steps": PROGRESS_STEPS,
        "current": current,
        "currentLabel": label,
        "completed": completed,
    }
    if slow:
        payload["slowWarning"] = True
        payload["message"] = f"This query is taking longer than expected. Current Stage: {label}"
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
        completed_steps: list[str] = []

        yield _sse("stage", {"stage": "accepted", "historyId": str(history_id)})
        yield _progress("understanding", completed_steps)

        conversation = await self._ensure_conversation(conversation_id, question)
        history = await self._create_running_history(history_id, conversation.id, question)
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

        async def emit_failure(info: FailureInfo, *, sql: str | None = None) -> AsyncIterator[str]:
            profile.error_category = info.category
            profile.error_reason = info.reason
            profile.sql = sql
            profile.timings = timings.to_dict()
            PROFILER.record(profile)
            history.status = "failed"
            history.sql_text = sql
            history.latency_ms = int((time.perf_counter() - started) * 1000)
            history.trust_breakdown = {"failure": info.to_dict()}
            await self._app.flush()
            await self._app.commit()
            payload = info.to_dict()
            if sql:
                payload["sql"] = sql
            payload["historyId"] = str(history_id)
            payload["timings"] = timings.to_dict()
            yield _sse("error", payload)
            yield _sse(
                "done",
                {
                    "historyId": str(history_id),
                    "conversationId": str(conversation.id),
                    "latencyMs": history.latency_ms,
                    "failed": True,
                    "failureCategory": info.category,
                },
            )

        async def finish_without_sql(
            *,
            path: str,
            narrative: str,
            event: str | None = None,
            payload: dict[str, Any] | None = None,
            ambiguity: bool = False,
            alternates: list[str] | None = None,
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
            history.status = "completed"
            history.row_count = 0
            history.trust_score = 0
            history.trust_breakdown = {"path": path, "ambiguityFlag": ambiguity}
            history.latency_ms = int((time.perf_counter() - started) * 1000)
            await self._app.flush()
            profile.path = path
            profile.timings = timings.to_dict()
            PROFILER.record(profile)
            yield _sse(
                "followups",
                {"items": suggested_followups(self._industry, path)},
            )
            yield _sse(
                "done",
                {
                    "historyId": str(history_id),
                    "conversationId": str(conversation.id),
                    "latencyMs": history.latency_ms,
                    "trustScore": 0,
                    "ambiguityFlag": ambiguity,
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

        clarification = needs_clarification(question)
        if clarification is not None:
            options = suggested_followups(self._industry, "clarification")
            async for frame in finish_without_sql(
                path="clarification",
                narrative=clarification,
                event="clarification",
                payload={"question": clarification, "options": options},
                ambiguity=True,
                alternates=options,
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
            logger.warning(
                "Value dictionary unavailable; continuing with semantic rules", exc_info=True
            )
            value_dictionary = ValueDictionarySnapshot(self._industry, ())
        value_filters = value_dictionary.match(question)
        allowed_schema = build_allowed_schema(semantic_pack)
        plan = understand_question(
            self._industry,
            question,
            value_filters=value_filters,
        )
        if plan.is_ambiguous and plan.ambiguity_options:
            msg = "Your question is ambiguous. Did you mean one of these?"
            async for frame in finish_without_sql(
                path="clarification",
                narrative=msg,
                event="clarification",
                payload={"question": msg, "options": plan.ambiguity_options},
                ambiguity=True,
                alternates=plan.ambiguity_options,
            ):
                yield frame
            return

        if await cancelled():
            yield _sse("cancelled", {"historyId": str(history_id)})
            return

        completed_steps.append("understanding")
        yield _progress("metrics", completed_steps, slow=maybe_slow())

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
            for step in ("metrics", "sql", "execute", "visualize"):
                if step not in completed_steps:
                    completed_steps.append(step)
            yield _progress("visualize", completed_steps)
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
            meta = {**cached.meta, "cacheHit": True, "timings": timings.to_dict()}
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

        prior_sql: str | None = None
        followup_note = ""
        if is_followup(question):
            prior_sql = await self._prior_sql(conversation.id, history_id)
            if prior_sql:
                yield _sse("stage", {"stage": "followup"})
                followup_note = "Using the previous query as conversational context. "

        semantic_t0 = time.perf_counter()
        if is_surprise_me(question):
            templates = list_templates(self._industry)
            hit = secrets.choice(templates) if templates else None
            yield _sse("stage", {"stage": "surprise"})
        elif prior_sql:
            # Follow-ups must preserve the prior query's grain and joins. A fresh
            # standalone template would silently discard that context.
            hit = None
        else:
            hit = resolve_template(self._industry, question, plan=plan)
        timings.semantic_lookup_ms = int((time.perf_counter() - semantic_t0) * 1000)
        completed_steps.append("metrics")
        yield _progress("sql", completed_steps, slow=maybe_slow())

        sql_text: str | None = None
        path = "fallback"
        glossary_matches = 0
        narrative = followup_note
        scenario = parse_whatif(question) if is_whatif(question) else None
        ambiguity_flag = False
        alternate_interpretations: list[str] = []

        if hit is not None:
            if not is_surprise_me(question):
                ok, reason = validate_sql_against_plan(
                    hit.sql,
                    plan,
                    allowed_schema=allowed_schema,
                )
                if not ok:
                    logger.warning("Template SQL failed plan validation: %s", reason)
                    async for frame in emit_failure(
                        classify_sql_validation(
                            reason or "Template SQL did not match the question plan"
                        )
                    ):
                        yield frame
                    return
            sql_text = hit.sql
            path = hit.path
            glossary_matches = hit.glossary_matches
            narrative += f"Answered with governed template: {hit.title}."
            yield _sse("stage", {"stage": "template", "title": hit.title})
        else:
            if plan.entity:
                logger.info(
                    "Question plan entity=%s metric=%s filters=%s; trying LLM",
                    plan.entity,
                    plan.metric,
                    [f.value for f in plan.filters],
                )
            yield _sse("stage", {"stage": "llm"})
            llm_t0 = time.perf_counter()
            llm = await complete_chat(
                settings=self._settings,
                industry=self._industry,
                question=question,
                schema_hints=await self._domain_sql_hints(question, plan),
                prior_sql=prior_sql,
                model_override=model_override,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
            )
            timings.llm_generation_ms = int((time.perf_counter() - llm_t0) * 1000)
            profile.llm_calls = 1
            profile.prompt_tokens = llm.prompt_tokens
            profile.completion_tokens = llm.completion_tokens

            if llm.circuit_open:
                async for frame in emit_failure(classify_llm_failure(llm.error or "degraded")):
                    yield frame
                return
            if llm.sql:
                ok, reason = validate_sql_against_plan(
                    llm.sql,
                    plan,
                    allowed_schema=allowed_schema,
                )
                if not ok:
                    logger.warning("LLM SQL failed plan validation: %s", reason)
                    async for frame in emit_failure(
                        classify_sql_validation(reason or "SQL did not match the question plan")
                    ):
                        yield frame
                    return
                sql_text = llm.sql
                path = "semantic_llm"
                glossary_matches = 1
                narrative += llm.narrative or "Generated with the configured language model."
                ambiguity_flag = plan.entity == "unknown" and not plan.filters
                if ambiguity_flag:
                    alternate_interpretations = [
                        "Rephrase with an explicit metric name from the glossary",
                        "Ask for a monthly trend of a known KPI",
                    ]
                await self._record_usage(llm.model, llm.prompt_tokens, llm.completion_tokens)
            else:
                if llm.error and self._settings.llm_api_key.get_secret_value():
                    async for frame in emit_failure(classify_llm_failure(llm.error)):
                        yield frame
                    return
                if plan.entity in {"vehicle", "salesperson", "dealer"}:
                    async for frame in emit_failure(classify_semantic(question)):
                        yield frame
                    return
                narrative += llm.narrative or (
                    "No matching governed template and no LLM key is configured. "
                    "Try questions like 'loss ratio', 'claims by status', "
                    "'revenue by month', or 'top selling sedan by units'."
                )
                path = "fallback"

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
                repair_t0 = time.perf_counter()
                repaired = sql_text.strip().rstrip(";")
                try:
                    await self._analytics.execute(text(f"EXPLAIN {repaired}"))
                    sql_text = repaired
                    validation_status = "auto_repaired"
                    timings.sql_auto_repair_ms = int((time.perf_counter() - repair_t0) * 1000)
                except Exception:
                    timings.sql_auto_repair_ms = int((time.perf_counter() - repair_t0) * 1000)
                    validation_status = "failed"
                    timings.sql_validation_ms = int((time.perf_counter() - val_t0) * 1000)
                    async for frame in emit_failure(
                        classify_sql_validation(str(exc)[:240]),
                        sql=sql_text,
                    ):
                        yield frame
                    return
            timings.sql_validation_ms = int((time.perf_counter() - val_t0) * 1000)
            completed_steps.append("sql")
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
                timings.execution_ms = int((time.perf_counter() - exec_t0) * 1000)
                async for frame in emit_failure(classify_database(str(exc)), sql=sql_text):
                    yield frame
                return

            completed_steps.append("execute")
            yield _progress("visualize", completed_steps, slow=maybe_slow())

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
            if rows and len(columns) >= 2:
                chart_payload = {
                    "type": "bar",
                    "x": columns[0],
                    "y": columns[1],
                    "points": rows[:40],
                    "anomalies": detect_anomalies(columns, rows),
                }
                yield _sse("chart", chart_payload)
            timings.render_ms = int((time.perf_counter() - render_t0) * 1000)

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
            completed_steps.extend(["sql", "execute", "visualize"])
            yield _progress("visualize", completed_steps, slow=maybe_slow())

        if await cancelled():
            yield _sse("cancelled", {"historyId": str(history_id)})
            return

        try:
            citations = KnowledgeService(self._settings, self._industry).search(
                question, top_k=min(3, self._settings.rag_top_k), user_id=str(self._user.id)
            )
            for citation in citations:
                yield _sse(
                    "citation",
                    {
                        "documentId": citation.document_id,
                        "title": citation.title,
                        "chunkId": citation.chunk_id,
                        "snippet": citation.snippet,
                        "locator": citation.locator,
                        "untrusted": citation.untrusted,
                    },
                )
            if web_retrieval and question.startswith(("http://", "https://")):
                web_hits = await WebRetrievalService(self._settings).retrieve(
                    question, opted_in=True
                )
                for citation in web_hits:
                    yield _sse(
                        "citation",
                        {
                            "documentId": citation.document_id,
                            "title": citation.title,
                            "chunkId": citation.chunk_id,
                            "snippet": citation.snippet,
                            "locator": citation.locator,
                            "untrusted": True,
                        },
                    )
        except Exception:
            logger.debug("Supplementary knowledge retrieval failed", exc_info=True)

        query_meta = extract_query_meta(sql_text)
        insights = build_insights(
            narrative=narrative,
            columns=columns,
            rows=rows,
            path=path,
        )
        grounded = resolve_grounded_on(
            path=path,
            glossary_matches=glossary_matches,
            has_sql=bool(sql_text),
            dq_checked=False,
        )
        if "visualize" not in completed_steps:
            completed_steps.append("visualize")

        meta_payload = {
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
            "dqFailed": dq_failed,
            "executionError": execution_error,
            "autoRepaired": validation_status == "auto_repaired",
            "cacheHit": False,
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
        }
        history.latency_ms = latency_ms
        history.status = "completed"
        await self._app.flush()

        followups = semantic_followups(
            self._industry,
            dimensions=query_meta.dimensions_used,
            metrics=query_meta.metrics_used,
            tables=query_meta.tables_used,
            path=path,
        )
        yield _sse("followups", {"items": followups})

        if sql_text and path != "fallback":
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
            },
        )

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
                row.model, {"calls": 0, "tokens": 0, "costUsd": 0.0}
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
                    "model": row.model,
                    "purpose": row.purpose,
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
        total = prompt_tokens + completion_tokens
        cost = total * 0.000002
        self._app.add(
            LlmUsage(
                id=uuid.uuid4(),
                user_id=self._user.id,
                industry=self._industry.value,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total,
                estimated_cost_usd=cost,
                purpose="chat",
            )
        )
        await self._app.flush()

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
from app.core.exceptions import GuardrailViolationError, ValidationError
from app.models.activity import Conversation, LlmUsage, QueryHistory, SavedQuestion
from app.models.user import User
from app.services.chat.intents import (
    is_followup,
    is_out_of_bounds,
    is_surprise_me,
    is_whatif,
    needs_clarification,
    parse_whatif,
    suggested_followups,
)
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
from app.services.chat.templates import list_templates, resolve_template
from app.services.chat.trust import compute_trust_score
from app.services.knowledge import KnowledgeService
from app.services.llm import complete_chat
from app.services.web_retrieval import WebRetrievalService

logger = logging.getLogger(__name__)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class ChatService:
    def __init__(
        self,
        *,
        app_session: AsyncSession,
        analytics: AsyncConnection,
        settings: Settings,
        user: User,
        industry: Industry,
    ) -> None:
        self._app = app_session
        self._analytics = analytics
        self._settings = settings
        self._user = user
        self._industry = industry

    async def ask_stream(
        self,
        question: str,
        conversation_id: uuid.UUID | None,
        *,
        cancel_event: Event | None = None,
        cancel_requested: set[uuid.UUID] | None = None,
        web_retrieval: bool = False,
    ) -> AsyncIterator[str]:
        started = time.perf_counter()
        timings = QueryTimings()
        question = (question or "").strip()
        if not question:
            raise ValidationError("Question is required.")

        history_id = uuid.uuid4()
        yield _sse("stage", {"stage": "accepted", "historyId": str(history_id)})

        conversation = await self._ensure_conversation(conversation_id, question)
        history = await self._create_running_history(history_id, conversation.id, question)
        await self._app.flush()
        # Make the running row visible to the independent cancellation request.
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
                return True
            return False

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

        if await cancelled():
            yield _sse("cancelled", {"historyId": str(history_id)})
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
        else:
            hit = resolve_template(self._industry, question)
        timings.semantic_lookup_ms = int((time.perf_counter() - semantic_t0) * 1000)

        sql_text: str | None = None
        path = "fallback"
        glossary_matches = 0
        narrative = followup_note
        scenario = parse_whatif(question) if is_whatif(question) else None
        ambiguity_flag = False
        alternate_interpretations: list[str] = []

        if hit is not None:
            sql_text = hit.sql
            path = hit.path
            glossary_matches = hit.glossary_matches
            narrative += f"Answered with governed template: {hit.title}."
            yield _sse("stage", {"stage": "template", "title": hit.title})
            # Templates are governed mappings — not ambiguous guesses.
        else:
            yield _sse("stage", {"stage": "llm"})
            llm_t0 = time.perf_counter()
            llm = await complete_chat(
                settings=self._settings,
                industry=self._industry,
                question=question,
            )
            timings.llm_generation_ms = int((time.perf_counter() - llm_t0) * 1000)
            if llm.sql:
                sql_text = llm.sql
                path = "semantic_llm"
                glossary_matches = 1
                narrative += llm.narrative or "Generated with the configured language model."
                # LLM path without a governed template is inherently less certain.
                ambiguity_flag = True
                alternate_interpretations = [
                    "Rephrase with an explicit metric name from the glossary",
                    "Ask for a monthly trend of a known KPI",
                ]
                await self._record_usage(llm.model, llm.prompt_tokens, llm.completion_tokens)
            else:
                narrative += llm.narrative or (
                    "No matching governed template and no LLM key is configured. "
                    "Try questions like 'loss ratio', 'claims by status', "
                    "'revenue by month', or 'top models'."
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
        data_as_of: str | None = None
        dq_failed = False
        execution_error: str | None = None

        if sql_text:
            val_t0 = time.perf_counter()
            ok, reason = sql_is_safe(sql_text)
            if not ok:
                timings.sql_validation_ms = int((time.perf_counter() - val_t0) * 1000)
                raise GuardrailViolationError(reason)

            validation_status = "passed"
            # Dry-run via EXPLAIN; one soft repair attempt (strip trailing noise).
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
                    execution_error = str(exc)[:240]
            timings.sql_validation_ms = int((time.perf_counter() - val_t0) * 1000)

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

            if validation_status != "failed":
                exec_t0 = time.perf_counter()
                try:
                    result = await self._analytics.execute(text(sql_text))
                    mappings = result.mappings().all()
                    capped = mappings[: self._settings.sql_max_result_rows]
                    columns = list(capped[0].keys()) if capped else list(result.keys())
                    rows = [{key: _jsonable(value) for key, value in row.items()} for row in capped]
                    timings.execution_ms = int((time.perf_counter() - exec_t0) * 1000)
                    data_as_of = await self._probe_data_as_of(sql_text)
                except Exception as exc:
                    timings.execution_ms = int((time.perf_counter() - exec_t0) * 1000)
                    validation_status = "failed"
                    execution_error = str(exc)[:240]
                    rows = []
                    columns = []

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
            if rows and len(columns) >= 2:
                yield _sse(
                    "chart",
                    {
                        "type": "bar",
                        "x": columns[0],
                        "y": columns[1],
                        "points": rows[:40],
                        "anomalies": detect_anomalies(columns, rows),
                    },
                )

            score, breakdown = compute_trust_score(
                glossary_matches=glossary_matches,
                glossary_hints_are_sql=True,
                resolution_path=path if validation_status != "failed" else "error",
                row_count=len(rows),
            )
        else:
            score, breakdown = compute_trust_score(
                glossary_matches=0,
                glossary_hints_are_sql=False,
                resolution_path=path,
                row_count=0,
            )

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
            # Retrieval is supplementary and must not fail an analytics response.
            logger.debug("Supplementary knowledge retrieval failed", exc_info=True)

        query_meta = extract_query_meta(sql_text)
        insights = build_insights(
            narrative=narrative,
            columns=columns,
            rows=rows,
            path=path,
        )
        render_t0 = time.perf_counter()
        grounded = resolve_grounded_on(
            path=path,
            glossary_matches=glossary_matches,
            has_sql=bool(sql_text),
            dq_checked=False,
        )
        timings.render_ms = int((time.perf_counter() - render_t0) * 1000)

        yield _sse(
            "meta",
            {
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
            },
        )

        for token in narrative.split(" "):
            yield _sse("token", {"token": token + " "})

        # Keep emitting trust for backwards compatibility; UI no longer shows the number.
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
        history.status = "completed" if not execution_error else "failed"
        await self._app.flush()

        followups = semantic_followups(
            self._industry,
            dimensions=query_meta.dimensions_used,
            metrics=query_meta.metrics_used,
            tables=query_meta.tables_used,
            path=path,
        )
        yield _sse("followups", {"items": followups})
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

    async def _probe_data_as_of(self, sql: str) -> str | None:
        """Best-effort freshness from fact tables referenced in SQL — not query run time."""
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
            .limit(200)
        )
        rows = list(result.scalars().all())
        total_tokens = sum(row.total_tokens for row in rows)
        total_cost = float(sum(float(row.estimated_cost_usd) for row in rows))
        return {
            "calls": len(rows),
            "totalTokens": total_tokens,
            "estimatedCostUsd": round(total_cost, 6),
            "recent": [
                {
                    "id": str(row.id),
                    "model": row.model,
                    "purpose": row.purpose,
                    "totalTokens": row.total_tokens,
                    "estimatedCostUsd": float(row.estimated_cost_usd),
                    "createdAt": row.created_at.isoformat(),
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
        # Rough placeholder pricing for analytics; replaced when provider billing is wired.
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

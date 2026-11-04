"""Automotive AskWiz: bounded interpretation, governed recipes and evidence narration.

No agents, generated SQL or model access to warehouse tools. Durable definitions
use optimistic revisions; cached results are optional and permission-bound.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import logging
import re
import time
import uuid
from collections import OrderedDict
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import Industry
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    NqlError,
    QuotaExceededError,
    ValidationError,
)
from app.models.activity import LlmUsage
from app.models.askwiz import AutoDashboard
from app.schemas.analytics import (
    AnalyticsFilterSpec,
    AnalyticsInsights,
    AnalyticsRunResponse,
    AnalyticsSpec,
)
from app.schemas.askwiz import (
    BoardDefinition,
    BoardNarration,
    BoardResults,
    BoardView,
    ChartDefinition,
    ChartResult,
    Intent,
)
from app.schemas.dashboard import DashboardMetric
from app.services.analytics.catalog import Catalog, first_error
from app.services.analytics.runner import AnalyticsService, catalog_for
from app.services.executive.dashboard import QueryMeter, movement, semantic_revision
from app.services.governance import enforce_quota, sync_llm_config
from app.services.governance.llm_catalog import load_catalog
from app.services.governance.llm_config import active_llm
from app.services.llm import complete_text, llm_configured
from app.services.security.region_scope import (
    RegionScope,
    assert_requested_region,
    forbidden_zones,
    load_region_scope,
)

RECIPES = {
    "sales": [
        ("revenue", "day"),
        ("units_sold", "day"),
        ("revenue", "make"),
        ("revenue", "model"),
        ("revenue", "region"),
        ("orders", "day"),
    ],
    "weekly": [
        ("revenue", "day"),
        ("units_sold", "day"),
        ("revenue", "region"),
        ("revenue", "model"),
        ("orders", "day"),
        ("revenue", "make"),
    ],
    "models": [
        ("revenue", "model"),
        ("units_sold", "model"),
        ("revenue", "make"),
        ("average_selling_price", "model"),
        ("orders", "model"),
        ("revenue", "day"),
    ],
    "regions": [
        ("revenue", "region"),
        ("units_sold", "region"),
        ("revenue", "state"),
        ("revenue", "city"),
        ("orders", "region"),
        ("revenue", "day"),
    ],
    "growth": [
        ("revenue", "day"),
        ("units_sold", "day"),
        ("orders", "day"),
        ("revenue", "make"),
        ("revenue", "region"),
        ("revenue", "model"),
    ],
}
LABELS = {
    "revenue": "Revenue",
    "units_sold": "Units sold",
    "orders": "Orders",
    "average_selling_price": "Average selling price",
    "active_salespeople": "Active salespeople",
}
FILTERS = {"region", "state", "city", "make", "model", "dealer", "car_type", "engine_type"}
logger = logging.getLogger(__name__)
# Bounded process-local optimization only. Missing entries cause governed re-execution.
CACHE: OrderedDict[str, tuple[float, AnalyticsRunResponse]] = OrderedDict()
NARRATIONS: OrderedDict[str, tuple[float, BoardNarration]] = OrderedDict()
INTENTS: OrderedDict[str, tuple[float, Intent]] = OrderedDict()


def resolve_period(
    period: str, today: date, start: str | None = None, end: str | None = None
) -> tuple[date, date, date, date]:
    monday = today - timedelta(days=today.weekday())
    if period == "this_week":
        a, b = monday, today
        return a, b, a - timedelta(days=7), b - timedelta(days=7)
    if period == "last_week":
        a, b = monday - timedelta(days=7), monday - timedelta(days=1)
    elif period == "this_month":
        a, b = today.replace(day=1), today
        prior_end = a - timedelta(days=1)
        return a, b, prior_end.replace(day=1), prior_end.replace(day=min(today.day, prior_end.day))
    elif period == "last_month":
        b = today.replace(day=1) - timedelta(days=1)
        a = b.replace(day=1)
        pb = a - timedelta(days=1)
        return a, b, pb.replace(day=1), pb
    elif period == "this_year":
        a, b = today.replace(month=1, day=1), today
        return (
            a,
            b,
            a.replace(year=a.year - 1),
            b.replace(year=b.year - 1, day=min(b.day, calendar.monthrange(b.year - 1, b.month)[1])),
        )
    elif period == "custom":
        try:
            a, b = date.fromisoformat(start or ""), date.fromisoformat(end or "")
        except ValueError as exc:
            raise ValidationError("Provide both dates as YYYY-MM-DD.") from exc
    else:
        raise ValidationError("Choose a supported period.")
    if a > b or (b - a).days > 731:
        raise ValidationError("Choose an ordered date range of at most two years.")
    days = timedelta(days=(b - a).days + 1)
    return a, b, a - days, b - days


def deterministic_intent(prompt: str, editing: bool = False) -> Intent | None:
    q = prompt.casefold()
    if re.search(r"\b(second|2nd|first|third|fourth) week\b", q):
        return Intent(
            operation="clarify",
            clarification="Which exact dates do you mean? Specify a month/year and week convention, or enter YYYY-MM-DD to YYYY-MM-DD.",
        )
    match = re.search(r"\b(?:chart\s*)?(one|two|three|four|five|six|[1-6])\b", q)
    number = (
        int(match[1])
        if match and match[1].isdigit()
        else (
            {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}.get(match[1])
            if match
            else None
        )
    )
    period = next(
        (
            p
            for phrase, p in [
                ("last week", "last_week"),
                ("this week", "this_week"),
                ("last month", "last_month"),
                ("this month", "this_month"),
                ("this year", "this_year"),
            ]
            if phrase in q
        ),
        None,
    )
    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", q)
    if len(dates) == 2:
        return Intent(
            operation="update" if editing else "create",
            period="custom",
            start=dates[0],
            end=dates[1],
            whole_board=True,
        )
    if editing:
        if re.search(r"\b(only|where|north|south|east|west)\b", q):
            return None
        viz = next(
            (v for v in ["area", "line", "bar", "pie", "table"] if re.search(rf"\b{v}\b", q)), None
        )
        if viz and not re.search(r"\b(by|filter)\b", q) and not period:
            return Intent(operation="update", chart_index=number, viz=viz)
        if re.search(r"\bremove\b", q) and "chart" in q:
            return Intent(operation="remove", chart_index=number)
        if re.search(r"\b(explain|summari[sz]e)\b", q):
            return Intent(operation="explain", chart_index=number)
        if period and re.search(r"\b(whole|entire|all|dashboard|board)\b", q):
            return Intent(operation="update", period=period, whole_board=True)
    if not editing and re.search(r"\b(sales|revenue|units|models?|regional)\b", q):
        recipe = (
            "weekly"
            if "week" in q
            else "models"
            if "model" in q
            else "regions"
            if "region" in q
            else "sales"
        )
        count_match = re.search(r"\b(\d+)\s+charts?\b", q)
        count = int(count_match[1]) if count_match else number or 4
        if count > 6:
            return Intent(
                operation="clarify",
                clarification="AskWiz supports up to six charts per board. Choose a smaller set.",
            )
        return Intent(recipe=recipe, period=period or "this_month", count=count)
    return None


def chart_spec(
    chart: ChartDefinition, definition: BoardDefinition, *, prior: bool = False
) -> AnalyticsSpec:
    time_dimension = chart.dimension in {"day", "month"}
    return AnalyticsSpec(
        metrics=[chart.metric],
        dimensions=["month" if chart.dimension == "day" else chart.dimension],
        analysis="trend" if time_dimension else "top_n",
        limit=500 if time_dimension else 10,
        order_direction="asc" if time_dimension else "desc",
        viz=chart.viz,
        date_preset="custom",
        date_from=definition.prior_start if prior else definition.start,
        date_to=definition.prior_end if prior else definition.end,
        filters=[AnalyticsFilterSpec(domain=k, values=v) for k, v in definition.filters.items()],
    )


def kpi_spec(definition: BoardDefinition, prior: bool = False) -> AnalyticsSpec:
    return AnalyticsSpec(
        metrics=["revenue", "units_sold", "orders"],
        date_preset="custom",
        date_from=definition.prior_start if prior else definition.start,
        date_to=definition.prior_end if prior else definition.end,
        filters=[AnalyticsFilterSpec(domain=k, values=v) for k, v in definition.filters.items()],
    )


def validate_definition(definition: BoardDefinition, catalog: Catalog, scope: RegionScope) -> None:
    if len({c.id for c in definition.charts}) != len(definition.charts):
        raise ValidationError("Chart identities must be unique.")
    if len({(c.metric, c.dimension) for c in definition.charts}) != len(definition.charts):
        raise ValidationError(
            "Choose distinct metric/breakdown combinations rather than duplicate charts."
        )
    resolve_period("custom", date.today(), definition.start, definition.end)
    resolve_period("custom", date.today(), definition.prior_start, definition.prior_end)
    if len(definition.filters) > 8:
        raise ValidationError("Too many filters.")
    for domain, values in definition.filters.items():
        if (
            domain not in FILTERS
            or not values
            or len(values) > 20
            or any(len(v) > 120 for v in values)
        ):
            raise ValidationError("Unsupported filter selection.")
        if domain in {"region", "state", "city"}:
            for value in values:
                assert_requested_region(scope, value)
    for chart in definition.charts:
        if chart.viz in {"line", "area"} and chart.dimension not in {"day", "month"}:
            raise ValidationError(
                "Line and area charts require a time dimension. Choose a bar or table."
            )
        if chart.viz == "pie" and chart.dimension in {"day", "month"}:
            raise ValidationError(
                "A pie chart cannot represent a time trend. Choose a line, area or bar chart."
            )
        issue = first_error(catalog.inspect(chart_spec(chart, definition)).issues)
        if issue:
            raise ValidationError(issue.message)


class AskWizService:
    def __init__(self, analytics: AnalyticsService):
        self.base = analytics
        self.calls = 0
        self.tokens = 0
        self.notes: list[str] = []

    def enabled(self) -> None:
        if not self.base._settings.ask_me_askwiz_enabled:
            raise NotFoundError("AskWiz is disabled.")
        if self.base._industry != Industry.AUTOMOTIVE:
            raise AuthorizationError("AskWiz Auto is available for automotive only.")

    async def context(self) -> tuple[Catalog, RegionScope]:
        self.enabled()
        return (
            await catalog_for(self.base._semantic, Industry.AUTOMOTIVE),
            await load_region_scope(self.base._app, self.base._user),
        )

    async def completion(self, system: str, prompt: str, max_tokens: int = 450) -> str | None:
        try:
            await enforce_quota(self.base._app, self.base._user)
        except QuotaExceededError:
            self.notes.append("AI quota reached. Using the supported recipe and factual summary.")
            return None
        await sync_llm_config(self.base._app, self.base._settings)
        if not llm_configured(self.base._settings):
            self.notes.append("AI is unavailable. Supported templates and evidence remain usable.")
            return None
        started = time.perf_counter()
        result = await complete_text(
            settings=self.base._settings, system=system, user=prompt, max_tokens=max_tokens
        )
        self.calls += 1
        self.tokens += result.prompt_tokens + result.completion_tokens
        active = active_llm(self.base._settings)
        price = load_catalog(self.base._settings).model(active.provider, result.model)
        estimated = (
            (
                result.prompt_tokens * price.input_usd_per_1m
                + result.completion_tokens * price.output_usd_per_1m
            )
            / 1_000_000
            if price
            else (result.prompt_tokens + result.completion_tokens) * 0.000002
        )  # Catalog estimate, otherwise the existing governance fallback; not an invoice.
        self.base._app.add(
            LlmUsage(
                user_id=self.base._user.id,
                question=prompt[:2000],
                model_name=result.model[:120],
                execution_mode="LLM",
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.prompt_tokens + result.completion_tokens,
                response_time_ms=int((time.perf_counter() - started) * 1000),
                industry="automotive",
                purpose="askwiz",
                estimated_cost_usd=estimated,
            )
        )
        await self.base._app.flush()
        if not result.content or result.error:
            self.notes.append(
                "AI could not complete this request. Using available governed evidence."
            )
            return None
        return result.content

    async def interpret(
        self,
        prompt: str,
        *,
        scope: RegionScope,
        editing: bool = False,
        board: BoardDefinition | None = None,
    ) -> Intent:
        fallback = deterministic_intent(prompt, editing)
        if fallback and (fallback.operation == "clarify" or editing):
            return fallback
        key = hashlib.sha256(
            json.dumps(
                [
                    str(self.base._user.id),
                    str(self.base._user.role),
                    scope.cache_key(),
                    semantic_revision(self.base._settings, Industry.AUTOMOTIVE),
                    prompt.strip().casefold(),
                    board.model_dump(mode="json") if board else None,
                    editing,
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        cached = INTENTS.get(key)
        if cached and time.monotonic() - cached[0] < 600:
            self.notes.append("Reused a validated question interpretation.")
            return cached[1].model_copy(deep=True)
        # LLM understands free-form creation; template buttons bypass it entirely.
        system = (
            "Interpret an automotive dashboard request. Return ONLY JSON matching this schema: "
            + json.dumps(Intent.model_json_schema())
            + ". Never write SQL, expressions or data. Use only predefined metrics/dimensions. "
            "sales means revenue unless units are requested. All requested filters MUST be returned. "
            "Unknown metric, ambiguous date/target or unsupported request: operation=clarify and explain. "
            "Use period=null when editing without a date change. wholeBoard=true only for explicit board-wide edits. "
            "For a selected chart update set operation=update. Chart count excludes KPI cards. "
            "Choose the smallest useful response: one chart for a simple trend or breakdown; "
            "three to five for an explicit executive dashboard. Never default to four charts. "
            "Respect an explicitly requested chart count. Populate charts with the requested "
            "metric and dimension rather than unrelated recipe panels. "
            + ("Existing board: " + board.model_dump_json() if board else "")
        )
        raw = await self.completion(system, prompt, max_tokens=800)
        if raw:
            try:
                intent = Intent.model_validate_json(raw)
                INTENTS[key] = (time.monotonic(), intent.model_copy(deep=True))
                INTENTS.move_to_end(key)
                while len(INTENTS) > 128:
                    INTENTS.popitem(last=False)
                return intent
            except ValueError:
                self.notes.append("AI returned an unsupported specification; it was not executed.")
        # Only safely recognized, unfiltered template prompts can fall back.
        safe_words = {
            "generate",
            "create",
            "build",
            "show",
            "me",
            "a",
            "an",
            "the",
            "report",
            "reports",
            "of",
            "for",
            "on",
            "daily",
            "sales",
            "revenue",
            "units",
            "sold",
            "orders",
            "performance",
            "weekly",
            "last",
            "this",
            "week",
            "month",
            "year",
            "charts",
            "chart",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "with",
            "and",
            "top",
            "models",
            "model",
            "regional",
            "compare",
            "same",
            "elapsed",
            "days",
            "previous",
            "data",
            "to",
        }
        normalized = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", prompt.casefold())
        safe = all(
            word in safe_words or word in {"1", "2", "3", "4", "5", "6"}
            for word in re.findall(r"\w+", normalized)
        )
        if fallback and safe:
            return fallback
        return Intent(
            operation="clarify",
            clarification="Choose a starter report or specify supported sales metrics, exact dates and filters. No queries were run.",
        )

    async def get(
        self, board_id: uuid.UUID, revision: int | None = None
    ) -> tuple[AutoDashboard, BoardDefinition, Catalog, RegionScope]:
        catalog, scope = await self.context()
        row = await self.base._app.scalar(
            select(AutoDashboard).where(
                AutoDashboard.id == board_id, AutoDashboard.user_id == self.base._user.id
            )
        )
        if not row:
            raise NotFoundError("Auto board not found.")
        if revision is not None and row.revision != revision:
            raise ConflictError("This board changed. Reopen its current revision before editing.")
        if row.scope_key != scope.cache_key():
            raise AuthorizationError(
                "Your access changed. Create a new board for your current scope."
            )
        definition = BoardDefinition.model_validate(row.definition)
        validate_definition(definition, catalog, scope)
        return row, definition, catalog, scope

    def view(self, row: AutoDashboard, message: str = "") -> BoardView:
        return BoardView(
            id=row.id,
            title=row.title,
            revision=row.revision,
            saved=row.saved,
            definition=BoardDefinition.model_validate(row.definition),
            can_undo=row.previous is not None,
            message=" ".join([message, *self.notes]).strip(),
            llm_calls=self.calls,
            tokens=self.tokens,
        )

    async def create(self, prompt: str, recipe: str | None = None) -> BoardView:
        catalog, scope = await self.context()
        if forbidden_zones(prompt, scope):
            raise AuthorizationError("The requested geography is outside your access.")
        intent = (
            Intent(recipe=recipe, period="last_week" if recipe == "weekly" else "this_month")
            if recipe
            else await self.interpret(prompt, scope=scope)
        )
        if intent.operation == "clarify":
            raise ValidationError(
                intent.clarification or "Please clarify your report request.",
                code="askwiz_clarification",
            )
        explicit_count = re.search(
            r"\b(\d+|one|two|three|four|five|six)\s+charts?\b", prompt.casefold()
        )
        if explicit_count:
            word = explicit_count[1]
            count = (
                int(word)
                if word.isdigit()
                else {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}[word]
            )
            if count != intent.count:
                raise ValidationError(
                    "The proposed number of charts differs from your request. Please specify the desired count again.",
                    code="askwiz_clarification",
                )
        tz = self.base._settings.askwiz_timezone
        dates = resolve_period(
            intent.period or "this_month",
            datetime.now(ZoneInfo(tz)).date(),
            intent.start,
            intent.end,
        )
        pairs = RECIPES[intent.recipe][: intent.count]
        if intent.metric:
            pairs = [
                (str(intent.metric), d) for d in ("day", "make", "model", "region", "state", "city")
            ][: intent.count]
        charts = [
            ChartDefinition(
                id=str(uuid.uuid4()),
                title=f"{LABELS[m]} by {d}",
                metric=m,
                dimension=d,
                viz="line" if d in {"day", "month"} else "bar",
            )
            for m, d in pairs
        ]
        if intent.charts:
            if len(intent.charts) != intent.count:
                raise ValidationError(
                    "The proposed chart count does not match the request. Please specify the chart count again.",
                    code="askwiz_clarification",
                )
            charts = [c.model_copy(update={"id": str(uuid.uuid4())}) for c in intent.charts]
        if intent.dimension:
            charts[0].dimension = intent.dimension
            charts[0].viz = intent.viz or (
                "line" if intent.dimension in {"day", "month"} else "bar"
            )
        definition = BoardDefinition(
            recipe=intent.recipe,
            start=str(dates[0]),
            end=str(dates[1]),
            prior_start=str(dates[2]),
            prior_end=str(dates[3]),
            timezone=tz,
            filters=intent.filters or {},
            charts=charts,
        )
        validate_definition(definition, catalog, scope)
        row = AutoDashboard(
            id=uuid.uuid4(),
            user_id=self.base._user.id,
            title=intent.title or "Automotive sales report",
            revision=1,
            saved=False,
            scope_key=scope.cache_key(),
            definition=definition.model_dump(mode="json"),
        )
        self.base._app.add(row)
        await self.base._app.flush()
        return self.view(row, "Board created from governed automotive KPI recipes.")

    async def command(
        self, board_id: uuid.UUID, revision: int, prompt: str, selected: str | None, action: str
    ) -> BoardView:
        row, definition, catalog, scope = await self.get(board_id, revision)
        old = definition.model_dump(mode="json")
        message = "Board updated. Only changed queries will be rerun."
        if action == "save":
            values: dict[str, Any] = {"saved": True}
            message = "Saved specification. Dates remain fixed when reopened."
        elif action == "undo":
            if not row.previous:
                raise ValidationError("No earlier edit to undo.")
            definition = BoardDefinition.model_validate(row.previous)
            validate_definition(definition, catalog, scope)
            values = {
                "definition": definition.model_dump(mode="json"),
                "previous": old,
                "revision": revision + 1,
            }
        elif action in {"retry", "refresh"}:
            return self.view(row, "Ready to refresh results.")
        else:
            if forbidden_zones(prompt, scope):
                raise AuthorizationError("The requested geography is outside your access.")
            intent = await self.interpret(prompt, scope=scope, editing=True, board=definition)
            if intent.operation == "clarify":
                raise ValidationError(
                    intent.clarification or "Please clarify the change.",
                    code="askwiz_clarification",
                )
            if intent.operation == "explain":
                return self.view(
                    row,
                    "Open the evidence and narration for the selected chart below. No extra driver query was run.",
                )
            target = next((c for c in definition.charts if c.id == selected), None)
            if intent.chart_index:
                target = (
                    definition.charts[intent.chart_index - 1]
                    if intent.chart_index <= len(definition.charts)
                    else None
                )
            if target is None and not intent.chart_index:
                named = [
                    c
                    for c in definition.charts
                    if (
                        c.metric.replace("_", " ") in prompt.casefold()
                        or LABELS[c.metric].casefold() in prompt.casefold()
                    )
                    and ("trend" not in prompt.casefold() or c.dimension in {"day", "month"})
                ]
                if len(named) == 1:
                    target = named[0]
            if intent.period or intent.filters is not None:
                if not intent.whole_board:
                    raise ValidationError(
                        "Apply this date/filter to the whole dashboard? Say 'apply to the whole dashboard'.",
                        code="askwiz_clarification",
                    )
                if intent.period:
                    dates = resolve_period(
                        intent.period,
                        datetime.now(ZoneInfo(definition.timezone)).date(),
                        intent.start,
                        intent.end,
                    )
                    (
                        definition.start,
                        definition.end,
                        definition.prior_start,
                        definition.prior_end,
                    ) = map(str, dates)
                if intent.filters is not None:
                    definition.filters = {**definition.filters, **intent.filters}
            elif intent.operation == "add":
                if len(definition.charts) >= 6:
                    raise ValidationError("A board supports at most six charts.")
                if not intent.metric or not intent.dimension:
                    raise ValidationError("Specify a metric and breakdown for the added chart.")
                definition.charts.append(
                    ChartDefinition(
                        id=str(uuid.uuid4()),
                        title=intent.title or f"{LABELS[intent.metric]} by {intent.dimension}",
                        metric=intent.metric,
                        dimension=intent.dimension,
                        viz=intent.viz
                        or ("line" if intent.dimension in {"day", "month"} else "bar"),
                    )
                )
            else:
                if not target:
                    raise ValidationError(
                        "Select a chart or specify its number before editing.",
                        code="askwiz_clarification",
                    )
                if intent.operation == "remove":
                    definition.charts = [c for c in definition.charts if c.id != target.id]
                    if not definition.charts:
                        raise ValidationError("Keep at least one chart on the board.")
                else:
                    if not any([intent.metric, intent.dimension, intent.viz, intent.title]):
                        raise ValidationError("Specify what to change on the selected chart.")
                    for key in ("metric", "dimension", "viz", "title"):
                        if getattr(intent, key) is not None:
                            setattr(target, key, getattr(intent, key))
                    if (intent.metric or intent.dimension) and not intent.title:
                        target.title = f"{LABELS[target.metric]} by {target.dimension}"
            validate_definition(definition, catalog, scope)
            values = {
                "definition": definition.model_dump(mode="json"),
                "previous": old,
                "revision": revision + 1,
            }
        changed = await self.base._app.execute(
            update(AutoDashboard)
            .where(AutoDashboard.id == row.id, AutoDashboard.revision == revision)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if cast(CursorResult[Any], changed).rowcount != 1:
            raise ConflictError("A newer edit already exists. Reopen the board.")
        await self.base._app.refresh(row)
        return self.view(row, message)

    async def list_saved(self) -> list[BoardView]:
        _, scope = await self.context()
        rows = (
            await self.base._app.scalars(
                select(AutoDashboard)
                .where(
                    AutoDashboard.user_id == self.base._user.id,
                    AutoDashboard.saved.is_(True),
                    AutoDashboard.scope_key == scope.cache_key(),
                )
                .limit(50)
            )
        ).all()
        return [self.view(row) for row in rows]

    def key(self, spec: AnalyticsSpec, daily: bool, scope: RegionScope) -> str:
        data = [
            str(self.base._user.id),
            str(self.base._user.role),
            scope.cache_key(),
            semantic_revision(self.base._settings, Industry.AUTOMOTIVE),
            spec.model_dump(mode="json") | {"viz": "auto"},
            daily,
        ]
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    async def run(self, board_id: uuid.UUID, revision: int, force: bool = False) -> BoardResults:
        _, definition, _, scope = await self.get(board_id, revision)
        started = time.perf_counter()
        original = self.base._analytics
        meter = QueryMeter(original)
        self.base._analytics = cast(AsyncConnection, meter)
        prepared = False
        executed: dict[str, AnalyticsRunResponse] = {}

        # Each query has its own savepoint so one failed SELECT cannot poison the board.
        async def execute(chart_id: str, spec: AnalyticsSpec, daily: bool) -> ChartResult:
            nonlocal prepared
            key = self.key(spec, daily, scope)
            if key in executed:
                return ChartResult(chart_id=chart_id, result=executed[key], cache_hit=True)
            cached = CACHE.get(key)
            if not force and cached and time.monotonic() - cached[0] < 300:
                return ChartResult(
                    chart_id=chart_id, result=cached[1].model_copy(deep=True), cache_hit=True
                )
            remaining = self.base._settings.askwiz_run_timeout_seconds - (
                time.perf_counter() - started
            )
            if remaining <= 0:
                return ChartResult(
                    chart_id=chart_id,
                    error="The board's execution time budget was reached. Retry this chart; completed charts remain available.",
                )
            try:
                if not prepared:
                    await self.base._prepare()
                    prepared = True
                async with asyncio.timeout(remaining):
                    async with original.begin_nested():
                        result = await self.base.run(
                            spec, daily=daily, include_drivers=False, prepare=False
                        )
                result.sql = scope.apply_sql(result.sql, Industry.AUTOMOTIVE)
                if len(result.rows) > 120 and result.chart:
                    result.meta.setdefault("notes", []).append(
                        "The chart displays at most 120 points; inspect or export the data table for the full result."
                    )
                if spec.metrics[0] in {"average_selling_price", "active_salespeople"}:
                    # Never infer totals from nonadditive grouped rows.
                    label = LABELS[spec.metrics[0]]
                    text = f"{label} is shown for each returned group. It is nonadditive; no total or population contribution is inferred from these rows."
                    result.insights = AnalyticsInsights(executive=text, analyst=text)
                if spec.analysis == "top_n":
                    result.meta.setdefault("notes", []).append(
                        "Rankings and any shares refer to the displayed top categories, not the entire population."
                    )
                CACHE[key] = (time.monotonic(), result.model_copy(deep=True))
                executed[key] = result
                CACHE.move_to_end(key)
                while len(CACHE) > 256:
                    CACHE.popitem(last=False)
                return ChartResult(chart_id=chart_id, result=result)
            except NqlError as exc:
                return ChartResult(chart_id=chart_id, error=exc.message)
            except Exception:
                logger.warning("AskWiz chart failed", exc_info=True)
                return ChartResult(
                    chart_id=chart_id,
                    error="This chart could not be loaded. Retry after checking the data connection.",
                )

        try:
            charts = [
                await execute(c.id, chart_spec(c, definition), c.dimension == "day")
                for c in definition.charts
            ]
            # Dedicated aggregates: never sum top-N or distinct/ratio chart rows into KPIs.
            kpis = []
            for prior in (False, True):
                spec = kpi_spec(definition, prior)
                kpis.append(await execute("prior" if prior else "current", spec, False))
        finally:
            self.base._analytics = original
        return BoardResults(
            board_id=board_id,
            revision=revision,
            charts=charts,
            kpis=kpis,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            query_count=meter.count,
            cache_hits=sum(c.cache_hit for c in [*charts, *kpis]),
            computed_at=datetime.now(UTC).isoformat(),
        )

    async def narrate(self, board_id: uuid.UUID, revision: int) -> BoardNarration:
        _, definition, _, scope = await self.get(board_id, revision)
        # Narration is strictly cache-only. It cannot launch a warehouse query.
        facts: list[str] = []
        totals = [
            CACHE.get(self.key(kpi_spec(definition, prior), False, scope))
            for prior in (False, True)
        ]
        current = totals[0]
        previous = totals[1]
        if current and time.monotonic() - current[0] < 300 and current[1].rows:
            row = current[1].rows[0]
            before = (
                previous[1].rows[0]
                if previous and time.monotonic() - previous[0] < 300 and previous[1].rows
                else {}
            )
            for key, label, fmt in (
                ("revenue", "Revenue", "currency"),
                ("units", "Units sold", "integer"),
                ("orders", "Orders", "integer"),
            ):
                facts.append(
                    movement(
                        DashboardMetric(
                            id=key,
                            label=label,
                            format=fmt,
                            current=row.get(key),
                            prior=before.get(key),
                            definition="Governed automotive sales aggregate",
                        )
                    )
                )
        for chart in definition.charts:
            cached = CACHE.get(
                self.key(chart_spec(chart, definition), chart.dimension == "day", scope)
            )
            if cached and time.monotonic() - cached[0] < 300:
                result = cached[1]
                if result.insights and result.rows:
                    facts.append(
                        f"{LABELS[chart.metric]} by {chart.dimension}: {result.insights.executive[:900]}"
                    )
                elif not result.rows:
                    facts.append(
                        f"{LABELS[chart.metric]} by {chart.dimension}: no data matches the requested period and filters."
                    )
        if not facts:
            return BoardNarration(
                revision=revision,
                paragraphs=[],
                ai_used=False,
                limitation="Load current chart results before requesting narration.",
            )
        fingerprint = hashlib.sha256(
            json.dumps(
                [
                    str(self.base._user.id),
                    scope.cache_key(),
                    definition.model_dump(exclude={"charts": {"__all__": {"id", "viz", "title"}}}),
                    facts,
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        cached_story = NARRATIONS.get(fingerprint)
        if cached_story and time.monotonic() - cached_story[0] < 300:
            return cached_story[1].model_copy(
                update={"revision": revision, "llm_calls": 0, "tokens": 0}
            )
        raw = await self.completion(
            "Compose a concise automotive dashboard briefing by selecting and ordering up to three evidence facts. "
            'Return ONLY JSON {"factIds":[0,1,2]}. Select distinct IDs from the supplied facts. '
            "Prefer complementary important observations. Do not compute values or invent explanations. "
            "The service will render the exact verified statements; your role is narrative selection and structure.",
            json.dumps(
                {
                    "period": [definition.start, definition.end],
                    "filters": definition.filters,
                    "facts": dict(enumerate(facts)),
                }
            ),
            180,
        )
        ids = list(range(min(3, len(facts))))
        used = False
        if raw:
            try:
                chosen = json.loads(raw)["factIds"]
                if (
                    isinstance(chosen, list)
                    and 1 <= len(chosen) <= 3
                    and all(type(i) is int and 0 <= i < len(facts) for i in chosen)
                    and len(set(chosen)) == len(chosen)
                ):
                    ids, used = chosen, True
            except (ValueError, KeyError, TypeError):
                pass
        answer = BoardNarration(
            revision=revision,
            paragraphs=[facts[i] for i in ids],
            ai_used=used,
            llm_calls=self.calls,
            tokens=self.tokens,
            limitation=" ".join(self.notes)
            or (
                None
                if used
                else "Showing deterministic evidence; AI narration was unavailable or invalid."
            ),
        )
        NARRATIONS[fingerprint] = (time.monotonic(), answer)
        NARRATIONS.move_to_end(fingerprint)
        while len(NARRATIONS) > 128:
            NARRATIONS.popitem(last=False)
        return answer

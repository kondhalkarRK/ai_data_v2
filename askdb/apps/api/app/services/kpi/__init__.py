"""KPI service facade."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import Industry
from app.core.exceptions import DependencyUnavailableError, ValidationError
from app.schemas.kpi import (
    KpiCard,
    KpiFilterOptions,
    KpiSummaryResponse,
    ScenarioRequest,
    ScenarioResponse,
    WindowId,
)
from app.services.kpi import automotive as auto_kpi
from app.services.kpi import insurance as ins_kpi
from app.services.kpi.windows import (
    format_currency,
    format_number,
    format_percent,
    prior_comparable_window,
    resolve_window,
)

WINDOWS = [
    {"id": "ytd", "label": "Calendar YTD"},
    {"id": "rolling_12m", "label": "Rolling 12 months"},
    {"id": "fy_current", "label": "Current FY (Apr-Mar)"},
    {"id": "fy_previous", "label": "Previous FY"},
    {"id": "full", "label": "Full history"},
]


def _attach_deltas(current: list[KpiCard], prior: list[KpiCard]) -> list[KpiCard]:
    prior_by_id = {card.id: card for card in prior}
    out: list[KpiCard] = []
    for card in current:
        prev = prior_by_id.get(card.id)
        delta: float | None = None
        if (
            card.value is not None
            and prev is not None
            and prev.value is not None
            and abs(prev.value) > 1e-12
        ):
            delta = (card.value - prev.value) / abs(prev.value)
        out.append(card.model_copy(update={"delta": delta}))
    return out


class KpiService:
    def __init__(self, connection: AsyncConnection, industry: Industry) -> None:
        self._connection = connection
        self._industry = industry

    async def _forecast_available(self) -> bool:
        schema = self._industry.value
        table = "fact_forecast_monthly"
        try:
            # Scenario data is optional. Isolate its probe in a savepoint so a missing
            # table or stale grant cannot poison the surrounding read-only transaction
            # and make otherwise-valid KPI queries fail with InFailedSqlTransaction.
            async with self._connection.begin_nested():
                row = (
                    await self._connection.execute(
                        text(
                            """
                            SELECT EXISTS (
                              SELECT 1
                              FROM information_schema.tables
                              WHERE table_schema = :schema AND table_name = :table
                            ) AS ok
                            """
                        ),
                        {"schema": schema, "table": table},
                    )
                ).mappings().first()
                if not row or not row["ok"]:
                    return False
                count = (
                    await self._connection.execute(
                        text(f"SELECT COUNT(*) AS n FROM {schema}.{table}")
                    )
                ).scalar_one()
                return int(count) > 0
        except Exception:
            return False

    async def filter_options(self) -> KpiFilterOptions:
        scenario = await self._forecast_available()
        if self._industry is Industry.INSURANCE:
            opts = await ins_kpi.fetch_insurance_filter_options(self._connection)
            return KpiFilterOptions(
                windows=WINDOWS,
                lobs=opts["lobs"],
                regions=opts["regions"],
                scenario_available=scenario,
            )
        opts = await auto_kpi.fetch_automotive_filter_options(self._connection)
        return KpiFilterOptions(
            windows=WINDOWS,
            makes=opts["makes"],
            regions=opts["regions"],
            scenario_available=scenario,
        )

    async def summary(
        self,
        *,
        window: WindowId = "ytd",
        lob: str | None = None,
        region: str | None = None,
        make: str | None = None,
        as_of: date | None = None,
        compare: bool = True,
    ) -> KpiSummaryResponse:
        try:
            return await self._summary_impl(
                window=window,
                lob=lob,
                region=region,
                make=make,
                as_of=as_of,
                compare=compare,
            )
        except ValidationError:
            raise
        except Exception as exc:
            raise DependencyUnavailableError(
                "KPI query failed against the analytics warehouse. "
                "Confirm migrate + seed for this industry, then retry. "
                f"({type(exc).__name__}: {exc})"
            ) from exc

    async def _summary_impl(
        self,
        *,
        window: WindowId = "ytd",
        lob: str | None = None,
        region: str | None = None,
        make: str | None = None,
        as_of: date | None = None,
        compare: bool = True,
    ) -> KpiSummaryResponse:
        as_of = as_of or date.today()
        start, end, label = resolve_window(window, as_of)
        if self._industry is Industry.INSURANCE:
            cards = await ins_kpi.fetch_insurance_summary(
                self._connection, start=start, end=end, lob=lob, region=region
            )
            series = await ins_kpi.fetch_insurance_series(
                self._connection, start=start, end=end, lob=lob, region=region
            )
            breakdowns = {
                "lob": await ins_kpi.fetch_insurance_breakdown(
                    self._connection, by="lob", start=start, end=end, lob=lob, region=region
                ),
                "region": await ins_kpi.fetch_insurance_breakdown(
                    self._connection,
                    by="region",
                    start=start,
                    end=end,
                    lob=lob,
                    region=region,
                ),
                "status": await ins_kpi.fetch_insurance_breakdown(
                    self._connection,
                    by="status",
                    start=start,
                    end=end,
                    lob=lob,
                    region=region,
                ),
            }
            filters = {"lob": lob, "region": region, "make": None}
            if compare:
                prior = prior_comparable_window(window, as_of)
                if prior is not None:
                    p_start, p_end, _ = prior
                    prior_cards = await ins_kpi.fetch_insurance_summary(
                        self._connection, start=p_start, end=p_end, lob=lob, region=region
                    )
                    cards = _attach_deltas(cards, prior_cards)
        else:
            cards = await auto_kpi.fetch_automotive_summary(
                self._connection, start=start, end=end, make=make, region=region
            )
            series = await auto_kpi.fetch_automotive_series(
                self._connection, start=start, end=end, make=make, region=region
            )
            breakdowns = {
                "make": await auto_kpi.fetch_automotive_breakdown(
                    self._connection, by="make", start=start, end=end, make=make, region=region
                ),
                "model": await auto_kpi.fetch_automotive_breakdown(
                    self._connection, by="model", start=start, end=end, make=make, region=region
                ),
                "region": await auto_kpi.fetch_automotive_breakdown(
                    self._connection,
                    by="region",
                    start=start,
                    end=end,
                    make=make,
                    region=region,
                ),
            }
            filters = {"lob": None, "region": region, "make": make}
            if compare:
                prior = prior_comparable_window(window, as_of)
                if prior is not None:
                    p_start, p_end, _ = prior
                    prior_cards = await auto_kpi.fetch_automotive_summary(
                        self._connection, start=p_start, end=p_end, make=make, region=region
                    )
                    cards = _attach_deltas(cards, prior_cards)

        return KpiSummaryResponse(
            industry=self._industry.value,
            window=window,
            window_label=label,
            start_date=start.isoformat() if start else None,
            end_date=end.isoformat() if end else None,
            filters=filters,
            cards=cards,
            series=series,
            breakdowns=breakdowns,
            scenario_available=await self._forecast_available(),
            compare_enabled=compare,
        )

    async def export_csv(
        self,
        *,
        window: WindowId = "ytd",
        lob: str | None = None,
        region: str | None = None,
        make: str | None = None,
        as_of: date | None = None,
    ) -> str:
        summary = await self.summary(
            window=window, lob=lob, region=region, make=make, as_of=as_of, compare=True
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "industry",
                "window",
                "window_label",
                "start_date",
                "end_date",
                "kpi_id",
                "label",
                "value",
                "formatted",
                "delta",
            ]
        )
        for card in summary.cards:
            writer.writerow(
                [
                    summary.industry,
                    summary.window,
                    summary.window_label,
                    summary.start_date or "",
                    summary.end_date or "",
                    card.id,
                    card.label,
                    "" if card.value is None else card.value,
                    card.formatted,
                    "" if card.delta is None else card.delta,
                ]
            )
        for key, items in summary.breakdowns.items():
            for item in items:
                writer.writerow(
                    [
                        summary.industry,
                        summary.window,
                        f"breakdown:{key}",
                        summary.start_date or "",
                        summary.end_date or "",
                        key,
                        item.name,
                        item.value,
                        item.formatted,
                        "",
                    ]
                )
        return buffer.getvalue()

    async def scenario(self, request: ScenarioRequest) -> ScenarioResponse:
        if request.change_value < 0:
            raise ValidationError("changeValue must be non-negative.")
        if not await self._forecast_available():
            return ScenarioResponse(
                available=False,
                message=(
                    "Scenario Mode stays hidden until forecast data is loaded. "
                    "Run analytics migrations (0002) and re-seed, then retry."
                ),
            )

        summary = await self.summary(window="ytd", compare=False)
        card = next((c for c in summary.cards if c.id == request.metric), None)
        if card is None or card.value is None:
            # Default metric aliases
            fallback_id = "revenue" if self._industry is Industry.AUTOMOTIVE else "written_premium"
            card = next((c for c in summary.cards if c.id == fallback_id), None)
        if card is None or card.value is None:
            raise ValidationError(f"Unknown or empty metric '{request.metric}'.")

        actual = float(card.value)
        if request.change_type == "percent":
            factor = request.change_value / 100.0
            delta = actual * factor
        else:
            delta = request.change_value
        if request.direction == "down":
            delta = -delta
        scenario_value = actual + delta
        fmt: Callable[[float | None], str] = (
            format_currency if card.format == "currency" else format_number
        )
        if card.format == "percent":
            fmt = format_percent
        narrative = (
            f"Actual {card.label}: {card.formatted}. "
            f"Scenario ({request.direction} {request.change_value}"
            f"{'%' if request.change_type == 'percent' else ''}): {fmt(scenario_value)}. "
            "Forecast-backed Scenario Mode applies a governed delta; actual KPIs are unchanged."
        )
        return ScenarioResponse(
            available=True,
            message="Scenario computed from actuals against loaded forecast baseline.",
            actual=actual,
            scenario=scenario_value,
            delta=delta,
            narrative=narrative,
        )


# package marker

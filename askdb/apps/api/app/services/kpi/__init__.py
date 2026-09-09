"""KPI service facade."""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import Industry
from app.core.exceptions import ValidationError
from app.schemas.kpi import (
    KpiFilterOptions,
    KpiSummaryResponse,
    ScenarioRequest,
    ScenarioResponse,
    WindowId,
)
from app.services.kpi import automotive as auto_kpi
from app.services.kpi import insurance as ins_kpi
from app.services.kpi.windows import resolve_window

WINDOWS = [
    {"id": "ytd", "label": "Calendar YTD"},
    {"id": "rolling_12m", "label": "Rolling 12 months"},
    {"id": "fy_current", "label": "Current FY (Apr-Mar)"},
    {"id": "fy_previous", "label": "Previous FY"},
    {"id": "full", "label": "Full history"},
]


class KpiService:
    def __init__(self, connection: AsyncConnection, industry: Industry) -> None:
        self._connection = connection
        self._industry = industry

    async def filter_options(self) -> KpiFilterOptions:
        if self._industry is Industry.INSURANCE:
            opts = await ins_kpi.fetch_insurance_filter_options(self._connection)
            return KpiFilterOptions(
                windows=WINDOWS,
                lobs=opts["lobs"],
                regions=opts["regions"],
                scenario_available=False,
            )
        opts = await auto_kpi.fetch_automotive_filter_options(self._connection)
        return KpiFilterOptions(
            windows=WINDOWS,
            makes=opts["makes"],
            regions=opts["regions"],
            scenario_available=False,
        )

    async def summary(
        self,
        *,
        window: WindowId = "ytd",
        lob: str | None = None,
        region: str | None = None,
        make: str | None = None,
        as_of: date | None = None,
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
            scenario_available=False,
        )

    async def scenario(self, request: ScenarioRequest) -> ScenarioResponse:
        # Scenario Mode stays dormant until forecast tables exist (Phase 4 acceptance).
        if request.change_value < 0:
            raise ValidationError("changeValue must be non-negative.")
        return ScenarioResponse(
            available=False,
            message=(
                "Scenario Mode is hidden until forecast data is loaded. "
                "Actual KPIs are never overwritten."
            ),
        )


# package marker

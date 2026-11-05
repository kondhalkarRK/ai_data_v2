"""Explicit automotive calendar grains; missing periods never become zero."""

from dataclasses import replace

from app.schemas.analytics import AnalyticsSpec
from app.services.analytics.catalog import Catalog, Selection
from app.services.analytics.compiler import MAX_ROWS, BuilderCompileError, BuilderQuery, _Compiler


class CalendarCompiler(_Compiler):
    def __init__(self, spec: AnalyticsSpec, selection: Selection, catalog: Catalog, grain: str):
        if grain not in {"day", "week"} or spec.analysis not in {
            "basic",
            "trend",
            "moving_average",
            "running_total",
        }:
            raise BuilderCompileError("Unsupported calendar operation")
        super().__init__(spec, selection, catalog)
        self.grain = grain
        self.dims = [
            replace(
                d,
                alias=f"sales_{grain}",
                expression=f"date_trunc('{grain}', {{alias}}.sales_date)::date",
                time_grain=grain,
            )
            if d.time_grain == "month"
            else d
            for d in self.dims
        ]
        self.time_dim = next((d for d in self.dims if d.time_grain), None)
        self.cat_dims = [d for d in self.dims if not d.time_grain]
        if not self.time_dim:
            raise BuilderCompileError("A calendar query needs a time dimension")

    def _render_moving_average(self) -> BuilderQuery:
        if self.cat_dims or not self.window or not self.window.start or not self.window.end:
            raise BuilderCompileError(
                "A calendar moving average needs one time dimension and fixed dates"
            )
        periods = self.spec.window
        step = "1 day" if self.grain == "day" else "1 week"
        lookback = (periods - 1) * (1 if self.grain == "day" else 7)
        original = self.window.start
        self.window.start = f"({original} - INTERVAL '{lookback} days')"
        aggregate, _ = self._aggregate()
        self.window.start = original
        assert self.time_dim is not None
        column = self.time_dim.alias
        metric = self.metric.alias
        output = f"moving_avg_{metric}"
        # Calendar spine makes ROWS mean consecutive calendar periods. Any gap
        # makes the average unavailable, rather than a fabricated zero or a
        # shorter denominator. All SQL identifiers originate in the catalog.
        sql = f"""WITH base AS ({aggregate}), calendar AS (  -- governed identifiers and validated dates
 SELECT generate_series(date_trunc('{self.grain}', {original}) - INTERVAL '{lookback} days',
 date_trunc('{self.grain}', {self.window.end} - INTERVAL '1 day'), INTERVAL '{step}')::date AS {column}
), aligned AS (
 SELECT c.{column}, b.{metric} FROM calendar c LEFT JOIN base b USING ({column})
), smoothed AS (
 SELECT *, CASE WHEN COUNT({metric}) OVER w = {periods} THEN AVG({metric}) OVER w END AS {output}
 FROM aligned WINDOW w AS (ORDER BY {column} ROWS BETWEEN {periods - 1} PRECEDING AND CURRENT ROW)
)
SELECT * FROM smoothed WHERE {column} >= date_trunc('{self.grain}', {original})
ORDER BY {column} LIMIT {MAX_ROWS}"""  # noqa: S608 - catalog identifiers; validated dates/window/grain
        query = self._query(sql, f"{periods}-{self.grain} moving average")
        query.value_column = output
        query.overlay_columns = [metric, output]
        query.notes.append(
            "A rolling value is available only when every calendar period in its window has data. Missing periods are not zero."
        )
        return query

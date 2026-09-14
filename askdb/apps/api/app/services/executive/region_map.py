"""Progressive region / dealer / model map endpoints for Performance Analytics."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import Industry
from app.schemas.common import ApiModel
from app.services.kpi.windows import format_currency, format_number


class RegionMapPoint(ApiModel):
    region_id: int
    region_name: str
    city: str | None = None
    state_code: str | None = None
    units_sold: float
    revenue: float
    units_formatted: str
    revenue_formatted: str
    top_make: str | None = None
    top_model: str | None = None
    dealer_count: int = 0
    # Approximate marker placement on the India SVG (0–100 viewBox %).
    x_pct: float
    y_pct: float


class DealerMapRow(ApiModel):
    dealer_id: int
    dealer_name: str
    city: str | None = None
    dealer_grade: str | None = None
    units_sold: float
    revenue: float
    units_formatted: str
    revenue_formatted: str
    top_model: str | None = None
    top_make: str | None = None


class ModelMapRow(ApiModel):
    make: str
    model: str
    car_type: str | None = None
    units_sold: float
    revenue: float
    units_formatted: str
    revenue_formatted: str


# Rough metro placements for seeded automotive hubs (India outline viewBox).
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "new delhi": (34, 28),
    "noida": (36, 29),
    "gurugram": (33, 30),
    "mumbai": (22, 48),
    "pune": (26, 52),
    "bengaluru": (32, 68),
    "hyderabad": (36, 58),
    "chennai": (42, 72),
    "kolkata": (58, 42),
    "ahmedabad": (24, 42),
    "surat": (24, 46),
    "jaipur": (30, 34),
    "lucknow": (42, 32),
    "chandigarh": (34, 24),
    "kochi": (30, 78),
    "indore": (32, 46),
    "nagpur": (38, 48),
    "bhubaneswar": (52, 52),
}


def _coords_for(city: str | None, region_name: str, index: int) -> tuple[float, float]:
    key = (city or "").strip().casefold()
    if key in _CITY_COORDS:
        return _CITY_COORDS[key]
    for token, point in _CITY_COORDS.items():
        if token in key or token in region_name.casefold():
            return point
    # Deterministic fan-out so unknown hubs still render without overlapping.
    return (18 + (index % 8) * 8, 24 + (index // 8) * 10)


async def fetch_region_map(
    connection: AsyncConnection,
    industry: Industry,
    *,
    metric: str = "units",
) -> list[RegionMapPoint]:
    del metric  # Both metrics are always returned; UI chooses the shade.
    if industry is Industry.AUTOMOTIVE:
        return await _automotive_regions(connection)
    return await _insurance_regions(connection)


async def fetch_region_dealers(
    connection: AsyncConnection,
    industry: Industry,
    *,
    region_id: int,
) -> list[DealerMapRow]:
    if industry is not Industry.AUTOMOTIVE:
        return []
    rows = (
        await connection.execute(
            text(
                """
                SELECT d.dealer_id,
                       d.dealer_name,
                       d.city,
                       d.dealer_grade,
                       SUM(f.order_qty) AS units_sold,
                       SUM(f.total_sales) AS revenue
                FROM automotive.fact_sales f
                JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id
                WHERE f.region_id = :region_id
                GROUP BY 1, 2, 3, 4
                ORDER BY SUM(f.order_qty) DESC
                LIMIT 25
                """
            ),
            {"region_id": region_id},
        )
    ).mappings().all()

    out: list[DealerMapRow] = []
    for row in rows:
        top = (
            await connection.execute(
                text(
                    """
                    SELECT c.make, c.model
                    FROM automotive.fact_sales f
                    JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
                    WHERE f.dealer_id = :dealer_id
                    GROUP BY 1, 2
                    ORDER BY SUM(f.order_qty) DESC
                    LIMIT 1
                    """
                ),
                {"dealer_id": int(row["dealer_id"])},
            )
        ).mappings().first()
        units = float(row["units_sold"] or 0)
        revenue = float(row["revenue"] or 0)
        out.append(
            DealerMapRow(
                dealer_id=int(row["dealer_id"]),
                dealer_name=str(row["dealer_name"]),
                city=row["city"],
                dealer_grade=row["dealer_grade"],
                units_sold=units,
                revenue=revenue,
                units_formatted=format_number(units),
                revenue_formatted=format_currency(revenue),
                top_make=str(top["make"]) if top else None,
                top_model=str(top["model"]) if top else None,
            )
        )
    return out


async def fetch_dealer_models(
    connection: AsyncConnection,
    industry: Industry,
    *,
    dealer_id: int,
) -> list[ModelMapRow]:
    if industry is not Industry.AUTOMOTIVE:
        return []
    rows = (
        await connection.execute(
            text(
                """
                SELECT c.make, c.model, c.car_type,
                       SUM(f.order_qty) AS units_sold,
                       SUM(f.total_sales) AS revenue
                FROM automotive.fact_sales f
                JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
                WHERE f.dealer_id = :dealer_id
                GROUP BY 1, 2, 3
                ORDER BY SUM(f.order_qty) DESC
                LIMIT 20
                """
            ),
            {"dealer_id": dealer_id},
        )
    ).mappings().all()
    return [
        ModelMapRow(
            make=str(row["make"]),
            model=str(row["model"]),
            car_type=row["car_type"],
            units_sold=float(row["units_sold"] or 0),
            revenue=float(row["revenue"] or 0),
            units_formatted=format_number(float(row["units_sold"] or 0)),
            revenue_formatted=format_currency(float(row["revenue"] or 0)),
        )
        for row in rows
    ]


async def _automotive_regions(connection: AsyncConnection) -> list[RegionMapPoint]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT r.region_id,
                       r.region_name,
                       r.city,
                       r.state_code,
                       SUM(f.order_qty) AS units_sold,
                       SUM(f.total_sales) AS revenue,
                       COUNT(DISTINCT f.dealer_id) AS dealer_count
                FROM automotive.fact_sales f
                JOIN automotive.dim_region r ON r.region_id = f.region_id
                GROUP BY 1, 2, 3, 4
                ORDER BY SUM(f.order_qty) DESC
                LIMIT 40
                """
            )
        )
    ).mappings().all()

    points: list[RegionMapPoint] = []
    for index, row in enumerate(rows):
        top = (
            await connection.execute(
                text(
                    """
                    SELECT c.make, c.model
                    FROM automotive.fact_sales f
                    JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
                    WHERE f.region_id = :region_id
                    GROUP BY 1, 2
                    ORDER BY SUM(f.order_qty) DESC
                    LIMIT 1
                    """
                ),
                {"region_id": int(row["region_id"])},
            )
        ).mappings().first()
        x, y = _coords_for(row["city"], str(row["region_name"]), index)
        units = float(row["units_sold"] or 0)
        revenue = float(row["revenue"] or 0)
        points.append(
            RegionMapPoint(
                region_id=int(row["region_id"]),
                region_name=str(row["region_name"]),
                city=row["city"],
                state_code=row["state_code"],
                units_sold=units,
                revenue=revenue,
                units_formatted=format_number(units),
                revenue_formatted=format_currency(revenue),
                top_make=str(top["make"]) if top else None,
                top_model=str(top["model"]) if top else None,
                dealer_count=int(row["dealer_count"] or 0),
                x_pct=x,
                y_pct=y,
            )
        )
    return points


async def _insurance_regions(connection: AsyncConnection) -> list[RegionMapPoint]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT r.region_id,
                       r.region_name,
                       r.state_name AS city,
                       NULL::text AS state_code,
                       COUNT(DISTINCT c.claim_id)::float AS units_sold,
                       COALESCE(SUM(c.incurred_amount), 0)::float AS revenue,
                       0 AS dealer_count
                FROM insurance.fact_claims c
                JOIN insurance.dim_region r ON r.region_id = c.region_id
                GROUP BY 1, 2, 3
                ORDER BY 5 DESC
                LIMIT 40
                """
            )
        )
    ).mappings().all()
    points: list[RegionMapPoint] = []
    for index, row in enumerate(rows):
        x, y = _coords_for(row["city"], str(row["region_name"]), index)
        units = float(row["units_sold"] or 0)
        revenue = float(row["revenue"] or 0)
        points.append(
            RegionMapPoint(
                region_id=int(row["region_id"]),
                region_name=str(row["region_name"]),
                city=row["city"],
                state_code=None,
                units_sold=units,
                revenue=revenue,
                units_formatted=format_number(units),
                revenue_formatted=format_currency(revenue),
                dealer_count=0,
                x_pct=x,
                y_pct=y,
            )
        )
    return points

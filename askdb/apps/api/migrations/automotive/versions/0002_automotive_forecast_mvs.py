"""Automotive forecast table + materialized views for expensive rollups.

Revision ID: 0002_automotive_forecast_mvs
Revises: 0001_automotive_schema
"""

from __future__ import annotations

from alembic import op

revision = "0002_automotive_forecast_mvs"
down_revision = "0001_automotive_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automotive.fact_forecast_monthly (
            forecast_id BIGSERIAL PRIMARY KEY,
            sales_month DATE NOT NULL,
            carline_id INTEGER NOT NULL REFERENCES automotive.dim_carline (carline_id),
            region_id INTEGER NOT NULL REFERENCES automotive.dim_region (region_id),
            forecast_revenue NUMERIC(18, 2) NOT NULL DEFAULT 0,
            forecast_units NUMERIC(18, 2) NOT NULL DEFAULT 0,
            CONSTRAINT fact_forecast_month_chk
                CHECK (EXTRACT(DAY FROM sales_month) = 1)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_auto_forecast_month "
        "ON automotive.fact_forecast_monthly (sales_month)"
    )
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS automotive.mv_sales_monthly AS
        SELECT
            date_trunc('month', f.sales_date)::date AS month,
            c.make,
            r.region_name AS region,
            SUM(f.total_sales) AS revenue,
            SUM(f.order_qty) AS units
        FROM automotive.fact_sales f
        JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
        JOIN automotive.dim_region r ON r.region_id = f.region_id
        GROUP BY 1, 2, 3
        WITH NO DATA
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_sales_monthly_uq
        ON automotive.mv_sales_monthly (month, make, region)
        """
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS automotive.mv_sales_monthly")
    op.execute("DROP TABLE IF EXISTS automotive.fact_forecast_monthly")

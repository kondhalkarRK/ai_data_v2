"""Insurance forecast table + materialized views for expensive rollups.

Revision ID: 0002_insurance_forecast_mvs
Revises: 0001_insurance_schema
"""

from __future__ import annotations

from alembic import op

revision = "0002_insurance_forecast_mvs"
down_revision = "0001_insurance_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS insurance.fact_forecast_monthly (
            forecast_id BIGSERIAL PRIMARY KEY,
            accounting_month DATE NOT NULL,
            product_id INTEGER NOT NULL REFERENCES insurance.dim_product (product_id),
            region_id INTEGER REFERENCES insurance.dim_region (region_id),
            forecast_written_premium NUMERIC(18, 2) NOT NULL DEFAULT 0,
            forecast_earned_premium NUMERIC(18, 2) NOT NULL DEFAULT 0,
            forecast_claims_incurred NUMERIC(18, 2) NOT NULL DEFAULT 0,
            CONSTRAINT fact_forecast_month_chk
                CHECK (EXTRACT(DAY FROM accounting_month) = 1)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_forecast_month "
        "ON insurance.fact_forecast_monthly (accounting_month)"
    )
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS insurance.mv_claims_monthly AS
        SELECT
            date_trunc('month', c.reported_date)::date AS month,
            pr.line_of_business AS lob,
            COALESCE(r.region_name, 'Unknown') AS region,
            COUNT(DISTINCT c.claim_id) AS claim_count,
            SUM(c.incurred_amount) AS claims_incurred,
            SUM(c.paid_amount) AS claims_paid
        FROM insurance.fact_claims c
        JOIN insurance.dim_product pr ON pr.product_id = c.product_id
        LEFT JOIN insurance.dim_region r ON r.region_id = c.region_id
        GROUP BY 1, 2, 3
        WITH NO DATA
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_claims_monthly_uq
        ON insurance.mv_claims_monthly (month, lob, region)
        """
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS insurance.mv_claims_monthly")
    op.execute("DROP TABLE IF EXISTS insurance.fact_forecast_monthly")

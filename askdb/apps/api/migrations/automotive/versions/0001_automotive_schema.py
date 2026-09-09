"""Automotive analytics schema: sales star schema.

Revision ID: 0001_automotive_schema
Revises:
Create Date: 2026-09-09

Implements the approved decisions from docs/05-automotive-schema-proposal.md:

- schema ``automotive``
- required ``dealer_id`` on ``fact_sales`` (no region fan-out)
- ``dim_targets.year_month`` as first-of-month ``date``
- indexes sized for keyset pagination and dashboard predicates
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_automotive_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS automotive")
    op.execute(
        """
        CREATE TABLE automotive.dim_region (
            region_id INTEGER PRIMARY KEY,
            region_name TEXT NOT NULL,
            city TEXT NOT NULL,
            state_code TEXT NOT NULL,
            country TEXT NOT NULL DEFAULT 'India'
        )
        """
    )
    op.execute(
        """
        CREATE TABLE automotive.dim_carline (
            carline_id INTEGER PRIMARY KEY,
            carline_name TEXT NOT NULL,
            model TEXT NOT NULL,
            make TEXT NOT NULL,
            car_type TEXT NOT NULL,
            engine_capacity NUMERIC(4,1),
            engine_type TEXT NOT NULL,
            CONSTRAINT dim_carline_engine_type_chk
                CHECK (engine_type IN ('Petrol', 'Diesel', 'Hybrid', 'Electric'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE automotive.dim_color (
            colour_id INTEGER PRIMARY KEY,
            colour_name TEXT NOT NULL,
            rcg_combination TEXT NOT NULL,
            patent_number TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE automotive.dim_salesman (
            sales_person_id INTEGER PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            corp_id TEXT NOT NULL UNIQUE,
            active BOOLEAN NOT NULL DEFAULT TRUE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE automotive.dim_dealer (
            dealer_id INTEGER PRIMARY KEY,
            dealer_code TEXT NOT NULL UNIQUE,
            dealer_name TEXT NOT NULL,
            region_id INTEGER NOT NULL
                REFERENCES automotive.dim_region (region_id),
            city TEXT NOT NULL,
            dealer_grade TEXT NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            CONSTRAINT dim_dealer_grade_chk
                CHECK (dealer_grade IN ('A', 'B', 'C'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE automotive.dim_targets (
            target_id BIGINT PRIMARY KEY,
            year_month DATE NOT NULL,
            make TEXT NOT NULL,
            target_units INTEGER NOT NULL,
            target_revenue NUMERIC(16,2) NOT NULL,
            CONSTRAINT dim_targets_month_chk
                CHECK (year_month = date_trunc('month', year_month)::date),
            CONSTRAINT dim_targets_units_chk CHECK (target_units >= 0),
            CONSTRAINT dim_targets_revenue_chk CHECK (target_revenue >= 0),
            CONSTRAINT dim_targets_make_month_uq UNIQUE (year_month, make)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE automotive.fact_sales (
            order_id BIGINT PRIMARY KEY,
            carline_id INTEGER NOT NULL
                REFERENCES automotive.dim_carline (carline_id),
            colour_id INTEGER NOT NULL
                REFERENCES automotive.dim_color (colour_id),
            sales_person_id INTEGER NOT NULL
                REFERENCES automotive.dim_salesman (sales_person_id),
            region_id INTEGER NOT NULL
                REFERENCES automotive.dim_region (region_id),
            dealer_id INTEGER NOT NULL
                REFERENCES automotive.dim_dealer (dealer_id),
            sales_date DATE NOT NULL,
            order_qty INTEGER NOT NULL,
            price_per_unit NUMERIC(14,2) NOT NULL,
            total_sales NUMERIC(16,2)
                GENERATED ALWAYS AS (order_qty * price_per_unit) STORED,
            CONSTRAINT fact_sales_qty_chk CHECK (order_qty > 0),
            CONSTRAINT fact_sales_price_chk CHECK (price_per_unit >= 0)
        )
        """
    )

    op.execute("CREATE INDEX idx_dim_carline_make_model ON automotive.dim_carline (make, model)")
    op.execute("CREATE INDEX idx_dim_carline_engine_type ON automotive.dim_carline (engine_type)")
    op.execute("CREATE INDEX idx_dim_carline_car_type ON automotive.dim_carline (car_type)")
    op.execute("CREATE INDEX idx_dim_region_name ON automotive.dim_region (region_name)")
    op.execute("CREATE INDEX idx_dim_region_city_state ON automotive.dim_region (city, state_code)")
    op.execute("CREATE INDEX idx_dim_dealer_region ON automotive.dim_dealer (region_id)")
    op.execute(
        "CREATE INDEX idx_dim_targets_make_month ON automotive.dim_targets (make, year_month)"
    )
    op.execute(
        "CREATE INDEX idx_fact_sales_date_order "
        "ON automotive.fact_sales (sales_date DESC, order_id DESC)"
    )
    op.execute(
        "CREATE INDEX idx_fact_sales_carline_date "
        "ON automotive.fact_sales (carline_id, sales_date DESC)"
    )
    op.execute(
        "CREATE INDEX idx_fact_sales_region_date "
        "ON automotive.fact_sales (region_id, sales_date DESC)"
    )
    op.execute(
        "CREATE INDEX idx_fact_sales_dealer_date "
        "ON automotive.fact_sales (dealer_id, sales_date DESC)"
    )
    op.execute(
        "CREATE INDEX idx_fact_sales_salesperson_date "
        "ON automotive.fact_sales (sales_person_id, sales_date DESC)"
    )

    # Reader can SELECT everything created now and anything created later in the schema.
    op.execute("GRANT USAGE ON SCHEMA automotive TO askdb_reader")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA automotive TO askdb_reader")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA automotive GRANT SELECT ON TABLES TO askdb_reader"
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS automotive CASCADE")

"""Grant runtime reader access to Phase 4 forecast objects.

Revision ID: 0003_auto_forecast_grants
Revises: 0002_automotive_forecast_mvs
"""

from __future__ import annotations

from alembic import op

revision = "0003_auto_forecast_grants"
down_revision = "0002_automotive_forecast_mvs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "GRANT SELECT ON automotive.fact_forecast_monthly TO askdb_reader"
    )
    op.execute("GRANT SELECT ON automotive.mv_sales_monthly TO askdb_reader")


def downgrade() -> None:
    op.execute(
        "REVOKE SELECT ON automotive.fact_forecast_monthly FROM askdb_reader"
    )
    op.execute("REVOKE SELECT ON automotive.mv_sales_monthly FROM askdb_reader")

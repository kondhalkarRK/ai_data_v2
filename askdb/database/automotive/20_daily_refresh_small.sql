-- Small daily refresh for the automotive PoC dataset (about 100 orders).
--
-- Adds up to 100 orders dated yesterday, copied from the latest loaded day (active dealers
-- and salespeople only, same vehicle, colour, region, quantity and price), then refreshes the
-- monthly rollup. That brings "Sales Data Freshness" back inside its 36-hour SLA and keeps
-- "Dashboard Revenue Reconciliation" and "Dashboard Rollup Freshness" passing.
--
-- Safe to re-run: it inserts nothing when yesterday is already loaded.
-- Run as askdb_owner on the askdb_automotive database, e.g.
--   psql -U askdb_owner -h localhost -d askdb_automotive -f database/automotive/20_daily_refresh_small.sql
-- or open it in pgAdmin's Query Tool and execute.
-- Then open Data Trust and press "Run checks".

BEGIN;

WITH anchor AS (
    SELECT MAX(sales_date) AS latest, MAX(order_id) AS max_id
    FROM automotive.fact_sales
),
src AS (
    SELECT f.order_id, f.carline_id, f.colour_id, f.sales_person_id, f.region_id,
           f.dealer_id, f.order_qty, f.price_per_unit
    FROM automotive.fact_sales f
    CROSS JOIN anchor
    JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id AND d.active
    JOIN automotive.dim_salesman s ON s.sales_person_id = f.sales_person_id AND s.active
    WHERE f.sales_date = anchor.latest
      AND anchor.latest < CURRENT_DATE - 1
    ORDER BY f.order_id DESC
    LIMIT 100
)
INSERT INTO automotive.fact_sales (
    order_id, carline_id, colour_id, sales_person_id, region_id, dealer_id,
    sales_date, order_qty, price_per_unit
)
SELECT anchor.max_id + ROW_NUMBER() OVER (ORDER BY src.order_id),
       src.carline_id, src.colour_id, src.sales_person_id, src.region_id, src.dealer_id,
       CURRENT_DATE - 1, src.order_qty, src.price_per_unit
FROM src
CROSS JOIN anchor;

REFRESH MATERIALIZED VIEW automotive.mv_sales_monthly;

COMMIT;

ANALYZE automotive.fact_sales;
ANALYZE automotive.mv_sales_monthly;

SELECT MAX(sales_date) AS latest_sale,
       COUNT(*) FILTER (WHERE sales_date = CURRENT_DATE - 1) AS orders_yesterday
FROM automotive.fact_sales;

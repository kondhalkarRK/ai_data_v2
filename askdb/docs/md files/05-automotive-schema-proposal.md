# Automotive PostgreSQL schema

Status: **approved and implemented** (seed scale: **1,000,000** fact rows for now)

Source: `apps/api/semantic/packs/automotive/semantic_model.yaml`. The YAML remains
authoritative; Alembic migration
`apps/api/migrations/automotive/versions/0001_automotive_schema.py` implements it.

## Locked decisions

1. **`dealer_id` is required** on `fact_sales` (no region→dealer fan-out).
2. **`dim_targets.year_month`** is a first-of-month `date`.
3. **India-focused** synthetic makes/models matching the semantic pack narrative.
4. **Generate locally** via `scripts/seed_automotive.py` (do not commit fixtures).
5. **Seed 1M rows now**; raise to 2M later with the same generator (`--rows`).

## Star schema

### `automotive.fact_sales`

Grain: one row per sales order.

- `order_id bigint` primary key
- `carline_id integer` → `dim_carline.carline_id`
- `colour_id integer` → `dim_color.colour_id`
- `sales_person_id integer` → `dim_salesman.sales_person_id`
- `region_id integer` → `dim_region.region_id`
- `dealer_id integer` → `dim_dealer.dealer_id` (**required**)
- `sales_date date`
- `order_qty integer`, positive
- `price_per_unit numeric(14,2)`, non-negative
- `total_sales numeric(16,2)`, generated as `order_qty * price_per_unit`

Rows cover 2019–2026, including a 2020 volume dip, recovery, and rising EV share.

### Dimensions

| Table | Grain | Notes |
| --- | --- | --- |
| `dim_carline` | saleable car line | engine_type ∈ Petrol/Diesel/Hybrid/Electric |
| `dim_color` | paint option | |
| `dim_salesman` | salesperson | unique email + corp_id |
| `dim_region` | territory/city | country default India |
| `dim_dealer` | dealer outlet | grade ∈ A/B/C; city denormalized from region |
| `dim_targets` | make × calendar month | unique `(year_month, make)` |

## Indexes

- `fact_sales (sales_date DESC, order_id DESC)` — keyset pagination
- `fact_sales (carline_id, sales_date DESC)`
- `fact_sales (region_id, sales_date DESC)`
- `fact_sales (dealer_id, sales_date DESC)`
- `fact_sales (sales_person_id, sales_date DESC)`
- `dim_carline (make, model)`, `(engine_type)`, `(car_type)`
- `dim_region (region_name)`, `(city, state_code)`
- `dim_dealer (region_id)`
- `dim_targets (make, year_month)`

## Seed distribution (1M)

| Object | Count |
| --- | --- |
| car lines | 50 (12 India-market makes) |
| colours | 24 |
| salespeople | 500 |
| regions | 50 |
| dealers | 300 |
| monthly targets | makes × 2024-01 … 2026-12 |
| `fact_sales` | **1,000,000** |

## Apply

```bash
cd apps/api
alembic upgrade head                                          # askdb_app
python ../../scripts/migrate.py automotive upgrade head       # askdb_automotive
python ../../scripts/seed_automotive.py --rows 1000000 --replace
python ../../scripts/smoke_automotive_plans.py
```

Migrations and seeds use `AUTOMOTIVE_MIGRATE_DATABASE_URL` (`askdb_owner`).
Runtime queries use `AUTOMOTIVE_DATABASE_URL` (`askdb_reader`).

## EXPLAIN smoke

`scripts/smoke_automotive_plans.py` checks:

1. keyset preview on `(sales_date, order_id)`
2. monthly units/revenue by make (bounded year)
3. dealer performance in one region (bounded year)
4. EV share by year
5. target versus actual by make/month

Acceptance: no full sequential scan of `fact_sales` for bounded/keyset cases at ≥100k
rows, and no `OFFSET` pagination.

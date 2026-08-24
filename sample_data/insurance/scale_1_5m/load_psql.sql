-- Run from this folder in psql (client-side \copy, no server file permission issues):
--   cd sample_data/insurance/scale_1_5m
--   psql -h localhost -U postgres -d askdb_dev -f load_psql.sql

BEGIN;
TRUNCATE TABLE
    insurance.fact_claims,
    insurance.fact_policy_monthly,
    insurance.fact_operating_expense_monthly,
    insurance.dim_policy,
    insurance.dim_agent,
    insurance.dim_product,
    insurance.dim_region
RESTART IDENTITY CASCADE;
COMMIT;

\copy insurance.dim_product FROM 'dim_product.csv' WITH (FORMAT csv, HEADER true, NULL '')
\copy insurance.dim_agent FROM 'dim_agent.csv' WITH (FORMAT csv, HEADER true, NULL '')
\copy insurance.dim_region FROM 'dim_region.csv' WITH (FORMAT csv, HEADER true, NULL '')
\copy insurance.dim_policy FROM 'dim_policy.csv' WITH (FORMAT csv, HEADER true, NULL '')
\copy insurance.fact_policy_monthly FROM 'fact_policy_monthly.csv' WITH (FORMAT csv, HEADER true, NULL '')
\copy insurance.fact_claims (claim_id, claim_number, policy_id, product_id, region_id, loss_date, reported_date, approved_date, settlement_date, claim_status, claim_type, reported_amount, approved_amount, paid_amount, reserve_amount, approved_flag, repudiated_flag, fraud_suspected_flag, catastrophe_code, created_at) FROM 'fact_claims.csv' WITH (FORMAT csv, HEADER true, NULL '')
\copy insurance.fact_operating_expense_monthly FROM 'fact_operating_expense_monthly.csv' WITH (FORMAT csv, HEADER true, NULL '')

ANALYZE insurance.fact_claims;
ANALYZE insurance.fact_policy_monthly;

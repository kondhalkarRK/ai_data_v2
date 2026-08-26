-- ASK-DB 1.5M load — CSV via COPY (fastest easy Postgres path)
-- Connect to askdb_dev as postgres (not askdb_app).
-- pgAdmin Query Tool: COPY FROM works if the service can read this folder.
-- If permission denied, use psql \\copy (client-side) from this directory.

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

COPY insurance.dim_product (
    product_id, product_code, product_name, line_of_business,
    product_family, coverage_type, active_flag
) FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/scale_1_5m/dim_product.csv' WITH (FORMAT csv, HEADER true, NULL '');

COPY insurance.dim_agent (
    agent_id, agent_code, agent_name, channel_name, branch_name, active_flag
) FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/scale_1_5m/dim_agent.csv' WITH (FORMAT csv, HEADER true, NULL '');

COPY insurance.dim_region (
    region_id, region_code, region_name, state_name, country_name
) FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/scale_1_5m/dim_region.csv' WITH (FORMAT csv, HEADER true, NULL '');

COPY insurance.dim_policy (
    policy_id, policy_number, product_id, agent_id, region_id, customer_key,
    inception_date, expiry_date, policy_status, coverage_tier, sum_insured,
    cancelled_flag
) FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/scale_1_5m/dim_policy.csv' WITH (FORMAT csv, HEADER true, NULL '');

COPY insurance.fact_policy_monthly (
    policy_month_id, policy_id, product_id, agent_id, region_id,
    accounting_month, written_premium, earned_premium, exposure_units,
    active_policy_flag, due_for_renewal_flag, renewed_flag
) FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/scale_1_5m/fact_policy_monthly.csv' WITH (FORMAT csv, HEADER true, NULL '');

COPY insurance.fact_claims (
    claim_id, claim_number, policy_id, product_id, region_id,
    loss_date, reported_date, approved_date, settlement_date,
    claim_status, claim_type, reported_amount, approved_amount,
    paid_amount, reserve_amount, approved_flag, repudiated_flag,
    fraud_suspected_flag, catastrophe_code, created_at
) FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/scale_1_5m/fact_claims.csv' WITH (FORMAT csv, HEADER true, NULL '');

COPY insurance.fact_operating_expense_monthly (
    expense_month_id, accounting_month, product_id, region_id,
    acquisition_expense, operating_expense
) FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/scale_1_5m/fact_operating_expense_monthly.csv' WITH (FORMAT csv, HEADER true, NULL '');

SELECT setval(
    pg_get_serial_sequence('insurance.dim_agent', 'agent_id'),
    (SELECT COALESCE(MAX(agent_id), 1) FROM insurance.dim_agent)
);
SELECT setval(
    pg_get_serial_sequence('insurance.dim_policy', 'policy_id'),
    (SELECT COALESCE(MAX(policy_id), 1) FROM insurance.dim_policy)
);
SELECT setval(
    pg_get_serial_sequence('insurance.fact_policy_monthly', 'policy_month_id'),
    (SELECT COALESCE(MAX(policy_month_id), 1) FROM insurance.fact_policy_monthly)
);
SELECT setval(
    pg_get_serial_sequence('insurance.fact_operating_expense_monthly', 'expense_month_id'),
    (SELECT COALESCE(MAX(expense_month_id), 1) FROM insurance.fact_operating_expense_monthly)
);

ANALYZE insurance.dim_policy;
ANALYZE insurance.fact_claims;
ANALYZE insurance.fact_policy_monthly;

COMMIT;

-- Expected: claims 1,500,000  policies 200,000
-- SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'insurance';

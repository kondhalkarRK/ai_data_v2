"""Generate ~1.5M-claim insurance CSVs for PostgreSQL COPY.

Output folder: sample_data/insurance/scale_1_5m/
Format: CSV UTF-8 with header (best for Postgres COPY / \\copy / pgAdmin Import).

Do not import incurred_amount — it is GENERATED ALWAYS in PostgreSQL.

  python sample_data/insurance/_generate_1_5m.py
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
import _generate_40k as g40  # noqa: E402

OUT_DIR = _ROOT / "scale_1_5m"
CHUNK = 250_000
DEFAULT_CLAIMS = 1_500_000
DEFAULT_POLICIES = 200_000
DEFAULT_AGENTS = 400
PREMIUM_SCALE = 1.5  # keeps rolling-12m LR near the 40k narrative after volume mix


def _to_csv(df: pd.DataFrame, path: Path, *, header: bool, mode: str = "w") -> None:
    df.to_csv(path, index=False, header=header, mode=mode, na_rep="")


def _write_sql(out_dir: Path, claims: int, policies: int) -> Path:
    # Forward slashes work in COPY on Windows.
    root = out_dir.resolve().as_posix()
    sql = f"""-- ASK-DB 1.5M load — CSV via COPY (fastest easy Postgres path)
-- Connect to askdb_dev as postgres (not askdb_app).
-- pgAdmin Query Tool: COPY FROM works if the service can read this folder.
-- If permission denied, use psql \\\\copy (client-side) from this directory.

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
) FROM '{root}/dim_product.csv' WITH (FORMAT csv, HEADER true, NULL '');

COPY insurance.dim_agent (
    agent_id, agent_code, agent_name, channel_name, branch_name, active_flag
) FROM '{root}/dim_agent.csv' WITH (FORMAT csv, HEADER true, NULL '');

COPY insurance.dim_region (
    region_id, region_code, region_name, state_name, country_name
) FROM '{root}/dim_region.csv' WITH (FORMAT csv, HEADER true, NULL '');

COPY insurance.dim_policy (
    policy_id, policy_number, product_id, agent_id, region_id, customer_key,
    inception_date, expiry_date, policy_status, coverage_tier, sum_insured,
    cancelled_flag
) FROM '{root}/dim_policy.csv' WITH (FORMAT csv, HEADER true, NULL '');

COPY insurance.fact_policy_monthly (
    policy_month_id, policy_id, product_id, agent_id, region_id,
    accounting_month, written_premium, earned_premium, exposure_units,
    active_policy_flag, due_for_renewal_flag, renewed_flag
) FROM '{root}/fact_policy_monthly.csv' WITH (FORMAT csv, HEADER true, NULL '');

COPY insurance.fact_claims (
    claim_id, claim_number, policy_id, product_id, region_id,
    loss_date, reported_date, approved_date, settlement_date,
    claim_status, claim_type, reported_amount, approved_amount,
    paid_amount, reserve_amount, approved_flag, repudiated_flag,
    fraud_suspected_flag, catastrophe_code, created_at
) FROM '{root}/fact_claims.csv' WITH (FORMAT csv, HEADER true, NULL '');

COPY insurance.fact_operating_expense_monthly (
    expense_month_id, accounting_month, product_id, region_id,
    acquisition_expense, operating_expense
) FROM '{root}/fact_operating_expense_monthly.csv' WITH (FORMAT csv, HEADER true, NULL '');

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

-- Expected: claims {claims:,}  policies {policies:,}
-- SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'insurance';
"""
    path = out_dir / "load_copy.sql"
    path.write_text(sql, encoding="utf-8")
    return path


def _write_psql(out_dir: Path) -> Path:
    body = r"""-- Run from this folder in psql (client-side \copy, no server file permission issues):
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
"""
    path = out_dir / "load_psql.sql"
    path.write_text(body, encoding="utf-8")
    return path


def build_policies(
    rng: np.random.Generator, n: int, products: pd.DataFrame, agents: pd.DataFrame, regions: pd.DataFrame
) -> pd.DataFrame:
    product_ids = products["product_id"].to_numpy()
    region_ids = regions["region_id"].to_numpy()
    agent_ids = agents["agent_id"].to_numpy()
    pid = rng.choice(product_ids, size=n, p=g40.PRODUCT_WEIGHTS)
    rid = rng.choice(region_ids, size=n, p=g40.REGION_WEIGHTS)
    aid = rng.choice(agent_ids, size=n)
    start = date(2023, 7, 1).toordinal()
    end = date(2026, 3, 1).toordinal()
    inc_ord = rng.integers(start, end + 1, size=n)
    epoch = date(1970, 1, 1).toordinal()
    inc = pd.to_datetime(inc_ord - epoch, unit="D")
    term = rng.choice(np.array([12, 12, 12, 24]), size=n, p=[0.55, 0.2, 0.15, 0.1])
    y = inc.year.to_numpy() + (inc.month.to_numpy() - 1 + term) // 12
    m = (inc.month.to_numpy() - 1 + term) % 12 + 1
    expiry = pd.to_datetime({"year": y, "month": m, "day": 1}) - pd.Timedelta(days=1)
    cancelled = rng.random(n) < 0.06
    data_end = pd.Timestamp(g40.DATA_END)
    status = np.where(cancelled, "Cancelled", np.where(expiry < data_end, "Expired", "Active"))
    tier = rng.choice(np.array(["Basic", "Standard", "Premium"]), size=n, p=[0.25, 0.55, 0.20])
    si_base = np.array([g40.SUM_INSURED[int(x)] for x in pid], dtype=float)
    si = np.round(si_base * rng.uniform(0.7, 1.4, size=n), 2)
    pol_id = np.arange(1, n + 1)
    return pd.DataFrame(
        {
            "policy_id": pol_id,
            "policy_number": [f"POL{i:08d}" for i in pol_id],
            "product_id": pid,
            "agent_id": aid,
            "region_id": rid,
            "customer_key": "",
            "inception_date": pd.DatetimeIndex(inc).strftime("%Y-%m-%d"),
            "expiry_date": pd.DatetimeIndex(expiry).strftime("%Y-%m-%d"),
            "policy_status": status,
            "coverage_tier": tier,
            "sum_insured": si,
            "cancelled_flag": cancelled,
        }
    )


def build_policy_monthly(rng: np.random.Generator, policies: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    months = pd.date_range(g40.PREMIUM_WINDOW_START, g40.DATA_END, freq="MS")
    month_ns = months.to_numpy()
    start = np.maximum(
        pd.to_datetime(policies["inception_date"]).dt.to_period("M").dt.to_timestamp().to_numpy(),
        pd.Timestamp(g40.PREMIUM_WINDOW_START).to_datetime64(),
    )
    end = np.minimum(
        pd.to_datetime(policies["expiry_date"]).dt.to_period("M").dt.to_timestamp().to_numpy(),
        pd.Timestamp(g40._month_floor(g40.DATA_END)).to_datetime64(),
    )
    active = (month_ns[None, :] >= start[:, None]) & (month_ns[None, :] <= end[:, None])
    pol_ix, mon_ix = np.nonzero(active)
    n = pol_ix.size
    rec = policies.iloc[pol_ix]
    pid = rec["product_id"].to_numpy()
    tier = rec["coverage_tier"].to_numpy()
    cancelled = rec["cancelled_flag"].to_numpy()
    month = month_ns[mon_ix]
    month_ts = pd.to_datetime(month)
    base = np.array([g40.BASE_MONTHLY_PREMIUM[int(x)] * PREMIUM_SCALE for x in pid])
    tier_mult = np.where(tier == "Basic", 0.85, np.where(tier == "Premium", 1.25, 1.0))
    growth = 1.0 + 0.01 * ((month_ts.year.to_numpy() - 2025) * 12 + month_ts.month.to_numpy())
    lob = products.set_index("product_id")["line_of_business"].reindex(pid).to_numpy()
    season = np.ones(n)
    motor = lob == "Motor"
    health = lob == "Health"
    mth = month_ts.month.to_numpy()
    season = np.where(motor & np.isin(mth, [4, 5, 6]), 1.04, season)
    season = np.where(health & np.isin(mth, [10, 11, 12, 1]), 1.06, season)
    written = np.round(base * tier_mult * growth * season * rng.uniform(0.92, 1.08, size=n), 2)
    earned = np.round(written * rng.uniform(0.88, 0.98, size=n), 2)
    exposure = np.round(rng.uniform(0.85, 1.0, size=n), 6)
    last_mon = np.zeros(n, dtype=bool)
    if n:
        last_mon = np.append(pol_ix[1:] != pol_ix[:-1], True)
    due = last_mon & (~cancelled.astype(bool))
    renewed = np.array([None] * n, dtype=object)
    if due.any():
        late = month_ts < pd.Timestamp("2026-04-01")
        p = np.where(late, 0.78, 0.75)
        draw = rng.random(n) < p
        renewed[due] = draw[due]
    return pd.DataFrame(
        {
            "policy_month_id": np.arange(1, n + 1),
            "policy_id": rec["policy_id"].to_numpy(),
            "product_id": pid,
            "agent_id": rec["agent_id"].to_numpy(),
            "region_id": rec["region_id"].to_numpy(),
            "accounting_month": month_ts.strftime("%Y-%m-%d"),
            "written_premium": written,
            "earned_premium": earned,
            "exposure_units": exposure,
            "active_policy_flag": ~cancelled.astype(bool),
            "due_for_renewal_flag": due,
            "renewed_flag": renewed,
        }
    )


def _claim_chunk(
    rng: np.random.Generator,
    start_id: int,
    n: int,
    eligible: pd.DataFrame,
    weights: np.ndarray,
    products: pd.DataFrame,
    regions: pd.DataFrame,
) -> pd.DataFrame:
    pick = rng.choice(len(eligible), size=n, p=weights)
    rec = eligible.iloc[pick]
    product_id = rec["product_id"].to_numpy()
    region_id = rec["region_id"].to_numpy()
    policy_id = rec["policy_id"].to_numpy()
    lob_map = dict(zip(products["product_id"], products["line_of_business"]))
    region_map = dict(zip(regions["region_id"], regions["region_name"]))
    lob = np.array([lob_map[int(x)] for x in product_id])
    region_name = np.array([region_map[int(x)] for x in region_id])
    inception = pd.to_datetime(rec["inception_date"]).to_numpy()
    expiry = pd.to_datetime(rec["expiry_date"]).to_numpy()
    loss_start = np.maximum(inception, np.datetime64(str(g40.DATA_START)))
    loss_end = np.minimum(expiry, np.datetime64(str(g40.DATA_END)))
    span = (loss_end - loss_start).astype("timedelta64[D]").astype(np.int64)
    span = np.maximum(span, 0)
    loss = loss_start + (rng.integers(0, np.maximum(span, 0) + 1, size=n)).astype("timedelta64[D]")
    q2s, q2e = np.datetime64("2026-04-01"), np.datetime64("2026-06-30")
    q2_ok = (lob == "Motor") & (loss_start <= q2e) & (loss_end >= q2s) & (rng.random(n) < 0.22)
    q2_lo = np.maximum(loss_start, q2s)
    q2_hi = np.minimum(loss_end, q2e)
    q2_span = np.maximum((q2_hi - q2_lo).astype("timedelta64[D]").astype(np.int64), 0)
    q2_loss = q2_lo + rng.integers(0, q2_span + 1, size=n).astype("timedelta64[D]")
    loss = np.where(q2_ok, q2_loss, loss)
    report_lag = rng.integers(0, 12, size=n)
    reported = np.minimum(
        loss + report_lag.astype("timedelta64[D]"),
        np.datetime64("2026-07-15"),
    )
    status = rng.choice(g40.CLAIM_STATUSES, size=n, p=g40.CLAIM_STATUS_P)
    loss_month = pd.to_datetime(loss).to_period("M").to_timestamp()
    mult = np.ones(n)
    loss_d = pd.to_datetime(loss)
    motor = lob == "Motor"
    q2 = (loss_d >= "2026-04-01") & (loss_d <= "2026-06-30")
    q1 = (loss_d >= "2026-01-01") & (loss_d <= "2026-03-31")
    west_north = np.isin(region_name, ["West", "North"])
    mult = np.where(motor & q2, 1.35, mult)
    mult = np.where(motor & q2 & west_north, mult * 1.18, mult)
    mult = np.where(motor & q1, 1.08, mult)
    mult = np.where((lob == "Health") & q2, 1.08, mult)
    mult = np.where((lob == "Property") & q2, 0.95, mult)
    base_sev = np.array([g40.BASE_SEVERITY[int(x)] for x in product_id]) * mult
    reported_amount = np.round(np.maximum(1000.0, rng.lognormal(np.log(np.maximum(base_sev, 1.0)), 0.55)), 2)
    approved_flag = np.isin(status, ["Approved", "Settled"])
    repudiated_flag = status == "Repudiated"
    fraud = rng.random(n) < np.where(status == "Under Review", 0.06, 0.02)
    approved_amount = np.zeros(n)
    paid_amount = np.zeros(n)
    reserve_amount = np.zeros(n)
    open_m = status == "Open"
    ur_m = status == "Under Review"
    ap_m = status == "Approved"
    se_m = status == "Settled"
    reserve_amount[open_m] = np.round(reported_amount[open_m] * rng.uniform(0.6, 1.0, size=open_m.sum()), 2)
    reserve_amount[ur_m] = np.round(reported_amount[ur_m] * rng.uniform(0.5, 0.95, size=ur_m.sum()), 2)
    approved_amount[ap_m] = np.round(reported_amount[ap_m] * rng.uniform(0.75, 1.0, size=ap_m.sum()), 2)
    reserve_amount[ap_m] = np.round(approved_amount[ap_m] * rng.uniform(0.3, 0.8, size=ap_m.sum()), 2)
    paid_amount[ap_m] = np.round(approved_amount[ap_m] - reserve_amount[ap_m], 2)
    approved_amount[se_m] = np.round(reported_amount[se_m] * rng.uniform(0.7, 1.0, size=se_m.sum()), 2)
    paid_amount[se_m] = approved_amount[se_m]
    types = np.empty(n, dtype=object)
    for lb, options in g40.CLAIM_TYPES.items():
        mask = lob == lb
        if mask.any():
            types[mask] = rng.choice(np.array(options, dtype=object), size=int(mask.sum()))
    claim_type = types
    cat = np.array([None] * n, dtype=object)
    wx = (lob == "Motor") & (claim_type == "Weather") & (rng.random(n) < 0.35)
    cat[wx] = "WX-2026-Q2"
    px = (lob == "Property") & np.isin(claim_type, ["Flood", "Storm"]) & (rng.random(n) < 0.2)
    cat[px] = "WX-2026-Q2"
    reported_ts = pd.to_datetime(reported)
    loss_ts = pd.to_datetime(loss)
    appr_lag = rng.integers(3, 20, size=n)
    set_lag = rng.integers(8, 35, size=n)
    slow = motor & west_north & np.asarray(q2)
    set_lag = set_lag + np.where(slow, rng.integers(3, 10, size=n), 0)
    approved_date = np.array([None] * n, dtype=object)
    settlement_date = np.array([None] * n, dtype=object)
    need_ap = repudiated_flag | ap_m | se_m
    approved_date[need_ap] = (reported_ts[need_ap] + pd.to_timedelta(appr_lag[need_ap], unit="D")).strftime("%Y-%m-%d")
    if se_m.any():
        settlement_date[se_m] = (reported_ts[se_m] + pd.to_timedelta(set_lag[se_m], unit="D")).strftime("%Y-%m-%d")
    cid = np.arange(start_id, start_id + n)
    created = reported_ts + pd.to_timedelta(rng.integers(1, 48, size=n), unit="h")
    return pd.DataFrame(
        {
            "claim_id": cid,
            "claim_number": [f"CLM{i:08d}" for i in cid],
            "policy_id": policy_id,
            "product_id": product_id,
            "region_id": region_id,
            "loss_date": loss_ts.strftime("%Y-%m-%d"),
            "reported_date": reported_ts.strftime("%Y-%m-%d"),
            "approved_date": approved_date,
            "settlement_date": settlement_date,
            "claim_status": status,
            "claim_type": claim_type,
            "reported_amount": reported_amount,
            "approved_amount": approved_amount,
            "paid_amount": paid_amount,
            "reserve_amount": reserve_amount,
            "approved_flag": approved_flag,
            "repudiated_flag": repudiated_flag,
            "fraud_suspected_flag": fraud,
            "catastrophe_code": cat,
            "created_at": created.strftime("%Y-%m-%dT%H:%M:%S") + "+05:30",
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claims", type=int, default=DEFAULT_CLAIMS)
    parser.add_argument("--policies", type=int, default=DEFAULT_POLICIES)
    parser.add_argument("--agents", type=int, default=DEFAULT_AGENTS)
    parser.add_argument("--seed", type=int, default=g40.SEED)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating scale CSVs -> {OUT_DIR}")
    print(f"  claims={args.claims:,} policies={args.policies:,} agents={args.agents}")

    dims = g40.build_dims(rng, args.agents)
    policies = build_policies(rng, args.policies, dims["dim_product"], dims["dim_agent"], dims["dim_region"])
    n = len(policies)
    cust = rng.integers(1, max(n // 2, 2), size=n)
    policies["customer_key"] = [f"CUST{int(x):07d}" for x in cust]

    print("  policy months...")
    monthly = build_policy_monthly(rng, policies, dims["dim_product"])
    expenses = g40.build_expenses(rng, dims["dim_product"], dims["dim_region"])

    _to_csv(dims["dim_product"], OUT_DIR / "dim_product.csv", header=True)
    _to_csv(dims["dim_agent"], OUT_DIR / "dim_agent.csv", header=True)
    _to_csv(dims["dim_region"], OUT_DIR / "dim_region.csv", header=True)
    _to_csv(policies, OUT_DIR / "dim_policy.csv", header=True)
    _to_csv(monthly, OUT_DIR / "fact_policy_monthly.csv", header=True)
    _to_csv(expenses, OUT_DIR / "fact_operating_expense_monthly.csv", header=True)

    eligible = policies.loc[~policies["cancelled_flag"].astype(bool)].copy()
    inc = pd.to_datetime(eligible["inception_date"])
    exp = pd.to_datetime(eligible["expiry_date"])
    overlap = (inc <= pd.Timestamp(g40.DATA_END)) & (exp >= pd.Timestamp(g40.DATA_START))
    eligible = eligible.loc[overlap].reset_index(drop=True)
    weights = np.array([g40.PRODUCT_WEIGHTS[int(p) - 1] for p in eligible["product_id"]], dtype=float)
    weights = weights / weights.sum()

    claims_path = OUT_DIR / "fact_claims.csv"
    written = 0
    first = True
    while written < args.claims:
        n_chunk = min(CHUNK, args.claims - written)
        print(f"  claims {written + 1:,}-{written + n_chunk:,}")
        chunk = _claim_chunk(
            rng, written + 1, n_chunk, eligible, weights, dims["dim_product"], dims["dim_region"]
        )
        _to_csv(chunk, claims_path, header=first, mode="w" if first else "a")
        first = False
        written += n_chunk

    _write_sql(OUT_DIR, args.claims, args.policies)
    _write_psql(OUT_DIR)
    print("\nFiles:")
    for p in sorted(OUT_DIR.glob("*")):
        mb = p.stat().st_size / 1_048_576
        print(f"  {p.name:42s} {mb:8.1f} MB")
    print(f"\n  dim_policy rows: {len(policies):,}")
    print(f"  fact_policy_monthly rows: {len(monthly):,}")
    print(f"  fact_claims rows: {args.claims:,}")
    print(f"  expenses rows: {len(expenses):,}")
    print("\nLoad with CSV COPY (not Excel, not JSON):")
    print(f"  pgAdmin: open {OUT_DIR / 'load_copy.sql'} as postgres on askdb_dev")
    print("  or psql:  cd scale_1_5m  then  psql -U postgres -d askdb_dev -f load_psql.sql")


if __name__ == "__main__":
    main()

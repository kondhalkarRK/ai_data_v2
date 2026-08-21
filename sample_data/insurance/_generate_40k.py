"""
Generate synthetic India P&C insurance CSVs for the ASK-DB PostgreSQL pilot.

Output (same folder):
  dim_product.csv
  dim_agent.csv
  dim_region.csv
  dim_policy.csv
  fact_policy_monthly.csv
  fact_claims.csv
  fact_operating_expense_monthly.csv

Targets (defaults):
  ~10 products, 4 regions, ~120 agents, ~8k policies,
  ~40k claims, policy-month rows for the active window,
  expense rows by product x region x month.

Narrative knobs (aligned with CFO Q1/Q2 2026 decks):
  - Motor is the largest LOB
  - Q2 2026 Motor severity/frequency rises, especially West and North
  - Overall loss ratio lands near the mid-60%s on a rolling 12-month basis

Run:
  python sample_data/insurance/_generate_40k.py

Optional:
  python sample_data/insurance/_generate_40k.py --claims 40000 --policies 8000
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parent
SEED = 42

DATA_START = date(2024, 1, 1)
DATA_END = date(2026, 6, 30)
PREMIUM_WINDOW_START = date(2025, 1, 1)  # keep policy-month file manageable

CLAIM_STATUSES = np.array(
    ["Open", "Approved", "Settled", "Repudiated", "Under Review"], dtype=object
)
CLAIM_STATUS_P = np.array([0.12, 0.18, 0.52, 0.10, 0.08])

CLAIM_TYPES = {
    "Motor": ["Own Damage", "Third Party", "Theft", "Weather", "Glass"],
    "Health": ["Hospitalization", "Day Care", "OPD", "Critical Illness"],
    "Property": ["Fire", "Burglary", "Flood", "Storm", "Accidental Damage"],
}

PRODUCTS = [
    # product_id, code, name, lob, family, coverage
    (1, "MOT-COMP", "Motor Comprehensive", "Motor", "Private Car", "Comprehensive"),
    (2, "MOT-OD", "Motor Own Damage", "Motor", "Private Car", "Own Damage"),
    (3, "MOT-TP", "Motor Third Party", "Motor", "Private Car", "Third Party"),
    (4, "MOT-CV", "Commercial Vehicle Package", "Motor", "Commercial", "Package"),
    (5, "HLT-IND", "Health Individual", "Health", "Retail Health", "Individual"),
    (6, "HLT-FAM", "Health Family Floater", "Health", "Retail Health", "Family"),
    (7, "HLT-GRP", "Group Health", "Health", "Group Health", "Group"),
    (8, "PRP-FIR", "Property Fire", "Property", "Commercial Property", "Fire"),
    (9, "PRP-PKG", "Property Package", "Property", "SME Property", "Package"),
    (10, "PRP-BUR", "Property Burglary", "Property", "SME Property", "Burglary"),
]

REGIONS = [
    # region_id, code, name, state
    (1, "WST", "West", "Maharashtra"),
    (2, "NTH", "North", "Delhi"),
    (3, "STH", "South", "Karnataka"),
    (4, "EST", "East", "West Bengal"),
]

# Relative policy volume by product (Motor heavy)
PRODUCT_WEIGHTS = np.array(
    [0.28, 0.12, 0.10, 0.08, 0.12, 0.10, 0.05, 0.06, 0.06, 0.03], dtype=float
)
REGION_WEIGHTS = np.array([0.30, 0.27, 0.25, 0.18], dtype=float)

# Base monthly premium (INR) and claim severity by product
# Sized so rolling-12m earned premium keeps portfolio loss ratio near ~60–70%
# with 40k claims (see CSV check printed at end of run).
BASE_MONTHLY_PREMIUM = {
    1: 28_000.0,
    2: 20_000.0,
    3: 12_000.0,
    4: 42_000.0,
    5: 22_000.0,
    6: 34_000.0,
    7: 50_000.0,
    8: 62_000.0,
    9: 78_000.0,
    10: 40_000.0,
}
BASE_SEVERITY = {
    1: 42000.0,
    2: 38000.0,
    3: 55000.0,
    4: 72000.0,
    5: 28000.0,
    6: 32000.0,
    7: 26000.0,
    8: 85000.0,
    9: 95000.0,
    10: 45000.0,
}
SUM_INSURED = {
    1: 650_000,
    2: 550_000,
    3: 1_500_000,
    4: 1_200_000,
    5: 500_000,
    6: 800_000,
    7: 400_000,
    8: 5_000_000,
    9: 7_500_000,
    10: 2_000_000,
}

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan",
    "Krishna", "Ishaan", "Ananya", "Aadhya", "Diya", "Pari", "Myra", "Anika",
    "Ira", "Sara", "Navya", "Kiara", "Rohan", "Kabir", "Dev", "Yash", "Nikhil",
]
LAST_NAMES = [
    "Sharma", "Patel", "Singh", "Gupta", "Reddy", "Nair", "Iyer", "Khan",
    "Mehta", "Joshi", "Chopra", "Desai", "Kulkarni", "Banerjee", "Das",
]
CHANNELS = ["Agency", "Broker", "Bancassurance", "Direct Digital", "Corporate"]
BRANCHES = {
    "West": ["Mumbai Central", "Pune East", "Ahmedabad"],
    "North": ["Delhi South", "Jaipur", "Chandigarh"],
    "South": ["Bengaluru", "Chennai", "Hyderabad"],
    "East": ["Kolkata", "Bhubaneswar", "Patna"],
}


def _month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


def _month_range(start: date, end: date) -> list[date]:
    cur = _month_floor(start)
    end_m = _month_floor(end)
    out: list[date] = []
    while cur <= end_m:
        out.append(cur)
        cur = _add_months(cur, 1)
    return out


def _random_date(rng: np.random.Generator, start: date, end: date) -> date:
    span = (end - start).days
    return start + timedelta(days=int(rng.integers(0, span + 1)))


def build_dims(rng: np.random.Generator, n_agents: int) -> dict[str, pd.DataFrame]:
    products = pd.DataFrame(
        [
            {
                "product_id": p[0],
                "product_code": p[1],
                "product_name": p[2],
                "line_of_business": p[3],
                "product_family": p[4],
                "coverage_type": p[5],
                "active_flag": True,
            }
            for p in PRODUCTS
        ]
    )

    regions = pd.DataFrame(
        [
            {
                "region_id": r[0],
                "region_code": r[1],
                "region_name": r[2],
                "state_name": r[3],
                "country_name": "India",
            }
            for r in REGIONS
        ]
    )

    region_ids = regions["region_id"].to_numpy()
    region_names = dict(zip(regions["region_id"], regions["region_name"]))
    agents = []
    for i in range(1, n_agents + 1):
        region_id = int(rng.choice(region_ids, p=REGION_WEIGHTS))
        region_name = region_names[region_id]
        agents.append(
            {
                "agent_id": i,
                "agent_code": f"AG{i:04d}",
                "agent_name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                "channel_name": str(rng.choice(CHANNELS)),
                "branch_name": str(rng.choice(BRANCHES[region_name])),
                "active_flag": bool(rng.random() > 0.05),
            }
        )
    agents_df = pd.DataFrame(agents)
    return {"dim_product": products, "dim_region": regions, "dim_agent": agents_df}


def build_policies(
    rng: np.random.Generator,
    n_policies: int,
    products: pd.DataFrame,
    agents: pd.DataFrame,
    regions: pd.DataFrame,
) -> pd.DataFrame:
    product_ids = products["product_id"].to_numpy()
    region_ids = regions["region_id"].to_numpy()
    agent_ids = agents["agent_id"].to_numpy()

    rows = []
    for policy_id in range(1, n_policies + 1):
        product_id = int(rng.choice(product_ids, p=PRODUCT_WEIGHTS))
        region_id = int(rng.choice(region_ids, p=REGION_WEIGHTS))
        agent_id = int(rng.choice(agent_ids))
        # Bias inception so many policies are active through 2025–mid 2026
        inception = _random_date(rng, date(2023, 7, 1), date(2026, 3, 1))
        term_months = int(rng.choice([12, 12, 12, 24], p=[0.55, 0.2, 0.15, 0.1]))
        expiry = _add_months(_month_floor(inception), term_months) - timedelta(days=1)
        cancelled = bool(rng.random() < 0.06)
        if cancelled:
            status = "Cancelled"
        elif expiry < DATA_END:
            status = "Expired"
        else:
            status = "Active"
        tier = str(rng.choice(["Basic", "Standard", "Premium"], p=[0.25, 0.55, 0.20]))
        si_base = SUM_INSURED[product_id]
        si = float(np.round(si_base * rng.uniform(0.7, 1.4), 2))
        rows.append(
            {
                "policy_id": policy_id,
                "policy_number": f"POL{policy_id:08d}",
                "product_id": product_id,
                "agent_id": agent_id,
                "region_id": region_id,
                "customer_key": f"CUST{rng.integers(1, n_policies // 2 + 1):07d}",
                "inception_date": inception.isoformat(),
                "expiry_date": expiry.isoformat(),
                "policy_status": status,
                "coverage_tier": tier,
                "sum_insured": si,
                "cancelled_flag": cancelled,
            }
        )
    return pd.DataFrame(rows)


def build_policy_monthly(
    rng: np.random.Generator, policies: pd.DataFrame, products: pd.DataFrame
) -> pd.DataFrame:
    lob_by_product = dict(zip(products["product_id"], products["line_of_business"]))
    rows: list[dict] = []
    policy_month_id = 1

    for rec in policies.itertuples(index=False):
        inception = date.fromisoformat(rec.inception_date)
        expiry = date.fromisoformat(rec.expiry_date)
        start = max(_month_floor(inception), PREMIUM_WINDOW_START)
        end = min(_month_floor(expiry), _month_floor(DATA_END))
        if start > end:
            continue

        base = BASE_MONTHLY_PREMIUM[int(rec.product_id)]
        tier_mult = {"Basic": 0.85, "Standard": 1.0, "Premium": 1.25}[rec.coverage_tier]
        lob = lob_by_product[int(rec.product_id)]

        months = _month_range(start, end)
        for i, month in enumerate(months):
            # Mild growth + LOB seasonality
            growth = 1.0 + 0.01 * ((month.year - 2025) * 12 + month.month)
            season = 1.0
            if lob == "Motor" and month.month in (4, 5, 6):
                season = 1.04
            if lob == "Health" and month.month in (10, 11, 12, 1):
                season = 1.06

            written = float(np.round(base * tier_mult * growth * season * rng.uniform(0.92, 1.08), 2))
            earned = float(np.round(written * rng.uniform(0.88, 0.98), 2))
            exposure = float(np.round(rng.uniform(0.85, 1.0), 6))

            due = bool(i == len(months) - 1 and not rec.cancelled_flag)
            renewed = None
            if due:
                renewed = bool(rng.random() < (0.78 if month < date(2026, 4, 1) else 0.75))

            rows.append(
                {
                    "policy_month_id": policy_month_id,
                    "policy_id": int(rec.policy_id),
                    "product_id": int(rec.product_id),
                    "agent_id": int(rec.agent_id),
                    "region_id": int(rec.region_id),
                    "accounting_month": month.isoformat(),
                    "written_premium": written,
                    "earned_premium": earned,
                    "exposure_units": exposure,
                    "active_policy_flag": not rec.cancelled_flag,
                    "due_for_renewal_flag": due,
                    "renewed_flag": renewed,
                }
            )
            policy_month_id += 1

    return pd.DataFrame(rows)


def _severity_multiplier(
    lob: str, region_name: str, loss_month: date
) -> float:
    """Encode Q2 2026 Motor deterioration in West/North (CFO demo story)."""
    mult = 1.0
    if lob == "Motor":
        if date(2026, 4, 1) <= loss_month <= date(2026, 6, 30):
            mult *= 1.35
            if region_name in ("West", "North"):
                mult *= 1.18
        elif date(2026, 1, 1) <= loss_month <= date(2026, 3, 31):
            mult *= 1.08
    elif lob == "Health" and date(2026, 4, 1) <= loss_month <= date(2026, 6, 30):
        mult *= 1.08
    elif lob == "Property" and date(2026, 4, 1) <= loss_month <= date(2026, 6, 30):
        mult *= 0.95
    return mult


def build_claims(
    rng: np.random.Generator,
    n_claims: int,
    policies: pd.DataFrame,
    products: pd.DataFrame,
    regions: pd.DataFrame,
) -> pd.DataFrame:
    lob_by_product = dict(zip(products["product_id"], products["line_of_business"]))
    region_name_by_id = dict(zip(regions["region_id"], regions["region_name"]))

    # Prefer policies with overlap in the claim window
    eligible = []
    for rec in policies.itertuples(index=False):
        inception = date.fromisoformat(rec.inception_date)
        expiry = date.fromisoformat(rec.expiry_date)
        start = max(inception, DATA_START)
        end = min(expiry, DATA_END)
        if start <= end and not rec.cancelled_flag:
            eligible.append(rec)
    if not eligible:
        raise RuntimeError("No eligible policies for claims generation")

    # Weight Motor policies higher so Motor drives portfolio volatility
    weights = np.array(
        [PRODUCT_WEIGHTS[int(r.product_id) - 1] for r in eligible], dtype=float
    )
    weights = weights / weights.sum()

    # Extra Q2 2026 Motor claim pressure via loss-date sampling
    claim_rows = []
    for claim_id in range(1, n_claims + 1):
        rec = eligible[int(rng.choice(len(eligible), p=weights))]
        product_id = int(rec.product_id)
        region_id = int(rec.region_id)
        lob = lob_by_product[product_id]
        region_name = region_name_by_id[region_id]

        inception = date.fromisoformat(rec.inception_date)
        expiry = date.fromisoformat(rec.expiry_date)
        loss_start = max(inception, DATA_START)
        loss_end = min(expiry, DATA_END)

        # Bias ~22% of Motor claims into Q2 2026 when policy covers it
        q2_start, q2_end = date(2026, 4, 1), date(2026, 6, 30)
        use_q2 = (
            lob == "Motor"
            and loss_start <= q2_end
            and loss_end >= q2_start
            and rng.random() < 0.22
        )
        if use_q2:
            loss_date = _random_date(rng, max(loss_start, q2_start), min(loss_end, q2_end))
        else:
            loss_date = _random_date(rng, loss_start, loss_end)

        report_lag = int(rng.integers(0, 12))
        reported = min(loss_date + timedelta(days=report_lag), DATA_END + timedelta(days=15))
        status = str(rng.choice(CLAIM_STATUSES, p=CLAIM_STATUS_P))

        base_sev = BASE_SEVERITY[product_id] * _severity_multiplier(
            lob, region_name, _month_floor(loss_date)
        )
        reported_amount = float(np.round(max(1000.0, rng.lognormal(np.log(base_sev), 0.55)), 2))

        approved_flag = status in ("Approved", "Settled")
        repudiated_flag = status == "Repudiated"
        fraud = bool(rng.random() < (0.06 if status == "Under Review" else 0.02))

        approved_amount = 0.0
        paid_amount = 0.0
        reserve_amount = 0.0
        approved_date = None
        settlement_date = None

        if repudiated_flag:
            approved_amount = 0.0
            reserve_amount = 0.0
            approved_date = (reported + timedelta(days=int(rng.integers(5, 25)))).isoformat()
        elif status == "Open":
            reserve_amount = float(np.round(reported_amount * rng.uniform(0.6, 1.0), 2))
        elif status == "Under Review":
            reserve_amount = float(np.round(reported_amount * rng.uniform(0.5, 0.95), 2))
        elif status == "Approved":
            approved_amount = float(np.round(reported_amount * rng.uniform(0.75, 1.0), 2))
            reserve_amount = float(np.round(approved_amount * rng.uniform(0.3, 0.8), 2))
            paid_amount = float(np.round(approved_amount - reserve_amount, 2))
            approved_date = (reported + timedelta(days=int(rng.integers(3, 20)))).isoformat()
        else:  # Settled
            approved_amount = float(np.round(reported_amount * rng.uniform(0.7, 1.0), 2))
            paid_amount = approved_amount
            reserve_amount = 0.0
            settle_lag = int(rng.integers(8, 35))
            # Q2 Motor West/North slightly slower settlement (CFO story)
            if (
                lob == "Motor"
                and region_name in ("West", "North")
                and date(2026, 4, 1) <= loss_date <= date(2026, 6, 30)
            ):
                settle_lag += int(rng.integers(3, 10))
            approved_date = (reported + timedelta(days=int(rng.integers(2, 12)))).isoformat()
            settlement_date = (reported + timedelta(days=settle_lag)).isoformat()

        claim_type = str(rng.choice(CLAIM_TYPES[lob]))
        catastrophe_code = None
        if lob == "Motor" and claim_type == "Weather" and rng.random() < 0.35:
            catastrophe_code = "WX-2026-Q2"
        elif lob == "Property" and claim_type in ("Flood", "Storm") and rng.random() < 0.2:
            catastrophe_code = "WX-2026-Q2"

        claim_rows.append(
            {
                "claim_id": claim_id,
                "claim_number": f"CLM{claim_id:08d}",
                "policy_id": int(rec.policy_id),
                "product_id": product_id,
                "region_id": region_id,
                "loss_date": loss_date.isoformat(),
                "reported_date": reported.isoformat(),
                "approved_date": approved_date,
                "settlement_date": settlement_date,
                "claim_status": status,
                "claim_type": claim_type,
                "reported_amount": reported_amount,
                "approved_amount": approved_amount,
                "paid_amount": paid_amount,
                "reserve_amount": reserve_amount,
                # incurred_amount is GENERATED ALWAYS in PostgreSQL — omit from CSV
                "approved_flag": approved_flag,
                "repudiated_flag": repudiated_flag,
                "fraud_suspected_flag": fraud,
                "catastrophe_code": catastrophe_code,
                "created_at": (reported + timedelta(hours=int(rng.integers(1, 48)))).isoformat()
                + "T10:00:00+05:30",
            }
        )

    return pd.DataFrame(claim_rows)


def build_expenses(
    rng: np.random.Generator, products: pd.DataFrame, regions: pd.DataFrame
) -> pd.DataFrame:
    months = _month_range(PREMIUM_WINDOW_START, DATA_END)
    rows = []
    expense_id = 1
    for month in months:
        for _, prod in products.iterrows():
            for _, reg in regions.iterrows():
                acq = float(np.round(rng.uniform(80_000, 280_000), 2))
                opex = float(np.round(rng.uniform(120_000, 420_000), 2))
                rows.append(
                    {
                        "expense_month_id": expense_id,
                        "accounting_month": month.isoformat(),
                        "product_id": int(prod.product_id),
                        "region_id": int(reg.region_id),
                        "acquisition_expense": acq,
                        "operating_expense": opex,
                    }
                )
                expense_id += 1
    return pd.DataFrame(rows)


def _write_csv(df: pd.DataFrame, name: str) -> Path:
    path = OUT_DIR / name
    df.to_csv(path, index=False)
    return path


def _print_summary(frames: dict[str, pd.DataFrame]) -> None:
    print("\nGenerated files:")
    for name, df in frames.items():
        path = OUT_DIR / name
        print(f"  {path.name:40s} {len(df):>8,} rows")

    claims = frames["fact_claims.csv"]
    premium = frames["fact_policy_monthly.csv"]
    products = frames["dim_product.csv"]
    regions = frames["dim_region.csv"]

    claims = claims.merge(
        products[["product_id", "line_of_business"]], on="product_id", how="left"
    ).merge(regions[["region_id", "region_name"]], on="region_id", how="left")
    claims["incurred"] = claims["paid_amount"] + claims["reserve_amount"]
    claims["reported_date"] = pd.to_datetime(claims["reported_date"])
    premium["accounting_month"] = pd.to_datetime(premium["accounting_month"])

    max_date = max(claims["reported_date"].max(), premium["accounting_month"].max())
    roll_start = max_date - pd.DateOffset(months=12)
    c12 = claims[claims["reported_date"] >= roll_start]
    p12 = premium[premium["accounting_month"] >= roll_start.to_period("M").to_timestamp()]
    incurred = float(c12["incurred"].sum())
    earned = float(p12["earned_premium"].sum())
    lr = incurred / earned if earned else float("nan")
    print(
        f"\nApprox rolling-12m loss ratio (CSV check): {lr:.1%} "
        f"(incurred INR {incurred:,.0f} / earned INR {earned:,.0f})"
    )

    q2 = claims[
        (claims["line_of_business"] == "Motor")
        & (claims["reported_date"] >= "2026-04-01")
        & (claims["reported_date"] <= "2026-06-30")
    ]
    print(f"Motor claims reported in Q2 2026: {len(q2):,}")
    print("\nLoad order in pgAdmin / \\copy:")
    print("  1 dim_product  2 dim_agent  3 dim_region  4 dim_policy")
    print("  5 fact_policy_monthly  6 fact_claims  7 fact_operating_expense_monthly")
    print("\nDo NOT import incurred_amount - PostgreSQL generates it.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ~40k insurance pilot CSVs")
    parser.add_argument("--claims", type=int, default=40_000)
    parser.add_argument("--policies", type=int, default=8_000)
    parser.add_argument("--agents", type=int, default=120)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(
        f"Generating insurance sample: claims={args.claims:,}, "
        f"policies={args.policies:,}, agents={args.agents}, seed={args.seed}"
    )

    dims = build_dims(rng, args.agents)
    policies = build_policies(
        rng, args.policies, dims["dim_product"], dims["dim_agent"], dims["dim_region"]
    )
    policy_monthly = build_policy_monthly(rng, policies, dims["dim_product"])
    claims = build_claims(
        rng, args.claims, policies, dims["dim_product"], dims["dim_region"]
    )
    expenses = build_expenses(rng, dims["dim_product"], dims["dim_region"])

    frames = {
        "dim_product.csv": dims["dim_product"],
        "dim_agent.csv": dims["dim_agent"],
        "dim_region.csv": dims["dim_region"],
        "dim_policy.csv": policies,
        "fact_policy_monthly.csv": policy_monthly,
        "fact_claims.csv": claims,
        "fact_operating_expense_monthly.csv": expenses,
    }
    for name, df in frames.items():
        _write_csv(df, name)

    _print_summary(frames)


if __name__ == "__main__":
    main()

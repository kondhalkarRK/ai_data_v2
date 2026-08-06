"""
Generate dim_targets.csv and dim_dealer.csv from sample_data sales trends.
Run once: python sample_data/_generate_targets_dealers.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
RNG = np.random.default_rng(42)

DEALER_PREFIX = {
    "Delhi NCR": "NDL",
    "Chandigarh": "CHD",
    "Jaipur": "JPR",
    "Mumbai": "MUM",
    "Pune": "PNQ",
    "Ahmedabad": "AMD",
    "Bengaluru": "BLR",
    "Chennai": "MAA",
    "Hyderabad": "HYD",
    "Kochi": "COK",
    "Kolkata": "CCU",
    "Bhubaneswar": "BBI",
    "Indore": "IDR",
    "Nagpur": "NAG",
}

DEALER_SUFFIX = [
    "Motors", "Auto Hub", "Wheelers", "Drive", "Motors Pvt Ltd",
    "Automotive", "Car World", "Motors & Services",
]


def build_targets() -> pd.DataFrame:
    fs = pd.read_csv(ROOT / "fact_sales.csv", parse_dates=["sales_date"])
    dc = pd.read_csv(ROOT / "dim_carline.csv")
    merged = fs.merge(dc[["carline_id", "make"]], on="carline_id", how="left")
    merged = merged[(merged["sales_date"] >= "2024-01-01") & (merged["sales_date"] <= "2025-12-31")]

    merged["year_month"] = merged["sales_date"].dt.strftime("%Y-%m")
    actuals = (
        merged.groupby(["year_month", "make"], as_index=False)
        .agg(actual_units=("order_qty", "sum"), actual_revenue=("total_sales", "sum"))
    )
    asp = actuals.copy()
    asp["asp"] = asp["actual_revenue"] / asp["actual_units"].replace(0, np.nan)
    make_asp = asp.groupby("make")["asp"].median().to_dict()

    makes = sorted(dc["make"].dropna().unique())
    months = pd.date_range("2024-01-01", "2025-12-31", freq="MS").strftime("%Y-%m").tolist()

    # Make-level monthly baseline from actuals + seasonality
    make_month_avg = actuals.groupby(["make", "year_month"])["actual_units"].sum().unstack(fill_value=0)
    make_totals = actuals.groupby("make")["actual_units"].sum()
    national_share = make_totals / make_totals.sum()

    rows = []
    tid = 1
    for ym in months:
        month_num = int(ym.split("-")[1])
        season = 1.08 if month_num in (10, 11, 12) else (0.92 if month_num in (6, 7, 8) else 1.0)
        for make in makes:
            base = float(make_month_avg.get(make, pd.Series()).get(ym, np.nan))
            if np.isnan(base) or base <= 0:
                base = float(make_totals.get(make, 100) / 24) * season
            else:
                base = base * season

            stretch = 1.04 + float(national_share.get(make, 0.05)) * 0.08
            stretch += RNG.uniform(-0.02, 0.03)
            target_units = max(10, int(round(base * stretch)))
            asp_val = float(make_asp.get(make, 850000))
            target_revenue = round(target_units * asp_val, 2)

            rows.append({
                "target_id": tid,
                "year_month": ym,
                "make": make,
                "target_units": target_units,
                "target_revenue": target_revenue,
                "grain": "make_monthly",
            })
            tid += 1

    return pd.DataFrame(rows)


def build_dealers() -> pd.DataFrame:
    regions = pd.read_csv(ROOT / "dim_region.csv")
    rows = []
    did = 1
    for _, r in regions.iterrows():
        city = r["city"]
        prefix = DEALER_PREFIX.get(city, city[:3].upper())
        n_dealers = 3 if r["region_name"] in ("West", "South", "North") else 2
        for i in range(n_dealers):
            suffix = DEALER_SUFFIX[(did + i) % len(DEALER_SUFFIX)]
            name = f"{prefix} {suffix}" if i == 0 else f"{prefix} {['Central', 'Premium', 'Express'][i % 3]} {suffix}"
            rows.append({
                "dealer_id": did,
                "dealer_code": f"DLR-{prefix}-{i + 1:02d}",
                "dealer_name": name,
                "city": city,
                "region_id": int(r["region_id"]),
                "region_name": r["region_name"],
                "state_code": r["state_code"],
                "country": r["country"],
                "dealer_grade": ["A", "A", "B", "B", "C"][did % 5],
                "active": True,
            })
            did += 1
    return pd.DataFrame(rows)


if __name__ == "__main__":
    targets = build_targets()
    dealers = build_dealers()
    targets.to_csv(ROOT / "dim_targets.csv", index=False)
    dealers.to_csv(ROOT / "dim_dealer.csv", index=False)
    print(f"dim_targets.csv: {len(targets)} rows, {targets['make'].nunique()} makes")
    print(f"dim_dealer.csv: {len(dealers)} rows, {dealers['city'].nunique()} cities")

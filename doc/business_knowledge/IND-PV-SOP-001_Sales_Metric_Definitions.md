# IND-PV-SOP-001 — Sales Metric Definitions & KPI Dictionary

**Document ID:** IND-PV-SOP-001  
**Version:** 2.1  
**Effective date:** 01-Jan-2024  
**Last review:** 15-Jun-2026  
**Owner:** Sales Analytics COE / India Passenger Vehicles  
**Audience:** Executives, Business Controllers, Regional Managers, Data Analysts  
**Applies to dataset:** `fact_sales`, `dim_carline`, `dim_color`, `dim_salesman`, `dim_region` (India PV 2019–2026)

---

## 1. Purpose

This SOP defines the **certified business metrics** used for India passenger-vehicle (PV) retail analytics. All dashboards, chat answers, executive packs, and narrative commentary must use these definitions so numbers remain comparable across regions, OEMs, and time periods.

## 2. Scope

- Retail sales orders for passenger vehicles in India (hatchback, sedan, SUV, MPV).
- Powertrains: Petrol, Diesel, Hybrid, Electric.
- Geographic coverage: North, West, South, East, Central India metros and hubs.
- Time window of the reference warehouse: **January 2019 through June 2026**.

Out of scope: commercial vehicles, two-wheelers, spare-parts aftermarket, and wholesale dealer stock (unless separately certified later).

## 3. Certified metrics (map to physical columns)

| Business term | Certified definition | SQL / column rule | Format | Do NOT use |
|---|---|---|---|---|
| **Revenue** | Gross retail invoice value of vehicles sold | `SUM(total_sales)` | INR (₹ / Lakh / Crore) | `price_per_unit`, `AVG(total_sales)` |
| **Units Sold** | Physical vehicle volume | `SUM(order_qty)` | Integer + “units” | `COUNT(*)` alone when volume is asked |
| **Orders** | Distinct sales transactions | `COUNT(order_id)` | Integer | Confusing with Units Sold |
| **Average Selling Price (ASP)** | Revenue per unit | `SUM(total_sales) / NULLIF(SUM(order_qty),0)` | INR | Average of `price_per_unit` without qty weight |
| **Average Order Value (AOV)** | Revenue per order | `SUM(total_sales) / NULLIF(COUNT(order_id),0)` | INR | Same as ASP |
| **Active Salespeople** | Distinct sellers with at least one order in the filtered period | `COUNT(DISTINCT sales_person_id)` | Integer | Headcount from HR master alone |
| **Revenue per Salesperson** | Productivity | `SUM(total_sales) / NULLIF(COUNT(DISTINCT sales_person_id),0)` | INR | — |

### 3.1 Ambiguity rule (“sales”)

If a user says **“sales”** without clarifying:

1. Default interpretation = **Revenue** (`SUM(total_sales)`).
2. If the question contains volume words (units, volume, cars sold, how many vehicles) → **Units Sold**.
3. If the question contains “orders / bookings / transactions” → **Orders**.
4. When still ambiguous, ask: Revenue / Units / Orders.

### 3.2 Top Model / Top Performer rule

For cards or questions labelled **Top Model**, **Top Performer**, or **Sales Volume**:

- Rank by **`SUM(order_qty)`** (units), never by revenue alone.
- Display as: `{model} — {N} units sold`.
- A low-priced high-volume hatchback must outrank a high-priced low-volume SUV on volume KPIs.

## 4. Time intelligence standards

| Grain | Label format | Rule |
|---|---|---|
| Day | `YYYY-MM-DD` | `sales_date` |
| Month | `YYYY-MM` | `strftime('%Y-%m', sales_date)` |
| Quarter | `Q1-2023`, `Q2-2023`, … | Month bands 1–3 / 4–6 / 7–9 / 10–12. **Never** float division `(month-1)/3` |
| Year | `YYYY` | Calendar year on `sales_date` |

### 4.1 Festive seasonality (India)

September–December typically carry festive uplift (Navratri, Diwali, year-end). Narratives must not treat Q4 strength as “unexpected” without checking festive baseline.

### 4.2 COVID baseline year

**2020 is a depressed baseline**, not a normal comparator. Prefer YoY vs 2019 or vs 2021+ when commenting on recovery. See IND-PV-SOP-002.

## 5. Dimension standards

| Business concept | Preferred attribute | Notes |
|---|---|---|
| Brand / OEM | `make` | Maruti, Tata, Mahindra typically lead volume in this market |
| Model | `model` or `carline_name` | Prefer friendly labels over IDs |
| Body style | `car_type` | SUV / Hatchback / Sedan / MPV |
| Powertrain | `engine_type` | Petrol / Diesel / Hybrid / Electric |
| Colour | `colour_name` | White / Silver / Black dominate India preference |
| Region | `region_name` + `city` | Never show bare `region_id` to executives |
| Salesperson | `first_name || ' ' || last_name` | Never raw `sales_person_id` in narratives |

## 6. Narrative quality bar (executives)

Every executive-facing narrative should include:

1. **What happened** (metric + period + grain).
2. **Who led / lagged** (make, region, or model — max 2 leaders).
3. **Business context** (COVID, festive, EV shift — only if relevant).
4. **Recommended next question** (drill path).

Avoid: dumping raw IDs, decimal quarter labels, “breakdown of revenue” without a leader, or currency in £ when domain is India (use ₹).

## 7. Data quality expectations

- `sales_date` must be non-null after load (ISO dates). Null dates invalidate time narratives.
- `order_qty` ≥ 1 on fact rows.
- EV rows store **battery kWh** in `engine_capacity` (not zero). Do not flag EV capacity as financial outliers.
- Join path: `fact_sales` LEFT JOIN all dimensions on foreign keys defined in the semantic model.

## 8. Change control

Metric definition changes require COE approval and glossary YAML update in the same release. Chat answers must follow glossary SQL expressions when present.

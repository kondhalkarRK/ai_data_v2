# ASK-DB Insurance — Test Questions (Simple → Complex)

**Audience:** QA / demo / UAT  
**Mode:** `DATA_BACKEND=postgres`, industry pack **insurance**  
**Warehouse:** ~1.5M claims in PostgreSQL (`insurance` schema) — numbers come from SQL, not from loading the full table into Streamlit.

Use this list top-to-bottom. Check **Expected behaviour** before marking pass/fail.

---

## A. Clarification & incomplete (expect 2 suggestion chips)

| # | Question | Expected |
|---|----------|----------|
| A1 | `East` | Incomplete → 2 insurance suggestions (region-aware), not EV/sales |
| A2 | `show claims` | Incomplete → 2 suggestions with metric + dimension + year |
| A3 | `Motor` | Incomplete → Motor LOB suggestions (claims / premium) |
| A4 | `loss ratio` | Incomplete or guided → suggestions with region/product grain |
| A5 | `tell me about West` | Entity-only → 2 West-region suggestions |

**Pass if:** chips are insurance-domain; picking a chip runs a proper data query.

---

## B. Simple (single grain / clear metric)

| # | Question | What to check |
|---|----------|---------------|
| B1 | `Show claim count by region for 2025` | Multi-column: region + count (not one anonymous number) |
| B2 | `Show claims incurred by product for 2025` | product / LOB label + incurred |
| B3 | `Show earned premium by region for 2025` | Premium from `fact_policy_monthly`, not claim rows |
| B4 | `Show GWP by line of business for 2025` | Written premium by LOB |
| B5 | `How many claims were reported in East in 2025?` | East → `dim_region.region_name = 'East'` |
| B6 | `Total claims paid by claim status for 2025` | Status dimension + paid amount |

---

## C. Medium (ratios, rankings, ratios)

| # | Question | What to check |
|---|----------|---------------|
| C1 | `Monthly claim count and claims incurred for 2025` | Month + count + incurred (multi-metric) |
| C2 | `Top 10 products by claims incurred in 2025` | Rank starts at **1**, product name, metric |
| C3 | `Loss ratio by region for 2025` | region + incurred + earned + ratio (or equivalent supporting cols) |
| C4 | `Loss ratio by product (LOB) for 2025` | Compatible grain; NULLIF on denominator |
| C5 | `Average claim severity by region for 2025` | Severity = incurred / claim count |
| C6 | `Approval rate by region for 2025` | Approved / all claims |
| C7 | `Compare claims incurred for Motor vs Health in 2025` | LOB filter/group, both lines visible |
| C8 | `Earned premium and GWP by month for West in 2025` | West region + dual premium metrics |

---

## D. Complex (joins, multi-dim, business wording)

| # | Question | What to check |
|---|----------|---------------|
| D1 | `Show claim count and claims incurred for East by product in 2025` | Region + product + metrics |
| D2 | `Which region has the highest loss ratio in 2025?` | Rank/order; supporting premium + claims |
| D3 | `Top 5 agents by written premium in 2025` | Agent name + GWP; rank 1-based |
| D4 | `Claims incurred by region and LOB for 2025` | Two dimensions + metric |
| D5 | `Monthly loss ratio for Motor in East during 2025` | LOB + region + month + ratio |
| D6 | `Settlement days (average) by region for settled claims in 2025` | Settled filter + TAT |
| D7 | `Active policies count by region and product family` | Policy status / dim_policy grain |
| D8 | `Customer count and claim count by region for 2025` | `customer_key` + claims |

---

## E. Follow-ups (conversation / SQL anchor)

Ask **E0** first, then the follow-ups in order:

| # | Question | What to check |
|---|----------|---------------|
| E0 | `Show claims incurred by region for 2025` | Baseline result |
| E1 | `Only for East` | Narrows prior SQL; East filter |
| E2 | `Break that down by product` | Same East scope + product |
| E3 | `Now show monthly trend` | Time series under same filters |

---

## F. Guardrails & edge cases

| # | Question | Expected |
|---|----------|----------|
| F1 | `Delete all claims` | Blocked by SQL guardrails |
| F2 | `What is the weather in Mumbai?` | Out-of-scope / warm redirect |
| F3 | `Show me everything` / unfiltered detail dump | Bounded (≤1000 to app; UI shows ≤100) or timeout message — UI must not freeze |
| F4 | `One number only: total claims incurred in 2025` | Single scalar OK when explicitly asked |

---

## Suggested 10-minute leadership demo path

1. A1 `East` → show clarification  
2. B5 East claims  
3. C3 Loss ratio by region  
4. C2 Top 10 products (point at rank 1)  
5. D5 Monthly loss ratio Motor + East  
6. Briefly open **KPI** and **Preview/DQ** — warehouse stays in Postgres; UI only gets small aggregates  

---

## Scoring tips

| Signal | Good | Bad |
|--------|------|-----|
| Columns | Dimension label + metric(s) | Single unnamed `sum` column |
| Region words | East/West/North/South map correctly | Wrong region or ignored |
| Premium | From policy-month fact | Summed from claim rows |
| Rank | Starts at 1 | 0-based / missing |
| Volume to UI | Small frame (often &lt; 50 rows for aggregates) | Attempt to load 1.5M rows |

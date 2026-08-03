# IND-PV-SOP-004 — Regional Territory Performance Framework

**Document ID:** IND-PV-SOP-004  
**Version:** 1.3  
**Effective date:** 01-Jul-2023  
**Last review:** 01-Jun-2026  
**Owner:** Regional Sales Excellence  
**Audience:** Regional Heads, City Managers, Sales Ops, Executives  
**Related tables:** `dim_region` (`region_name`, `city`, `state_code`, `country`), `fact_sales.region_id`

---

## 1. Purpose

Define how India geographic performance is measured, reviewed, and narrated using the five commercial zones and fourteen city hubs in the analytics dataset.

## 2. Territory master (certified)

| Zone (`region_name`) | Hub cities in dataset | Review cadence |
|---|---|---|
| North | Delhi NCR, Chandigarh, Jaipur | Monthly + festive deep-dive |
| West | Mumbai, Pune, Ahmedabad | Monthly |
| South | Bengaluru, Chennai, Hyderabad, Kochi | Monthly |
| East | Kolkata, Bhubaneswar | Monthly |
| Central | Indore, Nagpur | Monthly |

Country is **India** for all hubs. External exports are out of scope.

## 3. Performance scorecard (per territory)

For each zone or city, the monthly pack must show:

1. **Units Sold** — `SUM(order_qty)`  
2. **Revenue** — `SUM(total_sales)`  
3. **ASP** — revenue / units  
4. **Orders** — `COUNT(order_id)`  
5. **Mix** — share of SUV vs Hatchback; EV share (SOP-003)  
6. **Concentration** — top make share (watch Maruti/Tata/Mahindra dominance)

### 3.1 Metro bias note

Delhi NCR, Mumbai, Bengaluru, Chennai, Hyderabad typically carry higher order weights in the extract. Narratives should not conclude “South is weak” from raw totals without normalising by hub count or comparing **per-city** run-rates.

## 4. Colour & preference overlays (optional)

India retail colour preference in this dataset skews to **White, Silver, Black, Grey, Pearl White**. Regional packs may show `colour_name` mix; treat colour as secondary insight, not a primary KPI.

## 5. Salesperson productivity

- Display name: `first_name || ' ' || last_name`.
- Active flag comes from `dim_salesman.active`.
- Territory questions about “who sells best in West” must filter `region_name = 'West'` then rank people by units or revenue as asked (default revenue for “best salesperson”, units for “volume leader”).

## 6. Drill path (mandatory for AI & analysts)

Country → Zone (`region_name`) → City → Make → Model → Colour

Never jump from Country straight to Model in an executive narrative without an intermediate geographic or brand roll-up when the question is regional.

## 7. Red / amber / green thresholds (guidance)

| Signal | Amber | Red |
|---|---|---|
| YoY units (vs non-2020 base) | −5% to −15% | < −15% |
| EV share lag vs national | −3 to −5 pp | < −5 pp vs national |
| Top-make concentration | > 45% | > 55% (diversification risk) |

Actions:

- Amber → regional review within 2 weeks.  
- Red → escalation to Sales Head; attach COVID/festive context if relevant (SOP-002).

## 8. Narrative examples

> “West (Mumbai–Pune–Ahmedabad) leads revenue contribution among zones this period. Within West, review Pune vs Mumbai unit mix before reallocating demo stock.”

> “East volumes remain thinner on a hub-count basis; evaluate Kolkata EV readiness separately from Bhubaneswar ICE demand.”

# IND-PV-SOP-004 — Dealer Network Territory Review & Escalation

**Document ID:** IND-PV-SOP-004  
**Version:** 2.0  
**Effective date:** 01-Jul-2023  
**Last review:** 01-Jul-2026  
**Owner:** Regional Sales Excellence / Network Development  
**Audience:** Regional Heads, City Managers, Dealer Principals, Sales Ops  

---

## 1. Purpose

Define the **monthly territory review** for India passenger-vehicle retail: how zones and city hubs are scored, when underperformance escalates, and how drill-downs must run before model-level conclusions.

## 2. Territory master

| Zone (`region_name`) | Hub cities | Primary review |
|---|---|---|
| North | Delhi NCR, Chandigarh, Jaipur | Monthly + festive deep-dive |
| West | Mumbai, Pune, Ahmedabad | Monthly |
| South | Bengaluru, Chennai, Hyderabad, Kochi | Monthly |
| East | Kolkata, Bhubaneswar | Monthly |
| Central | Indore, Nagpur | Monthly |

Country = **India** for all hubs. Export retail is out of scope.

## 3. Monthly scorecard (per zone / city)

Prepare in this order (Country → Zone → City → Make → Model):

1. Units Sold — `SUM(order_qty)`  
2. Revenue — `SUM(total_sales)`  
3. ASP — revenue / units  
4. Orders — `COUNT(order_id)`  
5. Mix — SUV vs Hatch; EV share (SOP-003)  
6. Concentration — top make share (watch Maruti / Tata / Mahindra)

### 3.1 Metro bias

Metro hubs can dominate zone totals. Always show **city contribution %** before declaring a zone “weak”.

## 4. Escalation thresholds

| Signal | Threshold | Action |
|---|---|---|
| Units vs prior year (same months) | ≤ −15% for 2 months | City Manager corrective plan |
| Units vs prior year | ≤ −25% for 2 months | Regional Head on-site review |
| EV share vs national | Gap ≥ 5 pp with stock available | EV Champion + marketing push |
| Aged retail stock > 90 days | > 10% of dealer stock | Stock liquidation plan |

## 5. Review meeting agenda (90 min)

1. Volume & revenue vs target (15)  
2. Mix & EV (15)  
3. Manpower / productivity (15)  
4. Aged stock & colour skew (15)  
5. Competitive losses (15)  
6. Actions with owners & dates (15)

## 6. Narrative rules

- Do not blame East underperformance on “brand” without checking festive timing and network density.  
- Do not aggregate all India then jump to one model — follow the drill path.  
- Incomplete year → label **YTD**.

## 7. Records

Store MBR pack + action log for 3 years. Analytics keys: `region_id` → `dim_region`.

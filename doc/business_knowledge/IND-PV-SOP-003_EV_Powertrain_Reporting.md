# IND-PV-SOP-003 — EV Retail Delivery, Stock Care & Powertrain Reporting

**Document ID:** IND-PV-SOP-003  
**Version:** 2.0  
**Effective date:** 01-Apr-2022  
**Last review:** 20-Jul-2026  
**Owner:** Electrification PMO / Product Analytics / Dealer Ops  
**Audience:** EV Champions, Sales Managers, PDI / Workshop, Marketing, Executives  

---

## 1. Purpose

Standardise **how EV retail is delivered at the dealership** and how EV / ICE mix is reported to leadership so “EV demand” stories are credible, unit-based, and comparable year over year.

## 2. Dealer EV delivery procedure

### 2.1 Pre-delivery (PDI)

1. Confirm software version / OTA status per OEM bulletin.  
2. Charge to OEM-specified handover SOC (typically 60–80%).  
3. Verify charger accessories, app pairing checklist, warranty card.  
4. Record usable pack size (kWh) from catalogue — maps to `engine_capacity` for Electric rows.

### 2.2 Customer handover

1. Demo: regenerative braking, charge ports, public charger workflow, connected services.  
2. Explain home charger / public charging SLA and roadside assistance for EV.  
3. Collect acknowledgement; only then close retail in DMS.

### 2.3 Stock care (unsold EV)

| Condition | Action | Owner |
|---|---|---|
| SOC below OEM floor | Top-up charge within 48 hrs | Workshop / EV Champion |
| Stationary > 14 days | Battery health check + drive cycle | Workshop |
| Software campaign open | Apply before retail | Service Advisor |

## 3. Powertrain classification (reporting)

| DMS / `engine_type` | Label in packs | Counts in **EV share**? |
|---|---|---|
| Electric | BEV / EV | **Yes** |
| Hybrid | Hybrid | No (unless question says “electrified”) |
| Petrol | ICE Petrol | No |
| Diesel | ICE Diesel | No |

### 3.1 Certified EV share formula

**EV share (%)** =  
`SUM(order_qty WHERE engine_type = 'Electric') / NULLIF(SUM(order_qty), 0) × 100`

- Grain: year → region → make.  
- Use **units**, not order count, when leadership asks about demand / share of sales.  
- “Electrified share” = Electric + Hybrid — label explicitly.

## 4. Is EV demand increasing? (executive answer playbook)

When asked *“Is EV demand increasing?”* / *“Are EVs taking off?”*:

1. Show **EV share by year** using the formula above.  
2. Show **absolute EV units** alongside share (share can rise while ICE volume stays larger).  
3. Call out inflection after **2023** as new EV nameplates enter the catalogue.  
4. Cite this SOP (IND-PV-SOP-003).  
5. Never say “everyone is buying EVs” while Petrol still leads absolute units.

Indicative trajectory in the India PV analytics extract: EV unit share moves from well under 1% (2019–20) into **mid-teens by 2025–26**, with Petrol remaining the volume backbone.

## 5. OEM EV nameplates (catalogue alignment)

Tata (Nexon EV, Punch EV, Tiago EV, Curvv EV, Harrier EV), Mahindra (XUV400, BE 6, XEV 9e), Maruti (e Vitara), Hyundai (Ioniq 5, Creta Electric), Toyota (Urban Cruiser EV), Kia (EV6, EV9), MG (ZS EV, Comet EV, Windsor EV), BYD (Atto 3, Seal).

Newer EV nameplates are expected mainly from **2023 onward** in retail extracts.

## 6. Data-quality rules

- Electric `engine_capacity` = **kWh**, must be > 0.  
- Do not average kWh with ICE litres in one KPI.  
- Do not run revenue-style IQR outlier logic on `engine_capacity`.

## 7. Compliance

Any published EV KPI must state units-based share. Chat / OKF answers on EV demand must cite **IND-PV-SOP-003**.

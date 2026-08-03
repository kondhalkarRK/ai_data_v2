# IND-PV-SOP-003 — EV & Powertrain Reporting Standards

**Document ID:** IND-PV-SOP-003  
**Version:** 1.6  
**Effective date:** 01-Apr-2022  
**Last review:** 20-Jun-2026  
**Owner:** Product Analytics / Electrification PMO  
**Audience:** Product Heads, Marketing, Sales Ops, Data Science, Executives  
**Related attributes:** `engine_type`, `engine_capacity`, `make`, `model`, `car_type`

---

## 1. Purpose

Standardise how **Electric, Hybrid, Petrol, and Diesel** sales are counted, labelled, and narrated so EV growth stories remain credible and comparable year over year.

## 2. Powertrain classification

| `engine_type` value | Business label | Notes |
|---|---|---|
| Electric | BEV / EV | Battery electric only |
| Hybrid | Hybrid (HEV/strong hybrid family in this extract) | Not counted inside EV share unless asked “electrified” |
| Petrol | ICE Petrol | Includes CNG siblings only if labelled separately later |
| Diesel | ICE Diesel | Declining share expected in passenger cars |

### 2.1 EV share formula (certified)

**EV share (%)** =  
`SUM(order_qty WHERE engine_type = 'Electric') / NULLIF(SUM(order_qty), 0) * 100`

- Default grain: year, then region or make.
- Do **not** use order count when the question says “share of sales volume”.
- “Electrified share” (if asked) = Electric + Hybrid units / total units. Always label explicitly.

### 2.2 Expected EV trajectory (India context for this dataset)

| Year | Indicative EV order share (reference extract) | Narrative cue |
|---|---|---|
| 2019 | ~0.5% | Nascent |
| 2020 | ~1% | Still early despite COVID |
| 2021–22 | ~2–4% | Early adoption |
| 2023 | ~7% | Inflection |
| 2024 | ~10% | Mainstream awareness |
| 2025–26 | ~14–16% | Structural shift |

Narratives should celebrate EV growth **and** remind leaders that ICE (especially Petrol SUV/hatch) still dominates absolute volume.

## 3. Engine capacity field rules

| Powertrain | Meaning of `engine_capacity` | Example |
|---|---|---|
| Petrol / Diesel / Hybrid | Engine displacement (litres) | 1.2, 1.5, 2.0 |
| Electric | **Usable battery pack (kWh)** | 24.0, 40.5, 59.0, 72.6 |

### 3.1 Data-quality rule

- EV `engine_capacity` must be **> 0**. Zero kWh is invalid and must not be used to imply “no engine”.
- Do **not** run financial IQR outlier logic on `engine_capacity` — it is a catalogue attribute, not a revenue metric.
- Never average EV kWh with ICE litres in one KPI without separating powertrains.

## 4. OEM EV storytelling (aligned to catalogue)

High-visibility EV models in the reference catalogue include:

- Tata: Nexon EV, Punch EV, Tiago EV  
- Mahindra: XUV400, BE 6  
- Hyundai: Ioniq 5  
- Kia: EV6  
- MG: ZS EV, Comet EV  

When ranking “top EV by volume”, filter `engine_type = 'Electric'` then rank by `SUM(order_qty)`.

ICE volume leaders (Maruti / Tata / Mahindra overall) must not be narrated as “losing” solely because EV share rises — check absolute units.

## 5. Executive Q&A playbook

| Question | Correct approach |
|---|---|
| “Are EVs taking off?” | Show EV share by year + absolute EV units; cite inflection post-2023 |
| “Which brand leads EV?” | Filter Electric; rank makes by units; optionally revenue |
| “Is SUV EV demand higher?” | Cross `car_type` × `engine_type` on units |
| “What battery sizes sell?” | Among Electric only, distribute `engine_capacity` (kWh) |

## 6. Narrative standards

Approved phrasing:

> “EV share of units rose from under 1% in 2019–20 to mid-teens by 2025–26 in this extract, while Petrol remains the volume backbone.”

Avoid:

> “Everyone is buying EVs now” (absolute ICE units still larger).  
> Mixing kWh and litres in one average.  
> Treating Hybrid as EV without saying “electrified”.

## 7. Compliance

Any published EV KPI must state the formula (units-based vs orders-based). Chat / OKF-assisted answers should cite this SOP when discussing EV demand.

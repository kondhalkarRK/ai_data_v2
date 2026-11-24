# IND-PV-SOP-001 — Retail Booking, Invoicing & Handover Control

**Document ID:** IND-PV-SOP-001  
**Version:** 3.0  
**Effective date:** 01-Apr-2024  
**Last review:** 15-Jul-2026  
**Owner:** Dealer Operations Excellence / India Passenger Vehicles  
**Audience:** Dealer Principals, Sales Managers, Billing Desk, Regional Controllers  
**Systems of record:** DMS / CRM booking → retail invoice → `fact_sales` analytics extract  

---

## 1. Purpose

Control how a **passenger-vehicle retail sale** is booked, invoiced, and handed over so every unit that appears in management reports is a real, customer-delivered retail event — not a stock transfer, demo movement, or cancelled booking.

## 2. Scope

| In scope | Out of scope |
|---|---|
| New PV retail to end customer (hatch / sedan / SUV / MPV) | Commercial vehicles, 2W, 3W |
| Petrol, Diesel, Hybrid, Electric | Pure wholesale billing to another dealer |
| India dealer network covered by analytics extract | Aftersales parts / labour RO |

## 3. Roles & responsibilities (RACI)

| Step | Sales Consultant | Sales Manager | Billing Desk | Regional Controller |
|---|---|---|---|---|
| Create booking | R | A | C | I |
| Credit / finance clearance | C | A | R | I |
| Raise retail invoice | C | C | R/A | I |
| Physical handover + OTP / gate pass | R | A | C | I |
| Post-sale analytics quality check | I | C | C | R/A |

## 4. Procedure

### 4.1 Booking (T0)

1. Capture customer KYC, model/variant, colour, powertrain, expected delivery week.  
2. Block inventory VIN / allotment in DMS.  
3. Do **not** treat booking as “sold” in volume dashboards.

### 4.2 Invoice (T1 — retail recognition)

1. Invoice only after: allotment confirmed, payment / finance disbursement cleared, insurance & RTO docs initiated.  
2. Invoice line must carry: order reference, carline, colour, salesman, outlet/region, qty (=1 for retail car), invoice value.  
3. Analytics mapping (certified):  
   - **Units Sold** = `SUM(order_qty)` on invoiced retail rows  
   - **Revenue** = `SUM(total_sales)`  
   - **Orders** = `COUNT(order_id)`  
   - **ASP** = Revenue / Units  

### 4.3 Handover (T2)

1. Complete PDI checklist, charge EV to policy SOC if Electric, explain warranty & connected features.  
2. Collect customer acknowledgement. Cancel invoice if handover fails within policy window and reverse analytics feed.

## 5. SLA & controls

| Control | Target | Breach action |
|---|---|---|
| Booking → invoice | ≤ 45 days (stock-dependent) | Sales Manager review |
| Invoice → handover | ≤ 7 calendar days | Escalate to Dealer Principal |
| Cancelled / reversed invoices | Same-day DMS reverse | Exclude from KPI packs |

## 6. Exceptions

- **Demo / courtesy cars:** separate stock movement code — never in retail Units Sold.  
- **Fleet / corporate:** allowed if end-user invoice exists; tag fleet flag in DMS.  
- **Partial year extracts (e.g. 2026 H1):** never annualise blindly in YoY packs.

## 7. Records

Retain invoice PDF, payment proof, handover sheet for **8 years** (tax / audit). Analytics extract retains `order_id`, `sales_date`, `order_qty`, `total_sales`, dimension FKs.

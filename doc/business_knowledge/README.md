# Business Knowledge Pack — India Passenger Vehicles (Dealer / OEM Ops)

These documents are **operating SOPs / MBR standards** used in India passenger-vehicle
retail networks. They align to the sample warehouse in `sample_data/`
(`fact_sales` + dimensions, 2019–mid 2026) but are written as **real dealership /
regional operating procedures**, not a glossary dump.

## Documents

| ID | File | What it governs |
|---|---|---|
| IND-PV-SOP-001 | Retail Booking, Invoicing & Handover | When a retail unit is recognised |
| IND-PV-SOP-002 | Demand Shock & Recovery Playbook | Lockdown / shock operating cadence |
| IND-PV-SOP-003 | EV Delivery, Stock Care & Reporting | EV handover + EV share formula |
| IND-PV-SOP-004 | Territory Review & Escalation | Zone/city MBR + thresholds |
| IND-PV-GUIDE-005 | MBR Narrative Pack Standard | How packs / AI commentary are written |

Markdown = source of truth. PDF twins (if present) are for stakeholder sharing.

## How to load into the app

1. Sidebar → **Knowledge Base (OKF)** → **SEED INDIA PV SOPs**  
   (App also auto-seeds when the OKF index is empty.)
2. Example questions:
   - “Is EV demand increasing?”
   - “Why were 2020 sales down?”
   - “Units sold by make”
3. Answers should show a **table** (when data-backed) + **narration** with **📎 Knowledge** citations.

## Force refresh after SOP edits

Use **SEED** with clear/reindex (or Clear Knowledge + Seed) so Chroma picks up new text.

# Business Knowledge Pack — India Passenger Vehicles

These documents are **real-project style SOPs / guides** aligned to the sample
dataset in `sample_data/` (fact_sales + dimensions, India PV 2019–2026).

## Documents

| ID | File | Audience | Use in answers |
|---|---|---|---|
| IND-PV-SOP-001 | Sales Metric Definitions | FP&A, analysts, AI | Certified metrics (Revenue, Units, ASP, quarters) |
| IND-PV-SOP-002 | COVID Recovery Playbook | CXO, FP&A | How to narrate 2020 trough & recovery |
| IND-PV-SOP-003 | EV & Powertrain Reporting | Product, marketing | EV share formula, kWh vs litres |
| IND-PV-SOP-004 | Regional Performance | Regional heads | Zone/city drill path & thresholds |
| IND-PV-GUIDE-005 | Executive Narrative Standards | Insights / Copilot | L1–L4 insight quality bar |

Each document is available as **Markdown** (source of truth) and **PDF**
(for OKF upload / stakeholder sharing).

## How to load into the app

1. Open the sidebar **Knowledge Base (OKF)** section.
2. Click **SEED INDIA PV SOPs** (ingests all `.md` / `.pdf` in this folder).
3. Ask questions such as:
   - “Why were 2020 sales down?”
   - “Is EV demand increasing?”
   - “Units sold by make”
4. Narratives should show **Business context** + **📎 Knowledge** citations.

## Warehouse path (future)

When this app connects to SQL Server / Synapse / Snowflake / Databricks,
keep these SOPs as the **business contract** layer — metrics and narrative
rules stay stable while the physical source changes.

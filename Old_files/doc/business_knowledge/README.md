# Business Knowledge Pack — India Passenger Vehicles

These files are **OKF business documents** — handbooks, regional targets, strategy plans, and operating SOPs for India PV retail. They power **policy / interpretation answers** when users ask things the CSV alone cannot explain.

## OKF vs semantic glossary (important)

| Layer | Location | Purpose | Example question |
|---|---|---|---|
| **Semantic glossary** | `semantic/business_glossary.yaml` | SQL metrics, columns, synonyms | *Show units sold by make* |
| **OKF business docs** | `doc/business_knowledge/` | Handbooks, targets, strategy, SOPs | *What is the North zone FY2026 target?* |

Do **not** duplicate full policy prose in the glossary. The glossary may **reference** OKF doc IDs (e.g. `IND-PV-SOP-003`) but operational detail lives here.

## Document library

### Operating SOPs (root folder)

| ID | File | Type |
|---|---|---|
| IND-PV-SOP-001 | Sales Metric Definitions | sop |
| IND-PV-SOP-002 | COVID Recovery Playbook | sop |
| IND-PV-SOP-003 | EV Powertrain Reporting | sop |
| IND-PV-SOP-004 | Regional Performance Framework | sop |
| IND-PV-GUIDE-005 | Executive Narrative Standards | guide |

### Handbooks (`handbooks/`)

| ID | File | Type |
|---|---|---|
| IND-PV-HB-001 | Dealer Operations Handbook | handbook |

### Regional targets (`regional/`)

| ID | File | Type |
|---|---|---|
| IND-PV-REG-001 | Regional Sales Targets FY2026 | regional_targets |

### Strategy plans (`strategy/`)

| ID | File | Type |
|---|---|---|
| IND-PV-STR-001 | Annual Growth Strategy FY2026 | strategy_plan |

Markdown = source of truth. PDF twins (if generated) are for stakeholder sharing only.

## Example questions → OKF (not glossary)

- *What is our EV strategy for FY2026?* → STR-001  
- *What is the East zone unit target?* → REG-001  
- ***Does monthly sales align with target?*** → **actuals from data + targets from REG-001**  
- ***Are we on track for North?*** → **YTD / monthly alignment vs REG-001**  
- *When does a booking count as a retail sale?* → HB-001 / SOP-001  
- *What escalation threshold applies for aged stock?* → SOP-004  
- *Is EV demand increasing?* → SOP-003 + optional data check  

## Load into the app

1. Sidebar → **Knowledge Base (OKF)** → **SEED INDIA PV SOPs**  
2. App auto-seeds on startup when the index is empty or content version changes.  
3. Answers cite document IDs in **📎 Knowledge** citations.

## After editing documents

Bump `_OKF_CONTENT_VERSION` in `features/okf_knowledge/okf_answer.py`, then **Clear Knowledge + Seed** in the sidebar.

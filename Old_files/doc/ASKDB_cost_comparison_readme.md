# ASK-DB LLM vs BI cost comparison — how to present

**File:** [`ASKDB_LLM_vs_BI_Cost_Comparison.xlsx`](ASKDB_LLM_vs_BI_Cost_Comparison.xlsx)  
**Regenerate:** `python doc/_generate_llm_bi_cost_xlsx.py`

## Sheets

| Sheet | Use |
|-------|-----|
| **Executive_Summary** | Open this first in the meeting |
| **Assumptions** | Yellow cells = live demo knobs (volume, narration %, BI quotes) |
| **LLM_Unit_Economics** | $1 buys how many questions (with / without narration) |
| **Monthly_Volume_Cost** | 30k Q showcase + 4.5k derived + High-tier narration sensitivity + chart |
| **BI_Warehouse_Compare** | Indicative Power BI + Snowflake vs ASK-DB LLM |

## Three talking points

1. **Usage-based AI vs fixed BI stack** — ASK-DB LLM cost scales with questions; classic BI is seats + warehouse + dashboard effort.
2. **Narration is the expensive dial** — default Insights/Table/Chart stay near ~2,500 tokens/Q; Narration chip ≈ 6,000 tokens/Q.
3. **Pick the GPT tier for the business case** — Small/Medium for scale demos; High when quality matters; edit yellow `$/1M` cells if Studio rates change.

## Caveats (say out loud)

- Capgemini Studio rates are **indicative**, not invoices.
- Power BI / Snowflake numbers are **placeholders** — replace before a formal business case.
- Not feature-parity with Power BI; framing is *cost shape* for NLQ-on-Postgres vs classic BI+DW.

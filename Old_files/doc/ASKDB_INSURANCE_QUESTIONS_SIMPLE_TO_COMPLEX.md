# ASK-DB Insurance — Questions (Simple → Complex → Very Complex)

**Mode:** PostgreSQL + insurance pack  
**Use:** demo, UAT, semantic/glossary coverage checks  
**Related:** [`insurance_test_questions.md`](./insurance_test_questions.md) (pass/fail checklist)

Ask top-to-bottom. Prefer **Chat Room · Full** mode unless noted.

---

## 1. Simple

Clear metric + one dimension (or one filter). Should hit glossary and return multi-column SQL results.

1. Show claim count by region for 2025
2. Show claims incurred by product for 2025
3. Show earned premium by region for 2025
4. Show GWP by line of business for 2025
5. How many claims were reported in East in 2025?
6. Total claims paid by claim status for 2025
7. Written premium by Motor, Health, and Property for 2025
8. Claim count for West in 2025
9. Total sale of policy across type
10. GWP by region last 12 months
11. Earned premium by LOB
12. Claim count by status
13. Premium by agent in West
14. Average claim severity for Health
15. Yearly GWP trend

---

## 2. Medium / Complex

Trends, rankings, ratios, business wording (sale / top selling / year).

1. Monthly claim count and claims incurred for 2025
2. Top 10 products by claims incurred in 2025
3. Loss ratio by region for 2025
4. Loss ratio by product (LOB) for 2025
5. Average claim severity by region for 2025
6. Approval rate by region for 2025
7. Compare claims incurred for Motor vs Health in 2025
8. Earned premium and GWP by month for West in 2025
9. Top selling policy across year
10. Best selling products in North
11. Top 5 products by written premium
12. Renewal rate by channel
13. Loss ratio by East region
14. Motor claims incurred by month
15. Top 5 agents by written premium in 2025
16. Which region has the highest loss ratio in 2025?
17. Claims incurred by region and LOB for 2025
18. Customer count and claim count by region for 2025

---

## 3. Very complex

Multi-dimension joins, ratios at fine grain, settlement/ops, follow-ups, edge wording.

1. Show claim count and claims incurred for East by product in 2025
2. Monthly loss ratio for Motor in East during 2025
3. Settlement days (average) by region for settled claims in 2025
4. Active policies count by region and product family
5. Top selling products by year and region for the last 3 years
6. GWP, earned premium, and loss ratio by LOB and region for 2025
7. Rank agents by GWP within each region for 2025 (rank restarts per region)
8. Month-over-month change in written premium for Motor in West
9. Claims incurred vs earned premium by product family for East in 2025
10. Fraud suspected claim count and incurred by region and LOB for 2025
11. Renewal rate by channel and LOB for policies due in 2025
12. Top 10 products by GWP across year, with rank starting at 1 each year
13. Average settlement TAT for Approved vs Settled claims by region in 2025
14. Loss ratio for Motor vs Property in South, monthly for 2025
15. Share of total GWP by LOB within each region for 2025 (percent of region)

### Follow-up chain (ask in order)

1. Show claims incurred by region for 2025  
2. Only for East  
3. Break that down by product  
4. Now show monthly trend  
5. Add loss ratio using earned premium for the same scope  

---

## 4. Incomplete / clarification (expect suggestion chips)

These should **not** run blind SQL; app should offer 2 complete insurance suggestions.

1. East
2. show claims
3. Motor
4. loss ratio
5. tell me about West
6. top selling
7. premium

---

## Quick semantic checks (after glossary updates)

| Question | Should map toward |
|----------|-------------------|
| total sale of policy across type | GWP + LOB/type |
| top selling policy across year | GWP rank by product + year |
| best selling products in North | GWP + North region |
| yearly GWP trend | GWP + year grain |
| renewal rate by channel | renewal rate + agent channel |

---

## Notes for scoring

- **Semantic trust:** ≥2 glossary hits → often 25/25 on semantic component (Postgres path now persists matches).
- **Numbers:** always from warehouse SQL (`fact_policy_monthly` for premium/sales; `fact_claims` for claims).
- **Rankings:** 1-based `rank`; default top-N = 10 if user omits N.
- **Year:** `across year` / `by year` → `EXTRACT(YEAR FROM accounting_month)` for premium.

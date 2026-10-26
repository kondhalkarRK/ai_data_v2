# Automotive — LLM & hybrid demo questions

Use these on **Automotive** industry with an **LLM API key** configured and `nlq_llm_reasoning_mode` at default **`llm_first`** unless noted.

**How to read the table**

| Column | Meaning |
|--------|---------|
| **LLM** | Expect SSE stage `llm` and **Grounded on → LLM** green when the model completed successfully. |
| **Hybrid** | Expect `meta.route` = `hybrid` plus `citation` events (works best with documents in the knowledge hub). |
| **Governed** | May still answer via semantic compiler/templates; LLM may run first then fall back. |

---

## LLM-oriented questions (complex / planner + validated SQL)

These trigger **`decision.path` = `llm_reasoning`** on typical configs (complex analysis or no single template).

1. Top 3 car models in each state by revenue  
2. Which dealers are above the regional average for revenue  
3. 6-month moving average of Tata revenue by month  
4. Month-over-month revenue growth for Hyundai by month  
5. Year-on-year growth ranking of dealers by revenue  
6. Brands with increasing revenue but decreasing unit sales  
7. Top 3 dealers in each region by units sold  
8. Which models are growing fastest by revenue in the SUV segment  
9. Running total of Maruti Suzuki revenue by month for the last 24 months  
10. Dealers above the regional average for units sold  
11. Compare MG and Kia revenue by year side by side  
12. Revenue contribution share by car type for electric vehicles  
13. Which colours have the highest revenue per region  
14. Top salesperson in each city by revenue (complex per-group shape)  
15. Period-over-period revenue growth by dealer for 2024 vs 2023  
16. Models with declining units but stable average selling price by month  
17. Rank dealers by revenue growth within each state  

---

## Hybrid questions (SQL + knowledge passages)

Routing uses explanation/insight phrasing (`why`, `factors`, `drivers`, `explain … increase/decrease`, etc.). Upload **dealer reports, market briefs, or strategy memos** for richer citations.

1. Why did Tata revenue increase in 2024 compared to 2023?  
2. What factors drove the drop in SUV sales last quarter?  
3. Explain the decrease in Maruti revenue in the west region  
4. What insights explain the spike in electric vehicle sales by month?  
5. Drivers of revenue growth for Hyundai dealers in 2024  
6. Why are sedan sales declining while SUV revenue is rising?  
7. What contributed to the increase in average selling price for premium brands?  
8. Reasons behind the growth in units sold for Tata in the north region  
9. Explain the increase in dealer revenue for grade A outlets compared to grade B  
10. What insights can you share about Maruti market share and regional performance?  
11. Why did total automotive revenue dip in Q2 despite higher SUV volumes?  
12. Factors affecting salesperson performance vs dealer outlet performance  
13. Explain the relationship between fuel type mix and revenue trend by month  
14. What drivers explain colour preference shifts for hatchbacks vs sedans?  
15. Why is the east region underperforming on revenue relative to the south?  

---

## Controls (usually **no** LLM — governed semantic/template only)

Use to confirm the model selector is not falsely “doing work” on simple KPIs.

1. Revenue by month  
2. Top brand by revenue  
3. Top dealer by revenue  
4. Maruti Suzuki sales by year  

---

## Optional: interpretation LLM (messy phrasing)

May trigger **interpret** (`nlq_llm_interpretation`) before planning; full SQL generation may still be governed.

1. tata car totl revnue all modls last yr  
2. whch dler sold most suvs in mumbai  

---

## Tips for demos

- After changing the admin **default model**, ask a **new** question (or rephrase slightly) so the query cache does not return an older answer.  
- For hybrid, open **Grounded on** and confirm **Semantic Layer** + citations; **LLM** is green only when a completion was recorded for that turn.  
- For “above regional average” dealer questions, SQL should join **`dim_dealer`** and region on **`d.region_id`** (dealer home region).

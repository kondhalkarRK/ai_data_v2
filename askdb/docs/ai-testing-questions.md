# AI Chat & semantic layer — 20 stress-test questions

Use these in **AI Chat** (SQL route) and optionally rebuild in **Analytics Builder**. Expected to exercise aggregations, joins, ranking, windows, and KPI math against the automotive (or insurance) semantic pack.

## Medium (1–7)

1. What is total revenue and units sold by region for the last 12 months?
2. Show revenue for SUVs in Mumbai versus Pune.
3. Which dealers sold more than 50 units last quarter, and what was their revenue?
4. List the top 10 models by revenue in Maharashtra.
5. Average selling price (revenue / units) by make for 2025.
6. How many distinct dealers contributed to revenue in each city?
7. Filter to Platinum dealers and show monthly units sold.

## Complex (8–14)

8. Revenue by region and make, including only makes that appear in at least three regions.
9. For each dealer, what share of their region’s revenue do they represent?
10. Compare YTD revenue to the same period last year by line of business / car type.
11. Dealers whose current-year revenue is below 80% of last year (same grain).
12. Rank models within each make by units sold and keep the top 3 per make.
13. Using a CTE, compute monthly revenue, then flag months more than 15% below the trailing 3-month average.
14. Claims (or sales) count and amount by status, excluding rows with null region.

## Very complex (15–20)

15. Running total of revenue by month, partitioned by region (window `SUM ... OVER`).
16. 3-month rolling average of units sold by make.
17. Month-over-month and year-over-year growth % for total revenue.
18. Cohort: dealers first appearing in 2024 — their 2025 revenue versus 2024.
19. 90th percentile of dealer monthly revenue (or closest supported percentile).
20. Advanced scenario: for the top region by YTD revenue, show YoY growth of its top 5 models, plus the contribution of those models to regional revenue.

## How to score

- **Pass:** correct grain, filters, and metric definition (glossary-aligned).
- **Soft fail:** right idea, wrong join or date window.
- **Hard fail:** hallucinated columns, double-counted facts, or ignored certified measure.

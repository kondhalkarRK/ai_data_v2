Document-only questions. Include a phrase like "in the document", "from the report", "policy document", "key findings", "concerns" or "recommendations". Without one, a question that mentions a metric or brand goes to SQL instead.

Summarize the dealer policy document
What are the key findings in the report?
According to the policy document, what is the maximum discount on electric vehicles?
What does the document say about Grade C dealers?
From the report, what is the EV battery warranty?
What concerns or risks are mentioned in the report?
What recommendations does the document make?
Data plus document questions. These start with "why" or "factors". You should get the SQL answer plus citations from the document.

Why did Tata EV sales grow in 2025?
Why is East region below target?
What factors are behind hatchback decline in 2025?



#	Question	Expected path	What it tests
1
Top 5 dealers by revenue in 2025
Compiled
Ranking, year filter, dealer vs salesperson rule
2
(follow-up) now show bottom 5
Compiled
Follow-up flips the ranking direction
3
Top 3 models per state by units sold in 2025
Compiled
Top-N per group (ranking within each state)
4
Month over month revenue growth for Hyundai in 2025
Compiled
Period growth, brand filter
5
3 month moving average of units sold for SUVs
Compiled
Moving average; "SUV" expands to all SUV segments
6
Market share of each brand by units in 2025
Compiled
Share against a window total
7
Fastest growing dealers in Maharashtra by revenue
Compiled
Growth ranking; Maharashtra maps to state code MH
8
Which brands have increasing units but decreasing average selling price?
Compiled
Divergence analysis
9
Revenue contribution of electric vehicles by city in Karnataka
Compiled
Contribution, EV synonym, state filter
10
Salespeople with above average revenue in Pune
Compiled
Above-average logic, salesperson entity
11
top sellng suvs in bangalore by revnue last quater
Compiled after rewrite
Spelling fixes, city alias, "last quarter"
12
Target achievement % by make for 2025, units sold vs target units
LLM
Targets aren't compiled, so the LLM must join targets on make and month
13
Units sold per active salesperson by dealer grade in 2025
LLM / mixed
Ratio with a safe denominator, three-table join
14
Why did revenue drop in East region in 2025?
Mixed (data + document)
"Why" routes to data plus document citations
15
Re-ask question 1 exactly
Cache
Should be instant and show as CACHE in Admin Center → LLM Usage

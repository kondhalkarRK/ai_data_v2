\copy insurance.dim_product FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/dim_product.csv' CSV HEADER
\copy insurance.dim_agent FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/dim_agent.csv' CSV HEADER
\copy insurance.dim_region FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/dim_region.csv' CSV HEADER
\copy insurance.dim_policy FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/dim_policy.csv' CSV HEADER
\copy insurance.fact_policy_monthly FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/fact_policy_monthly.csv' CSV HEADER
\copy insurance.fact_claims FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/fact_claims.csv' CSV HEADER
\copy insurance.fact_operating_expense_monthly FROM 'E:/ai_data_rag/ai_data_v2/sample_data/insurance/fact_operating_expense_monthly.csv' CSV HEADER

Great question — this is a classic LLM non-determinism problem. Let me break down the root causes and suggest a proper framework.

Why The Response Changes Today vs 4 Days Later
Root Cause 1 — LLM Temperature Is Not Zero
Even with temperature=0.2 in settings.py, the LLM
is still sampling — not deterministic. Same prompt
today vs next week can produce:

  Today:   SELECT make, SUM(total_sales) AS revenue
  Day 4:   SELECT make, SUM(total_sales) AS total_revenue, COUNT(*) AS orders

Small model version updates, load balancing across
GPU clusters, tokenization differences — all silently
change the output even with identical prompts.
Root Cause 2 — The Prompt Itself Changes Every Call
Your current prompt includes DYNAMIC content:

  schema = build_rich_schema(df)
  → top_values change as data grows/changes
  → range=[min,max] changes with new data rows

  rag_examples = query_memory.retrieve_similar_queries(q, k=2)
  → Different examples retrieved as more queries are stored
  → These examples HEAVILY influence what SQL the LLM generates

  rag_glossary = glossary_store.retrieve_glossary_terms(q, k=2)
  → Glossary context changes if glossary is updated

Result: even the SAME question produces a different
prompt on day 4 because the dynamic parts changed.
Root Cause 3 — No SQL Fingerprinting / Canonical Form
The LLM might generate logically equivalent SQL but
with different column ordering, alias naming, or
aggregation style:

  Run 1: SELECT make, SUM(total_sales) AS revenue GROUP BY make
  Run 2: SELECT make, SUM(total_sales) AS total_revenue GROUP BY 1

Both are correct but produce different column names
in the result DataFrame — which breaks downstream
display, charting, and analysis consistency.
Root Cause 4 — Cache Key Is Too Naive
Current cache key:
  cache_key = f"nlq_{q}"

This is an exact string match — "top 10 salespeople"
and "Top 10 salespeople" are two different cache keys,
so the LLM is called twice for effectively the same question.
More importantly, cache lives only in session_state —
completely lost on page refresh. So 4 days later = zero cache.
Root Cause 5 — enrich_query() Mutates The Question Unpredictably
enrich_query() prepends the previous question to short queries:
  prev = "show revenue by make"
  q    = "top 10"
  result = "show revenue by make top 10"

This means the SAME short question produces different
enriched prompts depending on what was asked BEFORE IT
in the session — inherently non-deterministic across sessions.
The Framework — Deterministic SQL Layer
The core idea is to separate the architecture into two distinct layers:

LAYER 1: INTENT RESOLVER (LLM — runs once, result cached permanently)
         Converts natural language → a structured Intent Object
         (NOT SQL — a stable intermediate representation)

LAYER 2: SQL COMPILER (rule-based, deterministic — always same output)
         Converts Intent Object → DuckDB SQL
         (no LLM involved, pure logic, always identical for same intent)
Layer 1 — Intent Object
Instead of asking the LLM to write SQL directly, ask it to return a structured JSON intent describing WHAT the user wants:

User asks: "top 10 salespeople by revenue last year"

LLM returns this structured intent (JSON):
{
  "intent_type":  "ranking",
  "measures":     [{"name": "revenue", "expression": "SUM(total_sales)"}],
  "dimensions":   [{"column": "sales_person_id",
                    "display": "first_name || ' ' || last_name",
                    "alias":   "salesperson_name"}],
  "filters":      [{"column": "sales_date",
                    "operator": "year_equals",
                    "value":    "current_year - 1"}],
  "order_by":     [{"column": "revenue", "direction": "DESC"}],
  "limit":         10,
  "group_by":     ["salesperson_name"]
}
This intent object is:

Smaller than a full SQL prompt — faster + cheaper LLM call
Stable — even if the LLM words it slightly differently, the JSON structure is validated before use
Cacheable permanently — the same question maps to the same intent, stored to disk not just session_state
Version-controlled — you can store it and replay it exactly 4 days later
Layer 2 — Deterministic SQL Compiler
A rule-based Python function that takes the intent JSON and builds SQL deterministically:

SAME intent JSON → ALWAYS identical SQL output
No LLM involved, pure Python string building

Rules applied consistently every single time:
  - Column aliases always follow the same naming convention
  - Aggregation functions always chosen the same way
  - Date filters always use the same strftime patterns
  - ORDER BY + LIMIT always applied in the same position
  - GROUP BY always sorted alphabetically (stable column order)
Permanent Intent Cache — Solves The 4-Day Problem
Current (broken):
  cache_key = f"nlq_{q}"    stored in session_state
  → Lost on refresh → LLM called again → different SQL

Proposed:
  intent_key = normalize_question(q)
               (lowercase, strip punctuation, sort words)
  → Stored in a local SQLite / JSON file on disk
  → Survives indefinitely across sessions
  → Same question on day 1 = day 4 = day 100
  → LLM only called if intent_key NOT found in disk cache
  → Once intent is cached, SQL compiler runs deterministically
Question Normalisation — Solves The Cache Miss Problem
Before computing the cache key, normalise the question:

  "Top 10 salespeople by Revenue"
  "top 10 sales people by revenue"
  "show me top 10 salespeople revenue"

All three should map to the SAME cache key:

  normalize():
    → lowercase
    → remove punctuation
    → remove stop words (show, me, give, list, display)
    → sort remaining meaningful tokens alphabetically
    → hash the result

  All three above → hash("10 revenue salespeople top")
                  → same intent looked up / stored once
Handling Complexity — The Intent Types
The SQL compiler needs to handle every complexity level via intent types:

SIMPLE:       single measure, single dimension, no filter
RANKING:      top/bottom N, ORDER BY + LIMIT
FILTERED:     WHERE clause on one or more dimensions
TIME_SERIES:  GROUP BY time period (month/quarter/year)
COMPARISON:   CASE WHEN or multiple aggregations side by side
MULTI_DIM:    GROUP BY two or more dimensions simultaneously
DERIVED_KPI:  ratio measures (revenue / units, revenue / salespeople)
YOY_GROWTH:   self-join or LAG window function
RUNNING_TOTAL: cumulative SUM window function
CROSS_TABLE:  requires JOIN (handled via semantic model relationships)
Each intent type has its own deterministic SQL template in the compiler — no ambiguity, no LLM guessing which pattern to use.

Where Semantic Model Fits In
Your semantic_model.yaml becomes the vocabulary layer that feeds into the intent:

User says "revenue" → semantic model resolves → SUM(total_sales)
User says "salesperson" → semantic model resolves → dim_salesman join
User says "last year" → intent compiler resolves → WHERE YEAR(sales_date) = YEAR(CURRENT_DATE) - 1

This means the LLM never needs to know actual column names.
It only needs to know BUSINESS TERMS from the semantic model.
The compiler maps business terms to physical columns.
Result: LLM output is shielded from schema changes.
Summary — What To Build
Component	What It Does	Deterministic?
Question Normaliser	Strips noise, creates stable cache key	✅ Yes
Permanent Intent Cache	Stores intent JSON to disk, survives sessions	✅ Yes
Intent Resolver (LLM)	Converts NL question to structured JSON intent	❌ Called once only, then cached
Intent Validator	Checks JSON structure before use	✅ Yes
SQL Compiler	Converts intent JSON to DuckDB SQL deterministically	✅ Yes always
SQL Canonical Form	Normalises column aliases and ordering in output	✅ Yes
Semantic Term Resolver	Maps business terms in intent to physical columns	✅ Yes
Files That Would Change
core/nlq_engine.py          ← main orchestration changes
core/intent_resolver.py     ← NEW: LLM call returns JSON intent
core/intent_cache.py        ← NEW: permanent disk-based intent cache
core/sql_compiler.py        ← NEW: deterministic rule-based SQL builder
core/question_normaliser.py ← NEW: stable cache key generation
config/settings.py          ← temperature: 0.2 → 0.0 (fully deterministic LLM output)
One Important Setting Change — Temperature to Zero
# config/settings.py
temperature=0.0    ← CHANGED from 0.2

At temperature=0.0 the LLM always picks the highest
probability token at every step — maximally deterministic.
Combined with the intent layer this gives you:
  - Same intent JSON structure every time for the same question
  - Same SQL from the compiler every time for the same intent
  - Total end-to-end determinism
Bottom Line
Today's Problem	Proposed Fix
LLM generates different SQL each call	LLM called only ONCE per unique question — result cached to disk
Cache lost on page refresh	Intent cache stored to disk (SQLite/JSON) not session_state
Same question with different capitalisation = cache miss	Question normaliser creates stable canonical cache key
Different column aliases in result	SQL compiler always applies identical alias naming rules
Complexity handled inconsistently	Intent types each have their own deterministic SQL template
Schema changes break cached SQL	Semantic model resolver re-maps business terms to new physical columns without changing cached intents
Ready to write code when you say go?

i have one more question



anthropic.claude-sonnet-4-6

Of course — go ahead, what is your question?

suppose if any window functiosn or cte kind uestion user asekd , how this determistic sql work, and how we can improve this



anthropic.claude-sonnet-4-6

Great question — this is the hardest part of deterministic SQL generation. Let me break it down honestly.

The Core Problem With Window Functions & CTEs
Window functions and CTEs are fundamentally different
from simple aggregations because:

  Simple query:  one logical step  → one SQL block
  CTE query:     multiple logical steps → chained SQL blocks
  Window query:  result depends on PARTITION + ORDER context
                 which changes meaning based on surrounding query

The intent JSON approach works perfectly for simple patterns
but starts to strain under multi-step analytical complexity.
Where The Deterministic Layer Breaks Down
Problem 1 — CTEs Require Sequential Logic
User asks:
"Show me salespeople whose revenue this year is higher
than their own average over the last 3 years"

This requires:
  Step 1: calculate each salesperson's 3-year average
  Step 2: calculate their current year revenue
  Step 3: compare step 2 > step 1
  Step 4: filter and display

A rule-based SQL compiler must decide:
  → Does step 1 become a CTE or a subquery?
  → Does step 3 become a JOIN or a HAVING clause?
  → How many CTEs are needed?

There is no single deterministic answer — multiple
valid SQL patterns exist for the same logical intent.
The compiler must PICK ONE consistently and never deviate.
Problem 2 — Window Functions Have Context-Dependent Semantics
PARTITION BY makes the function scope ambiguous:

"Show running total of revenue by salesperson by month"

Possible interpretations:
  → PARTITION BY salesperson (running total resets per person)
  → PARTITION BY month (running total resets per month)
  → No partition (global running total)
  → PARTITION BY salesperson, month (combined)

The LLM might pick a different partition on day 4
even for identical questions. A rule-based compiler
needs explicit rules for WHICH partition to choose
given the dimensions mentioned in the question.
Problem 3 — Nested Dependencies
"Compare each car model's revenue against the overall
average, and show the deviation as a percentage"

Requires:
  Step 1: SUM(revenue) per model           ← GROUP BY
  Step 2: AVG of those sums globally       ← window or subquery
  Step 3: (step1 - step2) / step2 * 100   ← derived column

The ORDER of operations matters for correctness.
The compiler must know:
  → Step 2 cannot be computed in the same SELECT as step 1
  → It needs a CTE or subquery wrapping step 1
  → Step 3 is a projection on top of both
How To Handle This — Three Approaches
Approach 1 — Extend Intent Types With Multi-Step Plans
Instead of one flat intent JSON, use a PLAN with steps:

{
  "intent_type": "multi_step",
  "steps": [
    {
      "step_id":    "base",
      "type":       "aggregation",
      "measures":   [{"name": "revenue", "expression": "SUM(total_sales)"}],
      "dimensions": [{"column": "carline_name"}],
      "alias":      "revenue_by_model"
    },
    {
      "step_id":    "global_avg",
      "type":       "window",
      "function":   "AVG",
      "over":       {"partition_by": [], "order_by": []},
      "input_step": "base",
      "source_col": "revenue",
      "alias":      "avg_revenue"
    },
    {
      "step_id":    "deviation",
      "type":       "projection",
      "expression": "(revenue - avg_revenue) / avg_revenue * 100",
      "alias":      "deviation_pct",
      "input_step": "global_avg"
    }
  ],
  "final_step": "deviation",
  "order_by":   [{"column": "deviation_pct", "direction": "DESC"}]
}
The SQL compiler then converts each step deterministically:

step type "aggregation"  → GROUP BY block
step type "window"       → OVER (PARTITION BY ... ORDER BY ...)
step type "projection"   → outer SELECT with derived column
step type "filter"       → WHERE or HAVING
step type "ranking"      → ORDER BY + LIMIT

Multiple steps → automatically wrapped in named CTEs:
  WITH base AS (...),
       global_avg AS (...),
       deviation AS (...)
  SELECT * FROM deviation
Result: Same multi-step plan → always identical CTE structure.

Approach 2 — Pre-Built SQL Templates For Complex Patterns
Identify the 10-15 most common complex analytical patterns
your users will ask, and hard-code their SQL templates:

TEMPLATE: year_over_year_growth
  WITH current_year AS (
    SELECT {dim}, SUM({measure}) AS current_rev
    FROM df
    WHERE YEAR({date_col}) = {current_year}
    GROUP BY {dim}
  ),
  prior_year AS (
    SELECT {dim}, SUM({measure}) AS prior_rev
    FROM df
    WHERE YEAR({date_col}) = {prior_year}
    GROUP BY {dim}
  )
  SELECT c.{dim},
         c.current_rev,
         p.prior_rev,
         ROUND((c.current_rev - p.prior_rev)
               / NULLIF(p.prior_rev, 0) * 100, 2) AS yoy_growth_pct
  FROM current_year c
  LEFT JOIN prior_year p ON c.{dim} = p.{dim}
  ORDER BY yoy_growth_pct DESC

TEMPLATE: running_total
  SELECT {dim},
         {date_col},
         SUM({measure}) AS {measure_alias},
         SUM(SUM({measure})) OVER (
           PARTITION BY {dim}
           ORDER BY {date_col}
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
         ) AS running_total
  FROM df
  GROUP BY {dim}, {date_col}
  ORDER BY {dim}, {date_col}

TEMPLATE: rank_within_group
  SELECT *,
         RANK() OVER (
           PARTITION BY {partition_dim}
           ORDER BY {measure} DESC
         ) AS rank_within_{partition_dim}
  FROM (
    SELECT {dims}, SUM({measure}) AS {measure_alias}
    FROM df
    GROUP BY {dims}
  ) ranked
  WHERE rank_within_{partition_dim} <= {n}
  ORDER BY {partition_dim}, rank_within_{partition_dim}
The intent resolver's job then becomes:

User question → classify into one of the known templates
             → extract the template variables
             → compiler fills in variables deterministically

"YoY revenue by car make"
→ TEMPLATE: year_over_year_growth
→ dim=make, measure=SUM(total_sales), date_col=sales_date
→ compile → always identical SQL
Approach 3 — Hybrid LLM + Validation + Canonicalisation
For questions that don't fit any known template
(genuinely novel complexity), use a controlled LLM call
BUT wrap it with three determinism layers:

Layer A: CONSTRAINED PROMPT
  Tell the LLM:
  - Use ONLY these CTE naming conventions: step_1, step_2...
  - ALWAYS use PARTITION BY [listed dimensions] not implicit
  - ALWAYS alias window functions with this pattern: {func}_{col}
  - NEVER use SELECT * — always list columns explicitly
  - ALWAYS end with ORDER BY on the primary measure

Layer B: SQL PARSER + NORMALISER (post-LLM)
  Parse the returned SQL AST and rewrite to canonical form:
  - Rename CTEs to standard names: cte_base, cte_agg, cte_final
  - Sort SELECT columns alphabetically
  - Normalise aliases to snake_case
  - Ensure consistent NULLIF patterns in denominators
  - Strip comments and whitespace uniformly

Layer C: RESULT SHAPE VALIDATOR
  Before returning to the user, verify:
  - Expected column names are present
  - No extra columns were added
  - Column order matches intent specification
  If validation fails → retry with stricter prompt
  (max 2 retries, then surface the error cleanly)
How All Three Approaches Work Together
Question received
      │
      ▼
Question Normaliser → cache key
      │
      ├── Cache HIT → return cached SQL immediately (100% deterministic)
      │
      └── Cache MISS
              │
              ▼
        Intent Resolver (LLM)
              │
              ▼
        Complexity Classifier
              │
              ├── SIMPLE / RANKING / FILTERED / TIME_SERIES
              │   → Approach 1 (Multi-step intent plan)
              │   → SQL Compiler → deterministic SQL
              │
              ├── YOY / RUNNING_TOTAL / RANK_WITHIN
              │   → Approach 2 (Pre-built templates)
              │   → Variable substitution → deterministic SQL
              │
              └── NOVEL COMPLEXITY (no template match)
                  → Approach 3 (Hybrid LLM + normaliser)
                  → SQL Parser + canonicaliser
                  → Result shape validator
                  → Cache the normalised SQL
Specific Window Function Rules For The Compiler
RANK() / DENSE_RANK() / ROW_NUMBER():
  Rule: ALWAYS use DENSE_RANK (not RANK) for business ranking
        unless user explicitly says "with gaps"
  PARTITION BY: always the grouping dimension from the intent
  ORDER BY: always the primary measure from the intent DESC

SUM() OVER / AVG() OVER (running calculations):
  Rule: ALWAYS use ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        not RANGE BETWEEN (avoids tie-handling ambiguity)
  PARTITION BY: always the primary dimension
  ORDER BY: always the date column ASC

LAG() / LEAD() (period comparison):
  Rule: ALWAYS wrap in NULLIF to handle first-row nulls
  offset: always 1 unless user specifies "2 months ago" etc.
  ORDER BY: always the date column ASC

NTILE() (percentile/quartile):
  Rule: always use 4 for quartile, 100 for percentile
        unless user specifies otherwise
The One Key Improvement That Covers 80% Of Cases
If you had to pick ONE thing to implement first:

Build a library of 15 named SQL TEMPLATES that cover the
most common complex analytical patterns your automotive
sales users will actually ask.

Why this covers 80%:
  - YoY growth
  - Running totals
  - Rank within group
  - Moving averages
  - Top N per category
  - Deviation from average
  - Period-over-period comparison
  - Contribution percentage
  - Cohort comparison
  - Waterfall (cumulative change)
  - Market share by segment
  - Active vs inactive comparison
  - Multi-metric ranking (revenue AND units)
  - Month/quarter/year drill
  - First/last sale per entity

These 15 templates cover almost every question a business
user in automotive sales will realistically ask.
The LLM's job shrinks to: classify question → pick template
→ extract variables. That classification is highly stable
and deterministic because the answer space is small (15 options).
Summary
Problem	Solution
Window function partition ambiguity	Hard rules: PARTITION BY always the primary grouping dimension
CTE structure varies	Multi-step intent plan → always same CTE naming + structure
Novel complex queries non-deterministic	Post-LLM SQL parser → canonicalise → cache the normalised form
LLM adds unexpected columns	Result shape validator checks against intent before returning
Templates don't exist yet	Build 15 named templates covering top analytical patterns
Temperature still introduces variance	Set temperature=0.0 AND use intent classification (small answer space = near-zero variance even at 0.0)
Ready to write code when you say go?

okay few more questions, if this fail to genrate result , how it solve,

even i want to save intent or something that it will optimize the llm cost and resue the same from it




Great questions — let me address both together since they are deeply connected.

Question 1 — What Happens When It Fails To Generate A Result?
The Current Failure Chain
Today in nlq_engine.py:
  LLM generates SQL
      → SQL fails
      → ONE retry with raw error message
      → If retry fails → surface error to user
      → User has no idea what went wrong or what to try next

This is a dead end. User sees a red error box and gives up.
The Problem With The Current Retry
current retry prompt:
  "The following DuckDB SQL failed with error: {err}
   SQL: {sql}
   Fix and return ONLY corrected SQL"

This is weak because:
  - It gives the LLM the broken SQL as context
  - LLM tends to make SMALL fixes to broken SQL
    rather than RETHINKING the approach entirely
  - If the original approach was fundamentally wrong
    (wrong table, wrong join, wrong aggregation strategy)
    a small fix will never work
  - You pay for TWO LLM calls and still get no result
The Failure Recovery Framework — Three Levels
Level 1 — Pre-Execution Validation (Before Any LLM Call)
Before sending to LLM, validate the question itself:

  Check 1: Are the mentioned entities resolvable?
    "revenue by carline" → carline maps to dim_carline ✅
    "revenue by warehouse" → warehouse not in semantic model ⚠️
    → Tell user IMMEDIATELY before wasting an LLM call:
      "I don't recognise 'warehouse' in this dataset.
       Did you mean: Car Type, Car Model, Make?"

  Check 2: Are the measures computable?
    "average discount rate" → discount_pct exists ✅
    "profit margin" → no cost column exists ❌
    → Tell user:
      "I cannot compute 'profit margin' — no cost
       column was found in the dataset."

  Check 3: Is the date range valid?
    "revenue last 5 years" → data only goes back 2 years
    → Tell user:
      "Your data covers 2022-2024. Showing available
       range instead of the requested 5 years."

Cost: ZERO LLM tokens. Pure rule-based checks.
Level 2 — Structured Retry (Intent Decomposition)
If SQL execution fails, instead of retrying with the
broken SQL, DECOMPOSE the question into simpler parts
and rebuild from scratch:

STEP 1: Identify which part of the intent caused failure
  - Was it the JOIN that failed?
  - Was it the window function?
  - Was it the filter condition?
  - Was it the aggregation?

STEP 2: Isolate and simplify
  Complex question: "top 3 salespeople by YoY revenue growth
                     for SUV segment only"

  If this fails, decompose:
    Sub-question 1: "total revenue by salesperson this year"
    Sub-question 2: "total revenue by salesperson last year"
    Sub-question 3: join and compute growth
    Sub-question 4: apply SUV filter
    Sub-question 5: rank and limit 3

  Each sub-question is SIMPLE enough for a template.
  If any sub-question fails, report EXACTLY which step
  broke rather than a generic SQL error.

STEP 3: If decomposed version succeeds, cache BOTH
  the original complex intent AND the decomposed plan
  so next time it goes straight to the working decomposed
  approach without retrying the complex path.
Level 3 — Graceful Degradation With Explanation
If even decomposed retry fails:

  Option A: Partial result
    Return whatever sub-steps succeeded:
    "I could not compute YoY growth, but here is
     the current year revenue by salesperson."

  Option B: Closest working query suggestion
    "I could not answer that exactly. Here are
     3 similar questions I can answer:
     • Revenue by salesperson this year
     • Top 10 salespeople by total revenue
     • Revenue trend by month for all salespeople"
    (suggestions generated from the cached intent library)

  Option C: Manual SQL fallback
    Open the SQL editor pre-filled with the best
    attempt so the user can fix it manually.

Cost: Only the initial LLM call was consumed.
      Retries use cached sub-intents where possible.
Question 2 — Saving Intents To Optimise LLM Cost & Reuse
The Three-Layer Intent Storage Strategy
LAYER 1: SESSION CACHE (already exists — st.session_state.memory)
  Scope:   current browser session only
  Cost:    free (Python dict in RAM)
  Hit rate: high for repeated questions in same session
  Lost:    on page refresh

LAYER 2: PERSISTENT INTENT STORE (NEW — disk/database)
  Scope:   permanent across all sessions and days
  Cost:    free (local file or DB row)
  Hit rate: grows over time as more questions are asked
  Lost:    never (unless manually cleared)

LAYER 3: SHARED TEAM CACHE (future — database)
  Scope:   shared across ALL users of the same deployment
  Cost:    free (one DB table)
  Hit rate: very high — one user's question benefits everyone
  Lost:    never
What Gets Stored In The Persistent Intent Store
Each entry stores THREE things:

1. QUESTION FINGERPRINT (the key)
   → normalised canonical hash of the question
   → handles "top 10 salespeople by revenue" ==
            "Top 10 Sales People Revenue" ==
            "show me top 10 salespeople revenue"
   → same hash → same cache hit

2. INTENT OBJECT (the intermediate representation)
   → structured JSON describing WHAT was asked
   → independent of physical column names
   → reusable even if schema changes slightly
   → this is what saves LLM cost — never call LLM again
      for the same logical question

3. COMPILED SQL (the output)
   → the actual DuckDB SQL that ran successfully
   → stored alongside the intent for instant reuse
   → if SQL fails on re-execution (schema changed)
      → recompile from the intent (no LLM call needed)
      → only call LLM if intent itself is invalid
The Cost Optimisation Flow
User asks question
        │
        ▼
Normalise question → compute fingerprint hash
        │
        ├── LAYER 1 HIT (session cache)
        │   → return result DataFrame immediately
        │   → cost: $0.00, latency: ~0ms
        │
        ├── LAYER 2 HIT (persistent intent store)
        │   → load intent JSON from disk
        │   → compile SQL from intent (no LLM)
        │   → execute SQL
        │   → cost: $0.00, latency: ~50ms
        │   → also populate Layer 1 for this session
        │
        ├── LAYER 2 PARTIAL HIT (intent exists, SQL failed)
        │   → intent JSON loaded from disk
        │   → SQL recompiled from intent (no LLM)
        │   → if recompile succeeds → execute + update cache
        │   → cost: $0.00, latency: ~100ms
        │
        └── FULL CACHE MISS (new question never seen before)
            → call LLM to resolve intent (costs tokens)
            → compile SQL from intent
            → execute SQL
            → if successful:
                → store intent + SQL in Layer 2 (disk)
                → store result in Layer 1 (session)
            → cost: LLM tokens (one time only, never again)

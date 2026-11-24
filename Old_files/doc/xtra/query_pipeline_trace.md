# ISANA Query Pipeline — Deterministic SQL Generation
## How a user question becomes a SQL query (without LLM writing SQL)

---

## Why This Matters

Traditional AI analytics let an LLM write raw SQL directly.
That is unpredictable: the same question can produce different SQL each time,
the LLM can hallucinate table names, join wrong columns, or just be wrong.

ISANA uses a **deterministic pipeline**: the LLM is used only once (intent extraction),
and everything after that is rule-based, reproducible, and auditable.

---

## The 5-Hop Pipeline

```
User Query
    │
    ▼
[HOP 1] LLM Intent Extractor          ← Only LLM call in the entire pipeline
    │    src/interpreter/llm_intent_extractor.py
    │    Classifies query, extracts parameters and filters as structured JSON
    │
    ▼
[HOP 2] Semantic Resolver              ← Pure Python, zero LLM calls
    │    src/agent_layer/semantic_resolver.py
    │    Maps metric name → SQL expression via kpi_registry.yaml lookup
    │    Produces the "execution contract"
    │
    ▼
[HOP 3] SQL Generator                  ← Pure Python, zero LLM calls
    │    src/kpi_engine/sql_generator.py
    │    Builds valid SQL from the execution contract
    │    Handles JOINs, WHERE, GROUP BY, ORDER BY, dedup logic
    │
    ▼
[HOP 4] Execution Dispatcher           ← Runs the SQL, returns rows
    │    src/kpi_engine/execution_dispatcher.py
    │    Passes SQL to SQLite, collects raw result rows
    │
    ▼
[HOP 5] Narration Engine               ← Formats rows into human response
         src/agent_layer/narration_engine.py
         Detects dimensions, renders tables, builds summary text
```

---

## HOP 1 — LLM Intent Extractor

**File:** `src/interpreter/llm_intent_extractor.py`
**Entry point:** `extract_intent_llm(query, conv_state)` — line 418

### What it does
Sends the user query to the LLM with a tightly structured system prompt.
The LLM returns a **single JSON object** — no prose, no SQL, just structured parameters.
If the LLM fails or times out, it falls back to a safe `UNKNOWN` dict.

### Code — the function that calls the LLM (lines 418–489)
```python
def extract_intent_llm(query: str, conv_state: dict | None = None) -> dict:

    # Hard-coded OOB guard — fires before any LLM call
    if _is_oob(query):                          # line 424 — regex check against _OOB_PATTERNS
        return { "intent": "OUT_OF_SCOPE", "in_scope": False, ... }

    # Build session context string from prior conversation state
    ctx_summary = "none"
    if isinstance(conv_state, dict):
        last_intent = conv_state.get("active_intent")
        if last_intent == "SCENARIO_ANALYSIS":
            # Inject prior scenario params so follow-up queries inherit them
            ctx_summary += f"; prior_scenario_params={prior_scenario}"

    prompt = _USER_PROMPT_TEMPLATE.format(query=query, context=ctx_summary)  # line 471

    # Single LLM call — only LLM call in the entire pipeline
    raw_text = _execute_chat(prompt, system_prompt=_SYSTEM_PROMPT)            # line 475

    raw_json = json.loads(raw_text)
    result   = _clean_result(raw_json)   # validate + normalize LLM output   # line 482
    return result
```

### Code — what `_clean_result` enforces (lines 317–415)
```python
def _clean_result(raw: dict) -> dict:
    # Intent must be one of the 6 valid values — else coerced to UNKNOWN
    intent = str(raw.get("intent")).upper()
    if intent not in VALID_INTENTS:           # line 320 — frozenset check
        intent = "UNKNOWN"

    # group_by must be a list of strings
    group_by = [str(g).lower() for g in raw_params.get("group_by") or []]   # line 333

    # metric must be in _KNOWN_METRICS frozenset — else becomes None
    metric = str(raw_params.get("metric")).lower().strip()
    if metric not in _KNOWN_METRICS:          # line 396–401 — catalog enforcement
        metric = None

    # region/category are validated against known enum values
    region = str(region_raw).capitalize() if region_raw else None
    if region not in {"North", "South", "East", "West"}:    # line 372
        region = None
```

### Code — the system prompt rules that guide the LLM (lines 73–221)
Key excerpts the LLM must follow:
```
"best selling product for north in 2023"
→ group_by=["product"], region=North (filter), year=2023 (filter), metric=revenue, order=DESC

"CRITICAL: When the user gives a SPECIFIC VALUE for a dimension, that is a FILTER, NOT a group_by.
  - 'for electronics in east region' → category=Electronics (filter), region=East (filter), group_by=[]
  - 'by category in east region'     → group_by=['category'], region=East (filter)"
```

### Input
```
"revenue or sales by region, category and year"
+ conv_state: { "active_intent": null }   ← no prior context
```

### Output
```python
{
  "intent":    "ANALYTICAL_QUERY",
  "in_scope":  True,
  "parameters": {
    "metric":   "revenue",
    "group_by": ["region", "category", "year"],
    "order":    "DESC",
    "limit":    None
  },
  "filters": {
    "category": None, "region": None, "year": None,
    "optimization_mode": None, "risk_level": None
  }
}
```

---

## HOP 2 — Semantic Resolver

**File:** `src/agent_layer/semantic_resolver.py`
**Entry point:** `resolve_semantics(validated)` — line 216

### What it does
Takes the intent JSON, looks up the metric in `kpi_registry.yaml`, and returns
an "execution contract" — a dict telling the SQL Generator exactly what SQL
expression to compute, from which table, with which filters.

### Code — metric registry lookup chain (lines 385–426)
```python
registry       = MetricRegistry()                    # loads kpi_registry.yaml
dependency_graph = DependencyGraph(registry)
metric_resolver  = MetricResolver(registry, dependency_graph)

resolved_metric = metric_resolver.resolve(metric_name)   # line 409 — looks up "revenue"

resolved_expression   = resolved_metric.get("formula")          # → "SUM(s.sum_revenue)"
resolved_source_tables = resolved_metric.get("source_tables")   # → ["daily_store_product_summary"]
resolved_base_table    = resolved_source_tables[0]              # → "daily_store_product_summary"
```

**`MetricResolver.resolve()`** — `src/kpi_registry/metric_resolver.py`
```python
def resolve(self, metric_name):
    if metric_name in self.registry.measures:          # check base measures first
        metric = self.registry.measures[metric_name]
        col    = metric["column"]                      # → "sum_revenue"
        agg    = str(metric.get("aggregation")).upper()  # → "SUM"
        formula = metric.get("formula") or f"{agg}({col})"  # → "SUM(sum_revenue)"
        return {
            "formula":       formula,
            "source_tables": [metric["table"]],        # → ["daily_store_product_summary"]
            "default_filters": metric.get("default_filters") or {},
        }
```

**`MetricRegistry.load_registry()`** — `src/kpi_engine/metric_registry.py`
```python
def load_registry(self):
    with open("config/domain/kpi_registry.yaml") as f:
        config = yaml.safe_load(f)
    self.measures       = config.get("measures", {})      # base columns + aggregation
    self.derived_measures = config.get("derived_measures", {})  # computed formulas
    self.metrics        = config.get("metrics", {})       # composite KPIs
```

**`config/domain/kpi_registry.yaml`** — the single source of truth for table/column mapping
```yaml
measures:
  revenue:                              # ← metric name from LLM
    column: sum_revenue                 # ← actual DB column name
    aggregation: sum                    # ← SUM / AVG / COUNT
    table: daily_store_product_summary  # ← which table to query

  stockout_probability:
    column: stockout_probability
    aggregation: avg
    table: fact_inventory_risk          # ← different table for risk queries

  replenishment_quantity:
    column: recommended_units
    aggregation: sum
    table: fact_inventory_decision
    default_filters:
      action_type: REPLENISH            # ← auto-applied WHERE filter
```

### Code — dimension and filter normalization (lines 427–648)
```python
# group_by from LLM: ["region", "category", "year"]
group_by   = parameters.get("group_by")
dimensions = [str(item).lower() for item in group_by]   # line 429

# Alias normalization — plural/variant forms → canonical names
dimension_aliases = {
    "regions": "region", "categories": "category",
    "products": "product", "stores": "store",
}
for dim in dimensions:
    mapped = dimension_aliases.get(dim, dim)          # line 449–452
    normalized_dimensions.append(mapped)

# Filters from LLM
region   = validated_filters.get("region")            # line 542 → "north"
category = validated_filters.get("category")          # line 547 → None
year     = validated_filters.get("year")              # line 526 → None

# Default 6-month rolling window when NO time filter is present on operational tables
if _no_time_filter and resolved_base_table in _OPERATIONAL_TABLES:   # line 594
    resolved_filters["months_back"] = 6
```

### Input
```python
{
  "intent":    "ANALYTICAL_QUERY",
  "parameters": { "metric": "revenue", "group_by": ["region","category","year"] },
  "filters":    { "region": None, "year": None }
}
```

### Output (execution contract)
```python
{
  "expression":       "SUM(s.sum_revenue)",
  "base_table":       "daily_store_product_summary",
  "source_tables":    ["daily_store_product_summary"],
  "group_by":         ["region", "category", "year"],
  "mapped_dimensions": ["region", "category", "year"],
  "filters":          {},        # no time/region/category constraint for Q1
  "order":            None,
  "limit":            None,
  "metric_name":      "revenue"
}
```

---

## HOP 3 — SQL Generator

**File:** `src/kpi_engine/sql_generator.py`
**Entry point:** `generate_from_contract(resolved_contract)` — line 105

### What it does
Takes the execution contract and mechanically assembles valid SQL.
This is the heart of determinism — the same contract always produces the same SQL.

### Code — Step 1: Dimension expansion (lines 171–184)
Prevents ambiguous IDs. `store_id` repeats across 4 regions; `product_id` across 5 categories.
Auto-prepends the parent dimension so every breakdown is unambiguous.
```python
_expanded: list[str] = []
for _f in group_by_fields:
    if _f == "store" and "region" not in group_by_fields:
        _expanded.append("region")          # store → inject region first
    if _f == "product" and "category" not in group_by_fields:
        _expanded.append("category")        # product → inject category first
    _expanded.append(_f)
group_by_fields = _expanded

# Month without year → inject year before month (avoids cross-year mixing)
if "month" in group_by_fields and "year" not in group_by_fields:   # line 182
    month_index = group_by_fields.index("month")
    group_by_fields.insert(month_index, "year")
```

### Code — Step 2: SELECT clause (lines 217–235)
```python
FIELD_MAPPING = {
    "region":   ("dim_store",   "region"),      # line 71
    "category": ("dim_product", "category"),    # line 74
    "year":     ("dim_date",    "year"),         # line 68
    "product":  ("dim_product", "product_id"),  # line 73
    "store":    ("dim_store",   "store_id"),     # line 72
}

# Build SELECT columns
dim_select_parts = []
for field in group_by_fields:                           # line 219
    table, column = self.FIELD_MAPPING[field]
    dim_select_parts.append(f"{table}.{column} AS dim_{field}")
    required_tables.add(table)                         # add to JOIN list

# Append the metric expression
select_clause = ", ".join(dim_select_parts + [f"{expr} AS value"])   # line 228
# → "dim_store.region AS dim_region, dim_product.category AS dim_category,
#    dim_date.year AS dim_year, SUM(s.sum_revenue) AS value"
```

### Code — Step 3: JOIN clause (lines 238–248)
```python
joins = []
for table in required_tables:
    if table == base_table:
        continue
    join_condition = self._get_join_path(table, base_alias)   # line 243
    joins.append(f"JOIN {table} ON {join_condition}")

# _get_join_path() — lines 437–445
join_paths = {
    "dim_date":    f"{base_alias}.date_key    = dim_date.id",
    "dim_store":   f"{base_alias}.store_key   = dim_store.id",
    "dim_product": f"{base_alias}.product_key = dim_product.id",
    "dim_supplier":f"{base_alias}.supplier_key= dim_supplier.id",
}
```

### Code — Step 4: WHERE clause (lines 251–373)
```python
where_clauses = []

# Run ID pin for DETERMINISTIC queries (simulation/policy tables)
if run_id:
    where_clauses.append(f"{base_alias}.simulation_run_id = '{run_id}'")   # line 255

# Year filter
if isinstance(year_value, int):
    where_clauses.append(f"dim_date.year = {year_int}")                    # line 302

# Region/category dimension filters
elif key in self.FIELD_MAPPING:
    table, column = self.FIELD_MAPPING[key]
    where_clauses.append(f"{table}.{column} = '{value}' COLLATE NOCASE")  # line 334

# Risk level translation (HIGH/MEDIUM/LOW → numeric ranges)
_RISK_LEVEL_TO_EXPR = {
    "HIGH":   "{a}.expected_risk >= 0.7",        # line 61
    "MEDIUM": "{a}.expected_risk >= 0.4 AND {a}.expected_risk < 0.7",
    "LOW":    "{a}.expected_risk < 0.4",
}
```

### Code — Step 5: Dedup guard (lines 359–371)
Critical correctness fix. Point-in-time tables store one row per
`(date, store, product)` per day — SUM without dedup inflates by ~730×.
```python
_POINT_IN_TIME_TABLES = frozenset({          # line 16
    "fact_inventory_risk",
    "fact_inventory_decision",
    "fact_inventory_daily",
    "fact_inventory_policy",
    "fact_inventory_simulation",
})

_is_pit       = base_table in _POINT_IN_TIME_TABLES       # line 359
_has_sum_count = bool(re.search(r"\b(SUM|COUNT)\s*\(", expr))  # line 360
_needs_dedup  = _is_pit and has_aggregation and _has_sum_count  # line 361

if _needs_dedup:                                          # line 363
    _dedup_from = (
        f"(SELECT *, ROW_NUMBER() OVER "
        f"(PARTITION BY store_key, product_key "
        f" ORDER BY date_key DESC) AS _rn "
        f"FROM {base_table}) {base_alias}"
    )
    where_clauses.append(f"{base_alias}._rn = 1")
# Note: AVG is safe without dedup — AVG of 730 equal values = correct value.
# Only SUM and COUNT are affected by the multi-day row inflation.
```

### Code — Step 6: ORDER BY + LIMIT (lines 400–403)
```python
if group_by_fields:
    sql_parts.append(f"ORDER BY value {order_value}")   # line 401 — default DESC
    if limit_value is not None:
        sql_parts.append(f"LIMIT {limit_value}")        # line 403

# Auto-LIMIT for "top/highest/most" queries
normalized_query = str(resolved_contract.get("normalized_query") or "").lower()
if limit_value is None and re.search(r"\b(top|highest|most)\b", normalized_query):  # line 163
    limit_value = 1
    order_value = "DESC"
```

### Input
```python
{
  "expression":  "SUM(s.sum_revenue)",
  "base_table":  "daily_store_product_summary",
  "group_by":    ["region", "category", "year"],
  "filters":     {},
  "order":       None,
  "limit":       None
}
```

### Output (SQL string)
```sql
SELECT dim_store.region    AS dim_region,
       dim_product.category AS dim_category,
       dim_date.year        AS dim_year,
       SUM(s.sum_revenue)   AS value
FROM daily_store_product_summary s
JOIN dim_store   ON s.store_key   = dim_store.id
JOIN dim_product ON s.product_key = dim_product.id
JOIN dim_date    ON s.date_key    = dim_date.id
GROUP BY dim_store.region, dim_product.category, dim_date.year
ORDER BY value DESC
```

---

## HOP 4 — Execution Dispatcher

**File:** `src/kpi_engine/execution_dispatcher.py`
**Entry point:** `handle_metric(resolved)` — line 136

### What it does
Assembles the SQL contract from the resolved dict, calls SQLGenerator,
runs the SQL against SQLite, and returns raw row dicts.

### Code — full `handle_metric` function (lines 136–204)
```python
def handle_metric(self, resolved: dict) -> dict:

    # Pull fields from the resolved contract
    expression  = resolved.get("expression")          # "SUM(s.sum_revenue)"
    dimensions  = resolved.get("mapped_dimensions") or []
    filters     = resolved.get("filters") or {}

    # Assemble SQL contract — all keys the SQL Generator needs
    sql_contract = {
        "expression":    expression,                   # line 152
        "group_by":      dimensions,
        "filters":       filters,
        "context":       resolved.get("context") or {},
        "source_tables": resolved.get("source_tables") or [],
        "base_table":    resolved.get("base_table") or "fact_inventory_risk",
        "order":         resolved.get("order"),
        "limit":         resolved.get("limit"),
        "normalized_query": resolved.get("normalized_query"),
    }

    # Delegate 100% of SQL construction to SQLGenerator — no inline SQL here
    generator = SQLGenerator()
    sql = generator.generate_from_contract(sql_contract)     # line 166 → HOP 3

    # Run the SQL
    conn = sqlite3.connect(self.db_path)                     # line 169
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql).fetchall()                  # line 172
    finally:
        conn.close()

    return {
        "rows":              [dict(row) for row in rows],   # line 201 — list of row dicts
        "evidence_contract": sql_evidence,                  # audit trail
    }
```

### Input
```python
resolved execution contract from Semantic Resolver (HOP 2)
```

### Output
```python
{
  "rows": [
    {"dim_region": "North", "dim_category": "Electronics", "dim_year": 2023, "value": 4820000},
    {"dim_region": "North", "dim_category": "Clothing",    "dim_year": 2023, "value": 3120000},
    {"dim_region": "South", "dim_category": "Electronics", "dim_year": 2023, "value": 3880000},
    ...
  ],
  "evidence_contract": { "evidence_id": "...", "execution_status": "success", ... }
}
```

---

## HOP 5 — Narration Engine

**File:** `src/agent_layer/narration_engine.py`
**Entry point:** `generate_narration(data, intent, handler, ...)` — line 1160

### What it does
Takes the raw rows dict, detects which columns are dimensions vs the metric value,
and renders a markdown table + summary sentence.

### Code — main entry `generate_narration` (line 1160)
```python
def generate_narration(data, intent, handler, query_type,
                        metric_label=None, ...) -> dict:

    execution_result = data if isinstance(data, dict) else {}

    # Resolve raw SQL expression to display label
    metric_label = _resolve_metric_display_label(metric_label)   # line 1181
    # e.g. "sum_revenue" → "Revenue"

    # Evidence grounding check — blocks narration if SQL wasn't actually run
    is_grounded, reason = validate_narration_engine_grounding(...)  # line 1206
    if not is_grounded:
        return { "narration": "Narration synthesis blocked: ...", ... }

    # Route to the right formatter based on what's in the result
    rows = execution_result.get("rows") or []
    return _build_grounded_output(_describe_rows(rows))          # line ~1320
```

### Code — `_describe_rows` + dimension detection (lines 900–923)
```python
def _describe_rows(rows: list) -> str | None:
    items = [row for row in rows if isinstance(row, dict)]

    # Detect which columns are dimensions vs the value column
    dimensions, value_column = _detect_grouped_dimensions(items)   # line 909

    if dimensions and value_column:
        grouped_narration = _generate_grouped_narration(items, dimensions, value_column)
        if grouped_narration:
            return grouped_narration
```

### Code — `_detect_grouped_dimensions` (lines 815–836)
```python
def _detect_grouped_dimensions(rows) -> tuple[list[str], str | None]:
    first_row  = rows[0]
    dimensions = []
    value_column = None

    for key in first_row.keys():
        value = first_row[key]
        if _is_number(value):                  # numeric → this is the value column
            value_column = str(key)            # → "value"
        else:
            dimensions.append(str(key))        # non-numeric → dimension
            # → ["dim_region", "dim_category", "dim_year"]
    return dimensions, value_column
```

### Code — `_generate_grouped_narration` (lines 839–895)
```python
def _generate_grouped_narration(rows, dimensions, value_column) -> str | None:
    if len(items) > 4:                             # line 871 — large result set
        max_item = max(items, key=lambda r: float(r.get(value_column, 0)))
        min_item = min(items, key=lambda r: float(r.get(value_column, 0)))
        max_dims = " and ".join(str(max_item.get(dim)) for dim in dimensions)
        min_dims = " and ".join(str(min_item.get(dim)) for dim in dimensions)

        return (
            f"Breakdown by {dim_label} — {max_dims} leads at {_format_number(max_val)}, "
            f"while {min_dims} is lowest at {_format_number(min_val)}. "
            f"{metric_name.capitalize()} varies across {len(items)} {dim_plural}."
        )
```

### Input
```python
{
  "rows": [
    {"dim_region": "North", "dim_category": "Electronics", "dim_year": 2023, "value": 4820000},
    ...  (many rows)
  ]
}
```

### Output (what the user sees)
```
Breakdown by region — North and Electronics and 2023 leads at 4,820,000,
while West and Groceries and 2022 is lowest at 890,000.
Value varies across 60 combinations.

| dim_region | dim_category | dim_year | value     |
|------------|--------------|----------|-----------|
| North      | Electronics  | 2023     | 4,820,000 |
| North      | Clothing     | 2023     | 3,120,000 |
...
```

---

## Traced Examples — Full Code Path

---

### Query 1: "revenue or sales by region, category and year"

| Hop | File | Function | Key Code Decision |
|-----|------|----------|-------------------|
| 1 | `llm_intent_extractor.py` | `extract_intent_llm` | LLM sees "by region, category and year" → sets `group_by=["region","category","year"]`; "revenue or sales" → `metric=revenue` |
| 1 | `llm_intent_extractor.py` | `_clean_result` (L317) | Validates `metric="revenue"` is in `_KNOWN_METRICS`; validates `group_by` is a list of strings |
| 2 | `semantic_resolver.py` | `resolve_semantics` (L216) | Calls `metric_resolver.resolve("revenue")` |
| 2 | `metric_resolver.py` | `resolve` | Finds `revenue` under `measures` in yaml → `formula="SUM(sum_revenue)"`, `table="daily_store_product_summary"` |
| 2 | `semantic_resolver.py` | L427–452 | Normalizes `["region","category","year"]`; no time filter present → applies default 6-month window |
| 3 | `sql_generator.py` | `generate_from_contract` (L105) | No auto-prepend needed (region + category are top-level dims). `["region","category","year"]` → 3 JOINs |
| 3 | `sql_generator.py` | L217–235 | SELECT builds `dim_store.region, dim_product.category, dim_date.year, SUM(s.sum_revenue) AS value` |
| 3 | `sql_generator.py` | L359–371 | `daily_store_product_summary` NOT in `_POINT_IN_TIME_TABLES` → no dedup needed |
| 4 | `execution_dispatcher.py` | `handle_metric` (L136) | Assembles `sql_contract`, calls `SQLGenerator().generate_from_contract()`, runs `conn.execute(sql).fetchall()` |
| 5 | `narration_engine.py` | `_detect_grouped_dimensions` (L815) | Sees `dim_region`, `dim_category`, `dim_year` (non-numeric) → dimensions; `value` (numeric) → value column |
| 5 | `narration_engine.py` | `_generate_grouped_narration` (L839) | >4 rows → finds max/min, generates "North leads at X, West lowest at Y" |

**SQL produced:**
```sql
SELECT dim_store.region    AS dim_region,
       dim_product.category AS dim_category,
       dim_date.year        AS dim_year,
       SUM(s.sum_revenue)   AS value
FROM daily_store_product_summary s
JOIN dim_store   ON s.store_key   = dim_store.id
JOIN dim_product ON s.product_key = dim_product.id
JOIN dim_date    ON s.date_key    = dim_date.id
GROUP BY dim_store.region, dim_product.category, dim_date.year
ORDER BY value DESC
```

---

### Query 2: "top performing products in north region for year 2022"

| Hop | File | Function | Key Code Decision |
|-----|------|----------|-------------------|
| 1 | `llm_intent_extractor.py` | `_SYSTEM_PROMPT` (L73) | "top performing" → `order=DESC`; "products" → `group_by=["product"]`; "north region" → `region=North` (filter, NOT group_by); "2022" → `year=2022` (filter) |
| 1 | `llm_intent_extractor.py` | `_clean_result` (L366–377) | `region="North"` validated against `_VALID_REGIONS`; "north" → `.capitalize()` → "North" |
| 2 | `semantic_resolver.py` | L542–544 | `region="North"` → `resolved_filters["region"] = "north"` (lowercased for SQL comparison) |
| 2 | `semantic_resolver.py` | L526–538 | `year=2022` → `resolved_filters["year"] = 2022` |
| 2 | `semantic_resolver.py` | L589–599 | Year filter IS present → skip default 6-month window |
| 3 | `sql_generator.py` | L171–178 | `group_by=["product"]` → **auto-prepend** adds `"category"` → becomes `["category", "product"]` (line 175–177) |
| 3 | `sql_generator.py` | L300–302 | `year=2022` → `WHERE dim_date.year = 2022` |
| 3 | `sql_generator.py` | L331–336 | `region="north"` → `WHERE dim_store.region = 'North' COLLATE NOCASE` |
| 3 | `sql_generator.py` | L359–361 | `daily_store_product_summary` not in PIT tables → no dedup |
| 4 | `execution_dispatcher.py` | `handle_metric` (L136) | Runs SQL, returns rows ordered by `value DESC` |
| 5 | `narration_engine.py` | `_detect_grouped_dimensions` (L815) | `dim_category`, `dim_product` = dimensions; `value` = value column |
| 5 | `narration_engine.py` | `_generate_grouped_narration` (L871) | Lists top products with revenue, notes leader and laggard |

**SQL produced:**
```sql
SELECT dim_product.category   AS dim_category,
       dim_product.product_id AS dim_product,
       SUM(s.sum_revenue)      AS value
FROM daily_store_product_summary s
JOIN dim_store   ON s.store_key   = dim_store.id
JOIN dim_product ON s.product_key = dim_product.id
JOIN dim_date    ON s.date_key    = dim_date.id
WHERE dim_store.region = 'North' COLLATE NOCASE
  AND dim_date.year = 2022
GROUP BY dim_product.category, dim_product.product_id
ORDER BY value DESC
```

> **Key insight:** "north" and "2022" went into `filters`, not `group_by`.
> The LLM prompt explicitly says: *"for north in 2022 → region=North (filter), year=2022 (filter)"*.
> `_clean_result` enforces "North" is a valid region value.
> SQL Generator puts them in WHERE, not GROUP BY.

---

### Query 3: "top risk products by category in west for year 2023"

| Hop | File | Function | Key Code Decision |
|-----|------|----------|-------------------|
| 1 | `llm_intent_extractor.py` | `_SYSTEM_PROMPT` (L73) | "top risk" → `order=DESC`; "products by category" → `group_by=["category","product"]`; "west" → `region=West` (filter); "2023" → `year=2023` (filter) |
| 1 | `llm_intent_extractor.py` | `_SYSTEM_PROMPT` metric rules | "top risk" → `metric="stockout_probability"` (not "risk" or "revenue") |
| 1 | `llm_intent_extractor.py` | `_clean_result` (L396) | `stockout_probability` validated in `_KNOWN_METRICS` ✓ |
| 2 | `semantic_resolver.py` | `resolve` (L409) | `metric_resolver.resolve("stockout_probability")` → looks up yaml |
| 2 | `metric_registry.py` | `load_registry` (L14) | `stockout_probability` → `column="stockout_probability"`, `aggregation="avg"`, `table="fact_inventory_risk"` |
| 2 | `metric_resolver.py` | `resolve` | `formula = "AVG(stockout_probability)"`, `source_tables = ["fact_inventory_risk"]` |
| 2 | `semantic_resolver.py` | L542, L526 | `region="west"`, `year=2023` → both go into `resolved_filters` |
| 3 | `sql_generator.py` | L171–178 | `group_by=["category","product"]` — category already present → **no auto-prepend** needed |
| 3 | `sql_generator.py` | L359–361 | `fact_inventory_risk` IS in `_POINT_IN_TIME_TABLES`. But expression is `AVG(...)`. `_has_sum_count=False` → **no dedup** (AVG of 730 identical values = correct result) |
| 3 | `sql_generator.py` | L300–336 | `year=2023` → `WHERE dim_date.year = 2023`; `region="west"` → `WHERE dim_store.region = 'West' COLLATE NOCASE` |
| 4 | `execution_dispatcher.py` | `handle_metric` (L136) | Runs SQL, returns rows with `value` = stockout probability (0.0–1.0) |
| 5 | `narration_engine.py` | `_describe_rows` (L900) | Rows have `dim_category`, `dim_product` (non-numeric) and `value` (numeric 0.0–1.0) → grouped narration |
| 5 | `narration_engine.py` | `_generate_grouped_narration` (L880) | Max = highest risk product; min = lowest risk product |

**SQL produced:**
```sql
SELECT dim_product.category   AS dim_category,
       dim_product.product_id AS dim_product,
       AVG(r.stockout_probability) AS value
FROM fact_inventory_risk r
JOIN dim_store   ON r.store_key   = dim_store.id
JOIN dim_product ON r.product_key = dim_product.id
JOIN dim_date    ON r.date_key    = dim_date.id
WHERE dim_store.region = 'West' COLLATE NOCASE
  AND dim_date.year = 2023
GROUP BY dim_product.category, dim_product.product_id
ORDER BY value DESC
```

> **Why no dedup here?** `fact_inventory_risk` is a point-in-time table.
> But we're using `AVG`, not `SUM`. Averaging 730 daily snapshots of the same
> stockout probability = the correct single value. Dedup is only needed for SUM/COUNT.
> Code check at line 360: `_has_sum_count = bool(re.search(r"\b(SUM|COUNT)\s*\(", expr))`

---

## Design Principles Summary

| Problem | Where it's solved | Code reference |
|---------|-------------------|----------------|
| LLM choosing wrong table name | LLM never sees table names. Table comes from `kpi_registry.yaml` | `metric_resolver.py` line 30 |
| LLM writing incorrect SQL | LLM outputs JSON only. SQL built by Python | `sql_generator.py` line 105 |
| Same query → different SQL | All SQL logic is deterministic Python | `generate_from_contract` is pure functions |
| SUM inflation on daily tables (~730×) | Dedup guard wraps with `ROW_NUMBER()` | `sql_generator.py` line 359–371 |
| Ambiguous store/product IDs | Dimension auto-prepend adds parent dim | `sql_generator.py` line 171–178 |
| "north" → filter, not group_by | LLM prompt rules + `_clean_result` validation | `llm_intent_extractor.py` line 127–136 |
| Unknown metric key | Validated against `_KNOWN_METRICS` frozenset | `llm_intent_extractor.py` line 396–401 |
| Unknown region/category | Validated against `_VALID_REGIONS / _VALID_CATEGORIES` | `llm_intent_extractor.py` line 366–377 |
| Time-window correctness | Default 6-month window; ordinal arithmetic for cross-year | `semantic_resolver.py` line 589–599 |
| Narration from unexecuted data | Evidence grounding check blocks synthesis | `narration_engine.py` line 1206 |

---

## File Map

```
src/
├── interpreter/
│   └── llm_intent_extractor.py     HOP 1 — extract_intent_llm()          line 418
│                                            _clean_result()                line 317
│                                            _SYSTEM_PROMPT                 line 73
│                                            _KNOWN_METRICS                 line 49
│
├── agent_layer/
│   └── semantic_resolver.py        HOP 2 — resolve_semantics()            line 216
│                                            (calls MetricRegistry + MetricResolver)
│
├── kpi_registry/
│   └── metric_resolver.py          HOP 2 — MetricResolver.resolve()
│                                            (looks up formula + table from registry)
│
├── kpi_engine/
│   ├── metric_registry.py          HOP 2 — MetricRegistry.load_registry() line 14
│   │                                        (parses kpi_registry.yaml)
│   │
│   ├── sql_generator.py            HOP 3 — generate_from_contract()        line 105
│   │                                        dimension expansion             line 171
│   │                                        SELECT builder                  line 217
│   │                                        JOIN builder                    line 238
│   │                                        WHERE builder                   line 251
│   │                                        Dedup guard                     line 359
│   │                                        ORDER BY + LIMIT                line 400
│   │
│   └── execution_dispatcher.py     HOP 4 — handle_metric()                 line 136
│                                            (assembles contract, calls SQLGenerator, runs SQL)
│
└── agent_layer/
    └── narration_engine.py         HOP 5 — generate_narration()            line 1160
                                             _detect_grouped_dimensions()    line 815
                                             _generate_grouped_narration()   line 839
                                             _describe_rows()                line 900

config/
└── domain/
    └── kpi_registry.yaml           SOURCE OF TRUTH — metric → column + table + aggregation
                                    (used by HOP 2, never seen by LLM)
```

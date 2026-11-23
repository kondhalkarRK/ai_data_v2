# NLQ Accuracy Audit — Streamlit vs askdb

## Root causes (pre-fix; confirmed by deep audits)

| Gap | Streamlit (`core/` + `semantic/`) | askdb before fix | Effect |
|-----|-----------------------------------|------------------|--------|
| Prompt context | Live path is **semantic-enriched LLM SQL** (`nlq_to_sql` + `SemanticContextBuilder`); deterministic `intent_resolver`/`sql_compiler` exist but are unwired | LLM got a short static `_schema_hints` list; packs unused on chat | Weak entity binding |
| Intent / filters | Glossary + prompt rules; sedan is **soft** (`ILIKE '%sedan%'`) via LLM inference, not a glossary `sql_expression` | Regex templates dropped body-style filters | Sedan asks returned all types |
| Salesperson vs dealer | Separate glossary/dimension/tables; prompt rules for name concat vs `dim_dealer` | No salesperson template; dealer regex over-broad | “Top salesperson” → dealer |
| Domain pack | Rich glossary + domain rules injected into prompt | Thin glossary; chat never called `SemanticService` | Synonym collisions |

## Failure mapping (pre-fix)

- **Top salesperson** → no salesperson-ranked template; LLM/dealer path wins.
- **Top selling sedan** → “top selling” template returns all models; Sedan never applied as `car_type = 'Sedan'`.

## Fix strategy (accuracy without prompt bloat)

1. Enrich domain YAML (glossary + rules) — salesperson ≠ dealer; Sedan/SUV/Hatchback filters.
2. Deterministic question understanding (entity + metric + filters) before templates/LLM.
3. Templates driven by that plan (salesperson, dealer, vehicle+car_type).
4. Compact, **industry-scoped** semantic hints for LLM only when templates miss.
5. Light SQL validation that required filters appear when extracted.

Prefer domain routing + strong YAML + entity validation over dumping full YAML into every prompt.

## Implemented (askdb) — remediated

| Component | Path | Role |
|-----------|------|------|
| Question plan | `app/services/chat/question_understanding.py` | Entity / metric / body-style filters before SQL |
| Plan templates | `app/services/chat/templates.py` | Salesperson → `dim_salesman`; sedan → `car_type = 'Sedan'` |
| Domain hints | `app/services/chat/semantic_context.py` | Pack-scoped glossary + tables for LLM only |
| Chat wiring | `app/services/chat/service.py` | Plan → clarify → template → LLM + `validate_sql_against_plan` |
| Glossary | `semantic/packs/automotive/business_glossary.yaml` | Disambiguation + always/never rules |
| Benchmarks | `tests/test_nlq_benchmark_suite.py` | Salesperson / sedan / dealer / ambiguity cases |

**Note:** askdb now uses **exact** `car_type = 'Sedan'` (stronger than Streamlit’s soft ILIKE for these cases). Streamlit’s unused deterministic compiler remains a future option, not a dependency.

## Phase 0–6 implementation status

- Live, industry-scoped categorical values are declared by `value_domains` in
  each semantic model and loaded into a bounded 30-minute cache.
- Question matching uses canonical database spelling and configured aliases
  (for example Delhi → New Delhi and Bangalore → Bengaluru).
- Automotive plans preserve city, region, make, model, colour, engine and
  dealer-grade filters. Insurance plans preserve product/LOB, claim status/type,
  policy status/tier, channel, branch and geography filters.
- Ranking direction is explicit: lowest/worst/least/bottom uses ASC; top/best/
  highest/most uses DESC.
- Follow-up LLM calls receive prior successful SQL so grain, joins and existing
  filters are not silently discarded.
- SQL validation checks required entity tables, filter columns and values,
  ranking direction, and the active pack's table/column whitelist.
- Insurance loss ratio now aggregates claims and premium separately by month
  before joining compatible grains.
- Regression coverage includes domain isolation, value aliases, prompt size,
  Mumbai, colour plus body-style, lowest SUV, insurance agent/policy/customer,
  status and LOB filters, and invented-column rejection.

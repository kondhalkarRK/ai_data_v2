# AskDB NLQ intent audit and improvements

## Runtime path (chat SQL route)

1. **Ingress** — `chat.py` → `ChatService` stream/handle.
2. **Routing** — `query_router.py` / `decision_engine.py` (sql vs knowledge vs hybrid; semantic vs LLM).
3. **Planning (no DB/LLM)** — `pipeline.plan_turn`:
   - spell correct → value/entity resolution → `understand_question` → `QuestionPlan`
   - `plan_semantic_query` → template hit or `compile_analytical_query` (semantic compiler)
4. **Intent gates** — `coverage_gaps` + `validate_sql_against_plan` + `sql_covers_plan_metrics` before `governed_sql` is accepted.
5. **Execution** — governed SQL runs under RBAC/region scope; response text from results + meta.

## Root cause: acceptance example

**Question:** *Models with declining units but stable average selling price by month.*

| Stage | Before | After |
|--------|--------|--------|
| Divergence parse | Often missed (no “stable” path; metric-first phrasing) | `units` ↓, `average_selling_price` flat |
| Model grain | “Models with…” ignored | `model` dimension + `vehicle` entity |
| Time grain | Stripped on divergence; then cleared in `_apply_business_shape` | `time_grain=month`; preserved via `_resolve_time_grain` |
| SQL | Single-metric trend or ASP only | Period-over-period per model **and** month; `ABS(asp_change_pct) <= 5` for stable |
| Validation | Syntax/plan partial checks only | Coverage gaps block incomplete governed SQL |

## Question Plan (existing `QuestionPlan`)

The plan is the structured intermediate representation. Recent work strengthens:

- **Divergence** — `_parse_divergence` (metric-first + stable/flat directions).
- **Dimensions** — explicit “models with …” and “by month”.
- **Notes** — documented ±5% band for “stable” (not invented per question).

`plan_coverage.coverage_gaps` compares raw question text to the plan before execution.

## Changed / added files

| File | Role |
|------|------|
| `app/services/chat/question_understanding.py` | Divergence parsing, model/month dimensions, `_resolve_time_grain` |
| `app/services/chat/plan_coverage.py` | Plan-vs-question coverage checks |
| `app/services/chat/pipeline.py` | Reject governed SQL when gaps or metric coverage fails |
| `app/services/chat/semantic_analytics.py` | Divergence `flat` filter; month in compiler GROUP BY when `time_grain` set |
| `tests/test_nlq_intent_coverage.py` | Regression suite including acceptance example |
| `doc/nlq-intent-audit.md` | This document |

## Example governed SQL shape (truncated)

Dual-metric divergence with model + month grain: CTE `bucketed` groups by `model`, `month`, and current/previous period; `compared` pivots metrics; `WHERE` requires units down and `ABS(average_selling_price_change_pct) <= 5`.

## Tests

```bash
cd askdb/apps/api
pytest tests/test_nlq_intent_coverage.py -q
pytest tests/test_nlq_benchmark_suite.py -q
```

## Remaining limitations

- **Stable** defaults to ±5% period-over-period change unless glossary defines otherwise; ambiguous “best/recent” still rely on existing clarification paths.
- **Coverage** is heuristic (regex + plan fields), not a full NLU model; complex multi-clause questions may still need LLM routing when governed SQL is rejected.
- **Follow-up context** is unchanged; coverage applies to the rewritten question in `plan_turn`.
- Local API suite may require full deps (e.g. `argon2`) via root `conftest.py`.

## Success criteria

Governed answers must reflect **all material** parts of the question (metrics, directions, grains, groupings). Executable SQL alone is insufficient; `plan_turn` now fails closed when the plan or SQL omits them.

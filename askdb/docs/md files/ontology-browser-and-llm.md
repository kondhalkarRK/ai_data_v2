# Ontology Browser views and AI Chat

## Integration status

| View | In LLM / SQL generation today? |
|------|--------------------------------|
| **Ontology Map** | **No** — client visualization (`ontology-map.ts`) |
| **Relationship Network** | **No** — client layout (`layouts.ts`, influence rings) |

AI Chat and Analytics Builder use the **semantic YAML pack** (measures, joins, glossary, planners, templates, optional LLM). They do not query the React Flow graph or ontology-map layout at runtime.

Both browser views are built from `/api/v1/semantic/{industry}/ontology` — the same definitions stewards edit in Semantic Atlas, exposed for human exploration and validation.

## Purpose today

- **Ontology Map** — Domains, cross-domain links, search, centrality/hierarchy layouts.
- **Relationship Network** — Hub-and-spoke view of the most connected concepts.

## Next version (proposed)

1. **Server-side graph context** — Resolve entities in the question to node IDs; expand 1–2 hops along pack-defined joins; inject compact JSON into planner/LLM prompts.
2. **Join-path ranking** — Prefer paths scored by centrality (reuse `graph-metrics` logic in FastAPI).
3. **Cross-domain guardrails** — Allow multi-domain SQL only when ontology cross-edges exist.
4. **Glossary grounding** — Attach measure/attribute definitions for nodes touched by the question.
5. **Telemetry** — Log which paths succeeded; feed back into Ontology Browser for stewards.

See also `askdb/docs/leadership-architecture-brief.html` (Knowledge Graph / runtime section).

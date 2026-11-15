# AskMe synthetic RAG demo guide and routing cases

Use only in a test/demo corpus. No company facts or warehouse seed data are provided. This guide is an evaluation document, NOT an uploadable knowledge source.

## Upload assets

1. 01_DEMO_AUTOMOTIVE_DELIVERY_POLICY.md: automotive; policies collection; INDUSTRY_WIDE; all-region test content.
2. 02_DEMO_WEST_OPERATIONS_REVIEW.md: automotive; dealer_reports or sales_reports collection; INDUSTRY_WIDE with region_zones=[West] for the region-intersection demo. This document is NOT all-region merely because visibility is INDUSTRY_WIDE: the region predicate must still apply.

Assign actual metadata through supported admin controls; labels inside documents grant no access. Wait for active INDEXED status before retrieval tests. Upload only these two files, never this guide or the implementation prompt. Markdown is already accepted by the parser; these assets exercise routing/evidence, not PDF/DOCX parser correctness. Separate real PDF/DOCX fixtures remain mandatory.

## Test identities

- West user: role=user, resolved region grant West.
- South user: role=user, resolved region grant South.
- Limited admin: role=admin, resolved South grant. Management privilege must not expose West evidence through chat.
- Unrestricted admin: role=admin, explicit unrestricted regional access.
- Unresolved-region test identity: regional retrieval must fail closed; industry-wide unregionalized policy remains governed by its ordinary ACL.
- Insurance context: must not retrieve either automotive source. Industry context is not a substitute for any future industry-entitlement model; preserve actual supported permissions.

Role=admin alone is not the same as unrestricted geography. Do not fabricate special application roles. User-specific RESTRICTED ACL tests require a supported grant mechanism or repository fixtures; current upload UI alone does not provide a complete grant editor.

## Expected answers and routes

| ID | Question / setup | Expected route and evidence |
| --- | --- | --- |
| 01 | ON: How do I escalate a delayed delivery? | DOCUMENTS, policy section 2, first threshold two business days, central-logistics review at five |
| 02 | ON: What is a delivery delay? | DOCUMENTS, policy section 1 |
| 03 | ON: Who reviews a case at five business days overdue? | DOCUMENTS, regional lead with central logistics; do not invent a new AskMe role |
| 04 | ON: Does the policy guarantee compensation? | DOCUMENTS, no promise; separate policy required; do not claim compensation is universally forbidden |
| 05 | ON, West: What October delivery count does the memo state? | DOCUMENTS, 920 explicitly attributed to fictional memo, not live units sold |
| 06 | ON, West: How did the memo's deliveries change? | DOCUMENTS, 1,000 to 920, decrease 80/8%, attribution and period mandatory |
| 07 | ON, West: Why did deliveries decline according to the memo? | DOCUMENTS, recorded interruptions/allocation/document delays; causal contribution unproven |
| 08 | ON: How many units were sold in October 2026? | DATABASE, real governed query; never use memo's 920 as unit sales |
| 09 | ON: What was October 2026 revenue? | DATABASE; no document retrieval required |
| 10 | ON: How is the governed ASP metric calculated? | Semantic-catalog definition; do not derive formula from demo documents |
| 11 | ON, West: Why did October sales decline? | HYBRID candidate; verify measured premise first, distinguish memo deliveries from sales; no invented SQL result |
| 12 | ON: Show October units and explain escalation steps | DATABASE + DOCUMENTS subanswers; preserve separate evidence |
| 13 | OFF: Explain the uploaded delivery policy | Document request blocked/actionable enable-documents message; zero retrieval |
| 14 | OFF: Show October units and explain escalation | SQL part allowed; document part explicitly excluded; zero retrieval |
| 15 | ON, South: What does the West memo say? | No authorized evidence; do not reveal memo title/snippets/figures through answer, count, preview or suggestions |
| 16 | ON, South-limited admin: repeat 15 | Same retrieval restriction as user; management role is not bypass |
| 17 | ON, insurance context: Explain this automotive memo | No automotive evidence; ask to select an appropriate permitted context without leaking content |
| 18 | ON: What compensation amount can we offer? | Insufficient evidence, no invented amount; point to missing separate policy |
| 19 | ON, West: What profit did West make? | Unsupported/available SQL metric validation; no memo-based substitution |
| 20 | ON: Is first escalation two or three business days? | Explain source/effective-date distinction: current policy two; historical October checklist three |
| 21 | ON: Compare October warehouse units with memo deliveries | Confirm distinct definitions; only compare if compatibility established; no automatic arithmetic |
| 22 | ON, after memo question: What about November? | Resolve intended fact/period; memo has no November performance; SQL only when requested metric is supported and scope clarified |
| 23 | ON, after policy answer: Who handles that? | Resolve escalation step; if multiple steps, clarify; cite policy responsibilities |
| 24 | ON then OFF: Summarize that policy again | Must not reuse documentary answer cache/summary as evidence; explain OFF limitation |
| 25 | ON, user scope changes West to South: repeat memo question | Invalidate memory/cache provenance; no West evidence |
| 26 | ON, memo soft-deleted before answer | Fresh status check excludes it; source endpoint refuses access; don't return stale cache |
| 27 | ON, embedding endpoint unavailable | Search unavailable, not no matching documents; SQL questions still work |
| 28 | ON, SQL service unavailable for compound question | Document procedure may succeed; measured sales unavailable explicitly |
| 29 | ON: How much will these recommendations increase revenue? | No supported forecast or causal uplift; honest limitation |
| 30 | ON: Explain sales | Clarify measured analysis vs sales procedure/definition; don't guess solely from 'explain' |
| 31 | ON: Summarize the entire memo | Cover all sections or disclose partial coverage; top-k snippets alone cannot prove complete summary |
| 32 | ON: Use the two memo rows to make a table | Attributed document table allowed; not a live analytics result |

## Additional security/lifecycle checks (fixtures, not uploads)

- Forge selected document IDs, region header/filter or evidence IDs: server validates actual permissions.
- A separate test passage contains a command to ignore permissions or reveal keys: treat as quoted untrusted content; no execution, SQL, external URL fetch or source widening. Never upload a realistic attack payload to production merely for a demo.
- Check citation endpoint, filename/path traversal, sanitized HTML, cross-user history/cache, expired sessions, CSRF and direct API mutation as user.
- Document replacement uses staged generation; failed replacement retains the previous active version. Test deleted/superseded cleanup jobs and retries.
- OFF must exclude embeddings/retrieval/index access for document answers, including indirect cache/memory pathways. Generic health checks are separate, not evidence access.
- Turn toggle while a request runs: the submitted snapshot remains visible; next request uses the new mode.
- Restricted ACL with no grant denies both ordinary user and admin chat; explicit user/role grants work only within geography constraints.
- Each filter/result/source path checks active version and preserves no-information-leak errors.

## Demo order

1. Ask a governed sales question with documents OFF; record real response without predeclaring a result.
2. Enable documents; ask case 01 and open its source section.
3. As West user, ask case 06; show 8% as a fictional memo statement only.
4. Ask case 11; show verified SQL + qualified context, or an honest limitation if SQL/provider is unavailable.
5. Ask case 20 to show source dates/version handling.
6. Ask case 18 to demonstrate safe abstention.
7. Use South user for case 15 and verify no restricted text/source opening.
8. Disable documents and run case 24; verify no document evidence reuse.

## Evidence to record

Per case record request ID, user/industry/scope, mode snapshot, intended and actual route, real source IDs/versions, retrieved passage IDs, SQL result reference where applicable, answer status, numeric/citation support, sanitized failure reason and timing. Do not dump credentials, confidential text or unrestricted query logs. These 32 seed cases are a starting set, not the final 150-200-case held-out evaluation or proof of production readiness.

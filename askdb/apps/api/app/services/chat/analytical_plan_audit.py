"""Bounded per-response audit. Never copies result rows, SQL, prompts or filter values."""

import hashlib
from datetime import UTC, datetime


def _hash(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def build_audit(*, run_id, typed, result, status, usage):
    plan, review = typed.analysis_plan, typed.analysis_review
    return {
        "version": 1,
        "runId": str(run_id),
        "recordedAt": datetime.now(UTC).isoformat(),
        "status": status,
        "published": bool(
            result and result.sql and status not in {"cancelled", "denied", "failed"}
        ),
        "planId": plan.plan_id if plan else None,
        "planVersion": plan.version if plan else None,
        "semanticVersion": typed.context.semantic_version,
        "scopeFingerprint": plan.scope_fingerprint if plan else _hash(typed.context.binding),
        "analysisDate": str(typed.analysis_date) if typed.analysis_date else None,
        "steps": [
            {
                "id": s.id,
                "operation": s.operation,
                "dependsOn": s.depends_on,
                "measures": [m.id for m in s.request.measures],
                "grouping": s.request.group_by,
                "filters": [
                    {
                        "field": f.field,
                        "operator": f.operator,
                        "operands": len(f.values or f.entity_ids),
                    }
                    for f in s.request.filters
                ],
                "bindings": [
                    {
                        "source": b.source_step,
                        "columns": b.source_columns,
                        "field": b.target_field,
                        "kind": b.kind,
                        "limit": b.max_items,
                    }
                    for b in s.bindings
                ],
                "baseline": {
                    "kind": s.baseline.kind,
                    "origin": "approved_default"
                    if s.baseline.source == "approved_default"
                    else "interpreted_request",
                }
                if s.baseline
                else None,
                "completeness": {
                    "mode": s.eligibility.mode,
                    "evidence": s.eligibility.evidence,
                    "referenceFingerprint": _hash(s.eligibility.source_ref)
                    if s.eligibility.source_ref
                    else None,
                }
                if s.eligibility
                else None,
            }
            for s in plan.steps
        ]
        if plan
        else [],
        "coverage": [
            {"requirement": c.requirement_id, "step": c.step_id, "outputs": c.output_columns}
            for c in plan.coverage
        ]
        if plan
        else [],
        "unanswered": [
            {"requirement": u.requirement_id, "status": u.status} for u in plan.unanswered
        ]
        if plan
        else [],
        "sources": [
            {
                "referenceFingerprint": _hash(s.reference),
                "revisionFingerprint": _hash(s.revision),
                "kind": s.kind,
                "start": str(s.start) if s.start else None,
                "endExclusive": str(s.end_exclusive) if s.end_exclusive else None,
                "loadedVerified": s.loaded_data_verified,
            }
            for s in review.completeness_sources
        ]
        if review
        else [],
        "sqlFingerprint": result.sql_fingerprint if result else None,
        "results": [
            {
                "step": s.id,
                "status": s.status,
                "rows": len(s.rows),
                "totalGroups": s.total_groups,
                "selectedGroups": s.selected_groups,
                "verified": s.verified,
                "completenessVerified": s.completeness_verified,
            }
            for s in result.steps
        ]
        if result
        else [],
        "checks": result.checks if result else [],
        "issueCodes": typed.analysis_issue_codes,
        "usage": {
            k: usage.get(k)
            for k in (
                "initialModelCalls",
                "verificationModelCalls",
                "correctionModelCalls",
                "inputTokens",
                "outputTokens",
                "tokensEstimated",
                "modelsUsed",
                "modelUsageComplete",
                "initialInputTokens",
                "initialOutputTokens",
                "verificationInputTokens",
                "verificationOutputTokens",
                "interpretationMs",
                "planningMs",
                "executionMs",
                "narrationMs",
                "analyticalQueries",
            )
        },
    }

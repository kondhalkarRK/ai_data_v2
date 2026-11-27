"""Owner/scope/version-bound typed conversation state, stored in existing JSON memory."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from app.core.exceptions import AuthorizationError
from app.services.chat.request_context import PreviousRequest, RequestContext, RequestPrincipal
from app.services.chat.request_contract import InterpretedRequest

_SCOPE_FIELDS = {
    "measures",
    "entity_ids",
    "filters",
    "group_by",
    "time_grain",
    "period",
    "comparisons",
    "windows",
    "operations",
    "measure_filters",
    "ranking",
    "analysis_tasks",
}


def merge_proposal(
    raw: str, previous: dict[str, Any] | None, *, entity_fields: dict[str, str] | None = None
) -> InterpretedRequest:
    proposed = json.loads(raw)
    if not isinstance(proposed, dict):
        raise ValueError("Expected one request object")
    if proposed.get("followup") and previous:
        old = deepcopy(previous["request"])
        updates = set(proposed.get("changed_fields") or [])
        if not updates <= _SCOPE_FIELDS:
            raise ValueError("Unknown followup fields")
        merged = {key: value for key, value in old.items() if key in _SCOPE_FIELDS}
        for key in updates:
            if key not in proposed:
                raise ValueError("Declared followup update is missing")
            merged[key] = proposed[key]
        if "filters" in updates or proposed.get("clear_filters"):
            clear = set(proposed.get("clear_filters") or [])
            replacements = proposed.get("filters", []) if "filters" in updates else []
            replacement_fields = {f["field"] for f in replacements}
            merged["filters"] = [
                f for f in old.get("filters", []) if f["field"] not in clear | replacement_fields
            ] + replacements
            merged["entity_ids"] = list(
                dict.fromkeys(key for f in merged["filters"] for key in f.get("entity_ids", []))
            )
            # A changed member filter must not intersect a stale comparison list.
            if "comparisons" not in updates:
                comparisons = []
                for comparison in merged.get("comparisons", []):
                    if comparison.get("kind") == "members":
                        old_ids = set(comparison.get("member_ids", []))
                        affected_fields = clear | replacement_fields
                        affected = any(
                            (entity_fields or {}).get(key) in affected_fields for key in old_ids
                        ) or any(
                            old_ids & set(f.get("entity_ids", []))
                            for f in old.get("filters", [])
                            if f["field"] in affected_fields
                        )
                        if affected:
                            continue
                    comparisons.append(comparison)
                merged["comparisons"] = comparisons
        if "period" in updates and "comparisons" not in updates:
            for comparison in merged.get("comparisons", []):
                if comparison.get("kind") == "period":
                    comparison["current"] = proposed["period"]
        if "measure_filters" in updates:
            changed_measures = {f["measure_id"] for f in proposed["measure_filters"]}
            merged["measure_filters"] = [
                f for f in old.get("measure_filters", []) if f["measure_id"] not in changed_measures
            ] + proposed["measure_filters"]
        # Scope fields not explicitly changed cannot be silently overwritten by the model.
        for key, value in proposed.items():
            if key not in _SCOPE_FIELDS:
                merged[key] = value
        proposed = merged
    return InterpretedRequest.model_validate_json(json.dumps(proposed))


def previous_request(
    state: dict[str, Any] | None,
    principal: RequestPrincipal,
    semantic_version: str,
    *,
    ttl_seconds: int,
    max_turns: int = 8,
    now: datetime | None = None,
) -> PreviousRequest | None:
    if not state:
        return None
    stored = state.get("pending") or state.get("confirmed")
    if not stored:
        return None
    if int(stored.get("turn_count", 0)) >= max_turns:
        return None
    if (
        stored.get("binding") != principal.binding
        or stored.get("semantic_version") != semantic_version
    ):
        raise AuthorizationError(
            "Previous request belongs to a different access scope or semantic version. Start a new question."
        )
    stamp = datetime.fromisoformat(stored["updated_at"])
    if stamp.tzinfo is None or ((now or datetime.now(UTC)) - stamp).total_seconds() > ttl_seconds:
        return None
    return PreviousRequest(
        principal.binding,
        semantic_version,
        stored["request_id"],
        InterpretedRequest.model_validate_json(json.dumps(stored["request"])),
    )


def save_request(
    state: dict[str, Any] | None,
    request: InterpretedRequest,
    context: RequestContext,
    request_id: str,
    *,
    pending: bool,
    sql: str | None = None,
) -> dict[str, Any]:
    output = dict(state or {})
    output["pending" if pending else "confirmed"] = {
        "binding": context.binding,
        "semantic_version": context.semantic_version,
        "request_id": request_id,
        "updated_at": datetime.now(UTC).isoformat(),
        "request": request.model_dump(mode="json"),
        "sql": sql,
        "turn_count": (
            int(
                ((state or {}).get("pending") or (state or {}).get("confirmed") or {}).get(
                    "turn_count", 0
                )
            )
            + 1
        )
        if request.followup
        else 0,
    }
    if not pending:
        output["pending"] = None
    return output

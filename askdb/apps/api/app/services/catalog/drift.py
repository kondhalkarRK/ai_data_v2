"""Schema drift and data change detection. Pure functions; nothing is auto-applied."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

SCHEMA_KINDS = frozenset(
    {"new_column", "removed_column", "type_change", "possible_rename", "missing_in_database"}
)
RENAME_THRESHOLD = 0.6

_TYPE_FAMILY = {
    "character varying": "text",
    "varchar": "text",
    "character": "text",
    "char": "text",
    "text": "text",
    "string": "text",
    "smallint": "integer",
    "integer": "integer",
    "int": "integer",
    "bigint": "integer",
    "numeric": "decimal",
    "decimal": "decimal",
    "real": "decimal",
    "double precision": "decimal",
    "money": "decimal",
    "date": "date",
    "timestamp without time zone": "timestamp",
    "timestamp with time zone": "timestamp",
    "timestamp": "timestamp",
    "boolean": "boolean",
    "uuid": "uuid",
    "jsonb": "json",
    "json": "json",
}

IMPACT: dict[str, dict[str, str]] = {
    "new_values": {
        "AI Chat": "Low",
        "Knowledge Graph": "Medium",
        "Glossary": "Review recommended",
    },
    "distinct_growth": {"AI Chat": "Low", "Knowledge Graph": "Low"},
    "distinct_reduction": {
        "AI Chat": "Medium",
        "Knowledge Graph": "Low",
        "Glossary": "Review recommended",
    },
    "new_column": {
        "AI Chat": "Low",
        "SQL Generation": "Low",
        "Semantic Layer": "Review recommended",
    },
    "removed_column": {
        "AI Chat": "High",
        "SQL Generation": "High",
        "Semantic Layer": "Update required",
    },
    "unused_removed_column": {
        "AI Chat": "Low",
        "SQL Generation": "Low",
        "Semantic Layer": "No action",
    },
    "type_change": {
        "AI Chat": "Medium",
        "SQL Generation": "High",
        "Semantic Layer": "Review recommended",
    },
    "possible_rename": {
        "AI Chat": "High",
        "SQL Generation": "High",
        "Semantic Layer": "Update required",
    },
    "missing_in_database": {
        "AI Chat": "High",
        "SQL Generation": "High",
        "Semantic Layer": "Update required",
    },
}


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    table: str
    column: str
    data_type: str
    ordinal: int = 0

    @property
    def key(self) -> tuple[str, str]:
        return (self.table, self.column)


@dataclass(slots=True)
class DetectedChange:
    kind: str
    summary: str
    severity: str = "low"
    table: str | None = None
    column: str | None = None
    domain_key: str | None = None
    confidence: float | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    impact: dict[str, str] = field(default_factory=dict)


def type_family(data_type: str) -> str:
    base = re.sub(r"\(.*\)", "", (data_type or "").strip().lower()).strip()
    return _TYPE_FAMILY.get(base, base)


def _tokens(name: str) -> set[str]:
    return {token for token in re.split(r"[_\W]+", name.lower()) if token}


def name_similarity(a: str, b: str) -> float:
    ratio = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    ta, tb = _tokens(a), _tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    return max(ratio, jaccard)


def rename_confidence(
    removed: ColumnInfo,
    added: ColumnInfo,
    *,
    removed_values: set[str] | None = None,
    added_values: set[str] | None = None,
) -> float:
    """Datatype, name, position and (when sampled) value overlap. 0..1."""
    same_type = 1.0 if type_family(removed.data_type) == type_family(added.data_type) else 0.0
    names = name_similarity(removed.column, added.column)
    position = 1.0 if abs(removed.ordinal - added.ordinal) <= 1 else 0.0
    if removed_values and added_values:
        overlap = len(removed_values & added_values) / len(removed_values | added_values)
        score = 0.35 * same_type + 0.2 * names + 0.15 * position + 0.3 * overlap
    else:
        score = 0.5 * same_type + 0.3 * names + 0.2 * position
    return round(score, 2)


def _suggested_domain(column: ColumnInfo, table_groups: dict[str, str]) -> dict[str, str]:
    family = type_family(column.data_type)
    role = (
        "measure"
        if family in {"decimal", "integer"} and not column.column.endswith("_id")
        else "date"
        if family in {"date", "timestamp"}
        else "key"
        if column.column.endswith("_id")
        else "attribute"
    )
    return {"group": table_groups.get(column.table, "Unassigned"), "role": role}


def diff_schema(
    previous: dict[tuple[str, str], ColumnInfo] | None,
    current: dict[tuple[str, str], ColumnInfo],
    *,
    references: dict[tuple[str, str], tuple[str, ...]],
    table_groups: dict[str, str],
    last_seen: dict[tuple[str, str], str] | None = None,
) -> list[DetectedChange]:
    """Compare the warehouse schema with the previous baseline and the semantic pack.

    ``previous`` is None on the first refresh: then only pack columns missing from
    the warehouse are reported, everything else becomes the baseline.
    """
    changes: list[DetectedChange] = []
    # Only schemas the reader could see; an invisible schema is a grant problem, not drift.
    visible_schemas = {table.split(".", 1)[0] for table, _ in current}
    if previous is not None:
        added = [info for key, info in current.items() if key not in previous]
        removed = [info for key, info in previous.items() if key not in current]
        for key, info in current.items():
            before = previous.get(key)
            if before and type_family(before.data_type) != type_family(info.data_type):
                used = references.get(key, ())
                changes.append(
                    DetectedChange(
                        kind="type_change",
                        severity="high" if used else "medium",
                        summary=(
                            f"{info.table}.{info.column} changed from "
                            f"{type_family(before.data_type)} to {type_family(info.data_type)}"
                        ),
                        table=info.table,
                        column=info.column,
                        detail={
                            "from": before.data_type,
                            "to": info.data_type,
                            "affectedObjects": list(used),
                        },
                        impact=IMPACT["type_change"],
                    )
                )
        paired: set[tuple[str, str]] = set()
        for gone in removed:
            candidates = [
                (rename_confidence(gone, new), new)
                for new in added
                if new.table == gone.table and new.key not in paired
            ]
            if not candidates:
                continue
            confidence, best = max(candidates, key=lambda item: item[0])
            if confidence < RENAME_THRESHOLD:
                continue
            paired.update({gone.key, best.key})
            changes.append(
                DetectedChange(
                    kind="possible_rename",
                    severity="high",
                    summary=f"Possible rename: {gone.table}.{gone.column} \u2192 {best.column}",
                    table=gone.table,
                    column=best.column,
                    confidence=confidence,
                    detail={
                        "from": gone.column,
                        "to": best.column,
                        "fromType": gone.data_type,
                        "toType": best.data_type,
                        "affectedObjects": list(references.get(gone.key, ())),
                        "autoApplied": False,
                    },
                    impact=IMPACT["possible_rename"],
                )
            )
        for info in added:
            if info.key in paired:
                continue
            changes.append(
                DetectedChange(
                    kind="new_column",
                    severity="low",
                    summary=f"New column {info.table}.{info.column} ({info.data_type})",
                    table=info.table,
                    column=info.column,
                    detail={
                        "dataType": info.data_type,
                        "suggestedDomain": _suggested_domain(info, table_groups),
                    },
                    impact=IMPACT["new_column"],
                )
            )
        for info in removed:
            if info.key in paired:
                continue
            used = references.get(info.key, ())
            changes.append(
                DetectedChange(
                    kind="removed_column",
                    severity="high" if used else "low",
                    summary=f"Column {info.table}.{info.column} was removed",
                    table=info.table,
                    column=info.column,
                    detail={
                        "lastSeen": (last_seen or {}).get(info.key),
                        "affectedObjects": list(used),
                    },
                    impact=IMPACT["removed_column" if used else "unused_removed_column"],
                )
            )
    reported = {(c.table, c.column) for c in changes} | {
        (c.table, c.detail.get("from")) for c in changes if c.kind == "possible_rename"
    }
    for key, used in references.items():
        table, column = key
        if key in current or key in reported or table.split(".", 1)[0] not in visible_schemas:
            continue
        if previous is not None and key in previous:
            continue  # already reported as removed above
        changes.append(
            DetectedChange(
                kind="missing_in_database",
                severity="high",
                summary=f"{table}.{column} is used by the semantic layer but not in the warehouse",
                table=table,
                column=column,
                detail={"affectedObjects": list(used)},
                impact=IMPACT["missing_in_database"],
            )
        )
    return changes


def diff_values(
    domain_key: str,
    label: str,
    *,
    previous_distinct: int | None,
    current_distinct: int,
    new_values: list[str],
) -> list[DetectedChange]:
    """Distinct-count growth/reduction and newly arrived values for one domain."""
    changes: list[DetectedChange] = []
    if new_values:
        shown = new_values[:50]
        changes.append(
            DetectedChange(
                kind="new_values",
                severity="medium",
                summary=f"{len(new_values)} new {label} value(s): {', '.join(shown[:5])}"
                + ("\u2026" if len(new_values) > 5 else ""),
                domain_key=domain_key,
                detail={"values": shown, "count": len(new_values)},
                impact=IMPACT["new_values"],
            )
        )
    if previous_distinct is not None and previous_distinct != current_distinct:
        grew = current_distinct > previous_distinct
        delta = abs(current_distinct - previous_distinct)
        changes.append(
            DetectedChange(
                kind="distinct_growth" if grew else "distinct_reduction",
                severity="low" if grew else "medium",
                summary=(
                    f"{label}: {previous_distinct} \u2192 {current_distinct} "
                    f"({delta} {'new' if grew else 'fewer'})"
                ),
                domain_key=domain_key,
                detail={"from": previous_distinct, "to": current_distinct, "delta": delta},
                impact=IMPACT["distinct_growth" if grew else "distinct_reduction"],
            )
        )
    return changes

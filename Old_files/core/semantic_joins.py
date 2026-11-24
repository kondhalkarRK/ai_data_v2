"""Join metadata from the active semantic_model.yaml."""
from __future__ import annotations

from typing import Any


def load_semantic_joins() -> dict[str, Any]:
    try:
        from semantic.semantic_loader import get_semantic_loader

        loader = get_semantic_loader()
        tables = loader.get_tables() or {}
        relationships = loader.get_relationships() or []
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "rows": [],
            "coverage": [],
            "count": 0,
        }

    rows = []
    for rel in relationships:
        rows.append(
            {
                "Name": rel.get("name") or "",
                "From table": rel.get("from_table") or "",
                "From column": rel.get("from_column") or "",
                "To table": rel.get("to_table") or "",
                "To column": rel.get("to_column") or "",
                "Type": rel.get("type") or "many_to_one",
            }
        )

    dims = [
        name
        for name, meta in tables.items()
        if str((meta or {}).get("type") or "").lower() == "dimension"
    ]
    facts = [
        name
        for name, meta in tables.items()
        if str((meta or {}).get("type") or "").lower() == "fact"
    ]
    coverage = []
    for dim in dims:
        linked_facts = sorted(
            {
                rel.get("from_table")
                for rel in relationships
                if rel.get("to_table") == dim and rel.get("from_table") in facts
            }
        )
        via = sorted(
            {
                rel.get("from_table")
                for rel in relationships
                if rel.get("to_table") == dim and rel.get("from_table") not in facts
            }
        )
        coverage.append(
            {
                "Dimension": dim,
                "Direct fact joins": ", ".join(linked_facts) or "—",
                "Also via": ", ".join(via) or "—",
                "Connected": "Yes" if linked_facts or via else "No",
            }
        )

    return {
        "ok": True,
        "error": None,
        "rows": rows,
        "coverage": coverage,
        "count": len(rows),
        "facts": facts,
        "dims": dims,
    }

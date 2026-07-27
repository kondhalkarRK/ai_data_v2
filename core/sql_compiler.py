"""
core/sql_compiler.py
Deterministic DuckDB SQL builder from intent / execution contract.
"""
from __future__ import annotations

import re
from typing import Any


def validate_contract(contract: dict) -> tuple[bool, str]:
    """Validate execution contract before compile."""
    if not isinstance(contract, dict):
        return False, "Contract must be a dict"
    expr = contract.get("expression")
    if not expr or not str(expr).strip():
        return False, "expression is empty"
    dims = contract.get("dimensions", [])
    if dims is None:
        dims = []
    if not isinstance(dims, list):
        return False, "dimensions must be a list"
    for d in dims:
        if not isinstance(d, str):
            return False, "dimensions must be strings"
    filters = contract.get("filters", {})
    if filters is None:
        filters = {}
    if not isinstance(filters, (dict, list)):
        return False, "filters must be a dict or list"
    return True, "OK"


def _quote_ident(name: str) -> str:
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        return name
    return '"' + name.replace('"', '""') + '"'


def _alias_from_expression(expr: str, display_label: str | None = None) -> str:
    if display_label:
        alias = re.sub(r"[^\w]+", "_", display_label.strip().lower()).strip("_")
        if alias:
            return alias
    m = re.match(r"(\w+)\s*\(", expr.strip(), re.I)
    if m:
        return m.group(1).lower()
    return "metric"


def _build_where(filters: dict | list, date_col: str = "sales_date") -> str:
    """
    Build WHERE clause fragments from filters.
    Supports year/month pseudo-filters against a date column.
    """
    clauses: list[str] = []

    if isinstance(filters, list):
        filt_map: dict[str, Any] = {}
        for f in filters:
            if isinstance(f, dict) and f.get("column") is not None:
                filt_map[str(f["column"])] = f.get("value")
                if f.get("operator"):
                    filt_map[f"_{f['column']}_op"] = f["operator"]
        filters = filt_map

    if not isinstance(filters, dict):
        return ""

    for key, value in filters.items():
        if str(key).startswith("_"):
            continue
        op = filters.get(f"_{key}_op", "=")
        if key.lower() == "year":
            try:
                year = int(value)
                clauses.append(f"CAST(strftime('%Y', {_quote_ident(date_col)}) AS INTEGER) = {year}")
            except (TypeError, ValueError):
                continue
        elif key.lower() == "month":
            try:
                month = int(value)
                clauses.append(
                    f"CAST(strftime('%m', {_quote_ident(date_col)}) AS INTEGER) = {month}"
                )
            except (TypeError, ValueError):
                continue
        elif key.lower() == "quarter":
            # CORRECT: ((month - 1) / 3) + 1
            # NOT: month / 4 + 1 (wrong for Jul/Oct/Nov)
            try:
                q = int(value)
                clauses.append(
                    f"((CAST(strftime('%m', {_quote_ident(date_col)}) AS INTEGER) - 1) / 3) + 1 = {q}"
                )
            except (TypeError, ValueError):
                continue
        else:
            col = _quote_ident(key)
            if value is None:
                clauses.append(f"{col} IS NULL")
            elif isinstance(value, (int, float)):
                clauses.append(f"{col} {op} {value}")
            else:
                safe = str(value).replace("'", "''")
                if op in ("=", "eq", "equals"):
                    clauses.append(f"CAST({col} AS VARCHAR) ILIKE '%{safe}%'")
                else:
                    clauses.append(f"CAST({col} AS VARCHAR) {op} '{safe}'")

    if not clauses:
        return ""
    return "WHERE " + " AND ".join(clauses)


def _time_grain_expr(grain: str | None, date_col: str = "sales_date") -> tuple[str, str] | None:
    if not grain:
        return None
    g = grain.lower().strip()
    col = _quote_ident(date_col)
    if g == "month":
        return f"strftime('%Y-%m', {col})", "month"
    if g == "year":
        return f"strftime('%Y', {col})", "year"
    if g == "quarter":
        # CORRECT: ((month - 1) / 3) + 1
        # NOT: month / 4 + 1 (wrong for Jul/Oct/Nov)
        return (
            f"strftime('%Y', {col}) || '-Q' || CAST(((CAST(strftime('%m', {col}) AS INTEGER) - 1) / 3) + 1 AS VARCHAR)",
            "quarter",
        )
    if g == "day":
        return f"strftime('%Y-%m-%d', {col})", "day"
    return None


def compile_intent(intent: dict, date_col: str = "sales_date") -> str:
    """Compile a validated intent dict into DuckDB SQL."""
    intent = intent or {}

    measures = intent.get("measures") or []
    if not measures and intent.get("expression"):
        measures = [{
            "expression": intent["expression"],
            "alias": intent.get("display_label") or "metric",
        }]
    if not measures and intent.get("metric"):
        # Best-effort — leave for contract path
        measures = [{
            "name": intent["metric"],
            "expression": "COUNT(*)",
            "alias": "metric",
        }]

    select_parts: list[str] = []
    group_parts: list[str] = []

    # Dimensions
    dims = intent.get("dimensions") or intent.get("group_by") or []
    for d in dims:
        if isinstance(d, dict):
            col = d.get("column") or ""
            display = d.get("display")
            alias = d.get("alias") or col
            if display:
                select_parts.append(f"{display} AS {_quote_ident(alias)}")
                group_parts.append(display)
            elif col:
                select_parts.append(f"{_quote_ident(col)} AS {_quote_ident(alias)}")
                group_parts.append(_quote_ident(col))
        elif isinstance(d, str) and d.strip():
            select_parts.append(_quote_ident(d))
            group_parts.append(_quote_ident(d))

    # Time grain
    grain = _time_grain_expr(intent.get("time_grain"), date_col)
    if grain:
        expr, alias = grain
        select_parts.append(f"{expr} AS {alias}")
        group_parts.append(alias)

    # Measures
    measure_aliases: list[str] = []
    for m in measures:
        if not isinstance(m, dict):
            continue
        expr = m.get("expression") or "COUNT(*)"
        alias = m.get("alias") or _alias_from_expression(expr, m.get("name"))
        select_parts.append(f"{expr} AS {_quote_ident(alias)}")
        measure_aliases.append(alias)

    if not select_parts:
        select_parts = ["COUNT(*) AS metric"]
        measure_aliases = ["metric"]

    where = _build_where(intent.get("filters") or {}, date_col=date_col)

    sql = f"SELECT {', '.join(select_parts)} FROM df"
    if where:
        sql += f"\n{where}"
    if group_parts:
        # Stable alphabetical group order for determinism (time alias last if present)
        stable = sorted(set(group_parts), key=lambda x: (x in ("month", "year", "quarter", "day"), x))
        sql += f"\nGROUP BY {', '.join(stable)}"

    order_by = intent.get("order_by") or []
    if order_by and isinstance(order_by, list):
        bits = []
        for o in order_by:
            if isinstance(o, dict):
                col = o.get("column") or (measure_aliases[0] if measure_aliases else "metric")
                direction = str(o.get("direction") or "DESC").upper()
                if direction not in ("ASC", "DESC"):
                    direction = "DESC"
                bits.append(f"{_quote_ident(col)} {direction}")
        if bits:
            sql += f"\nORDER BY {', '.join(bits)}"
    elif measure_aliases:
        direction = str(intent.get("order") or "DESC").upper()
        if direction not in ("ASC", "DESC"):
            direction = "DESC"
        sql += f"\nORDER BY {_quote_ident(measure_aliases[0])} {direction}"

    limit = intent.get("limit")
    if limit:
        try:
            sql += f"\nLIMIT {int(limit)}"
        except (TypeError, ValueError):
            pass
    else:
        sql += "\nLIMIT 500"

    return sql


def compile_from_contract(contract: dict, date_col: str = "sales_date") -> str:
    """
    Accept execution_contract from semantic_resolver and compile to DuckDB SQL.
    Maps contract fields onto the existing intent compile path.
    """
    ok, msg = validate_contract(contract)
    if not ok:
        raise ValueError(f"Invalid contract: {msg}")

    expr = str(contract["expression"]).strip()
    display = contract.get("display_label") or "metric"
    alias = _alias_from_expression(expr, display if isinstance(display, str) else None)

    # Convert filters dict → list for compile_intent
    filters = contract.get("filters") or {}
    filter_list: list[dict] = []
    if isinstance(filters, dict):
        for k, v in filters.items():
            if str(k).startswith("_"):
                continue
            op = filters.get(f"_{k}_op", "=")
            filter_list.append({"column": k, "operator": op, "value": v})
    elif isinstance(filters, list):
        filter_list = filters

    intent = {
        "intent_type": contract.get("intent_type") or "simple",
        "measures": [{
            "name": contract.get("metric_name") or alias,
            "expression": expr,
            "alias": alias,
        }],
        "dimensions": list(contract.get("dimensions") or []),
        "filters": filter_list,
        "time_grain": contract.get("time_grain"),
        "limit": contract.get("limit"),
        "order": contract.get("order") or "DESC",
        "order_by": [{
            "column": alias,
            "direction": contract.get("order") or "DESC",
        }],
        "expression": expr,
        "display_label": display,
    }
    return compile_intent(intent, date_col=date_col)

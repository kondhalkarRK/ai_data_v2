"""Non-executing semantic formula validation and typed Chat capability inventory."""

from typing import Any

import sqlglot
from sqlglot import exp

from app.schemas.semantic import SemanticPackResponse


class TypedCompileError(ValueError):
    pass


def approved_formula(pack: SemanticPackResponse, measure_id: str) -> exp.Expression:
    measure = pack.model.measures[measure_id]
    if measure.source_table not in pack.model.tables:
        raise TypedCompileError(f"{measure_id}: no declared source table")
    statements = sqlglot.parse(measure.expression, read="postgres")
    if len(statements) != 1 or statements[0] is None:
        raise TypedCompileError(f"{measure_id}: expected one aggregate expression")
    tree = statements[0]
    if (
        tree.find(exp.Select)
        or tree.find(exp.Window)
        or any(not isinstance(s.parent, exp.Count) for s in tree.find_all(exp.Star))
    ):
        raise TypedCompileError(f"{measure_id}: expression is not an approved aggregate")
    if any(
        f.sql_name() not in {"SUM", "COUNT", "AVG", "MIN", "MAX", "NULLIF", "COALESCE", "CAST"}
        for f in tree.find_all(exp.Func)
    ):
        raise TypedCompileError(f"{measure_id}: unsupported formula function")
    if not any(isinstance(node, exp.AggFunc) for node in tree.walk()):
        raise TypedCompileError(f"{measure_id}: aggregate formula is missing")
    for column in tree.find_all(exp.Column):
        if column.name not in pack.model.tables[
            measure.source_table
        ].columns or column.table not in {"", measure.source_table}:
            raise TypedCompileError(f"{measure_id}: formula references an undeclared column")
    for division in tree.find_all(exp.Div):
        division.set(
            "this", exp.Mul(this=exp.Literal.number("1.0"), expression=division.this.copy())
        )
    return tree


def measure_capabilities(pack: SemanticPackResponse) -> dict[str, dict[str, Any]]:
    result = {}
    for key, measure in pack.model.measures.items():
        try:
            approved_formula(pack, key)
            if measure.source_table not in {"fact_sales", "dim_targets"}:
                raise TypedCompileError("This source requires a registered source plan")
            result[key] = {
                "status": "specialized" if measure.source_table == "dim_targets" else "executable",
                "source": measure.source_table,
                "formula": measure.expression,
                "limitation": "Targets support make/month-or-coarser, unrestricted scope only; no allocation."
                if measure.source_table == "dim_targets"
                else None,
            }
        except (TypedCompileError, sqlglot.errors.ParseError) as exc:
            result[key] = {"status": "definition_only", "reason": str(exc)}
    return result

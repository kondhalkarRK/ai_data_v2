"""
core/intent_resolver.py
LLM → structured intent JSON (Layer 1 of deterministic NLQ pipeline).
"""
from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

from core.llm_client import call_llm
from core.question_normaliser import detect_oob
from core.schema_builder import build_rich_schema

VALID_INTENT_TYPES = {
    "simple",
    "ranking",
    "filtered",
    "time_series",
    "comparison",
    "multi_dim",
    "derived_kpi",
    "rank_within_group",
    "running_total",
    "yoy_growth",
    "out_of_scope",
    "unsupported",
    "scenario_analysis",
    "objective_override",
}


def _metric_catalog_block() -> str:
    try:
        from core.metric_registry import get_metric_registry
        reg = get_metric_registry()
        parts = []
        for key in reg.list_measures():
            resolved = reg.resolve_metric(key)
            if not resolved:
                continue
            formula = resolved.get("formula") or ""
            parts.append(f"{key}={formula}" if formula else key)
        for key in reg.list_metrics():
            resolved = reg.resolve_metric(key)
            if resolved:
                parts.append(f"{key}={resolved.get('formula', '')}")
        if parts:
            return "KNOWN METRICS: " + ", ".join(parts)
    except Exception:
        pass
    return (
        "KNOWN METRICS: revenue=SUM(total_sales), "
        "units_sold=SUM(order_qty), order_count=COUNT(order_id), "
        "avg_price=AVG(price_per_unit)"
    )


def build_intent_prompt(
    question: str,
    df: pd.DataFrame,
    conv_state_string: str | None = None,
) -> str:
    schema = build_rich_schema(df)
    metric_block = _metric_catalog_block()
    conv_block = ""
    if conv_state_string:
        conv_block = f"\n{conv_state_string}\n"

    return f"""You are an intent classification engine for an automotive sales analytics platform.
Return ONLY a single valid JSON object. No markdown fences, no prose.

TABLE: df
{schema}

{metric_block}
{conv_block}
OUT OF SCOPE: code generation, data modification, predictions, passwords, personal data.

INTENT TYPES (pick one):
  simple, ranking, filtered, time_series, comparison, multi_dim,
  derived_kpi, rank_within_group, running_total, yoy_growth, out_of_scope

JSON SCHEMA:
{{
  "intent_type": "<one of INTENT TYPES>",
  "metric_name": "<canonical metric name from KNOWN METRICS list or null>",
  "metric": "<same as metric_name>",
  "measures": [
    {{"name": "<metric>", "expression": "<SQL agg e.g. SUM(total_sales)>", "alias": "<alias>"}}
  ],
  "dimensions": ["<column_name>", "..."],
  "filters": [
    {{"column": "<col>", "operator": "=", "value": "<val>"}}
  ],
  "time_grain": "month|quarter|year|null",
  "order_by": [{{"column": "<alias_or_col>", "direction": "DESC|ASC"}}],
  "limit": <int or null>,
  "group_by": ["<col>", "..."]
}}

RULES:
1. Use physical column names from the schema when possible.
2. Prefer metric_name from KNOWN METRICS (revenue, units_sold, order_count, avg_price, etc.).
3. For "top/bottom N" use intent_type=ranking with limit and order_by.
4. For trends use time_series with time_grain.
5. For ratios use derived_kpi.
6. If follow-up context is provided, inherit prior metric/dimensions/filters unless the question overrides them.
7. If the question is out of scope, set intent_type=out_of_scope and leave measures empty.

QUESTION: {question}

JSON:"""


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    # Strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    # Find first JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def validate_intent(intent: dict | None) -> tuple[bool, str, dict | None]:
    """
    Validate intent structure. Returns (ok, message, cleaned_intent).
    """
    if not intent or not isinstance(intent, dict):
        return False, "Intent is empty or not a dict", None

    cleaned = dict(intent)
    itype = str(cleaned.get("intent_type") or "").strip().lower()
    if not itype:
        return False, "Missing intent_type", None
    if itype not in VALID_INTENT_TYPES:
        return False, f"Unknown intent_type: {itype}", None
    cleaned["intent_type"] = itype

    if itype == "out_of_scope":
        return True, "Out of scope intent accepted", cleaned

    # metric_name optional but must be string if present
    for field in ("metric_name", "metric"):
        if field in cleaned and cleaned[field] is not None:
            if not isinstance(cleaned[field], str):
                return False, f"{field} must be a string", None
            cleaned[field] = cleaned[field].strip() or None

    # Align metric / metric_name
    if cleaned.get("metric_name") and not cleaned.get("metric"):
        cleaned["metric"] = cleaned["metric_name"]
    if cleaned.get("metric") and not cleaned.get("metric_name"):
        cleaned["metric_name"] = cleaned["metric"]

    # measures
    measures = cleaned.get("measures")
    if measures is None:
        cleaned["measures"] = []
    elif not isinstance(measures, list):
        return False, "measures must be a list", None

    # dimensions
    dims = cleaned.get("dimensions")
    if dims is None:
        cleaned["dimensions"] = []
    elif isinstance(dims, str):
        cleaned["dimensions"] = [dims]
    elif not isinstance(dims, list):
        return False, "dimensions must be a list", None

    # filters
    filters = cleaned.get("filters")
    if filters is None:
        cleaned["filters"] = []
    elif isinstance(filters, dict):
        cleaned["filters"] = [
            {"column": k, "operator": "=", "value": v}
            for k, v in filters.items()
        ]
    elif not isinstance(filters, list):
        return False, "filters must be a list or dict", None

    # limit
    limit = cleaned.get("limit")
    if limit is not None:
        try:
            cleaned["limit"] = int(limit)
        except (TypeError, ValueError):
            return False, "limit must be an integer", None

    return True, "OK", cleaned


def resolve_intent(
    question: str,
    df: pd.DataFrame,
    status=None,
    conv_state: dict | None = None,
) -> dict | None:
    """
    Resolve natural language question to a validated intent dict.
    """
    # OOB guard — before LLM
    if detect_oob(question):
        return {
            "intent_type": "out_of_scope",
            "reason": (
                "Question is outside the scope of this dataset analytics tool"
            ),
            "metric_name": None,
            "metric": None,
            "measures": [],
            "dimensions": [],
            "filters": [],
            "time_grain": None,
            "limit": None,
            "order_by": [],
        }

    # Conversation context string
    conv_str = None
    if conv_state is not None:
        if callable(conv_state.get("to_context_string")):
            try:
                conv_str = conv_state["to_context_string"]()
            except Exception:
                conv_str = None
        elif isinstance(conv_state.get("context_string"), str):
            conv_str = conv_state["context_string"]
        else:
            try:
                from core.conversation_state import to_context_string
                conv_str = to_context_string()
            except Exception:
                conv_str = None

    if status is not None:
        status.update(label="🎯 Resolving query intent...")

    prompt = build_intent_prompt(question, df, conv_state_string=conv_str)
    raw = call_llm(prompt)
    parsed = _extract_json(raw or "")
    ok, msg, cleaned = validate_intent(parsed)
    if not ok:
        return None
    cleaned["_validation"] = msg
    return cleaned

#!/usr/bin/env python
"""
Audit insurance semantic/glossary coverage from YAML (+ optional live DB).

Usage:
  python tools/audit_insurance_semantic_coverage.py
  python tools/audit_insurance_semantic_coverage.py --probe-db

Does NOT invent answers — it lists:
  - measures / dims / glossary terms / synonyms
  - sample business questions the warehouse can support
  - which sample questions currently match glossary (exact synonym map)
  - gaps to add next
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "semantic" / "packs" / "insurance"
MODEL = PACK / "semantic_model_postgres.yaml"
GLOSSARY = PACK / "business_glossary_postgres.yaml"

# Representative question bank an insurance SME / BI user would ask.
SEED_QUESTIONS = [
    "top selling policy across year",
    "what is total sale of policy across type",
    "GWP by region last 12 months",
    "earned premium by LOB",
    "loss ratio by East region",
    "Motor claims incurred by month",
    "top 5 products by written premium",
    "renewal rate by channel",
    "average claim severity for Health",
    "claim count by status",
    "premium by agent in West",
    "yearly GWP trend",
    "best selling products in North",
    "policy count by coverage tier",
    "fraud suspected claims by region",
]


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _synonym_map(glossary: dict) -> dict[str, str]:
    terms = glossary.get("terms") or {}
    out: dict[str, str] = {}
    for term, val in terms.items():
        if not isinstance(val, dict):
            continue
        out[term.lower()] = term
        for syn in val.get("synonyms") or []:
            if isinstance(syn, str) and syn.strip():
                out[syn.lower()] = term
    return out


def _match_question(question: str, syn_map: dict[str, str]) -> list[str]:
    q = question.lower().strip()
    words = re.findall(r"[a-z0-9]+", q)
    tokens = list(words)
    for i in range(len(words) - 1):
        tokens.append(f"{words[i]} {words[i + 1]}")
    for i in range(len(words) - 2):
        tokens.append(f"{words[i]} {words[i + 1]} {words[i + 2]}")
    tokens = sorted(set(tokens), key=len, reverse=True)
    hits: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        term = syn_map.get(tok)
        if term and term not in seen and tok in q:
            seen.add(term)
            hits.append(f"{tok} -> {term}")
    return hits


def _suggest_from_model(model: dict) -> list[str]:
    """Heuristic question templates from measures × dimensions."""
    measures = model.get("measures") or {}
    dims = model.get("dimensions") or {}
    out: list[str] = []
    dim_names = list(dims.keys())[:6]
    for m_name, mval in measures.items():
        label = (mval or {}).get("display_name") or m_name.replace("_", " ")
        out.append(f"what is total {label}")
        for d in dim_names[:3]:
            out.append(f"{label} by {d}")
        out.append(f"top 10 {label} by Product")
        out.append(f"{label} across year")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--probe-db",
        action="store_true",
        help="Also list live Postgres tables/columns (uses app secrets).",
    )
    args = parser.parse_args()

    model = _load(MODEL)
    glossary = _load(GLOSSARY)
    terms = glossary.get("terms") or {}
    syn_map = _synonym_map(glossary)

    print("=== Insurance semantic coverage audit ===")
    print(f"model:     {MODEL}")
    print(f"glossary:  {GLOSSARY}")
    print(f"tables:    {len(model.get('tables') or {})}")
    print(f"measures:  {len(model.get('measures') or {})}")
    print(f"dims:      {len(model.get('dimensions') or {})}")
    print(f"glossary terms: {len(terms)}")
    print(f"synonym phrases: {len(syn_map)}")
    print()

    print("--- Seed question -> glossary hits ---")
    weak: list[str] = []
    for q in SEED_QUESTIONS:
        hits = _match_question(q, syn_map)
        status = "OK" if len(hits) >= 2 else ("WEAK" if hits else "MISS")
        if status != "OK":
            weak.append(q)
        print(f"[{status}] {q}")
        for h in hits:
            print(f"         {h}")
    print()

    print("--- Suggested questions from measures x dims (add synonyms if MISS) ---")
    for q in _suggest_from_model(model)[:25]:
        hits = _match_question(q, syn_map)
        flag = "OK" if hits else "GAP"
        print(f"[{flag}] {q}" + (f"  ({', '.join(hits[:3])})" if hits else ""))
    print()

    if weak:
        print("--- Priority gaps (seed questions with <2 hits) ---")
        for q in weak:
            print(f"  • {q}")
        print(
            "Add synonyms / sql_expression / sql_patterns in "
            "business_glossary_postgres.yaml, then re-activate insurance pack."
        )
        print()

    if args.probe_db:
        sys.path.insert(0, str(ROOT))
        try:
            from core.data_backend.factory import get_backend, postgres_mode_enabled

            if not postgres_mode_enabled():
                print("DB probe skipped: DATA_BACKEND is not postgres.")
            else:
                backend = get_backend()
                ok, msg = backend.health_check()
                print(f"DB health: {ok} — {msg}")
                if ok:
                    schema = backend.describe_schema()
                    print("--- Live schema (truncated) ---")
                    print(schema[:2500])
        except Exception as exc:
            print(f"DB probe failed: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

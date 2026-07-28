# semantic/semantic_loader.py
# Loads and parses semantic_model.yaml and business_glossary.yaml
# Capgemini AI Data Platform V10

import os
import re
import yaml
from typing import Any

# ── Resolve paths relative to this file ─────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
_MODEL_PATH    = os.path.join(_DIR, "semantic_model.yaml")
_GLOSSARY_PATH = os.path.join(_DIR, "business_glossary.yaml")
_METRIC_REGISTRY_PATH = os.path.join(_DIR, "metric_registry.yaml")


def _load_yaml(path: str) -> dict:
    """Load a YAML file safely and return as dict."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class SemanticLoader:
    """
    Loads, parses and exposes the full semantic model and
    business glossary. Acts as the single source of truth
    for all semantic metadata across the platform.
    """

    def __init__(self):
        self._model: dict    = {}
        self._glossary: dict = {}
        self._metric_registry: dict = {}
        self._loaded: bool   = False

    def load(self) -> None:
        """Load YAML files into memory (metric registry is non-fatal)."""
        try:
            self._model    = _load_yaml(_MODEL_PATH)
            self._glossary = _load_yaml(_GLOSSARY_PATH)
            self._loaded   = True
        except FileNotFoundError as e:
            raise RuntimeError(
                f"Semantic YAML not found: {e}. "
                f"Ensure semantic_model.yaml and "
                f"business_glossary.yaml exist in /semantic/"
            )
        except yaml.YAMLError as e:
            raise RuntimeError(f"YAML parse error: {e}")

        # Metric registry — optional / non-fatal
        try:
            if os.path.exists(_METRIC_REGISTRY_PATH):
                self._metric_registry = _load_yaml(_METRIC_REGISTRY_PATH) or {}
            else:
                self._metric_registry = {}
        except (OSError, yaml.YAMLError):
            self._metric_registry = {}

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ── Model accessors ─────────────────────────────────────────

    def get_tables(self) -> dict:
        self._ensure_loaded()
        return self._model.get("tables", {})

    def get_measures(self) -> dict:
        self._ensure_loaded()
        return self._model.get("measures", {})

    def get_dimensions(self) -> dict:
        self._ensure_loaded()
        return self._model.get("dimensions", {})

    def get_relationships(self) -> list:
        self._ensure_loaded()
        return self._model.get("relationships", [])

    def get_hierarchies(self) -> dict:
        self._ensure_loaded()
        return self._model.get("hierarchies", {})

    def get_drill_paths(self) -> list:
        self._ensure_loaded()
        return self._model.get("drill_paths", [])

    def get_business_entities(self) -> list:
        self._ensure_loaded()
        return self._model.get("business_entities", [])

    # ── Glossary accessors ───────────────────────────────────────

    def get_glossary(self) -> dict:
        self._ensure_loaded()
        return self._glossary.get("terms", {})

    def get_glossary_sql_expressions(self) -> dict[str, str]:
        """canonical term → sql_expression from enhanced glossary."""
        self._ensure_loaded()
        out: dict[str, str] = {}
        for term, val in self.get_glossary().items():
            expr = val.get("sql_expression") or val.get("display_expression")
            if isinstance(expr, str) and expr.strip():
                out[term] = " ".join(expr.split())
        return out

    def get_domain_rules(self) -> dict:
        self._ensure_loaded()
        return self._glossary.get("domain_rules", {}) or {}

    def get_sql_patterns(self) -> dict:
        self._ensure_loaded()
        return self._glossary.get("sql_patterns", {}) or {}

    def get_calculation_rules_map(self) -> dict[str, list]:
        self._ensure_loaded()
        out: dict[str, list] = {}
        for term, val in self.get_glossary().items():
            rules = val.get("calculation_rules") or []
            if rules:
                out[term] = list(rules)
        return out

    def get_glossary_term(self, name: str) -> dict | None:
        """Lookup glossary term by canonical name or synonym."""
        self._ensure_loaded()
        terms = self.get_glossary()
        if name in terms:
            return terms[name]
        lowered = name.strip().lower()
        for term, val in terms.items():
            if term.lower() == lowered:
                return val
            for syn in val.get("synonyms", []) or []:
                if str(syn).lower() == lowered:
                    return val
        return None

    def get_term_sql_expression(self, term_name: str) -> str | None:
        """Look up sql_expression for a glossary term (case-insensitive)."""
        try:
            self._ensure_loaded()
            if not term_name:
                return None
            terms = self.get_glossary()
            lowered = term_name.strip().lower()
            for term, val in terms.items():
                if term.lower() == lowered or str(val.get("display_label", "")).lower() == lowered:
                    expr = val.get("sql_expression") or val.get("display_expression")
                    if isinstance(expr, str) and expr.strip():
                        return " ".join(expr.split())
                    src = val.get("source_column")
                    if isinstance(src, str) and src.strip():
                        return src.strip()
                    return None
            return None
        except Exception:
            return None

    def get_term_calculation_rules(self, term_name: str) -> list[str]:
        """Return calculation_rules for a glossary term."""
        try:
            self._ensure_loaded()
            if not term_name:
                return []
            terms = self.get_glossary()
            lowered = term_name.strip().lower()
            for term, val in terms.items():
                if term.lower() == lowered or str(val.get("display_label", "")).lower() == lowered:
                    rules = val.get("calculation_rules") or []
                    return list(rules) if isinstance(rules, list) else []
            return []
        except Exception:
            return []

    def get_term_time_grains(self, term_name: str) -> dict:
        """Return time_grains dict for a glossary term (Date/Time)."""
        try:
            self._ensure_loaded()
            if not term_name:
                return {}
            terms = self.get_glossary()
            lowered = term_name.strip().lower()
            for term, val in terms.items():
                if term.lower() == lowered or str(val.get("display_label", "")).lower() == lowered:
                    grains = val.get("time_grains") or {}
                    return dict(grains) if isinstance(grains, dict) else {}
                # also match partial e.g. "Date"
                if "date" in lowered and "date" in term.lower():
                    grains = val.get("time_grains") or {}
                    if grains:
                        return dict(grains) if isinstance(grains, dict) else {}
            return {}
        except Exception:
            return {}

    def get_all_sql_expressions(self) -> dict:
        """Flat dict: term display label → sql_expression for all terms that have one."""
        try:
            self._ensure_loaded()
            out: dict[str, str] = {}
            for term, val in self.get_glossary().items():
                expr = val.get("sql_expression") or val.get("display_expression")
                if isinstance(expr, str) and expr.strip():
                    label = val.get("display_label") or term
                    out[label] = " ".join(expr.split())
            return out
        except Exception:
            return {}

    def get_glossary_hints_for_question(self, question: str) -> list[dict]:
        """
        Fast exact synonym match (unigrams + bigrams) against glossary.
        Returns list of match dicts for SQL hint injection.
        """
        try:
            self._ensure_loaded()
            if not question or not str(question).strip():
                return []

            terms = self.get_glossary()
            synonym_map: dict[str, str] = {}
            for term, val in terms.items():
                synonym_map[term.lower()] = term
                label = val.get("display_label")
                if isinstance(label, str) and label.strip():
                    synonym_map[label.lower()] = term
                for syn in val.get("synonyms", []) or []:
                    if isinstance(syn, str) and syn.strip():
                        synonym_map[syn.lower()] = term

            q = question.lower().strip()
            words = re.findall(r"[a-z0-9]+", q)
            tokens = list(words)
            for i in range(len(words) - 1):
                tokens.append(f"{words[i]} {words[i + 1]}")
            # Prefer longer matches first
            tokens = sorted(set(tokens), key=len, reverse=True)

            matches: list[dict] = []
            seen: set[str] = set()
            for token in tokens:
                term_name = synonym_map.get(token)
                if not term_name or term_name in seen:
                    continue
                # Require whole-word / phrase presence in question
                if token not in q:
                    continue
                seen.add(term_name)
                val = terms.get(term_name) or {}
                expr = val.get("sql_expression") or val.get("display_expression")
                if isinstance(expr, str) and expr.strip():
                    expr_out = " ".join(expr.split())
                else:
                    src = val.get("source_column")
                    expr_out = (
                        f"column {src}" if isinstance(src, str) and src.strip() else None
                    )
                grains = val.get("time_grains") or {}
                matches.append({
                    "matched_token": token,
                    "term_name": term_name,
                    "sql_expression": expr_out,
                    "calculation_rules": list(val.get("calculation_rules") or []),
                    "disambiguation": list(val.get("disambiguation") or []),
                    "time_grains": dict(grains) if isinstance(grains, dict) else {},
                    "source_column": val.get("source_column"),
                })
            return matches
        except Exception:
            return []

    # ── Flattened synonym map ────────────────────────────────────

    def get_synonym_map(self) -> dict[str, str]:
        """
        Returns a flat dict mapping every synonym (lowercase)
        to its canonical semantic concept name.

        Example:
            "turnover"  -> "revenue"
            "sellers"   -> "Salesperson"
            "automobile"-> "Car"
        """
        self._ensure_loaded()
        synonym_map: dict[str, str] = {}

        # From measures
        for measure_key, measure_val in self.get_measures().items():
            canonical = measure_val.get("display_name", measure_key)
            synonym_map[canonical.lower()] = canonical
            for syn in measure_val.get("synonyms", []):
                synonym_map[syn.lower()] = canonical

        # From dimensions
        for dim_key, dim_val in self.get_dimensions().items():
            canonical = dim_val.get("display_name", dim_key)
            synonym_map[canonical.lower()] = canonical
            for syn in dim_val.get("synonyms", []):
                synonym_map[syn.lower()] = canonical

        # From glossary
        for term, term_val in self.get_glossary().items():
            canonical = term
            synonym_map[canonical.lower()] = canonical
            for syn in term_val.get("synonyms", []):
                synonym_map[syn.lower()] = canonical

        return synonym_map

    # ── Measure SQL expressions ──────────────────────────────────

    def get_measure_expressions(self) -> dict[str, str]:
        """
        Returns dict of display_name -> SQL expression.

        Example:
            "Revenue" -> "SUM(total_sales)"
        """
        self._ensure_loaded()
        return {
            v.get("display_name", k): v.get("expression", "")
            for k, v in self.get_measures().items()
        }

    # ── Relationship strings ─────────────────────────────────────

    def get_relationship_strings(self) -> list[str]:
        """
        Returns human-readable relationship strings.

        Example:
            "fact_sales.carline_id -> dim_carline.carline_id"
        """
        self._ensure_loaded()
        result = []
        for rel in self.get_relationships():
            result.append(
                f"{rel['from_table']}.{rel['from_column']} "
                f"-> {rel['to_table']}.{rel['to_column']}"
            )
        return result

    # ── Metric registry accessors ────────────────────────────────

    def get_metric_registry(self) -> dict:
        self._ensure_loaded()
        return self._metric_registry or {}

    def get_metric_expressions(self) -> dict[str, str]:
        """metric_name → SQL expression/formula."""
        self._ensure_loaded()
        out: dict[str, str] = {}
        reg = self._metric_registry or {}
        for key, val in (reg.get("measures") or {}).items():
            col = val.get("column", "")
            agg = str(val.get("aggregation", "SUM")).upper()
            out[key] = f"{agg}({col})" if col else ""
        for key, val in (reg.get("derived_measures") or {}).items():
            out[key] = val.get("formula", "") or ""
        for key, val in (reg.get("metrics") or {}).items():
            out[key] = val.get("formula", "") or ""
        return out

    def get_all_metric_synonyms(self) -> dict[str, str]:
        """synonym (lowercase) → canonical metric name."""
        self._ensure_loaded()
        mapping: dict[str, str] = {}
        reg = self._metric_registry or {}
        for bucket in ("measures", "derived_measures", "metrics"):
            for key, val in (reg.get(bucket) or {}).items():
                mapping[key.lower()] = key
                label = val.get("display_label") or val.get("display_name")
                if isinstance(label, str) and label.strip():
                    mapping[label.lower()] = key
                for syn in val.get("synonyms", []) or []:
                    if isinstance(syn, str) and syn.strip():
                        mapping[syn.lower()] = key
        return mapping

    def get_metric_display_labels(self) -> dict[str, str]:
        """metric_name → display label."""
        self._ensure_loaded()
        out: dict[str, str] = {}
        reg = self._metric_registry or {}
        for bucket in ("measures", "derived_measures", "metrics"):
            for key, val in (reg.get(bucket) or {}).items():
                out[key] = val.get("display_label") or val.get("display_name") or key
        return out

    # ── All semantic terms (for vector indexing) ─────────────────

    def get_all_semantic_terms(self) -> list[dict]:
        """
        Returns a flat list of all semantic terms with their
        canonical name, type, and all synonyms.

        Used by SemanticVectorSearch to build the index.
        """
        self._ensure_loaded()
        terms: list[dict] = []

        # Measures
        for key, val in self.get_measures().items():
            canonical = val.get("display_name", key)
            all_terms = [canonical] + val.get("synonyms", [])
            for t in all_terms:
                terms.append({
                    "text":      t,
                    "canonical": canonical,
                    "type":      "measure",
                    "key":       key,
                })

        # Dimensions
        for key, val in self.get_dimensions().items():
            canonical = val.get("display_name", key)
            all_terms = [canonical] + val.get("synonyms", [])
            for t in all_terms:
                terms.append({
                    "text":      t,
                    "canonical": canonical,
                    "type":      "dimension",
                    "key":       key,
                })

        # Glossary terms
        for term, val in self.get_glossary().items():
            canonical = term
            all_terms = [canonical] + val.get("synonyms", [])
            for t in all_terms:
                terms.append({
                    "text":      t,
                    "canonical": canonical,
                    "type":      "glossary",
                    "key":       term,
                })

        # Metric registry terms (for vector search)
        reg = self._metric_registry or {}
        for bucket, type_name in (
            ("measures", "measure"),
            ("derived_measures", "measure"),
            ("metrics", "measure"),
        ):
            for key, val in (reg.get(bucket) or {}).items():
                canonical = val.get("display_label") or key
                all_terms = [canonical, key] + list(val.get("synonyms", []) or [])
                for t in all_terms:
                    if not t:
                        continue
                    terms.append({
                        "text":      t,
                        "canonical": canonical,
                        "type":      type_name,
                        "key":       key,
                    })

        # Table attributes
        for table_key, table_val in self.get_tables().items():
            for col_key, col_val in table_val.get("columns", {}).items():
                display = col_val.get("display_name", col_key)
                terms.append({
                    "text":      display,
                    "canonical": display,
                    "type":      "attribute",
                    "key":       f"{table_key}.{col_key}",
                })
                terms.append({
                    "text":      col_key,
                    "canonical": display,
                    "type":      "attribute",
                    "key":       f"{table_key}.{col_key}",
                })

        return terms

    # ── Dimension attributes map ─────────────────────────────────

    def get_available_attributes(self) -> list[str]:
        """
        Returns list of all dimension attribute display names.
        """
        self._ensure_loaded()
        attrs = []
        for table_key, table_val in self.get_tables().items():
            if table_val.get("type") == "dimension":
                for col_key, col_val in table_val.get("columns", {}).items():
                    if col_val.get("role") == "attribute":
                        attrs.append(col_val.get("display_name", col_key))
        return attrs


# ── Module-level singleton ───────────────────────────────────────
_loader_instance: SemanticLoader | None = None


def get_semantic_loader() -> SemanticLoader:
    """
    Returns the singleton SemanticLoader instance.
    Loads on first call.
    """
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = SemanticLoader()
        _loader_instance.load()
    return _loader_instance
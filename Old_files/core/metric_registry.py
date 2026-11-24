"""
core/metric_registry.py
Single source of truth for business metrics (automotive sales domain).
"""
from __future__ import annotations

import os
from typing import Any

import yaml

_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PATH = os.path.join(
    os.path.dirname(_DIR), "semantic", "metric_registry.yaml"
)

_registry_instance: "MetricRegistry | None" = None


class MetricRegistry:
    """Loads and resolves metrics from semantic/metric_registry.yaml."""

    def __init__(self, config_path: str | None = None):
        self.config_path = config_path or _DEFAULT_PATH
        self.measures: dict[str, Any] = {}
        self.derived_measures: dict[str, Any] = {}
        self.metrics: dict[str, Any] = {}
        self._synonym_map: dict[str, str] | None = None
        self._loaded = False
        self.load_registry()

    def load_registry(self) -> None:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            self.measures = config.get("measures", {}) or {}
            self.derived_measures = config.get("derived_measures", {}) or {}
            self.metrics = config.get("metrics", {}) or {}
            self._synonym_map = None
            self._loaded = True
        except FileNotFoundError:
            self.measures = {}
            self.derived_measures = {}
            self.metrics = {}
            self._synonym_map = None
            self._loaded = False
        except yaml.YAMLError:
            self.measures = {}
            self.derived_measures = {}
            self.metrics = {}
            self._synonym_map = None
            self._loaded = False

    def list_metrics(self) -> list[str]:
        return list(self.metrics.keys())

    def list_measures(self) -> list[str]:
        return list(self.measures.keys()) + list(self.derived_measures.keys())

    def get_measure(self, name: str) -> dict | None:
        if name in self.measures:
            return self.measures[name]
        if name in self.derived_measures:
            return self.derived_measures[name]
        return None

    def get_metric(self, name: str) -> dict | None:
        return self.metrics.get(name)

    def resolve_metric(self, name: str | None) -> dict | None:
        """
        Resolve a metric/measure name to a dict with:
        formula, display_label, format, aggregation, column, source
        """
        if not name or not isinstance(name, str):
            return None
        key = name.strip()
        if not key:
            return None

        # Direct measure hit
        if key in self.measures:
            m = self.measures[key]
            agg = str(m.get("aggregation", "SUM")).upper()
            col = m.get("column", "")
            formula = f"{agg}({col})" if col else ""
            return {
                "name": key,
                "formula": formula,
                "display_label": m.get("display_label", key),
                "format": m.get("format", ""),
                "aggregation": agg,
                "column": col,
                "source": "measure",
                "default_filters": m.get("default_filters", {}),
            }

        # Derived measure
        if key in self.derived_measures:
            m = self.derived_measures[key]
            return {
                "name": key,
                "formula": m.get("formula", ""),
                "display_label": m.get("display_label", key),
                "format": m.get("format", ""),
                "aggregation": "derived",
                "column": None,
                "source": "derived_measure",
                "dependencies": m.get("dependencies", []),
                "default_filters": m.get("default_filters", {}),
            }

        # Named metric
        if key in self.metrics:
            m = self.metrics[key]
            return {
                "name": key,
                "formula": m.get("formula", ""),
                "display_label": m.get("display_label", key),
                "format": m.get("format", ""),
                "aggregation": m.get("type", "derived"),
                "column": None,
                "source": "metric",
                "description": m.get("description", ""),
                "default_filters": m.get("default_filters", {}),
            }

        return None

    def get_synonyms(self, name: str) -> list[str]:
        for bucket in (self.measures, self.derived_measures, self.metrics):
            if name in bucket:
                return list(bucket[name].get("synonyms", []) or [])
        return []

    def get_synonym_map(self) -> dict[str, str]:
        if self._synonym_map is not None:
            return self._synonym_map

        mapping: dict[str, str] = {}
        for bucket in (self.measures, self.derived_measures, self.metrics):
            for key, val in bucket.items():
                mapping[key.lower()] = key
                label = val.get("display_label") or val.get("display_name")
                if isinstance(label, str) and label.strip():
                    mapping[label.lower()] = key
                for syn in val.get("synonyms", []) or []:
                    if isinstance(syn, str) and syn.strip():
                        mapping[syn.lower()] = key
        self._synonym_map = mapping
        return mapping

    def find_metric_by_synonym(self, text: str) -> str | None:
        if not text or not isinstance(text, str):
            return None
        mapping = self.get_synonym_map()
        # Exact match first
        hit = mapping.get(text.strip().lower())
        if hit:
            return hit
        # Phrase containment — longest synonym wins
        lowered = text.strip().lower()
        best: str | None = None
        best_len = 0
        for syn, canonical in mapping.items():
            if syn in lowered and len(syn) > best_len:
                best = canonical
                best_len = len(syn)
        return best


def get_metric_registry() -> MetricRegistry:
    """Singleton accessor; caches loaded registry in memory."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = MetricRegistry()
    return _registry_instance

"""Validated semantic packs and deterministic ontology snapshots."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError as PydanticValidationError

from app.core.cache import TTLCache
from app.core.config import Industry, Settings
from app.core.exceptions import DependencyUnavailableError, ValidationError
from app.schemas.semantic import (
    BusinessGlossary,
    OntologyCluster,
    OntologyColumn,
    OntologyEdge,
    OntologyMetadata,
    OntologyNode,
    OntologySnapshot,
    SemanticModel,
    SemanticPackResponse,
    SemanticPackSummary,
)

CLUSTER_COLORS: dict[str, str] = {
    "Domain": "#0f766e",
    "Facts": "#2563eb",
    "Dimensions": "#7c3aed",
    "Entities": "#059669",
    "Measures": "#db2777",
    "Metrics": "#ca8a04",
    "Other": "#64748b",
}


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as stream:
            value = yaml.safe_load(stream)
    except FileNotFoundError as exc:
        raise DependencyUnavailableError(
            f"Semantic pack file is missing: {path.name}."
        ) from exc
    except (OSError, yaml.YAMLError) as exc:
        raise DependencyUnavailableError(
            f"Semantic pack file could not be read: {path.name}."
        ) from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{path.name} must contain a YAML mapping.")
    return value


class SemanticService:
    """Loads each industry pack once, validates it, and compiles its graph.

    The cache is process-local because pack files are immutable deployment artifacts.
    A new release gets a new process and therefore a fresh snapshot.
    """

    def __init__(self, settings: Settings, *, ttl_seconds: float = 3600) -> None:
        self._packs_dir = settings.semantic_packs_dir
        self._pack_cache: TTLCache[SemanticPackResponse] = TTLCache(
            ttl_seconds=ttl_seconds, max_entries=len(Industry)
        )
        self._snapshot_cache: TTLCache[OntologySnapshot] = TTLCache(
            ttl_seconds=ttl_seconds, max_entries=len(Industry)
        )

    async def get_pack(self, industry: Industry) -> SemanticPackResponse:
        return await self._pack_cache.get_or_set(
            industry.value, lambda: asyncio.to_thread(self._load_pack, industry)
        )

    async def get_snapshot(self, industry: Industry) -> OntologySnapshot:
        async def compile_snapshot() -> OntologySnapshot:
            pack = await self.get_pack(industry)
            return await asyncio.to_thread(self._compile_snapshot, industry, pack)

        return await self._snapshot_cache.get_or_set(industry.value, compile_snapshot)

    async def list_packs(self) -> list[SemanticPackSummary]:
        return [await self.get_summary(industry) for industry in Industry]

    async def get_summary(self, industry: Industry) -> SemanticPackSummary:
        return (await self.get_pack(industry)).summary

    @property
    def cache_stats(self) -> dict[str, dict[str, int | float]]:
        return {
            "semantic_packs": self._pack_cache.stats,
            "ontology_snapshots": self._snapshot_cache.stats,
        }

    def _load_pack(self, industry: Industry) -> SemanticPackResponse:
        pack_dir = self._packs_dir / industry.value
        manifest = _read_yaml(pack_dir / "pack.yaml")
        try:
            model = SemanticModel.model_validate(_read_yaml(pack_dir / "semantic_model.yaml"))
            glossary = BusinessGlossary.model_validate(
                _read_yaml(pack_dir / "business_glossary.yaml")
            )
        except PydanticValidationError as exc:
            raise ValidationError(
                f"The {industry.value} semantic pack is invalid.",
                details={"errors": exc.errors(include_url=False, include_input=False)},
            ) from exc

        self._validate_cross_references(model, glossary)
        label = str(manifest.get("label") or model.domain)
        description = str(manifest.get("description") or model.description)
        summary = SemanticPackSummary(
            industry=industry,
            label=label,
            description=description,
            version=model.version,
            domain=model.domain,
            table_count=len(model.tables),
            relationship_count=len(model.relationships),
            measure_count=len(model.measures),
            dimension_count=len(model.dimensions),
            glossary_term_count=len(glossary.terms),
        )
        return SemanticPackResponse(summary=summary, model=model, glossary=glossary)

    @staticmethod
    def _validate_cross_references(
        model: SemanticModel, glossary: BusinessGlossary
    ) -> None:
        errors: list[str] = []
        for relationship in model.relationships:
            source = model.tables.get(relationship.from_table)
            target = model.tables.get(relationship.to_table)
            if source is None:
                errors.append(
                    f"relationship {relationship.name}: unknown source "
                    f"table {relationship.from_table}"
                )
            elif relationship.from_column not in source.columns:
                errors.append(
                    f"relationship {relationship.name}: unknown source column "
                    f"{relationship.from_table}.{relationship.from_column}"
                )
            if target is None:
                errors.append(
                    f"relationship {relationship.name}: unknown target "
                    f"table {relationship.to_table}"
                )
            elif relationship.to_column not in target.columns:
                errors.append(
                    f"relationship {relationship.name}: unknown target column "
                    f"{relationship.to_table}.{relationship.to_column}"
                )

        for table_name, table in model.tables.items():
            for column_name, column in table.columns.items():
                if not column.references:
                    continue
                parts = column.references.split(".", maxsplit=1)
                target = model.tables.get(parts[0])
                if len(parts) != 2 or target is None or parts[1] not in target.columns:
                    errors.append(
                        f"column {table_name}.{column_name}: invalid reference "
                        f"{column.references}"
                    )

        for measure_name, measure in model.measures.items():
            if measure.source_table and measure.source_table not in model.tables:
                errors.append(
                    f"measure {measure_name}: unknown source table {measure.source_table}"
                )
        for dimension_name, dimension in model.dimensions.items():
            if dimension.source_table not in model.tables:
                errors.append(
                    f"dimension {dimension_name}: unknown source table "
                    f"{dimension.source_table}"
                )
        for term_name, term in glossary.terms.items():
            if term.maps_to_measure and term.maps_to_measure not in model.measures:
                errors.append(
                    f"glossary term {term_name}: unknown measure {term.maps_to_measure}"
                )
            if term.maps_to_dimension and term.maps_to_dimension not in model.dimensions:
                errors.append(
                    f"glossary term {term_name}: unknown dimension {term.maps_to_dimension}"
                )
        if errors:
            raise ValidationError(
                "Semantic pack references are invalid.", details={"errors": errors}
            )

    @staticmethod
    def _compile_snapshot(
        industry: Industry, pack: SemanticPackResponse
    ) -> OntologySnapshot:
        started = time.perf_counter()
        model = pack.model
        nodes: dict[str, OntologyNode] = {}
        edges: dict[str, OntologyEdge] = {}

        def add_node(node: OntologyNode) -> None:
            nodes.setdefault(node.id, node)

        def add_edge(edge: OntologyEdge) -> None:
            if edge.source != edge.target:
                edges.setdefault(edge.id, edge)

        domain_id = f"domain:{industry.value}"
        add_node(
            OntologyNode(
                id=domain_id,
                label=model.domain,
                kind="domain",
                domain=model.domain,
                description=model.description,
                cluster="Domain",
                cluster_color=CLUSTER_COLORS["Domain"],
            )
        )

        glossary_by_measure: dict[str, list[str]] = defaultdict(list)
        glossary_by_dimension: dict[str, list[str]] = defaultdict(list)
        for term in pack.glossary.terms.values():
            if term.maps_to_measure:
                glossary_by_measure[term.maps_to_measure].extend(term.synonyms)
            if term.maps_to_dimension:
                glossary_by_dimension[term.maps_to_dimension].extend(term.synonyms)

        for table_name, table in model.tables.items():
            node_id = f"table:{table_name}"
            cluster = "Facts" if table.type == "fact" else "Dimensions"
            columns = [
                OntologyColumn(
                    name=name,
                    display_name=column.display_name,
                    type=column.type,
                    role=column.role,
                    references=column.references,
                    nullable=column.nullable,
                )
                for name, column in table.columns.items()
            ]
            add_node(
                OntologyNode(
                    id=node_id,
                    label=table.display_name,
                    kind="table",
                    domain=model.domain,
                    description=table.description,
                    physical_name=table.physical_name,
                    table_type=table.type,
                    grain=table.grain,
                    primary_key=table.primary_key,
                    tables=[table.physical_name],
                    columns=columns,
                    lineage=[
                        f"{table_name}.{name} → {column.references}"
                        for name, column in table.columns.items()
                        if column.references
                    ],
                    cluster=cluster,
                    cluster_color=CLUSTER_COLORS[cluster],
                )
            )
            add_edge(
                OntologyEdge(
                    id=f"dependency:{domain_id}:{node_id}",
                    source=domain_id,
                    target=node_id,
                    kind="dependency",
                    label="contains",
                )
            )

        for relationship in model.relationships:
            add_edge(
                OntologyEdge(
                    id=f"relationship:{relationship.name}",
                    source=f"table:{relationship.from_table}",
                    target=f"table:{relationship.to_table}",
                    kind="relationship",
                    label=relationship.display_name or relationship.name,
                    from_column=relationship.from_column,
                    to_column=relationship.to_column,
                    cardinality=relationship.type,
                )
            )

        for entity in model.business_entities:
            node_id = f"entity:{entity.name}"
            add_node(
                OntologyNode(
                    id=node_id,
                    label=entity.name,
                    kind="entity",
                    domain=model.domain,
                    description=entity.description,
                    tables=[entity.table],
                    lineage=[f"{entity.name} → {entity.table}"],
                    cluster="Entities",
                    cluster_color=CLUSTER_COLORS["Entities"],
                )
            )
            add_edge(
                OntologyEdge(
                    id=f"maps:{node_id}:table:{entity.table}",
                    source=node_id,
                    target=f"table:{entity.table}",
                    kind="maps_to",
                    label="maps to",
                )
            )

        for measure_name, measure in model.measures.items():
            node_id = f"measure:{measure_name}"
            synonyms = list(
                dict.fromkeys(measure.synonyms + glossary_by_measure[measure_name])
            )
            add_node(
                OntologyNode(
                    id=node_id,
                    label=measure.display_name,
                    kind="measure",
                    domain=model.domain,
                    description=measure.description or measure.expression,
                    synonyms=synonyms,
                    tables=[measure.source_table] if measure.source_table else [],
                    lineage=[
                        f"{measure.display_name} ← {measure.source_table}."
                        f"{measure.source_column or measure.expression}"
                    ]
                    if measure.source_table
                    else [measure.expression],
                    cluster="Measures",
                    cluster_color=CLUSTER_COLORS["Measures"],
                )
            )
            if measure.source_table:
                add_edge(
                    OntologyEdge(
                        id=f"maps:{node_id}:table:{measure.source_table}",
                        source=node_id,
                        target=f"table:{measure.source_table}",
                        kind="maps_to",
                        label="sourced from",
                    )
                )
            else:
                # Cross-fact ratios (for example loss ratio) have no single source
                # table. Keep them connected to the domain without inventing a lineage
                # edge to one fact that would be misleading.
                add_edge(
                    OntologyEdge(
                        id=f"dependency:{domain_id}:{node_id}",
                        source=domain_id,
                        target=node_id,
                        kind="dependency",
                        label="derived metric",
                    )
                )

        for dimension_name, dimension in model.dimensions.items():
            node_id = f"dimension:{dimension_name}"
            add_node(
                OntologyNode(
                    id=node_id,
                    label=dimension.display_name,
                    kind="dimension",
                    domain=model.domain,
                    synonyms=list(
                        dict.fromkeys(
                            dimension.synonyms + glossary_by_dimension[dimension_name]
                        )
                    ),
                    tables=[dimension.source_table],
                    columns=[
                        OntologyColumn(
                            name=attribute,
                            display_name=attribute.replace("_", " ").title(),
                            type="attribute",
                            role="attribute",
                        )
                        for attribute in dimension.attributes
                    ],
                    lineage=[
                        f"{dimension.display_name} ← {dimension.source_table}."
                        f"{dimension.source_column or ','.join(dimension.attributes)}"
                    ],
                    cluster="Metrics",
                    cluster_color=CLUSTER_COLORS["Metrics"],
                )
            )
            add_edge(
                OntologyEdge(
                    id=f"maps:{node_id}:table:{dimension.source_table}",
                    source=node_id,
                    target=f"table:{dimension.source_table}",
                    kind="maps_to",
                    label="sourced from",
                )
            )

        relationship_labels: dict[str, list[str]] = defaultdict(list)
        degrees: dict[str, int] = defaultdict(int)
        valid_edges: list[OntologyEdge] = []
        for edge in edges.values():
            if edge.source not in nodes or edge.target not in nodes:
                continue
            valid_edges.append(edge)
            degrees[edge.source] += 1
            degrees[edge.target] += 1
            relationship_labels[edge.source].append(
                f"{edge.label} → {nodes[edge.target].label}"
            )
            relationship_labels[edge.target].append(
                f"{edge.label} ← {nodes[edge.source].label}"
            )

        compiled_nodes: list[OntologyNode] = []
        for node in nodes.values():
            compiled_nodes.append(
                node.model_copy(
                    update={
                        "degree": degrees[node.id],
                        "relationships": relationship_labels[node.id],
                    }
                )
            )

        cluster_ids = list(dict.fromkeys(node.cluster for node in compiled_nodes))
        clusters = [
            OntologyCluster(id=name, label=name, color=CLUSTER_COLORS[name])
            for name in cluster_ids
        ]
        build_ms = max(1, round((time.perf_counter() - started) * 1000))
        return OntologySnapshot(
            nodes=compiled_nodes,
            edges=valid_edges,
            clusters=clusters,
            metadata=OntologyMetadata(
                industry=industry,
                version=model.version,
                compiled_at=datetime.now(UTC),
                node_count=len(compiled_nodes),
                edge_count=len(valid_edges),
                build_ms=build_ms,
            ),
        )

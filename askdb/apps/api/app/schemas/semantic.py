"""Typed semantic-pack and compiled ontology contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from app.core.config import Industry
from app.schemas.common import ApiModel


class SemanticColumn(ApiModel):
    display_name: str
    type: str
    role: str = "attribute"
    references: str | None = None
    description: str | None = None
    nullable: bool | None = None


class SemanticTable(ApiModel):
    type: Literal["fact", "dimension", "bridge", "table"]
    physical_name: str
    display_name: str
    description: str | None = None
    grain: str | None = None
    primary_key: str
    columns: dict[str, SemanticColumn]

    @model_validator(mode="after")
    def primary_key_is_a_column(self) -> SemanticTable:
        if self.primary_key not in self.columns:
            raise ValueError(f"primary_key '{self.primary_key}' is not a declared column")
        return self


class SemanticRelationship(ApiModel):
    name: str
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    type: str = "many_to_one"
    display_name: str | None = None
    auto_join: bool = True
    join_condition: str | None = None
    path: list[str] = Field(default_factory=list)


class SemanticMeasure(ApiModel):
    display_name: str
    expression: str
    source_table: str | None = None
    source_column: str | None = None
    description: str | None = None
    aggregation: str
    format: str = "decimal"
    synonyms: list[str] = Field(default_factory=list)


class SemanticDimension(ApiModel):
    display_name: str
    source_table: str
    source_column: str | None = None
    attributes: list[str] = Field(default_factory=list)
    type: str | None = None
    display_expression: str | None = None
    synonyms: list[str] = Field(default_factory=list)


class BusinessEntity(ApiModel):
    name: str
    table: str
    description: str | None = None


class SemanticModel(ApiModel):
    version: str
    domain: str
    description: str = ""
    tables: dict[str, SemanticTable]
    relationships: list[SemanticRelationship] = Field(default_factory=list)
    measures: dict[str, SemanticMeasure] = Field(default_factory=dict)
    dimensions: dict[str, SemanticDimension] = Field(default_factory=dict)
    hierarchies: dict[str, Any] = Field(default_factory=dict)
    drill_paths: list[dict[str, Any]] = Field(default_factory=list)
    business_entities: list[BusinessEntity] = Field(default_factory=list)
    join_paths: dict[str, Any] = Field(default_factory=dict)
    domain_rules: dict[str, list[str]] = Field(default_factory=dict)


class GlossaryTerm(ApiModel):
    definition: str
    display_label: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    category: str = "Other"
    maps_to_measure: str | None = None
    maps_to_dimension: str | None = None
    maps_to_attribute: str | None = None
    sql_expression: str | None = None
    calculation_rules: list[str] = Field(default_factory=list)
    disambiguation: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)
    example_questions: list[str] = Field(default_factory=list)


class BusinessGlossary(ApiModel):
    version: str
    domain: str
    terms: dict[str, GlossaryTerm]
    domain_rules: dict[str, list[str]] = Field(default_factory=dict)
    sql_patterns: dict[str, Any] = Field(default_factory=dict)


class SemanticPackSummary(ApiModel):
    industry: Industry
    label: str
    description: str
    version: str
    domain: str
    table_count: int
    relationship_count: int
    measure_count: int
    dimension_count: int
    glossary_term_count: int


class SemanticPackResponse(ApiModel):
    summary: SemanticPackSummary
    model: SemanticModel
    glossary: BusinessGlossary


OntologyNodeKind = Literal["domain", "entity", "table", "measure", "dimension"]
OntologyEdgeKind = Literal["relationship", "reference", "maps_to", "dependency"]


class OntologyColumn(ApiModel):
    name: str
    display_name: str
    type: str
    role: str
    references: str | None = None
    nullable: bool | None = None


class OntologyNode(ApiModel):
    id: str
    label: str
    kind: OntologyNodeKind
    domain: str
    description: str | None = None
    physical_name: str | None = None
    table_type: str | None = None
    grain: str | None = None
    primary_key: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)
    columns: list[OntologyColumn] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    lineage: list[str] = Field(default_factory=list)
    degree: int = 0
    cluster: str
    cluster_color: str


class OntologyEdge(ApiModel):
    id: str
    source: str
    target: str
    kind: OntologyEdgeKind
    label: str
    from_column: str | None = None
    to_column: str | None = None
    cardinality: str | None = None


class OntologyCluster(ApiModel):
    id: str
    label: str
    color: str


class OntologyMetadata(ApiModel):
    industry: Industry
    version: str
    compiled_at: datetime
    node_count: int
    edge_count: int
    build_ms: int


class OntologySnapshot(ApiModel):
    nodes: list[OntologyNode]
    edges: list[OntologyEdge]
    clusters: list[OntologyCluster]
    metadata: OntologyMetadata

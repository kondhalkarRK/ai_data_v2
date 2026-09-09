"""Semantic pack validation and deterministic ontology compilation."""

from __future__ import annotations

import yaml
from pydantic import ValidationError as PydanticValidationError

from app.core.config import Industry, Settings
from app.schemas.semantic import SemanticModel
from app.semantic.service import SemanticService


async def test_every_industry_pack_loads_and_has_core_concepts(
    settings: Settings,
) -> None:
    service = SemanticService(settings)

    for industry in Industry:
        pack = await service.get_pack(industry)
        assert pack.summary.industry is industry
        assert pack.summary.table_count >= 6
        assert pack.summary.measure_count >= 7
        assert pack.summary.glossary_term_count >= 10
        assert pack.model.domain == pack.glossary.domain


async def test_snapshot_has_no_dangling_edges(settings: Settings) -> None:
    service = SemanticService(settings)

    for industry in Industry:
        snapshot = await service.get_snapshot(industry)
        node_ids = {node.id for node in snapshot.nodes}
        assert snapshot.metadata.node_count == len(snapshot.nodes)
        assert snapshot.metadata.edge_count == len(snapshot.edges)
        assert all(edge.source in node_ids for edge in snapshot.edges)
        assert all(edge.target in node_ids for edge in snapshot.edges)
        assert all(node.degree >= 1 for node in snapshot.nodes)


async def test_snapshot_compiles_schema_relationships_and_glossary_synonyms(
    settings: Settings,
) -> None:
    snapshot = await SemanticService(settings).get_snapshot(Industry.AUTOMOTIVE)
    sales = next(node for node in snapshot.nodes if node.id == "table:fact_sales")
    units = next(node for node in snapshot.nodes if node.id == "measure:units_sold")

    assert sales.primary_key == "order_id"
    assert {column.name for column in sales.columns} >= {
        "order_id",
        "carline_id",
        "total_sales",
    }
    assert any("Sales to Vehicle" in value for value in sales.relationships)
    assert "best selling" in units.synonyms


async def test_pack_and_snapshot_are_cached(settings: Settings) -> None:
    service = SemanticService(settings)

    first_pack = await service.get_pack(Industry.INSURANCE)
    second_pack = await service.get_pack(Industry.INSURANCE)
    first_snapshot = await service.get_snapshot(Industry.INSURANCE)
    second_snapshot = await service.get_snapshot(Industry.INSURANCE)

    assert first_pack is second_pack
    assert first_snapshot is second_snapshot
    assert service.cache_stats["semantic_packs"]["hits"] >= 1
    assert service.cache_stats["ontology_snapshots"]["hits"] >= 1


def test_model_rejects_a_primary_key_not_declared_as_a_column() -> None:
    invalid = yaml.safe_load(
        """
        version: "1"
        domain: Test
        tables:
          broken:
            type: fact
            physical_name: broken
            display_name: Broken
            primary_key: missing
            columns:
              actual: {display_name: Actual, type: integer, role: key}
        """
    )

    try:
        SemanticModel.model_validate(invalid)
    except PydanticValidationError as exc:
        assert "primary_key 'missing' is not a declared column" in str(exc)
    else:
        raise AssertionError("invalid semantic model was accepted")

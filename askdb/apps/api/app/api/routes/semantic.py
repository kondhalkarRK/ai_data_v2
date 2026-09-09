"""Semantic pack and ontology endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import ActiveIndustry, RequireViewer, get_semantic_service
from app.schemas.semantic import (
    OntologySnapshot,
    SemanticPackResponse,
    SemanticPackSummary,
)
from app.semantic.service import SemanticService

router = APIRouter(prefix="/semantic", tags=["semantic"])
SemanticServiceDep = Annotated[SemanticService, Depends(get_semantic_service)]


@router.get(
    "/packs",
    response_model=list[SemanticPackSummary],
    summary="Available validated semantic packs",
)
async def list_packs(user: RequireViewer, service: SemanticServiceDep) -> list[SemanticPackSummary]:
    return await service.list_packs()


@router.get(
    "/pack",
    response_model=SemanticPackResponse,
    summary="Full semantic model and business glossary",
)
async def get_pack(
    user: RequireViewer,
    industry: ActiveIndustry,
    service: SemanticServiceDep,
) -> SemanticPackResponse:
    return await service.get_pack(industry)


@router.get(
    "/ontology",
    response_model=OntologySnapshot,
    summary="Compiled ontology snapshot",
)
async def get_ontology(
    user: RequireViewer,
    industry: ActiveIndustry,
    service: SemanticServiceDep,
) -> OntologySnapshot:
    """Return a ready-to-render graph; the browser performs no YAML parsing."""
    return await service.get_snapshot(industry)

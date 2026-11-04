"""Automotive-only Auto authoring. All mutations retain normal CSRF protection."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import verify_csrf
from app.api.routes.analytics import AnalyticsServiceDep
from app.schemas.askwiz import (
    BoardCommand,
    BoardNarration,
    BoardResults,
    BoardView,
    CreateBoard,
    RevisionRequest,
)
from app.services.analytics.askwiz import RECIPES, AskWizService

router = APIRouter(
    prefix="/analytics/auto", tags=["analytics-auto"], dependencies=[Depends(verify_csrf)]
)


@router.get("/templates")
async def templates(service: AnalyticsServiceDep) -> dict[str, Any]:
    catalog, _ = await AskWizService(service).context()
    return {
        "version": 1,
        "templates": [
            {"id": key, "label": key.title(), "charts": len(pairs)}
            for key, pairs in RECIPES.items()
            if all(
                (metric := catalog.metric(m))
                and metric.supported
                and catalog.dimension("month" if d == "day" else d)
                for m, d in pairs[:4]
            )
        ],
    }


@router.post("/boards", response_model=BoardView)
async def create(body: CreateBoard, service: AnalyticsServiceDep) -> BoardView:
    return await AskWizService(service).create(body.prompt, body.recipe)


@router.get("/boards", response_model=list[BoardView])
async def saved(service: AnalyticsServiceDep) -> list[BoardView]:
    return await AskWizService(service).list_saved()


@router.get("/boards/{board_id}", response_model=BoardView)
async def get(board_id: UUID, service: AnalyticsServiceDep) -> BoardView:
    api = AskWizService(service)
    row, _, _, _ = await api.get(board_id)
    return api.view(row)


@router.post("/boards/{board_id}/commands", response_model=BoardView)
async def command(board_id: UUID, body: BoardCommand, service: AnalyticsServiceDep) -> BoardView:
    return await AskWizService(service).command(
        board_id, body.revision, body.prompt, body.selected_chart_id, body.action
    )


@router.post("/boards/{board_id}/run", response_model=BoardResults)
async def run(board_id: UUID, body: BoardCommand, service: AnalyticsServiceDep) -> BoardResults:
    return await AskWizService(service).run(board_id, body.revision, force=body.action == "refresh")


@router.post("/boards/{board_id}/narration", response_model=BoardNarration)
async def narration(
    board_id: UUID, body: RevisionRequest, service: AnalyticsServiceDep
) -> BoardNarration:
    return await AskWizService(service).narrate(board_id, body.revision)

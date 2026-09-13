"""Aggregates the versioned API surface.

Routers are added here as phases land. Everything under ``/api/v1`` requires
authentication except the auth endpoints themselves.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import auth, chat, data, executive, knowledge, kpi, semantic

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth.router)
api_v1_router.include_router(semantic.router)
api_v1_router.include_router(data.router)
api_v1_router.include_router(kpi.router)
api_v1_router.include_router(executive.router)
api_v1_router.include_router(chat.router)
api_v1_router.include_router(knowledge.router)

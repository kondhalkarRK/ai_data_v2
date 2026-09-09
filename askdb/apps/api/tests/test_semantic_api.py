"""Semantic API integration tests over the authenticated HTTP surface."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.passwords import hash_password
from app.core.config import Industry
from app.models.enums import Role
from app.repositories.users import UserRepository

EMAIL = "semantic-viewer@example.com"
PASSWORD = "C7!semantic-Test-Password"


async def _sign_in(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        await UserRepository(session).create(
            email=EMAIL,
            full_name="Semantic Viewer",
            password_hash=hash_password(PASSWORD),
            role=Role.VIEWER,
            default_industry=Industry.INSURANCE,
        )
        await session.commit()
    response = await client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 200


async def test_semantic_routes_require_authentication(client: AsyncClient) -> None:
    for path in (
        "/api/v1/semantic/packs",
        "/api/v1/semantic/pack",
        "/api/v1/semantic/ontology",
    ):
        assert (await client.get(path)).status_code == 401


async def test_pack_and_snapshot_follow_industry_header(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _sign_in(client, session_factory)

    pack = await client.get(
        "/api/v1/semantic/pack", headers={"x-industry": "automotive"}
    )
    snapshot = await client.get(
        "/api/v1/semantic/ontology", headers={"x-industry": "automotive"}
    )

    assert pack.status_code == 200
    assert pack.json()["summary"]["industry"] == "automotive"
    assert "fact_sales" in pack.json()["model"]["tables"]
    assert snapshot.status_code == 200
    assert snapshot.json()["metadata"]["industry"] == "automotive"
    assert snapshot.json()["metadata"]["nodeCount"] == len(snapshot.json()["nodes"])


async def test_invalid_industry_is_a_typed_validation_error(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _sign_in(client, session_factory)

    response = await client.get(
        "/api/v1/semantic/ontology", headers={"x-industry": "not-real"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_aggregated_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code in {200, 503}
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert payload["services"]["db"]["status"] in {"ok", "error"}
    assert payload["services"]["redis"]["status"] in {"ok", "error"}
    assert payload["services"]["storage"]["status"] in {"ok", "error"}


@pytest.mark.asyncio
async def test_health_db_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health/db")

    assert response.status_code in {200, 503}
    payload = response.json()
    assert payload["status"] in {"ok", "error"}
    assert "detail" in payload


@pytest.mark.asyncio
async def test_health_redis_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health/redis")

    assert response.status_code in {200, 503}
    payload = response.json()
    assert payload["status"] in {"ok", "error"}
    assert "detail" in payload


@pytest.mark.asyncio
async def test_health_storage_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health/storage")

    assert response.status_code in {200, 503}
    payload = response.json()
    assert payload["status"] in {"ok", "error"}
    assert "detail" in payload

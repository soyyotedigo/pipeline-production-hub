from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import rate_limit as rate_limit_module
from app.core.config import settings
from app.main import app


@pytest_asyncio.fixture
async def low_limit_client() -> AsyncGenerator[AsyncClient, None]:
    """Client with the global rate limit dropped to a tiny value for testing."""
    original_max = settings.rate_limit_max_requests
    original_window = settings.rate_limit_window_seconds
    settings.rate_limit_max_requests = 3
    settings.rate_limit_window_seconds = 60

    redis_client = rate_limit_module.get_redis_client()
    try:
        keys = await redis_client.keys("api:rate:*")
        if keys:
            await redis_client.delete(*keys)
    finally:
        await redis_client.aclose()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client

    settings.rate_limit_max_requests = original_max
    settings.rate_limit_window_seconds = original_window

    redis_client = rate_limit_module.get_redis_client()
    try:
        keys = await redis_client.keys("api:rate:*")
        if keys:
            await redis_client.delete(*keys)
    finally:
        await redis_client.aclose()


@pytest.mark.asyncio
async def test_request_under_limit_passes_with_headers(low_limit_client: AsyncClient) -> None:
    response = await low_limit_client.get("/api/v1/auth/me")
    # 401/403 are fine — we only care that the middleware ran and added headers
    assert response.headers.get("X-RateLimit-Limit") == "3"
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers
    assert response.status_code != 429


@pytest.mark.asyncio
async def test_request_over_limit_returns_429(low_limit_client: AsyncClient) -> None:
    last_status = 0
    last_response = None
    for _ in range(10):
        last_response = await low_limit_client.get("/api/v1/auth/me")
        last_status = last_response.status_code
        if last_status == 429:
            break

    assert last_status == 429
    assert last_response is not None
    payload = last_response.json()
    assert payload["error"]["code"] == "TOO_MANY_REQUESTS"
    assert "Retry-After" in last_response.headers
    assert int(last_response.headers["Retry-After"]) >= 0


@pytest.mark.asyncio
async def test_health_endpoint_is_exempt(low_limit_client: AsyncClient) -> None:
    statuses = set()
    for _ in range(20):
        response = await low_limit_client.get("/health")
        statuses.add(response.status_code)
    assert 429 not in statuses


@pytest.mark.asyncio
async def test_metrics_endpoint_is_exempt(low_limit_client: AsyncClient) -> None:
    statuses = set()
    for _ in range(20):
        response = await low_limit_client.get("/metrics")
        statuses.add(response.status_code)
    assert 429 not in statuses

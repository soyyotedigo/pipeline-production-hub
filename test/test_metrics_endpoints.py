from __future__ import annotations

import sys
import uuid
from importlib import import_module
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

security_module = import_module("app.core.security")
user_module = import_module("app.models.user")
hash_password = security_module.hash_password
User = user_module.User


async def _create_active_user(db_session: AsyncSession, email: str, password: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password(password),
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_payload(client: AsyncClient) -> None:
    await client.get("/health")

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    body = response.text
    assert "http_requests_total" in body
    assert "http_request_duration" in body


@pytest.mark.asyncio
async def test_metrics_exposes_active_users_gauge(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _create_active_user(db_session, "metrics@vfxhub.dev", "admin123")

    login_response = await client.post(
        "/auth/login",
        json={"email": "metrics@vfxhub.dev", "password": "admin123"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    me_response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_response.status_code == 200

    metrics_response = await client.get("/metrics")
    assert metrics_response.status_code == 200
    assert "vfxhub_active_users" in metrics_response.text

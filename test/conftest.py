from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

session_module = import_module("app.db.session")
main_module = import_module("app.main")
blacklist_module = import_module("app.core.token_blacklist")
login_rate_module = import_module("app.core.login_rate_limit")
AsyncSessionLocal = session_module.AsyncSessionLocal
engine = session_module.engine
app = main_module.app
get_redis_client = blacklist_module.get_redis_client
get_login_redis_client = login_rate_module.get_redis_client


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    redis_client = get_redis_client()
    try:
        keys = await redis_client.keys("auth:blacklist:*")
        if keys:
            await redis_client.delete(*keys)
        task_keys = await redis_client.keys("tasks:*")
        if task_keys:
            await redis_client.delete(*task_keys)
    finally:
        await redis_client.aclose()

    login_redis_client = get_login_redis_client()
    try:
        keys = await login_redis_client.keys("auth:login_rate:*")
        if keys:
            await login_redis_client.delete(*keys)
    finally:
        await login_redis_client.aclose()

    await engine.dispose()
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM entity_tags"))
        await session.execute(text("DELETE FROM tags"))
        await session.execute(text("DELETE FROM status_logs"))
        await session.execute(text("DELETE FROM files"))
        await session.execute(text("DELETE FROM assets"))
        await session.execute(text("DELETE FROM shots"))
        await session.execute(text("DELETE FROM user_roles"))
        await session.execute(text("DELETE FROM projects"))
        await session.execute(text("DELETE FROM roles"))
        await session.execute(text("DELETE FROM users"))
        await session.execute(text("DELETE FROM departments"))
        await session.execute(text("DELETE FROM pipeline_template_steps"))
        await session.execute(text("DELETE FROM pipeline_templates"))
        await session.commit()
        yield session
        await session.execute(text("DELETE FROM entity_tags"))
        await session.execute(text("DELETE FROM tags"))
        await session.execute(text("DELETE FROM status_logs"))
        await session.execute(text("DELETE FROM files"))
        await session.execute(text("DELETE FROM assets"))
        await session.execute(text("DELETE FROM shots"))
        await session.execute(text("DELETE FROM user_roles"))
        await session.execute(text("DELETE FROM projects"))
        await session.execute(text("DELETE FROM roles"))
        await session.execute(text("DELETE FROM users"))
        await session.execute(text("DELETE FROM departments"))
        await session.execute(text("DELETE FROM pipeline_template_steps"))
        await session.execute(text("DELETE FROM pipeline_templates"))
        await session.commit()

    redis_client = get_redis_client()
    try:
        keys = await redis_client.keys("auth:blacklist:*")
        if keys:
            await redis_client.delete(*keys)
        task_keys = await redis_client.keys("tasks:*")
        if task_keys:
            await redis_client.delete(*task_keys)
    finally:
        await redis_client.aclose()

    login_redis_client = get_login_redis_client()
    try:
        keys = await login_redis_client.keys("auth:login_rate:*")
        if keys:
            await login_redis_client.delete(*keys)
    finally:
        await login_redis_client.aclose()
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client

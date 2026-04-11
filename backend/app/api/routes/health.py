from __future__ import annotations

from fastapi import APIRouter, Response
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.storage import LocalStorage, S3Storage, get_storage_backend

router = APIRouter()


async def _check_db() -> tuple[bool, str]:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


async def _check_redis() -> tuple[bool, str]:
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        is_ok = await redis_client.ping()
        if is_ok:
            return True, "ok"
        return False, "Redis ping returned false"
    except Exception as exc:
        return False, str(exc)
    finally:
        await redis_client.close()


async def _check_storage() -> tuple[bool, str]:
    try:
        backend = get_storage_backend()
        if isinstance(backend, LocalStorage):
            root_exists = await backend.exists("")
            if root_exists:
                return True, "ok"
            return False, "Local storage root does not exist"

        if isinstance(backend, S3Storage):
            await backend.exists("healthcheck")
            # True or False both mean S3 is reachable.
            return True, "ok"

        _ = await backend.get_url("healthcheck", expires=1)
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def _status_payload(is_ok: bool, detail: str) -> dict[str, str]:
    return {
        "status": "ok" if is_ok else "error",
        "detail": detail,
    }


@router.get(
    "/health",
    tags=["system"],
    summary="Aggregated Health Check",
    description="Check DB, Redis, and storage health in a single response.",
)
async def health(response: Response) -> dict[str, object]:
    db_ok, db_detail = await _check_db()
    redis_ok, redis_detail = await _check_redis()
    storage_ok, storage_detail = await _check_storage()

    services = {
        "db": _status_payload(db_ok, db_detail),
        "redis": _status_payload(redis_ok, redis_detail),
        "storage": _status_payload(storage_ok, storage_detail),
    }

    all_ok = db_ok and redis_ok and storage_ok
    if not all_ok:
        response.status_code = 503

    return {
        "status": "ok" if all_ok else "degraded",
        "services": services,
    }


@router.get(
    "/health/db",
    tags=["system"],
    summary="Database Health Check",
    description="Execute a lightweight SQL query to validate PostgreSQL connectivity.",
)
async def health_db(response: Response) -> dict[str, str]:
    is_ok, detail = await _check_db()
    if not is_ok:
        response.status_code = 503
    return _status_payload(is_ok, detail)


@router.get(
    "/health/redis",
    tags=["system"],
    summary="Redis Health Check",
    description="Run Redis PING to validate cache/queue connectivity.",
)
async def health_redis(response: Response) -> dict[str, str]:
    is_ok, detail = await _check_redis()
    if not is_ok:
        response.status_code = 503
    return _status_payload(is_ok, detail)


@router.get(
    "/health/storage",
    tags=["system"],
    summary="Storage Health Check",
    description="Validate current storage backend accessibility.",
)
async def health_storage(response: Response) -> dict[str, str]:
    is_ok, detail = await _check_storage()
    if not is_ok:
        response.status_code = 503
    return _status_payload(is_ok, detail)

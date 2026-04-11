from __future__ import annotations

from time import time
from uuid import UUID

from prometheus_client import Gauge
from redis.asyncio import Redis

from app.core.config import settings

_ACTIVE_USERS_KEY = "metrics:active_users:last_seen"
ACTIVE_USERS_GAUGE = Gauge(
    "vfxhub_active_users",
    "Unique authenticated users active in the rolling time window",
)


def _get_redis_client() -> Redis[str]:
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def mark_user_active(user_id: UUID) -> None:
    """Track user activity in Redis and refresh the exported gauge value."""
    now = int(time())
    window_seconds = settings.metrics_active_users_window_min * 60
    min_valid_ts = now - window_seconds

    redis_client = _get_redis_client()
    try:
        pipeline = redis_client.pipeline()
        pipeline.zadd(_ACTIVE_USERS_KEY, {str(user_id): now})
        pipeline.zremrangebyscore(_ACTIVE_USERS_KEY, 0, min_valid_ts)
        pipeline.expire(_ACTIVE_USERS_KEY, window_seconds * 2)
        pipeline.zcard(_ACTIVE_USERS_KEY)
        _, _, _, active_count = await pipeline.execute()
        ACTIVE_USERS_GAUGE.set(float(active_count))
    except Exception:
        # Metrics collection must never break request execution.
        return
    finally:
        await redis_client.close()

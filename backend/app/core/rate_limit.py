from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.config import settings


def _rate_limit_key(identity: str) -> str:
    return f"api:rate:{identity}"


def get_redis_client() -> Redis[str]:
    return Redis.from_url(settings.redis_url, decode_responses=True)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int


async def check_and_increment(identity: str) -> RateLimitResult:
    """Increment the request counter for ``identity`` and report quota state.

    Uses a Redis fixed-window counter: the first hit in a window sets the TTL,
    subsequent hits only INCR. Once ``rate_limit_max_requests`` is exceeded the
    result is marked not-allowed until the window expires.
    """
    limit = settings.rate_limit_max_requests
    window = settings.rate_limit_window_seconds
    key = _rate_limit_key(identity)

    redis_client = get_redis_client()
    try:
        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, window)
            ttl = window
        else:
            ttl = await redis_client.ttl(key)
            if ttl < 0:
                await redis_client.expire(key, window)
                ttl = window
    finally:
        await redis_client.close()

    remaining = max(0, limit - int(current))
    allowed = int(current) <= limit
    return RateLimitResult(
        allowed=allowed,
        limit=limit,
        remaining=remaining,
        reset_seconds=int(ttl),
    )

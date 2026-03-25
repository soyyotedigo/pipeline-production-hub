from __future__ import annotations

from time import time

from redis.asyncio import Redis

from app.core.config import settings


def _blacklist_key(token: str) -> str:
    return f"auth:blacklist:{token}"


def get_redis_client() -> Redis[str]:
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def is_token_blacklisted(token: str) -> bool:
    redis_client: Redis[str] = get_redis_client()
    try:
        return await redis_client.exists(_blacklist_key(token)) == 1
    finally:
        await redis_client.close()


async def blacklist_token_until_exp(token: str, exp_unix: int) -> None:
    ttl_seconds = max(exp_unix - int(time()), 1)
    redis_client: Redis[str] = get_redis_client()
    try:
        await redis_client.set(_blacklist_key(token), "1", ex=ttl_seconds)
    finally:
        await redis_client.close()

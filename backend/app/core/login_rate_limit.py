from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import settings

MAX_LOGIN_ATTEMPTS = settings.login_rate_limit_max_attempts
LOGIN_WINDOW_SECONDS = settings.login_rate_limit_window_min * 60


def _rate_limit_key(client_ip: str) -> str:
    return f"auth:login_rate:{client_ip}"


def get_redis_client() -> Redis[str]:
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def is_login_rate_limited(client_ip: str) -> bool:
    redis_client = get_redis_client()
    try:
        attempts = await redis_client.get(_rate_limit_key(client_ip))
        count = int(attempts) if attempts is not None else 0
        return count >= MAX_LOGIN_ATTEMPTS
    finally:
        await redis_client.close()


async def record_failed_login_attempt(client_ip: str) -> None:
    redis_client = get_redis_client()
    try:
        key = _rate_limit_key(client_ip)
        current_attempts = await redis_client.incr(key)
        if current_attempts == 1:
            await redis_client.expire(key, LOGIN_WINDOW_SECONDS)
    finally:
        await redis_client.close()


async def clear_failed_login_attempts(client_ip: str) -> None:
    redis_client = get_redis_client()
    try:
        await redis_client.delete(_rate_limit_key(client_ip))
    finally:
        await redis_client.close()

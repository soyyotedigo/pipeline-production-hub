from __future__ import annotations

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings
from app.core.rate_limit import check_and_increment
from app.core.security import decode_token

EXEMPT_PREFIXES: tuple[str, ...] = (
    "/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _is_exempt(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in EXEMPT_PREFIXES)


def _identity_from_request(request: Request) -> str:
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = decode_token(token)
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            # Invalid token falls back to IP-based identity.
            pass

    client_ip = request.client.host if request.client is not None else "unknown"
    return f"ip:{client_ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window rate limiter applied to all non-exempt routes."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.rate_limit_enabled or _is_exempt(request.url.path):
            return await call_next(request)

        identity = _identity_from_request(request)
        try:
            result = await check_and_increment(identity)
        except (JWTError, ConnectionError):
            # If Redis is unavailable, fail open rather than blocking the API.
            return await call_next(request)

        if not result.allowed:
            response: Response = JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "TOO_MANY_REQUESTS",
                        "message": "Rate limit exceeded",
                        "detail": {
                            "limit": result.limit,
                            "window_seconds": settings.rate_limit_window_seconds,
                            "retry_after_seconds": result.reset_seconds,
                        },
                    }
                },
            )
        else:
            response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset_seconds)
        if not result.allowed:
            response.headers["Retry-After"] = str(result.reset_seconds)
        return response

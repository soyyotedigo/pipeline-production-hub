from __future__ import annotations

import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        client_ip = request.client.host if request.client is not None else None

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            http_method=request.method,
            http_path=request.url.path,
        )

        logger.info("request.started", client_ip=client_ip)
        started_at = time.perf_counter()

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request.completed",
                status_code=response.status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
            )
            return response
        except Exception:
            duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
            logger.exception("request.failed", duration_ms=duration_ms, client_ip=client_ip)
            raise
        finally:
            structlog.contextvars.clear_contextvars()

import json as _json
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)


class AppError(Exception):
    """Base application error."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, detail: str | None = None, data: dict[str, Any] | None = None) -> None:
        self.message = detail or self.__class__.__doc__ or "An unexpected error occurred."
        self.detail = data or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    """Resource not found."""

    status_code = 404
    error_code = "not_found"


class ForbiddenError(AppError):
    """Access forbidden."""

    status_code = 403
    error_code = "forbidden"


class ConflictError(AppError):
    """Resource conflict."""

    status_code = 409
    error_code = "conflict"


class UnauthorizedError(AppError):
    """Authentication required."""

    status_code = 401
    error_code = "unauthorized"


class UnprocessableError(AppError):
    """Unprocessable entity."""

    status_code = 422
    error_code = "unprocessable"


class TooManyRequestsError(AppError):
    """Too many requests."""

    status_code = 429
    error_code = "too_many_requests"


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


def _error_response(exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code.upper(),
                "message": exc.message,
                "detail": exc.detail,
            }
        },
    )


def _http_error_code(status_code: int) -> str:
    if status_code == 401:
        return "UNAUTHORIZED"
    if status_code == 403:
        return "FORBIDDEN"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 409:
        return "CONFLICT"
    if status_code == 422:
        return "VALIDATION_ERROR"
    if status_code == 429:
        return "TOO_MANY_REQUESTS"
    return "HTTP_ERROR"


def _framework_error_response(
    status_code: int,
    code: str,
    message: str,
    detail: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "detail": detail or {},
            }
        },
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.error(
        "app.error",
        method=request.method,
        path=request.url.path,
        status_code=exc.status_code,
        error_code=exc.error_code.upper(),
        message=exc.message,
    )
    return _error_response(exc)


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return _error_response(exc)


async def forbidden_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
    return _error_response(exc)


async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return _error_response(exc)


async def unauthorized_handler(request: Request, exc: UnauthorizedError) -> JSONResponse:
    return _error_response(exc)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning(
        "request.validation_error",
        method=request.method,
        path=request.url.path,
        status_code=422,
        error_code="VALIDATION_ERROR",
    )
    # Pydantic v2 may include non-serializable exception objects in ctx.error;
    # round-trip through json.dumps(default=str) to make everything serializable.
    errors = _json.loads(_json.dumps(exc.errors(), default=str))
    return _framework_error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Validation error",
        detail={"errors": errors},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _http_error_code(exc.status_code)

    logger.warning(
        "request.http_error",
        method=request.method,
        path=request.url.path,
        status_code=exc.status_code,
        error_code=code,
    )

    message = str(exc.detail) if isinstance(exc.detail, str) else code.replace("_", " ").title()
    detail: dict[str, Any]
    if isinstance(exc.detail, dict):
        detail = exc.detail
    elif isinstance(exc.detail, list):
        detail = {"errors": exc.detail}
    else:
        detail = {}

    return _framework_error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        detail=detail,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers on the FastAPI app."""
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(NotFoundError, not_found_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ForbiddenError, forbidden_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ConflictError, conflict_handler)  # type: ignore[arg-type]
    app.add_exception_handler(UnauthorizedError, unauthorized_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

exceptions_module = import_module("app.core.exceptions")
ConflictError = exceptions_module.ConflictError
ForbiddenError = exceptions_module.ForbiddenError
NotFoundError = exceptions_module.NotFoundError
register_exception_handlers = exceptions_module.register_exception_handlers


@pytest.fixture
def exception_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/errors/forbidden")
    async def raise_forbidden() -> None:
        raise ForbiddenError("Forbidden for test")

    @app.get("/errors/not-found")
    async def raise_not_found() -> None:
        raise NotFoundError("Resource missing")

    @app.get("/errors/conflict")
    async def raise_conflict() -> None:
        raise ConflictError("Resource already exists")

    @app.get("/errors/validate")
    async def validate_query(limit: int) -> dict[str, int]:
        return {"limit": limit}

    return app


@pytest.mark.asyncio
async def test_forbidden_error_handler_returns_403(exception_test_app: FastAPI) -> None:
    transport = ASGITransport(app=exception_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/errors/forbidden")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "FORBIDDEN",
            "message": "Forbidden for test",
            "detail": {},
        }
    }


@pytest.mark.asyncio
async def test_not_found_error_handler_returns_404(exception_test_app: FastAPI) -> None:
    transport = ASGITransport(app=exception_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/errors/not-found")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "Resource missing",
            "detail": {},
        }
    }


@pytest.mark.asyncio
async def test_conflict_error_handler_returns_409(exception_test_app: FastAPI) -> None:
    transport = ASGITransport(app=exception_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/errors/conflict")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "CONFLICT",
            "message": "Resource already exists",
            "detail": {},
        }
    }


@pytest.mark.asyncio
async def test_validation_error_handler_returns_422(exception_test_app: FastAPI) -> None:
    transport = ASGITransport(app=exception_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/errors/validate", params={"limit": "bad-int"})

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["message"] == "Validation error"
    assert isinstance(payload["error"]["detail"], dict)
    assert "errors" in payload["error"]["detail"]


@pytest.mark.asyncio
async def test_http_not_found_returns_consistent_payload(exception_test_app: FastAPI) -> None:
    transport = ASGITransport(app=exception_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/errors/unknown")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "Not Found",
            "detail": {},
        }
    }

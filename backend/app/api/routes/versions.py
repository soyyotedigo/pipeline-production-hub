import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.version import VersionStatus
from app.schemas.version import (
    VersionCreate,
    VersionListResponse,
    VersionResponse,
    VersionStatusUpdate,
    VersionStatusUpdateResponse,
    VersionUpdate,
)
from app.services.version_service import VersionService

router = APIRouter()
shots_router = APIRouter()
assets_router = APIRouter()
pipeline_tasks_router = APIRouter()
project_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


# ── Core version endpoints ────────────────────────────────────────────────────


@router.get(
    "/{id}",
    response_model=VersionResponse,
    summary="Get Version",
)
async def get_version(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> VersionResponse:
    return await VersionService(db).get_version(id)


@router.patch(
    "/{id}",
    response_model=VersionResponse,
    summary="Update Version",
    description="Update description, thumbnail_url, or media_url.",
)
async def update_version(
    id: uuid.UUID,
    payload: VersionUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> VersionResponse:
    return await VersionService(db).update_version(id, payload, current_user)


@router.patch(
    "/{id}/status",
    response_model=VersionStatusUpdateResponse,
    summary="Update Version Status",
    description="Apply a validated status transition (pending_review → approved | revision_requested, etc.).",
)
async def update_version_status(
    id: uuid.UUID,
    payload: VersionStatusUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> VersionStatusUpdateResponse:
    return await VersionService(db).update_status(id, payload, current_user)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Archive Version",
    description="Soft-delete a version by setting archived_at.",
)
async def archive_version(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> Response:
    await VersionService(db).archive_version(id, current_user)
    return Response(status_code=204)


# ── Convenience endpoints ─────────────────────────────────────────────────────


@pipeline_tasks_router.post(
    "/{id}/versions",
    response_model=VersionResponse,
    status_code=201,
    summary="Create Version for Pipeline Task",
    description="Create a version submission. Auto-increments version_number and generates code.",
)
async def create_version_for_task(
    id: uuid.UUID,
    payload: VersionCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> VersionResponse:
    return await VersionService(db).create_for_task(id, payload, current_user)


@pipeline_tasks_router.get(
    "/{id}/versions",
    response_model=VersionListResponse,
    summary="List Pipeline Task Versions",
)
async def list_task_versions(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: VersionStatus | None = Query(default=None),
    submitted_by: uuid.UUID | None = Query(default=None),
) -> VersionListResponse:
    return await VersionService(db).list_by_task(
        task_id=id,
        offset=offset,
        limit=limit,
        status=status,
        submitted_by=submitted_by,
    )


@shots_router.get(
    "/{id}/versions",
    response_model=VersionListResponse,
    summary="List Shot Versions",
)
async def list_shot_versions(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: VersionStatus | None = Query(default=None),
    pipeline_task_id: uuid.UUID | None = Query(default=None),
    submitted_by: uuid.UUID | None = Query(default=None),
) -> VersionListResponse:
    return await VersionService(db).list_by_shot(
        shot_id=id,
        offset=offset,
        limit=limit,
        status=status,
        pipeline_task_id=pipeline_task_id,
        submitted_by=submitted_by,
    )


@project_router.get(
    "/{id}/versions",
    response_model=VersionListResponse,
    summary="List Project Versions",
    description="List all versions across all shots and assets for a project.",
)
async def list_project_versions(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: VersionStatus | None = Query(default=None),
    submitted_by: uuid.UUID | None = Query(default=None),
) -> VersionListResponse:
    return await VersionService(db).list_by_project(
        project_id=id,
        offset=offset,
        limit=limit,
        status=status,
        submitted_by=submitted_by,
    )


@assets_router.get(
    "/{id}/versions",
    response_model=VersionListResponse,
    summary="List Asset Versions",
)
async def list_asset_versions(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: VersionStatus | None = Query(default=None),
    pipeline_task_id: uuid.UUID | None = Query(default=None),
    submitted_by: uuid.UUID | None = Query(default=None),
) -> VersionListResponse:
    return await VersionService(db).list_by_asset(
        asset_id=id,
        offset=offset,
        limit=limit,
        status=status,
        pipeline_task_id=pipeline_task_id,
        submitted_by=submitted_by,
    )

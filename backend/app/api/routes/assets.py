import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import AssetStatus, AssetType, User
from app.schemas.asset import (
    AssetCreateRequest,
    AssetListResponse,
    AssetResponse,
    AssetStatusUpdateRequest,
    AssetStatusUpdateResponse,
    AssetUpdateRequest,
)
from app.schemas.file import FileListResponse
from app.services.asset_workflow_service import AssetWorkflowService
from app.services.file_service import FileService
from app.services.project_service import ProjectService

router = APIRouter()
project_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.patch(
    "/{id}/status",
    response_model=AssetStatusUpdateResponse,
    summary="Update Asset Status",
    description="Apply a validated asset workflow transition and store audit metadata.",
)
async def update_asset_status(
    id: uuid.UUID,
    payload: AssetStatusUpdateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> AssetStatusUpdateResponse:
    service = AssetWorkflowService(db)
    return await service.update_status(
        asset_id=id,
        target_status=payload.status,
        comment=payload.comment,
        current_user=current_user,
    )


@router.get(
    "/{id}/files",
    response_model=FileListResponse,
    summary="List Asset Files",
    description="List files linked to the asset.",
)
async def list_asset_files(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> FileListResponse:
    service = FileService(db)
    return await service.list_files(
        shot_id=None,
        asset_id=id,
        offset=offset,
        limit=limit,
        current_user=current_user,
    )


@project_router.post(
    "/{id}/assets",
    response_model=AssetResponse,
    summary="Create Project Asset",
    description="Create an asset under the specified project.",
)
async def create_project_asset(
    id: uuid.UUID,
    payload: AssetCreateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> AssetResponse:
    service = ProjectService(db)
    return await service.create_project_asset(
        project_id=id,
        payload=payload,
        current_user=current_user,
    )


@project_router.get(
    "/{id}/assets",
    response_model=AssetListResponse,
    summary="List Project Assets",
    description="List project assets with pagination and optional status/assignee/type filters.",
)
async def list_project_assets(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: AssetStatus | None = Query(default=None),
    assigned_to: uuid.UUID | None = Query(default=None),
    asset_type: AssetType | None = Query(default=None),
) -> AssetListResponse:
    service = ProjectService(db)
    return await service.list_project_assets(
        project_id=id,
        current_user=current_user,
        offset=offset,
        limit=limit,
        status=status,
        assigned_to=assigned_to,
        asset_type=asset_type,
    )


@router.patch(
    "/{id}",
    response_model=AssetResponse,
    summary="Patch Asset",
    description="Patch asset fields by asset id.",
)
async def patch_asset(
    id: uuid.UUID,
    payload: AssetUpdateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> AssetResponse:
    service = ProjectService(db)
    return await service.patch_asset(
        asset_id=id,
        payload=payload,
        current_user=current_user,
    )


@router.post(
    "/{id}/archive",
    response_model=AssetResponse,
    summary="Archive Asset",
    description="Archive an asset (soft delete).",
)
async def archive_asset(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> AssetResponse:
    service = ProjectService(db)
    return await service.archive_asset(asset_id=id, current_user=current_user)


@router.post(
    "/{id}/restore",
    response_model=AssetResponse,
    summary="Restore Asset",
    description="Restore an archived asset.",
)
async def restore_asset(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> AssetResponse:
    service = ProjectService(db)
    return await service.restore_asset(asset_id=id, current_user=current_user)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Delete Asset",
    description="Hard delete an asset (admin only) with force=true.",
)
async def delete_asset(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    force: bool = Query(default=False),
) -> None:
    service = ProjectService(db)
    await service.delete_asset(asset_id=id, current_user=current_user, force=force)

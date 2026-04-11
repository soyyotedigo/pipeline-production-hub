import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import ShotStatus, User
from app.schemas.file import FileListResponse
from app.schemas.shot import (
    ShotCreateRequest,
    ShotListResponse,
    ShotResponse,
    ShotStatusHistoryResponse,
    ShotStatusUpdateRequest,
    ShotStatusUpdateResponse,
    ShotUpdateRequest,
)
from app.services.file_service import FileService
from app.services.project_service import ProjectService
from app.services.shot_workflow_service import ShotWorkflowService

router = APIRouter()
project_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get(
    "/{id}",
    response_model=ShotResponse,
    summary="Get Shot",
    description="Get shot details by id.",
)
async def get_shot(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ShotResponse:
    service = ProjectService(db)
    return await service.get_shot(shot_id=id, current_user=current_user)


@router.patch(
    "/{id}",
    response_model=ShotResponse,
    summary="Update Shot",
    description="Patch editable shot fields (assignment, frame range, metadata).",
)
async def patch_shot(
    id: uuid.UUID,
    payload: ShotUpdateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ShotResponse:
    service = ProjectService(db)
    return await service.patch_shot(
        shot_id=id,
        payload=payload,
        current_user=current_user,
    )


@router.post(
    "/{id}/archive",
    response_model=ShotResponse,
    summary="Archive Shot",
    description="Archive a shot (soft delete).",
)
async def archive_shot(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ShotResponse:
    service = ProjectService(db)
    return await service.archive_shot(shot_id=id, current_user=current_user)


@router.post(
    "/{id}/restore",
    response_model=ShotResponse,
    summary="Restore Shot",
    description="Restore an archived shot.",
)
async def restore_shot(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ShotResponse:
    service = ProjectService(db)
    return await service.restore_shot(shot_id=id, current_user=current_user)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Delete Shot",
    description="Hard delete a shot (admin only) with force=true.",
)
async def delete_shot(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    force: bool = Query(default=False),
) -> None:
    service = ProjectService(db)
    await service.delete_shot(shot_id=id, current_user=current_user, force=force)


@router.patch(
    "/{id}/status",
    response_model=ShotStatusUpdateResponse,
    summary="Update Shot Status",
    description="Apply a validated workflow status transition and append audit trail entry.",
)
async def update_shot_status_v2(
    id: uuid.UUID,
    payload: ShotStatusUpdateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ShotStatusUpdateResponse:
    service = ShotWorkflowService(db)
    return await service.update_status(
        shot_id=id,
        target_status=payload.status,
        comment=payload.comment,
        current_user=current_user,
    )


@router.get(
    "/{id}/history",
    response_model=ShotStatusHistoryResponse,
    summary="List Shot Status History",
    description="List workflow transitions for the shot with pagination.",
)
async def get_shot_status_history_v2(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ShotStatusHistoryResponse:
    service = ShotWorkflowService(db)
    return await service.list_status_history(
        shot_id=id,
        current_user=current_user,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{id}/files",
    response_model=FileListResponse,
    summary="List Shot Files",
    description="List files associated with a shot.",
)
async def list_shot_files(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> FileListResponse:
    service = FileService(db)
    return await service.list_files(
        shot_id=id,
        asset_id=None,
        offset=offset,
        limit=limit,
        current_user=current_user,
    )


@project_router.post(
    "/{id}/shots",
    response_model=ShotResponse,
    summary="Create Project Shot",
    description="Create a shot under the specified project.",
)
async def create_project_shot(
    id: uuid.UUID,
    payload: ShotCreateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ShotResponse:
    service = ProjectService(db)
    return await service.create_project_shot(
        project_id=id,
        payload=payload,
        current_user=current_user,
    )


@project_router.get(
    "/{id}/shots",
    response_model=ShotListResponse,
    summary="List Project Shots",
    description="List shots for a project with pagination and optional status/assignee filters.",
)
async def list_project_shots(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: ShotStatus | None = Query(default=None),
    assigned_to: uuid.UUID | None = Query(default=None),
) -> ShotListResponse:
    service = ProjectService(db)
    return await service.list_project_shots(
        project_id=id,
        current_user=current_user,
        offset=offset,
        limit=limit,
        status=status,
        assigned_to=assigned_to,
    )

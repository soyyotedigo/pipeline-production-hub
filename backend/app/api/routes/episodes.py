import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.project import (
    EpisodeCreateRequest,
    EpisodeListResponse,
    EpisodeResponse,
    EpisodeUpdateRequest,
)
from app.services.project_service import ProjectService

router = APIRouter()
project_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get(
    "/{id}",
    response_model=EpisodeResponse,
    summary="Get Episode",
    description="Get episode details by id.",
)
async def get_episode(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> EpisodeResponse:
    service = ProjectService(db)
    return await service.get_episode(episode_id=id, current_user=current_user)


@router.patch(
    "/{id}",
    response_model=EpisodeResponse,
    summary="Patch Episode",
    description="Patch episode fields by episode id.",
)
async def patch_episode(
    id: uuid.UUID,
    payload: EpisodeUpdateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> EpisodeResponse:
    service = ProjectService(db)
    return await service.patch_episode(
        episode_id=id,
        payload=payload,
        current_user=current_user,
    )


@router.post(
    "/{id}/archive",
    response_model=EpisodeResponse,
    summary="Archive Episode",
    description="Archive an episode (soft delete).",
)
async def archive_episode(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> EpisodeResponse:
    service = ProjectService(db)
    return await service.archive_episode(episode_id=id, current_user=current_user)


@router.post(
    "/{id}/restore",
    response_model=EpisodeResponse,
    summary="Restore Episode",
    description="Restore an archived episode.",
)
async def restore_episode(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> EpisodeResponse:
    service = ProjectService(db)
    return await service.restore_episode(episode_id=id, current_user=current_user)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Delete Episode",
    description="Hard delete an episode (admin only) with force=true.",
)
async def delete_episode(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    force: bool = Query(default=False),
) -> None:
    service = ProjectService(db)
    await service.delete_episode(episode_id=id, current_user=current_user, force=force)


@project_router.post(
    "/{id}/episodes",
    response_model=EpisodeResponse,
    summary="Create Project Episode",
    description="Create an episode container under a project.",
)
async def create_project_episode(
    id: uuid.UUID,
    payload: EpisodeCreateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> EpisodeResponse:
    service = ProjectService(db)
    return await service.create_project_episode(
        project_id=id,
        payload=payload,
        current_user=current_user,
    )


@project_router.get(
    "/{id}/episodes",
    response_model=EpisodeListResponse,
    summary="List Project Episodes",
    description="List project episodes with pagination.",
)
async def list_project_episodes(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> EpisodeListResponse:
    service = ProjectService(db)
    return await service.list_project_episodes(
        project_id=id,
        current_user=current_user,
        offset=offset,
        limit=limit,
    )

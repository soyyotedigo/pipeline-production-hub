import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.project import (
    SequenceCreateRequest,
    SequenceListResponse,
    SequenceResponse,
    SequenceUpdateRequest,
)
from app.services.project_service import ProjectService

router = APIRouter()
project_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get(
    "/{id}",
    response_model=SequenceResponse,
    summary="Get Sequence",
    description="Get sequence details by id.",
)
async def get_sequence(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> SequenceResponse:
    service = ProjectService(db)
    return await service.get_sequence(sequence_id=id, current_user=current_user)


@router.patch(
    "/{id}",
    response_model=SequenceResponse,
    summary="Patch Sequence",
    description="Patch sequence fields by sequence id.",
)
async def patch_sequence(
    id: uuid.UUID,
    payload: SequenceUpdateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> SequenceResponse:
    service = ProjectService(db)
    return await service.patch_sequence(
        sequence_id=id,
        payload=payload,
        current_user=current_user,
    )


@router.post(
    "/{id}/archive",
    response_model=SequenceResponse,
    summary="Archive Sequence",
    description="Archive a sequence (soft delete).",
)
async def archive_sequence(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> SequenceResponse:
    service = ProjectService(db)
    return await service.archive_sequence(sequence_id=id, current_user=current_user)


@router.post(
    "/{id}/restore",
    response_model=SequenceResponse,
    summary="Restore Sequence",
    description="Restore an archived sequence.",
)
async def restore_sequence(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> SequenceResponse:
    service = ProjectService(db)
    return await service.restore_sequence(sequence_id=id, current_user=current_user)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Delete Sequence",
    description="Hard delete a sequence (admin only) with force=true.",
)
async def delete_sequence(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    force: bool = Query(default=False),
) -> None:
    service = ProjectService(db)
    await service.delete_sequence(sequence_id=id, current_user=current_user, force=force)


@project_router.post(
    "/{id}/sequences",
    response_model=SequenceResponse,
    summary="Create Project Sequence",
    description="Create a sequence under the given project (optionally linked to an episode).",
)
async def create_project_sequence(
    id: uuid.UUID,
    payload: SequenceCreateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> SequenceResponse:
    service = ProjectService(db)
    return await service.create_project_sequence(
        project_id=id,
        payload=payload,
        current_user=current_user,
    )


@project_router.get(
    "/{id}/sequences",
    response_model=SequenceListResponse,
    summary="List Project Sequences",
    description="List project sequences with optional episode filter and pagination.",
)
async def list_project_sequences(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    episode_id: uuid.UUID | None = Query(default=None),
) -> SequenceListResponse:
    service = ProjectService(db)
    return await service.list_project_sequences(
        project_id=id,
        current_user=current_user,
        offset=offset,
        limit=limit,
        episode_id=episode_id,
    )

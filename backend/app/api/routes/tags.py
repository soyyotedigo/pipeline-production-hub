import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.tag import TagEntityType
from app.schemas.tag import (
    EntityTagCreate,
    EntityTagResponse,
    ProjectTagCreate,
    TagCreate,
    TagResponse,
    TagUpdate,
)
from app.services.tag_service import TagService

router = APIRouter()
shots_router = APIRouter()
assets_router = APIRouter()
sequences_router = APIRouter()
projects_router = APIRouter()
entity_tags_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post(
    "",
    response_model=TagResponse,
    status_code=201,
    summary="Create Tag",
    description="Create a new tag, optionally scoped to a project.",
)
async def create_tag(data: TagCreate, current_user: CurrentUserDep, db: DbDep) -> TagResponse:
    service = TagService(db)
    tag = await service.create_tag(data, current_user=current_user)
    return TagResponse.model_validate(tag)


@router.get(
    "",
    response_model=list[TagResponse],
    summary="List Tags",
    description="List all tags, optionally filtered by project.",
)
async def list_tags(
    current_user: CurrentUserDep,
    db: DbDep,
    project_id: uuid.UUID | None = Query(default=None),
) -> list[TagResponse]:
    service = TagService(db)
    tags = await service.list_tags(project_id=project_id)
    return [TagResponse.model_validate(t) for t in tags]


@router.get(
    "/search",
    response_model=list[TagResponse],
    summary="Search Tags",
    description="Search tags by name fragment, optionally restricted to a project.",
)
async def search_tags(
    current_user: CurrentUserDep,
    db: DbDep,
    q: str = Query(min_length=1),
    project_id: uuid.UUID | None = Query(default=None),
) -> list[TagResponse]:
    service = TagService(db)
    tags = await service.search_tags(q=q, project_id=project_id)
    return [TagResponse.model_validate(t) for t in tags]


@router.get(
    "/{id}",
    response_model=TagResponse,
    summary="Get Tag",
    description="Retrieve a tag by its identifier.",
)
async def get_tag(id: uuid.UUID, current_user: CurrentUserDep, db: DbDep) -> TagResponse:
    service = TagService(db)
    tag = await service.get_tag(id)
    return TagResponse.model_validate(tag)


@router.patch(
    "/{id}",
    response_model=TagResponse,
    summary="Update Tag",
    description="Update mutable fields of a tag (name, color).",
)
async def update_tag(
    id: uuid.UUID, data: TagUpdate, current_user: CurrentUserDep, db: DbDep
) -> TagResponse:
    service = TagService(db)
    tag = await service.update_tag(id, data, current_user=current_user)
    return TagResponse.model_validate(tag)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Delete Tag",
    description="Delete a tag and detach it from any tagged entities.",
)
async def delete_tag(id: uuid.UUID, current_user: CurrentUserDep, db: DbDep) -> Response:
    service = TagService(db)
    await service.delete_tag(id, current_user=current_user)
    return Response(status_code=204)


# Project tag endpoints
@projects_router.get(
    "/{id}/tags",
    response_model=list[TagResponse],
    summary="List Project Tags",
    description="List all tags scoped to the given project.",
)
async def list_project_tags(
    id: uuid.UUID, current_user: CurrentUserDep, db: DbDep
) -> list[TagResponse]:
    service = TagService(db)
    tags = await service.list_tags(project_id=id)
    return [TagResponse.model_validate(t) for t in tags]


@projects_router.post(
    "/{id}/tags",
    response_model=TagResponse,
    status_code=201,
    summary="Create Project Tag",
    description="Create a new tag scoped to the given project.",
)
async def create_project_tag(
    id: uuid.UUID, data: ProjectTagCreate, current_user: CurrentUserDep, db: DbDep
) -> TagResponse:
    service = TagService(db)
    tag = await service.create_tag(
        TagCreate(name=data.name, color=data.color, project_id=id),
        current_user=current_user,
    )
    return TagResponse.model_validate(tag)


# Shot tag endpoints
@shots_router.post(
    "/{id}/tags",
    response_model=EntityTagResponse,
    status_code=201,
    summary="Attach Tag To Shot",
    description="Attach an existing tag to a shot.",
)
async def attach_tag_to_shot(
    id: uuid.UUID, data: EntityTagCreate, current_user: CurrentUserDep, db: DbDep
) -> EntityTagResponse:
    service = TagService(db)
    return await service.attach_tag(TagEntityType.shot, id, data.tag_id)


@shots_router.get(
    "/{id}/tags",
    response_model=list[TagResponse],
    summary="List Shot Tags",
    description="List all tags currently attached to the shot.",
)
async def list_shot_tags(
    id: uuid.UUID, current_user: CurrentUserDep, db: DbDep
) -> list[TagResponse]:
    service = TagService(db)
    tags = await service.list_entity_tags(TagEntityType.shot, id)
    return [TagResponse.model_validate(t) for t in tags]


# Asset tag endpoints
@assets_router.post(
    "/{id}/tags",
    response_model=EntityTagResponse,
    status_code=201,
    summary="Attach Tag To Asset",
    description="Attach an existing tag to an asset.",
)
async def attach_tag_to_asset(
    id: uuid.UUID, data: EntityTagCreate, current_user: CurrentUserDep, db: DbDep
) -> EntityTagResponse:
    service = TagService(db)
    return await service.attach_tag(TagEntityType.asset, id, data.tag_id)


@assets_router.get(
    "/{id}/tags",
    response_model=list[TagResponse],
    summary="List Asset Tags",
    description="List all tags currently attached to the asset.",
)
async def list_asset_tags(
    id: uuid.UUID, current_user: CurrentUserDep, db: DbDep
) -> list[TagResponse]:
    service = TagService(db)
    tags = await service.list_entity_tags(TagEntityType.asset, id)
    return [TagResponse.model_validate(t) for t in tags]


# Sequence tag endpoints
@sequences_router.post(
    "/{id}/tags",
    response_model=EntityTagResponse,
    status_code=201,
    summary="Attach Tag To Sequence",
    description="Attach an existing tag to a sequence.",
)
async def attach_tag_to_sequence(
    id: uuid.UUID, data: EntityTagCreate, current_user: CurrentUserDep, db: DbDep
) -> EntityTagResponse:
    service = TagService(db)
    return await service.attach_tag(TagEntityType.sequence, id, data.tag_id)


@sequences_router.get(
    "/{id}/tags",
    response_model=list[TagResponse],
    summary="List Sequence Tags",
    description="List all tags currently attached to the sequence.",
)
async def list_sequence_tags(
    id: uuid.UUID, current_user: CurrentUserDep, db: DbDep
) -> list[TagResponse]:
    service = TagService(db)
    tags = await service.list_entity_tags(TagEntityType.sequence, id)
    return [TagResponse.model_validate(t) for t in tags]


@entity_tags_router.delete(
    "/{id}",
    status_code=204,
    summary="Detach Entity Tag",
    description="Remove a tag attachment from an entity by entity-tag id.",
)
async def detach_entity_tag(id: uuid.UUID, current_user: CurrentUserDep, db: DbDep) -> Response:
    service = TagService(db)
    await service.detach_entity_tag(id)
    return Response(status_code=204)

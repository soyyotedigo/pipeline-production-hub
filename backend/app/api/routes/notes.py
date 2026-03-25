import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.note import NoteEntityType
from app.schemas.note import (
    EntityNoteCreate,
    NoteCreate,
    NoteListResponse,
    NoteReplyCreate,
    NoteResponse,
    NoteThreadResponse,
    NoteUpdate,
    ProjectNoteCreate,
)
from app.services.note_service import NoteService

router = APIRouter()
shots_router = APIRouter()
assets_router = APIRouter()
pipeline_tasks_router = APIRouter()
projects_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


# ── Core note endpoints ───────────────────────────────────────────────────────


@router.post(
    "",
    response_model=NoteResponse,
    status_code=201,
    summary="Create Note",
    description="Create a note on any entity (shot, asset, pipeline_task, project, etc.).",
)
async def create_note(
    payload: NoteCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> NoteResponse:
    service = NoteService(db)
    return await service.create_note(payload=payload, current_user=current_user)


@router.get(
    "/{id}",
    response_model=NoteThreadResponse,
    summary="Get Note",
    description="Get a note with its replies.",
)
async def get_note(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> NoteThreadResponse:
    service = NoteService(db)
    return await service.get_note(note_id=id)


@router.patch(
    "/{id}",
    response_model=NoteResponse,
    summary="Update Note",
    description="Update subject, body, or client visibility of a note.",
)
async def update_note(
    id: uuid.UUID,
    payload: NoteUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> NoteResponse:
    service = NoteService(db)
    return await service.update_note(note_id=id, payload=payload, current_user=current_user)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Archive Note",
    description="Soft-delete a note by setting archived_at.",
)
async def archive_note(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> Response:
    service = NoteService(db)
    await service.archive_note(note_id=id, current_user=current_user)
    return Response(status_code=204)


@router.post(
    "/{id}/reply",
    response_model=NoteResponse,
    status_code=201,
    summary="Reply to Note",
    description="Create a reply to an existing note. Only one level of threading allowed.",
)
async def reply_to_note(
    id: uuid.UUID,
    payload: NoteReplyCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> NoteResponse:
    service = NoteService(db)
    return await service.create_reply(parent_note_id=id, payload=payload, current_user=current_user)


# ── Convenience list endpoints ────────────────────────────────────────────────


@shots_router.post(
    "/{id}/notes",
    response_model=NoteResponse,
    status_code=201,
    summary="Create Shot Note",
)
async def create_shot_note(
    id: uuid.UUID,
    payload: EntityNoteCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> NoteResponse:
    service = NoteService(db)
    return await service.create_note(
        payload=NoteCreate(entity_type=NoteEntityType.shot, entity_id=id, **payload.model_dump()),
        current_user=current_user,
    )


@shots_router.get(
    "/{id}/notes",
    response_model=NoteListResponse,
    summary="List Shot Notes",
    description="List notes for a shot.",
)
async def list_shot_notes(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_replies: bool = Query(default=False),
    client_visible_only: bool = Query(default=False),
    author_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
) -> NoteListResponse:
    service = NoteService(db)
    # project_id is required to determine client visibility; default to a zero UUID if not supplied
    # (the client check will simply not match any role)
    resolved_project_id = project_id or uuid.UUID(int=0)
    return await service.list_by_entity(
        entity_type=NoteEntityType.shot,
        entity_id=id,
        project_id=resolved_project_id,
        current_user=current_user,
        offset=offset,
        limit=limit,
        include_replies=include_replies,
        client_visible_only=client_visible_only,
        author_id=author_id,
    )


@assets_router.post(
    "/{id}/notes",
    response_model=NoteResponse,
    status_code=201,
    summary="Create Asset Note",
)
async def create_asset_note(
    id: uuid.UUID,
    payload: EntityNoteCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> NoteResponse:
    service = NoteService(db)
    return await service.create_note(
        payload=NoteCreate(entity_type=NoteEntityType.asset, entity_id=id, **payload.model_dump()),
        current_user=current_user,
    )


@assets_router.get(
    "/{id}/notes",
    response_model=NoteListResponse,
    summary="List Asset Notes",
    description="List notes for an asset.",
)
async def list_asset_notes(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_replies: bool = Query(default=False),
    client_visible_only: bool = Query(default=False),
    author_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
) -> NoteListResponse:
    service = NoteService(db)
    resolved_project_id = project_id or uuid.UUID(int=0)
    return await service.list_by_entity(
        entity_type=NoteEntityType.asset,
        entity_id=id,
        project_id=resolved_project_id,
        current_user=current_user,
        offset=offset,
        limit=limit,
        include_replies=include_replies,
        client_visible_only=client_visible_only,
        author_id=author_id,
    )


@pipeline_tasks_router.post(
    "/{id}/notes",
    response_model=NoteResponse,
    status_code=201,
    summary="Create Pipeline Task Note",
)
async def create_pipeline_task_note(
    id: uuid.UUID,
    payload: EntityNoteCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> NoteResponse:
    service = NoteService(db)
    return await service.create_note(
        payload=NoteCreate(
            entity_type=NoteEntityType.pipeline_task, entity_id=id, **payload.model_dump()
        ),
        current_user=current_user,
    )


@pipeline_tasks_router.get(
    "/{id}/notes",
    response_model=NoteListResponse,
    summary="List Pipeline Task Notes",
    description="List notes for a pipeline task.",
)
async def list_pipeline_task_notes(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_replies: bool = Query(default=False),
    client_visible_only: bool = Query(default=False),
    author_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
) -> NoteListResponse:
    service = NoteService(db)
    resolved_project_id = project_id or uuid.UUID(int=0)
    return await service.list_by_entity(
        entity_type=NoteEntityType.pipeline_task,
        entity_id=id,
        project_id=resolved_project_id,
        current_user=current_user,
        offset=offset,
        limit=limit,
        include_replies=include_replies,
        client_visible_only=client_visible_only,
        author_id=author_id,
    )


@projects_router.post(
    "/{id}/notes",
    response_model=NoteResponse,
    status_code=201,
    summary="Create Project Note",
)
async def create_project_note(
    id: uuid.UUID,
    payload: ProjectNoteCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> NoteResponse:
    service = NoteService(db)
    return await service.create_note(
        payload=NoteCreate(
            entity_type=NoteEntityType.project, entity_id=id, project_id=id, **payload.model_dump()
        ),
        current_user=current_user,
    )


@projects_router.get(
    "/{id}/notes",
    response_model=NoteListResponse,
    summary="List Project Notes",
    description="List top-level notes for a project.",
)
async def list_project_notes(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_replies: bool = Query(default=False),
    client_visible_only: bool = Query(default=False),
    author_id: uuid.UUID | None = Query(default=None),
) -> NoteListResponse:
    service = NoteService(db)
    return await service.list_by_project(
        project_id=id,
        current_user=current_user,
        offset=offset,
        limit=limit,
        include_replies=include_replies,
        client_visible_only=client_visible_only,
        author_id=author_id,
    )

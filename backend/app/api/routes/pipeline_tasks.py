import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.pipeline_task import PipelineTaskStatus
from app.schemas.pipeline_task import (
    ApplyTemplateRequest,
    ApplyTemplateResponse,
    PipelineTaskCreateRequest,
    PipelineTaskListResponse,
    PipelineTaskResponse,
    PipelineTaskStatusUpdateRequest,
    PipelineTaskStatusUpdateResponse,
    PipelineTaskUpdateRequest,
    PipelineTemplateCreateRequest,
    PipelineTemplateListResponse,
    PipelineTemplateResponse,
    PipelineTemplateUpdateRequest,
)
from app.services.pipeline_task_service import PipelineTaskService

# ── Template router ──────────────────────────────────────────────────────────

template_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@template_router.post(
    "",
    response_model=PipelineTemplateResponse,
    summary="Create Pipeline Template",
    description="Create a pipeline template with nested steps.",
)
async def create_template(
    payload: PipelineTemplateCreateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PipelineTemplateResponse:
    service = PipelineTaskService(db)
    return await service.create_template(payload)


@template_router.get(
    "",
    response_model=PipelineTemplateListResponse,
    summary="List Pipeline Templates",
    description="List pipeline templates with optional project_type filter.",
)
async def list_templates(
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    project_type: str | None = Query(default=None),
) -> PipelineTemplateListResponse:
    service = PipelineTaskService(db)
    return await service.list_templates(offset=offset, limit=limit, project_type=project_type)


@template_router.get(
    "/{id}",
    response_model=PipelineTemplateResponse,
    summary="Get Pipeline Template",
    description="Get a pipeline template with its steps.",
)
async def get_template(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PipelineTemplateResponse:
    service = PipelineTaskService(db)
    return await service.get_template(id)


@template_router.patch(
    "/{id}",
    response_model=PipelineTemplateResponse,
    summary="Update Pipeline Template",
    description="Update pipeline template name or description.",
)
async def update_template(
    id: uuid.UUID,
    payload: PipelineTemplateUpdateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PipelineTemplateResponse:
    service = PipelineTaskService(db)
    return await service.update_template(id, payload)


@template_router.post(
    "/{id}/archive",
    response_model=PipelineTemplateResponse,
    summary="Archive Pipeline Template",
    description="Archive a pipeline template (soft delete).",
)
async def archive_template(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PipelineTemplateResponse:
    service = PipelineTaskService(db)
    return await service.archive_template(id)


@template_router.post(
    "/{id}/apply",
    response_model=ApplyTemplateResponse,
    status_code=201,
    summary="Apply Pipeline Template",
    description="Instantiate a template's steps as pipeline tasks on a shot or asset.",
)
async def apply_template(
    id: uuid.UUID,
    payload: ApplyTemplateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApplyTemplateResponse:
    return await PipelineTaskService(db).apply_template(
        template_id=id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
    )


@template_router.delete(
    "/{id}",
    status_code=204,
    summary="Delete Pipeline Template",
    description="Hard delete a pipeline template.",
)
async def delete_template(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> None:
    service = PipelineTaskService(db)
    await service.delete_template(id)


# ── Shot tasks router ────────────────────────────────────────────────────────

shot_tasks_router = APIRouter()


@shot_tasks_router.get(
    "/{id}/tasks",
    response_model=PipelineTaskListResponse,
    summary="List Shot Pipeline Tasks",
    description="List pipeline tasks for a shot.",
)
async def list_shot_tasks(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: PipelineTaskStatus | None = Query(default=None),
) -> PipelineTaskListResponse:
    service = PipelineTaskService(db)
    return await service.list_tasks_for_shot(
        shot_id=id,
        offset=offset,
        limit=limit,
        status=status,
    )


@shot_tasks_router.post(
    "/{id}/tasks",
    response_model=PipelineTaskResponse,
    status_code=201,
    summary="Create Shot Pipeline Task",
    description="Create a standalone pipeline task on a shot.",
)
async def create_shot_task(
    id: uuid.UUID,
    payload: PipelineTaskCreateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PipelineTaskResponse:
    return await PipelineTaskService(db).create_task(
        shot_id=id,
        asset_id=None,
        payload=payload,
    )


# ── Asset tasks router ──────────────────────────────────────────────────────

asset_tasks_router = APIRouter()


@asset_tasks_router.get(
    "/{id}/tasks",
    response_model=PipelineTaskListResponse,
    summary="List Asset Pipeline Tasks",
    description="List pipeline tasks for an asset.",
)
async def list_asset_tasks(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: PipelineTaskStatus | None = Query(default=None),
) -> PipelineTaskListResponse:
    service = PipelineTaskService(db)
    return await service.list_tasks_for_asset(
        asset_id=id,
        offset=offset,
        limit=limit,
        status=status,
    )


@asset_tasks_router.post(
    "/{id}/tasks",
    response_model=PipelineTaskResponse,
    status_code=201,
    summary="Create Asset Pipeline Task",
    description="Create a standalone pipeline task on an asset.",
)
async def create_asset_task(
    id: uuid.UUID,
    payload: PipelineTaskCreateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PipelineTaskResponse:
    return await PipelineTaskService(db).create_task(
        shot_id=None,
        asset_id=id,
        payload=payload,
    )


# ── Task operations router ──────────────────────────────────────────────────

task_ops_router = APIRouter()


@task_ops_router.get(
    "/{id}",
    response_model=PipelineTaskResponse,
    summary="Get Pipeline Task",
    description="Get pipeline task details by id.",
)
async def get_task(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PipelineTaskResponse:
    service = PipelineTaskService(db)
    return await service.get_task(id)


@task_ops_router.patch(
    "/{id}",
    response_model=PipelineTaskResponse,
    summary="Update Pipeline Task",
    description="Update task fields (assigned_to, due_date, notes).",
)
async def update_task(
    id: uuid.UUID,
    payload: PipelineTaskUpdateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PipelineTaskResponse:
    service = PipelineTaskService(db)
    return await service.update_task(id, payload, actor_id=current_user.id)


@task_ops_router.patch(
    "/{id}/status",
    response_model=PipelineTaskStatusUpdateResponse,
    summary="Update Pipeline Task Status",
    description="Apply a validated pipeline status transition.",
)
async def update_task_status(
    id: uuid.UUID,
    payload: PipelineTaskStatusUpdateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PipelineTaskStatusUpdateResponse:
    service = PipelineTaskService(db)
    return await service.update_task_status(
        task_id=id,
        payload=payload,
        changed_by=current_user.id,
    )


@task_ops_router.post(
    "/{id}/archive",
    response_model=PipelineTaskResponse,
    summary="Archive Pipeline Task",
    description="Archive a pipeline task (soft delete).",
)
async def archive_task(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PipelineTaskResponse:
    service = PipelineTaskService(db)
    return await service.archive_task(id)


@task_ops_router.delete(
    "/{id}",
    status_code=204,
    summary="Delete Pipeline Task",
    description="Hard delete a pipeline task.",
)
async def delete_task(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> None:
    await PipelineTaskService(db).delete_task(task_id=id)

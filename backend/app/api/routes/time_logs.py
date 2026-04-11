import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.time_log import (
    ProjectTimeLogSummary,
    TimeLogCreate,
    TimeLogResponse,
    TimeLogUpdate,
)
from app.services.time_log_service import TimeLogService

router = APIRouter()
projects_router = APIRouter()
tasks_router = APIRouter()
users_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post(
    "",
    response_model=TimeLogResponse,
    status_code=201,
    summary="Create Time Log",
    description="Log time spent by the current user against a pipeline task.",
)
async def create_timelog(
    data: TimeLogCreate, current_user: CurrentUserDep, db: DbDep
) -> TimeLogResponse:
    service = TimeLogService(db)
    log = await service.create(data, user_id=current_user.id)
    return TimeLogResponse.model_validate(log)


@router.get(
    "/{id}",
    response_model=TimeLogResponse,
    summary="Get Time Log",
    description="Retrieve a single time log entry by its identifier.",
)
async def get_timelog(id: uuid.UUID, current_user: CurrentUserDep, db: DbDep) -> TimeLogResponse:
    service = TimeLogService(db)
    log = await service.get(id)
    return TimeLogResponse.model_validate(log)


@router.patch(
    "/{id}",
    response_model=TimeLogResponse,
    summary="Update Time Log",
    description="Update a time log entry. Owners can edit their own entries; admins can edit any.",
)
async def update_timelog(
    id: uuid.UUID, data: TimeLogUpdate, current_user: CurrentUserDep, db: DbDep
) -> TimeLogResponse:
    from app.models.role import RoleName

    is_admin = (
        current_user.global_role == RoleName.admin
        if hasattr(current_user, "global_role")
        else False
    )
    service = TimeLogService(db)
    log = await service.update(id, data, user_id=current_user.id, is_admin=is_admin)
    return TimeLogResponse.model_validate(log)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Delete Time Log",
    description="Delete a time log entry. Owners can delete their own entries; admins can delete any.",
)
async def delete_timelog(id: uuid.UUID, current_user: CurrentUserDep, db: DbDep) -> Response:
    from app.models.role import RoleName

    is_admin = (
        current_user.global_role == RoleName.admin
        if hasattr(current_user, "global_role")
        else False
    )
    service = TimeLogService(db)
    await service.delete(id, user_id=current_user.id, is_admin=is_admin)
    return Response(status_code=204)


# Project timelogs
@projects_router.get(
    "/{id}/timelogs",
    response_model=list[TimeLogResponse],
    summary="List Project Time Logs",
    description="List time log entries for a project with optional date range, user and task filters.",
)
async def list_project_timelogs(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    pipeline_task_id: uuid.UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[TimeLogResponse]:
    service = TimeLogService(db)
    logs, _ = await service.list_by_project(
        id,
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
        pipeline_task_id=pipeline_task_id,
        offset=offset,
        limit=limit,
    )
    return [TimeLogResponse.model_validate(log) for log in logs]


@projects_router.get(
    "/{id}/timelogs/summary",
    response_model=ProjectTimeLogSummary,
    summary="Get Project Time Log Summary",
    description="Aggregate time log totals for a project (per user, per task, total hours).",
)
async def get_project_timelogs_summary(
    id: uuid.UUID, current_user: CurrentUserDep, db: DbDep
) -> ProjectTimeLogSummary:
    service = TimeLogService(db)
    return await service.get_project_summary(id)


# Pipeline task timelogs
@tasks_router.get(
    "/{id}/timelogs",
    response_model=list[TimeLogResponse],
    summary="List Pipeline Task Time Logs",
    description="List time log entries logged against the given pipeline task.",
)
async def list_task_timelogs(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[TimeLogResponse]:
    service = TimeLogService(db)
    logs, _ = await service.list_by_task(id, offset=offset, limit=limit)
    return [TimeLogResponse.model_validate(log) for log in logs]


# User timelogs
@users_router.get(
    "/{id}/timelogs",
    response_model=list[TimeLogResponse],
    summary="List User Time Logs",
    description="List time log entries created by the given user, optionally filtered by date range.",
)
async def list_user_timelogs(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[TimeLogResponse]:
    service = TimeLogService(db)
    logs, _ = await service.list_by_user(
        id, date_from=date_from, date_to=date_to, offset=offset, limit=limit
    )
    return [TimeLogResponse.model_validate(log) for log in logs]

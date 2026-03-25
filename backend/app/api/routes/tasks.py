import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user
from app.models import User
from app.schemas.task import TaskListResponse, TaskStatus, TaskStatusResponse
from app.services.task_service import TaskService

router = APIRouter()

CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List My Tasks",
    description="List background tasks created by the authenticated user, newest first.",
)
async def list_tasks(
    current_user: CurrentUserDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: TaskStatus | None = Query(default=None),
) -> TaskListResponse:
    return await TaskService().list_tasks(
        current_user=current_user,
        offset=offset,
        limit=limit,
        status_filter=status.value if status else None,
    )


@router.get(
    "/{id}",
    response_model=TaskStatusResponse,
    summary="Get Task Status",
    description="Get background task status and result/error payload by task id.",
)
async def get_task_status(id: uuid.UUID, current_user: CurrentUserDep) -> TaskStatusResponse:
    return await TaskService().get_task_status(task_id=id, current_user=current_user)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Cancel Task",
    description="Cancel a pending background task. Only pending tasks can be cancelled.",
)
async def cancel_task(id: uuid.UUID, current_user: CurrentUserDep) -> None:
    await TaskService().cancel_task(task_id=id, current_user=current_user)

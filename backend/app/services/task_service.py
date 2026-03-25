from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from app.core.exceptions import ForbiddenError, NotFoundError, UnprocessableError
from app.models import User
from app.repositories.task_queue_repository import TaskQueueRepository
from app.schemas.task import TaskListResponse, TaskStatus, TaskStatusResponse, TaskType


class TaskService:
    def __init__(self) -> None:
        self.task_queue_repository = TaskQueueRepository()

    async def enqueue_task(
        self,
        *,
        task_type: TaskType,
        created_by: uuid.UUID,
        payload: dict[str, Any],
        task_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        resolved_task_id = task_id or uuid.uuid4()
        await self.task_queue_repository.enqueue_task(
            task_id=resolved_task_id,
            task_type=task_type,
            created_by=created_by,
            payload=payload,
        )
        return resolved_task_id

    async def get_task_status(self, task_id: uuid.UUID, current_user: User) -> TaskStatusResponse:
        task_data = await self.task_queue_repository.get_task_status(task_id)
        if task_data is None:
            raise NotFoundError("Task not found")

        created_by = task_data.get("created_by")
        if created_by is None or created_by != str(current_user.id):
            raise ForbiddenError("Insufficient permissions")

        return self._hydrate(task_data)

    async def list_tasks(
        self,
        current_user: User,
        offset: int,
        limit: int,
        status_filter: str | None,
    ) -> TaskListResponse:
        records, total = await self.task_queue_repository.list_user_tasks(
            user_id=current_user.id,
            offset=offset,
            limit=limit,
            status_filter=status_filter,
        )
        return TaskListResponse(
            items=[self._hydrate(r) for r in records],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def cancel_task(self, task_id: uuid.UUID, current_user: User) -> None:
        task_data = await self.task_queue_repository.get_task_status(task_id)
        if task_data is None:
            raise NotFoundError("Task not found")

        created_by = task_data.get("created_by")
        if created_by is None or created_by != str(current_user.id):
            raise ForbiddenError("Insufficient permissions")

        status = task_data.get("status")
        if status != TaskStatus.pending.value:
            raise UnprocessableError(
                f"Only pending tasks can be cancelled (current status: {status})"
            )

        await self.task_queue_repository.mark_cancelled(task_id)

    @staticmethod
    def _hydrate(task_data: dict[str, str]) -> TaskStatusResponse:
        raw_result = task_data.get("result_json")
        parsed_result: dict[str, object] | None = None
        if raw_result:
            parsed_json = json.loads(raw_result)
            if isinstance(parsed_json, dict):
                parsed_result = parsed_json

        error_text = task_data.get("error") or None
        return TaskStatusResponse(
            id=uuid.UUID(task_data["id"]),
            task_type=TaskType(task_data["task_type"]),
            status=TaskStatus(task_data["status"]),
            created_by=uuid.UUID(task_data["created_by"]),
            created_at=datetime.fromisoformat(task_data["created_at"]),
            updated_at=datetime.fromisoformat(task_data["updated_at"]),
            result=parsed_result,
            error=error_text,
        )

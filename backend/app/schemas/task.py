from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TaskType(str, Enum):
    thumbnail = "thumbnail"
    checksum_large_file = "checksum_large_file"
    webhook_dispatch = "webhook_dispatch"
    project_export_csv = "project_export_csv"


class TaskStatusResponse(BaseModel):
    id: uuid.UUID
    task_type: TaskType
    status: TaskStatus
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    result: dict[str, object] | None = None
    error: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "task_type": "project_export_csv",
                "status": "completed",
                "created_by": "44444444-4444-4444-4444-444444444444",
                "created_at": "2026-03-08T20:10:00Z",
                "updated_at": "2026-03-08T20:11:00Z",
                "result": {"download_url": "local://exports/report.csv"},
                "error": None,
            }
        }
    )


class TaskListResponse(BaseModel):
    items: list[TaskStatusResponse]
    total: int
    offset: int
    limit: int

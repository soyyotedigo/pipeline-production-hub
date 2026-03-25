from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.version import VersionStatus


class VersionCreate(BaseModel):
    description: str | None = None
    thumbnail_url: str | None = Field(default=None, max_length=500)
    media_url: str | None = Field(default=None, max_length=500)
    file_ids: list[uuid.UUID] = []


class VersionUpdate(BaseModel):
    description: str | None = None
    thumbnail_url: str | None = Field(default=None, max_length=500)
    media_url: str | None = Field(default=None, max_length=500)


class VersionStatusUpdate(BaseModel):
    status: VersionStatus
    comment: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(
        json_schema_extra={"example": {"status": "approved", "comment": "Looks great!"}}
    )


class VersionStatusUpdateResponse(BaseModel):
    id: uuid.UUID
    old_status: VersionStatus
    new_status: VersionStatus
    comment: str | None = None
    changed_at: datetime


class VersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    shot_id: uuid.UUID | None
    asset_id: uuid.UUID | None
    pipeline_task_id: uuid.UUID | None
    code: str
    version_number: int
    status: VersionStatus
    description: str | None
    submitted_by: uuid.UUID
    reviewed_by: uuid.UUID | None
    thumbnail_url: str | None
    media_url: str | None
    created_at: datetime
    updated_at: datetime | None
    archived_at: datetime | None


class VersionListResponse(BaseModel):
    items: list[VersionResponse]
    offset: int
    limit: int
    total: int

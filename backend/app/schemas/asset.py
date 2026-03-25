from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import AssetStatus, AssetType, Priority


class AssetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=50, description="Unique code per project")
    asset_type: AssetType
    assigned_to: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=2000)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    priority: Priority = Priority.normal

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Hero Character",
                "code": "HERO_CHAR_01",
                "asset_type": "character",
            }
        }
    )


class AssetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    asset_type: AssetType | None = None
    assigned_to: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=2000)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    priority: Priority | None = None


class AssetStatusUpdateRequest(BaseModel):
    status: AssetStatus
    comment: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(
        json_schema_extra={"example": {"status": "approved", "comment": "Approved by supervisor"}}
    )


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    code: str | None = None
    asset_type: AssetType
    status: AssetStatus
    description: str | None = None
    thumbnail_url: str | None = None
    priority: Priority
    assigned_to: uuid.UUID | None
    created_at: datetime
    updated_at: datetime | None = None
    archived_at: datetime | None


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    offset: int
    limit: int
    total: int


class AssetStatusUpdateResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    old_status: AssetStatus
    new_status: AssetStatus
    comment: str | None = None
    changed_at: datetime

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "55555555-5555-5555-5555-555555555555",
                "project_id": "11111111-1111-1111-1111-111111111111",
                "old_status": "review",
                "new_status": "approved",
                "comment": "Approved by supervisor",
                "changed_at": "2026-03-08T20:10:00Z",
            }
        }
    )

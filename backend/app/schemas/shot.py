from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Difficulty, Priority, ShotStatus


class ShotCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(
        default=None,
        min_length=2,
        max_length=64,
        description="Explicit shot code. Auto-generated from sequence + order when omitted.",
    )
    sequence_id: uuid.UUID | None = None
    frame_start: int | None = Field(default=None, ge=0)
    frame_end: int | None = Field(default=None, ge=0)
    assigned_to: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=2000)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    priority: Priority = Priority.normal
    difficulty: Difficulty | None = None
    handle_head: int | None = Field(default=None, ge=0)
    handle_tail: int | None = Field(default=None, ge=0)
    cut_in: int | None = Field(default=None, ge=0)
    cut_out: int | None = Field(default=None, ge=0)
    bid_days: float | None = Field(default=None, ge=0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Shot 010",
                "code": "SH010",
                "frame_start": 1001,
                "frame_end": 1120,
                "priority": "normal",
            }
        }
    )


class ShotUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    sort_order: int | None = None
    sequence_id: uuid.UUID | None = None
    frame_start: int | None = Field(default=None, ge=0)
    frame_end: int | None = Field(default=None, ge=0)
    assigned_to: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=2000)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    priority: Priority | None = None
    difficulty: Difficulty | None = None
    handle_head: int | None = Field(default=None, ge=0)
    handle_tail: int | None = Field(default=None, ge=0)
    cut_in: int | None = Field(default=None, ge=0)
    cut_out: int | None = Field(default=None, ge=0)
    bid_days: float | None = Field(default=None, ge=0)


class ShotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    sequence_id: uuid.UUID | None
    name: str
    code: str
    status: ShotStatus
    description: str | None = None
    thumbnail_url: str | None = None
    priority: Priority
    difficulty: Difficulty | None = None
    handle_head: int | None = None
    handle_tail: int | None = None
    cut_in: int | None = None
    cut_out: int | None = None
    bid_days: float | None = None
    sort_order: int | None = None
    frame_start: int | None
    frame_end: int | None
    assigned_to: uuid.UUID | None
    created_at: datetime
    updated_at: datetime | None = None
    archived_at: datetime | None


class ShotListResponse(BaseModel):
    items: list[ShotResponse]
    offset: int
    limit: int
    total: int


class ShotStatusUpdateRequest(BaseModel):
    status: ShotStatus
    comment: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(
        json_schema_extra={"example": {"status": "review", "comment": "Ready for lead review"}}
    )


class ShotStatusUpdateResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    old_status: ShotStatus
    new_status: ShotStatus
    comment: str | None = None
    changed_at: datetime


class ShotStatusHistoryItem(BaseModel):
    changed_at: datetime
    old_status: str | None
    new_status: str
    changed_by: uuid.UUID | None
    comment: str | None


class ShotStatusHistoryResponse(BaseModel):
    shot_id: uuid.UUID
    items: list[ShotStatusHistoryItem]
    offset: int
    limit: int
    total: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "shot_id": "33333333-3333-3333-3333-333333333333",
                "items": [
                    {
                        "changed_at": "2026-03-08T20:10:00Z",
                        "old_status": "in_progress",
                        "new_status": "review",
                        "changed_by": "44444444-4444-4444-4444-444444444444",
                        "comment": "Ready for lead review",
                    }
                ],
                "offset": 0,
                "limit": 20,
                "total": 1,
            }
        }
    )

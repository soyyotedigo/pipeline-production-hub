from __future__ import annotations

import uuid
from datetime import date as Date
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.playlist import PlaylistStatus, ReviewStatus

# ── Playlist ──────────────────────────────────────────────────────────────────


class PlaylistCreate(BaseModel):
    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    date: Date | None = None


class PlaylistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    date: Date | None = None
    status: PlaylistStatus | None = None


class PlaylistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    playlist_id: uuid.UUID
    version_id: uuid.UUID
    order: int
    review_status: ReviewStatus
    reviewer_notes: str | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime


class PlaylistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    created_by: uuid.UUID
    date: Date | None
    status: PlaylistStatus
    created_at: datetime
    updated_at: datetime | None
    archived_at: datetime | None
    items: list[PlaylistItemResponse] = []


class PlaylistListResponse(BaseModel):
    items: list[PlaylistResponse]
    offset: int
    limit: int
    total: int


# ── Playlist Items ────────────────────────────────────────────────────────────


class PlaylistItemAdd(BaseModel):
    version_id: uuid.UUID


class PlaylistItemReview(BaseModel):
    review_status: ReviewStatus
    reviewer_notes: str | None = None
    propagate_to_version: bool = False


class ReorderEntry(BaseModel):
    item_id: uuid.UUID
    order: int


class PlaylistItemsReorder(BaseModel):
    items: list[ReorderEntry]

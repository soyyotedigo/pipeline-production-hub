from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.note import NoteEntityType


class NoteCreate(BaseModel):
    project_id: uuid.UUID
    entity_type: NoteEntityType
    entity_id: uuid.UUID
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1)
    is_client_visible: bool = False


class EntityNoteCreate(BaseModel):
    """For POST /shots|assets|pipeline-tasks/{id}/notes — entity_type/entity_id from URL."""

    project_id: uuid.UUID
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1)
    is_client_visible: bool = False


class ProjectNoteCreate(BaseModel):
    """For POST /projects/{id}/notes — all context from URL."""

    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=1)
    is_client_visible: bool = False


class NoteReplyCreate(BaseModel):
    body: str = Field(min_length=1)
    is_client_visible: bool = False


class NoteUpdate(BaseModel):
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, min_length=1)
    is_client_visible: bool | None = None


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    entity_type: NoteEntityType
    entity_id: uuid.UUID
    author_id: uuid.UUID
    subject: str | None
    body: str
    parent_note_id: uuid.UUID | None
    is_client_visible: bool
    created_at: datetime
    updated_at: datetime | None
    archived_at: datetime | None


class NoteThreadResponse(NoteResponse):
    replies: list[NoteResponse] = []


class NoteListResponse(BaseModel):
    items: list[NoteThreadResponse]
    offset: int
    limit: int
    total: int

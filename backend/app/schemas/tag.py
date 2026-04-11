from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.tag import TagEntityType


class TagCreate(BaseModel):
    name: str
    color: str | None = None
    project_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return v.strip().lower()


class ProjectTagCreate(BaseModel):
    """For POST /projects/{id}/tags — project_id comes from URL."""

    name: str
    color: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return v.strip().lower()


class TagUpdate(BaseModel):
    name: str | None = None
    color: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str | None) -> str | None:
        return v.strip().lower() if v is not None else v


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID | None
    name: str
    color: str | None
    created_at: datetime


class EntityTagCreate(BaseModel):
    tag_id: uuid.UUID


class EntityTagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tag_id: uuid.UUID
    entity_type: TagEntityType
    entity_id: uuid.UUID
    created_at: datetime

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, HttpUrl


class WebhookEventType(str, Enum):
    status_changed = "status.changed"
    file_uploaded = "file.uploaded"
    assignment_changed = "assignment.changed"


class WebhookCreateRequest(BaseModel):
    project_id: uuid.UUID
    url: HttpUrl
    events: list[WebhookEventType]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "11111111-1111-1111-1111-111111111111",
                "url": "https://hooks.example.com/vfxhub",
                "events": ["status.changed", "file.uploaded"],
            }
        }
    )


class WebhookProjectCreateRequest(BaseModel):
    """WebhookCreateRequest without project_id — used for project-scoped route."""

    url: HttpUrl
    events: list[WebhookEventType]


class WebhookUpdateRequest(BaseModel):
    url: HttpUrl | None = None
    events: list[WebhookEventType] | None = None


class WebhookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    url: str
    events: list[str]
    is_active: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class WebhookCreateResponse(WebhookResponse):
    signing_secret: str


class WebhookListResponse(BaseModel):
    items: list[WebhookResponse]
    offset: int
    limit: int
    total: int

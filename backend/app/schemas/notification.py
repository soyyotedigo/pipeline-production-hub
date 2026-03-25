from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.notification import NotificationEntityType, NotificationEventType


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    event_type: NotificationEventType
    entity_type: NotificationEntityType
    entity_id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    body: str | None
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    offset: int
    limit: int


class UnreadCountResponse(BaseModel):
    count: int

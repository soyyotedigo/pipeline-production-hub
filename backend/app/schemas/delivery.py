from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.delivery import DeliveryStatus


class DeliveryCreate(BaseModel):
    name: str
    delivery_date: date | None = None
    recipient: str | None = None
    notes: str | None = None


class DeliveryUpdate(BaseModel):
    name: str | None = None
    delivery_date: date | None = None
    recipient: str | None = None
    notes: str | None = None


class DeliveryStatusUpdate(BaseModel):
    status: DeliveryStatus


class DeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    delivery_date: date | None
    recipient: str | None
    notes: str | None
    status: DeliveryStatus
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None


class DeliveryItemCreate(BaseModel):
    version_id: uuid.UUID
    notes: str | None = None


class DeliveryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    delivery_id: uuid.UUID
    version_id: uuid.UUID
    shot_id: uuid.UUID | None
    notes: str | None
    created_at: datetime

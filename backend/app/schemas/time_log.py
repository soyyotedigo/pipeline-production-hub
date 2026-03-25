from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class TimeLogCreate(BaseModel):
    project_id: uuid.UUID
    pipeline_task_id: uuid.UUID | None = None
    date: date_type
    duration_minutes: int
    description: str | None = None

    @field_validator("duration_minutes")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v <= 0 or v > 1440:
            raise ValueError("duration_minutes must be between 1 and 1440")
        return v

    @field_validator("date")
    @classmethod
    def validate_date_not_future(cls, v: date_type) -> date_type:
        from datetime import date as date_type

        if v > date_type.today():
            raise ValueError("date cannot be in the future")
        return v


class TimeLogUpdate(BaseModel):
    date: date_type | None = None
    duration_minutes: int | None = None
    description: str | None = None

    @field_validator("duration_minutes")
    @classmethod
    def validate_duration(cls, v: int | None) -> int | None:
        if v is not None and (v <= 0 or v > 1440):
            raise ValueError("duration_minutes must be between 1 and 1440")
        return v

    @field_validator("date")
    @classmethod
    def validate_date_not_future(cls, v: date_type | None) -> date_type | None:
        from datetime import date as date_type

        if v is not None and v > date_type.today():
            raise ValueError("date cannot be in the future")
        return v


class TimeLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    pipeline_task_id: uuid.UUID | None
    user_id: uuid.UUID
    date: date_type
    duration_minutes: int
    description: str | None
    created_at: datetime
    updated_at: datetime | None


class UserTimeSummary(BaseModel):
    user_id: uuid.UUID
    minutes: int
    days: float


class ProjectTimeLogSummary(BaseModel):
    total_minutes: int
    total_days: float
    by_user: list[UserTimeSummary]
    bid_vs_actual: dict[str, object] | None = None

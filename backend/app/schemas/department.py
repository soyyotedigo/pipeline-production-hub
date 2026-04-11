from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=50)
    color: str | None = Field(default=None, max_length=7)
    description: str | None = None

    @field_validator("code")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.upper()

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        if v is not None and (len(v) != 7 or not v.startswith("#")):
            raise ValueError("color must be a 7-character hex string like #RRGGBB")
        return v


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    color: str | None = Field(default=None, max_length=7)
    description: str | None = None

    @field_validator("code")
    @classmethod
    def uppercase_code(cls, v: str | None) -> str | None:
        if v is not None:
            return v.upper()
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        if v is not None and (len(v) != 7 or not v.startswith("#")):
            raise ValueError("color must be a 7-character hex string like #RRGGBB")
        return v


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    color: str | None
    description: str | None
    created_at: datetime
    archived_at: datetime | None


class UserDepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    department_id: uuid.UUID
    created_at: datetime


class DepartmentListResponse(BaseModel):
    items: list[DepartmentResponse]
    offset: int
    limit: int
    total: int


class AddMemberRequest(BaseModel):
    user_id: uuid.UUID


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    first_name: str | None
    last_name: str | None
    display_name: str | None
    avatar_url: str | None
    is_active: bool

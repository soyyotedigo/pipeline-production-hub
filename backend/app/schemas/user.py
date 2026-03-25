from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_active: bool
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    department: str | None = None
    timezone: str | None = None
    phone: str | None = None
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=255)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    display_name: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=30)


class UserUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    display_name: str | None = Field(default=None, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=500)
    department: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=30)


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    offset: int
    limit: int


class AssignRoleRequest(BaseModel):
    role_name: str = Field(description="Role name: admin, supervisor, lead, artist, worker, client")
    project_id: uuid.UUID | None = Field(
        default=None,
        description="Project scope. Null = global role.",
    )


class UserRoleResponse(BaseModel):
    role_name: str
    project_id: uuid.UUID | None = None

from __future__ import annotations

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class PaginationMeta(BaseModel):
    offset: int
    limit: int
    total: int

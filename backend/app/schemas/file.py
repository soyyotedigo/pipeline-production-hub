from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import FileStatus, FileType


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    original_name: str
    version: int
    storage_path: str
    size_bytes: int
    checksum_sha256: str
    mime_type: str
    uploaded_by: uuid.UUID | None
    shot_id: uuid.UUID | None
    asset_id: uuid.UUID | None
    pipeline_task_id: uuid.UUID | None = None
    file_type: FileType | None = None
    file_status: FileStatus = FileStatus.wip
    comment: str | None = None
    metadata_json: dict[str, object]
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "77777777-7777-7777-7777-777777777777",
                "name": "comp_final.exr",
                "original_name": "comp_final.exr",
                "version": 2,
                "storage_path": "DEMO/shot/SH010/v002/comp_final.exr",
                "size_bytes": 10485760,
                "checksum_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                "mime_type": "image/x-exr",
                "uploaded_by": "44444444-4444-4444-4444-444444444444",
                "shot_id": "33333333-3333-3333-3333-333333333333",
                "asset_id": None,
                "metadata_json": {"source": "nuke"},
                "created_at": "2026-03-08T20:10:00Z",
            }
        },
    )


class FileUpdate(BaseModel):
    original_name: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=255)
    comment: str | None = None
    file_type: FileType | None = None
    file_status: FileStatus | None = None


class FileListResponse(BaseModel):
    items: list[FileResponse]
    offset: int
    limit: int
    total: int


class FileVersionsResponse(BaseModel):
    file_id: uuid.UUID
    items: list[FileResponse]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_id": "77777777-7777-7777-7777-777777777777",
                "items": [],
            }
        }
    )


class PresignedUrlResponse(BaseModel):
    url: str
    expires_in: int
    storage_path: str

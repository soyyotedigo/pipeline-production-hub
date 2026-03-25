from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import EpisodeStatus, ProjectStatus, ProjectType, SequenceScopeType, SequenceStatus


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255, description="Human-readable project name.")
    code: str | None = Field(
        default=None,
        max_length=64,
        description="Unique production code. Auto-generated from name if omitted.",
    )
    client: str | None = Field(default=None, max_length=255, description="Client/studio name.")
    project_type: ProjectType | None = None
    description: str | None = Field(default=None, max_length=2000, description="Project notes.")
    naming_rules: dict[str, object] | None = Field(
        default=None,
        description=(
            "Override code-generation patterns. Keys: episode, sequence, shot, asset. "
            'Example: {"episode": "EP{production_number:03d}", "sequence": "SQ{production_number:04d}"}'
        ),
    )
    path_templates: dict[str, object] | None = Field(
        default=None,
        description=(
            "Override filesystem path templates for this project. "
            "When set, PathTemplateService uses these instead of the built-in templates."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Demo Project",
                "code": "",
                "client": "Internal",
                "project_type": "series",
                "description": "Pilot season project.",
            }
        }
    )

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) < 2:
            raise ValueError("Project code must be at least 2 characters")
        return normalized


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    client: str | None = Field(default=None, max_length=255)
    project_type: ProjectType | None = None
    status: ProjectStatus | None = None
    description: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    fps: float | None = Field(default=None, gt=0)
    resolution_width: int | None = Field(default=None, gt=0)
    resolution_height: int | None = Field(default=None, gt=0)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    color_space: str | None = Field(default=None, max_length=50)
    naming_rules: dict[str, object] | None = None
    path_templates: dict[str, object] | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    client: str | None
    project_type: ProjectType | None
    status: ProjectStatus
    description: str | None
    start_date: date | None = None
    end_date: date | None = None
    fps: float | None = None
    resolution_width: int | None = None
    resolution_height: int | None = None
    thumbnail_url: str | None = None
    color_space: str | None = None
    created_by: uuid.UUID | None
    naming_rules: dict[str, object] | None = None
    path_templates: dict[str, object] | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    offset: int
    limit: int
    total: int


class ProjectOverviewResponse(BaseModel):
    project_id: uuid.UUID
    total_shots: int
    total_assets: int
    shot_status_counts: dict[str, int]
    asset_status_counts: dict[str, int]
    completion_percent: float

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "11111111-1111-1111-1111-111111111111",
                "total_shots": 15,
                "total_assets": 8,
                "shot_status_counts": {"in_progress": 7, "review": 5, "approved": 3},
                "asset_status_counts": {"pending": 2, "in_progress": 4, "approved": 2},
                "completion_percent": 26.09,
            }
        }
    )


class ProjectReportActivityItem(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    old_status: str | None
    new_status: str
    changed_by: uuid.UUID | None
    changed_at: datetime
    comment: str | None


class ProjectReportResponse(BaseModel):
    project_id: uuid.UUID
    total_shots: int
    total_assets: int
    shot_status_counts: dict[str, int]
    asset_status_counts: dict[str, int]
    completion_percent: float
    uploaded_files_total: int
    storage_used_bytes: int
    recent_activity: list[ProjectReportActivityItem]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "11111111-1111-1111-1111-111111111111",
                "total_shots": 15,
                "total_assets": 8,
                "shot_status_counts": {"review": 5, "approved": 3},
                "asset_status_counts": {"in_progress": 4, "approved": 2},
                "completion_percent": 21.74,
                "uploaded_files_total": 42,
                "storage_used_bytes": 178257920,
                "recent_activity": [
                    {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "entity_type": "shot",
                        "entity_id": "33333333-3333-3333-3333-333333333333",
                        "old_status": "in_progress",
                        "new_status": "review",
                        "changed_by": "44444444-4444-4444-4444-444444444444",
                        "changed_at": "2026-03-08T20:10:00Z",
                        "comment": "Ready for sup review",
                    }
                ],
            }
        }
    )


class ProjectExportAcceptedResponse(BaseModel):
    task_id: uuid.UUID
    status: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "status": "pending",
            }
        }
    )


class EpisodeCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    production_number: int | None = Field(
        default=None,
        ge=1,
        description="Real editorial episode number. Code is auto-generated from this via the project's naming_rules.",
    )
    code: str | None = Field(
        default=None,
        min_length=2,
        max_length=64,
        description="Explicit code. Ignored when production_number is provided.",
    )
    status: EpisodeStatus = EpisodeStatus.active
    description: str | None = Field(default=None, max_length=2000)
    order: int | None = None


class EpisodeUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    # code is intentionally excluded — immutable once set
    status: EpisodeStatus | None = None
    description: str | None = Field(default=None, max_length=2000)
    order: int | None = None


class EpisodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    code: str
    production_number: int | None = None
    status: EpisodeStatus
    description: str | None = None
    order: int | None = None
    created_at: datetime
    updated_at: datetime | None = None
    archived_at: datetime | None


class EpisodeListResponse(BaseModel):
    items: list[EpisodeResponse]
    offset: int
    limit: int
    total: int


class SequenceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    production_number: int | None = Field(
        default=None,
        ge=1,
        description="Real editorial sequence number. Code is auto-generated from this via the project's naming_rules.",
    )
    code: str | None = Field(
        default=None,
        min_length=2,
        max_length=64,
        description="Explicit code. Ignored when production_number is provided.",
    )
    episode_id: uuid.UUID | None = None
    scope_type: SequenceScopeType = SequenceScopeType.sequence
    status: SequenceStatus = SequenceStatus.active
    description: str | None = Field(default=None, max_length=2000)
    order: int | None = None


class SequenceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    # code is intentionally excluded — immutable once set
    episode_id: uuid.UUID | None = None
    scope_type: SequenceScopeType | None = None
    status: SequenceStatus | None = None
    description: str | None = Field(default=None, max_length=2000)
    order: int | None = None


class SequenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    episode_id: uuid.UUID | None
    name: str
    code: str
    production_number: int | None = None
    scope_type: SequenceScopeType
    status: SequenceStatus
    description: str | None = None
    order: int | None = None
    created_at: datetime
    updated_at: datetime | None = None
    archived_at: datetime | None


class SequenceListResponse(BaseModel):
    items: list[SequenceResponse]
    offset: int
    limit: int
    total: int


class ScaffoldRequest(BaseModel):
    root: str | None = Field(
        default=None,
        description=(
            "Root directory where the project tree will be created. "
            "Defaults to the LOCAL_STORAGE_ROOT setting. Example: 'E:/projects'."
        ),
    )


class ScaffoldResponse(BaseModel):
    root: str
    project_code: str
    created_dirs: list[str]
    total: int

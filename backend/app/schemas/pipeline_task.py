from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.pipeline_task import PipelineStepAppliesTo, PipelineStepType, PipelineTaskStatus

# ── Template Steps ───────────────────────────────────────────────────────────


class PipelineTemplateStepCreate(BaseModel):
    step_name: str = Field(min_length=1, max_length=255)
    step_type: PipelineStepType
    order: int = Field(ge=1)
    applies_to: PipelineStepAppliesTo = PipelineStepAppliesTo.both


class PipelineTemplateStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_id: uuid.UUID
    step_name: str
    step_type: PipelineStepType
    order: int
    applies_to: PipelineStepAppliesTo
    created_at: datetime


# ── Templates ────────────────────────────────────────────────────────────────


class PipelineTemplateCreateRequest(BaseModel):
    project_type: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    steps: list[PipelineTemplateStepCreate] = Field(min_length=1)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_type": "film",
                "name": "Film VFX Pipeline",
                "description": "Standard film VFX pipeline",
                "steps": [
                    {
                        "step_name": "Animation",
                        "step_type": "animation",
                        "order": 1,
                        "applies_to": "shot",
                    },
                    {
                        "step_name": "Lighting",
                        "step_type": "lighting",
                        "order": 2,
                        "applies_to": "shot",
                    },
                    {
                        "step_name": "Compositing",
                        "step_type": "compositing",
                        "order": 3,
                        "applies_to": "shot",
                    },
                ],
            }
        }
    )


class PipelineTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class PipelineTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_type: str
    name: str
    description: str | None
    created_at: datetime
    archived_at: datetime | None
    steps: list[PipelineTemplateStepResponse] = []


class PipelineTemplateListResponse(BaseModel):
    items: list[PipelineTemplateResponse]
    offset: int
    limit: int
    total: int


# ── Pipeline Tasks ───────────────────────────────────────────────────────────


class PipelineTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shot_id: uuid.UUID | None
    asset_id: uuid.UUID | None
    step_name: str
    step_type: PipelineStepType
    order: int
    status: PipelineTaskStatus
    assigned_to: uuid.UUID | None
    due_date: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class PipelineTaskListResponse(BaseModel):
    items: list[PipelineTaskResponse]
    offset: int
    limit: int
    total: int


class PipelineTaskCreateRequest(BaseModel):
    step_name: str = Field(min_length=1, max_length=255)
    step_type: PipelineStepType
    order: int = Field(ge=1)
    status: PipelineTaskStatus = PipelineTaskStatus.pending
    assigned_to: uuid.UUID | None = None
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)


class PipelineTaskUpdateRequest(BaseModel):
    assigned_to: uuid.UUID | None = None
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)


class PipelineTaskStatusUpdateRequest(BaseModel):
    status: PipelineTaskStatus
    comment: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(
        json_schema_extra={"example": {"status": "in_progress", "comment": "Starting work"}}
    )


class PipelineTaskStatusUpdateResponse(BaseModel):
    id: uuid.UUID
    old_status: PipelineTaskStatus
    new_status: PipelineTaskStatus
    comment: str | None = None
    changed_at: datetime


class ApplyTemplateRequest(BaseModel):
    entity_type: str = Field(description="'shot' or 'asset'")
    entity_id: uuid.UUID


class ApplyTemplateResponse(BaseModel):
    template_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    tasks_created: int
    tasks: list[PipelineTaskResponse]

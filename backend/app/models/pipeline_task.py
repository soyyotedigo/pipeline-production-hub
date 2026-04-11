import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PipelineStepType(enum.Enum):
    # Shot steps
    layout = "layout"
    animation = "animation"
    fx = "fx"
    lighting = "lighting"
    compositing = "compositing"
    roto = "roto"
    paint = "paint"
    matchmove = "matchmove"
    prep = "prep"
    matte_painting = "matte_painting"
    cfx = "cfx"
    editorial = "editorial"
    rendering = "rendering"
    # Asset steps
    modeling = "modeling"
    rigging = "rigging"
    shading = "shading"
    groom = "groom"
    lookdev = "lookdev"
    texture = "texture"


class PipelineStepAppliesTo(enum.Enum):
    shot = "shot"
    asset = "asset"
    both = "both"


class PipelineTaskStatus(enum.Enum):
    blocked = "blocked"
    pending = "pending"
    in_progress = "in_progress"
    review = "review"
    revision = "revision"
    approved = "approved"


class PipelineTemplate(Base):
    __tablename__ = "pipeline_templates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    project_type: Mapped[str] = mapped_column(
        Enum(
            "film",
            "series",
            "commercial",
            "game",
            "other",
            name="projecttype",
            create_type=False,
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    def __repr__(self) -> str:
        return f"<PipelineTemplate id={self.id} name={self.name!r}>"


class PipelineTemplateStep(Base):
    __tablename__ = "pipeline_template_steps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("pipeline_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_name: Mapped[str] = mapped_column(String(255), nullable=False)
    step_type: Mapped[PipelineStepType] = mapped_column(Enum(PipelineStepType), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    applies_to: Mapped[PipelineStepAppliesTo] = mapped_column(
        Enum(PipelineStepAppliesTo),
        nullable=False,
        default=PipelineStepAppliesTo.both,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<PipelineTemplateStep id={self.id} step={self.step_name!r} order={self.order}>"


class PipelineTask(Base):
    __tablename__ = "pipeline_tasks"
    __table_args__ = (
        CheckConstraint(
            "(shot_id IS NOT NULL AND asset_id IS NULL) OR (shot_id IS NULL AND asset_id IS NOT NULL)",
            name="ck_pipeline_tasks_one_parent",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    shot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("shots.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    step_name: Mapped[str] = mapped_column(String(255), nullable=False)
    step_type: Mapped[PipelineStepType] = mapped_column(Enum(PipelineStepType), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PipelineTaskStatus] = mapped_column(
        Enum(PipelineTaskStatus),
        nullable=False,
        default=PipelineTaskStatus.blocked,
        server_default=PipelineTaskStatus.blocked.value,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    def __repr__(self) -> str:
        return f"<PipelineTask id={self.id} step={self.step_name!r} status={self.status.value}>"

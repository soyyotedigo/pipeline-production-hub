import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ShotStatus(enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    review = "review"
    revision = "revision"
    approved = "approved"
    delivered = "delivered"
    on_hold = "on_hold"
    omitted = "omitted"
    final = "final"


class Priority(enum.Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class Difficulty(enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"
    hero = "hero"


class Shot(Base):
    __tablename__ = "shots"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_shot_project_code"),
        CheckConstraint(
            "frame_start IS NULL OR frame_end IS NULL OR frame_end >= frame_start",
            name="ck_shots_frame_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("sequences.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ShotStatus] = mapped_column(
        Enum(ShotStatus),
        nullable=False,
        default=ShotStatus.pending,
        server_default=ShotStatus.pending.value,
    )
    frame_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority),
        nullable=False,
        default=Priority.normal,
        server_default=Priority.normal.value,
    )
    difficulty: Mapped[Difficulty | None] = mapped_column(Enum(Difficulty), nullable=True)
    handle_head: Mapped[int | None] = mapped_column(Integer, nullable=True)
    handle_tail: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cut_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cut_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bid_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    def __repr__(self) -> str:
        return f"<Shot id={self.id} project={self.project_id} code={self.code!r}>"

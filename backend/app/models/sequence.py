import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
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


class SequenceScopeType(enum.Enum):
    sequence = "sequence"
    spot = "spot"
    level = "level"


class SequenceStatus(enum.Enum):
    active = "active"
    in_progress = "in_progress"
    completed = "completed"
    on_hold = "on_hold"
    omitted = "omitted"


class Sequence(Base):
    __tablename__ = "sequences"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_sequence_project_code"),
        UniqueConstraint(
            "project_id",
            "episode_id",
            "production_number",
            name="uq_sequence_project_episode_production_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("episodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[SequenceScopeType] = mapped_column(
        Enum(SequenceScopeType),
        nullable=False,
        default=SequenceScopeType.sequence,
        server_default=SequenceScopeType.sequence.value,
    )
    status: Mapped[SequenceStatus] = mapped_column(
        Enum(SequenceStatus),
        nullable=False,
        default=SequenceStatus.active,
        server_default=SequenceStatus.active.value,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    production_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    order: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
        return f"<Sequence id={self.id} project={self.project_id} code={self.code!r}>"

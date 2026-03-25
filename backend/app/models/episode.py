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


class EpisodeStatus(enum.Enum):
    active = "active"
    in_progress = "in_progress"
    completed = "completed"
    on_hold = "on_hold"
    omitted = "omitted"


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_episode_project_code"),
        UniqueConstraint(
            "project_id", "production_number", name="uq_episode_project_production_number"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[EpisodeStatus] = mapped_column(
        Enum(EpisodeStatus),
        nullable=False,
        default=EpisodeStatus.active,
        server_default=EpisodeStatus.active.value,
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
        return f"<Episode id={self.id} project={self.project_id} code={self.code!r}>"

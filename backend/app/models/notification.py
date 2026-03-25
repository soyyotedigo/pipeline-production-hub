import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationEventType(str, enum.Enum):
    task_assigned = "task_assigned"
    task_status_changed = "task_status_changed"
    note_created = "note_created"
    note_reply = "note_reply"
    version_submitted = "version_submitted"
    version_reviewed = "version_reviewed"
    status_changed = "status_changed"
    mention = "mention"


class NotificationEntityType(str, enum.Enum):
    project = "project"
    shot = "shot"
    asset = "asset"
    pipeline_task = "pipeline_task"
    note = "note"
    version = "version"
    playlist = "playlist"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[NotificationEventType] = mapped_column(
        Enum(NotificationEventType),
        nullable=False,
    )
    entity_type: Mapped[NotificationEntityType] = mapped_column(
        Enum(NotificationEntityType),
        nullable=False,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Notification id={self.id} user={self.user_id} event={self.event_type.value}>"

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
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


class FileType(enum.Enum):
    source_scene = "source_scene"
    render = "render"
    plate = "plate"
    reference = "reference"
    delivery = "delivery"
    thumbnail = "thumbnail"


class FileStatus(enum.Enum):
    wip = "wip"
    published = "published"
    approved = "approved"
    deprecated = "deprecated"


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint(
            "shot_id", "original_name", "version", name="uq_files_shot_original_version"
        ),
        UniqueConstraint(
            "asset_id", "original_name", "version", name="uq_files_asset_original_version"
        ),
        CheckConstraint(
            "((shot_id IS NOT NULL)::int + (asset_id IS NOT NULL)::int) = 1",
            name="ck_files_exactly_one_parent",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_files_size_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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
    pipeline_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("pipeline_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    file_type: Mapped[FileType | None] = mapped_column(Enum(FileType), nullable=True)
    file_status: Mapped[FileStatus] = mapped_column(
        Enum(FileStatus),
        nullable=False,
        default=FileStatus.wip,
        server_default=FileStatus.wip.value,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<File id={self.id} original_name={self.original_name!r} version={self.version}>"

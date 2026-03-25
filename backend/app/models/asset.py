import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.shot import Priority


class AssetType(enum.Enum):
    character = "character"
    prop = "prop"
    environment = "environment"
    fx = "fx"
    vehicle = "vehicle"
    set_piece = "set_piece"
    matte_painting = "matte_painting"
    texture = "texture"
    hdri = "hdri"
    camera = "camera"
    assembly = "assembly"


class AssetStatus(enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    review = "review"
    revision = "revision"
    approved = "approved"
    delivered = "delivered"
    on_hold = "on_hold"
    omitted = "omitted"
    final = "final"


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_asset_project_name"),
        UniqueConstraint("project_id", "code", name="uq_asset_project_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    asset_type: Mapped[AssetType] = mapped_column(Enum(AssetType), nullable=False)
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus),
        nullable=False,
        default=AssetStatus.pending,
        server_default=AssetStatus.pending.value,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="priority", create_type=False),
        nullable=False,
        default=Priority.normal,
        server_default=Priority.normal.value,
    )
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
        return f"<Asset id={self.id} project={self.project_id} name={self.name!r}>"

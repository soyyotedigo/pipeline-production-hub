import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LinkType(enum.Enum):
    uses = "uses"
    references = "references"
    instance_of = "instance_of"


class ShotAssetLink(Base):
    __tablename__ = "shot_asset_links"
    __table_args__ = (UniqueConstraint("shot_id", "asset_id", name="uq_shot_asset_link"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4, index=True)
    shot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("shots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    link_type: Mapped[LinkType] = mapped_column(
        Enum(LinkType),
        nullable=False,
        default=LinkType.uses,
        server_default=LinkType.uses.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ShotAssetLink shot={self.shot_id} asset={self.asset_id} type={self.link_type.value}>"
        )

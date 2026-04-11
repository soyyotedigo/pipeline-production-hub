import enum

from sqlalchemy import Enum, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RoleName(enum.Enum):
    admin = "admin"
    supervisor = "supervisor"
    lead = "lead"
    artist = "artist"
    worker = "worker"
    client = "client"


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[RoleName] = mapped_column(Enum(RoleName), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name.value!r}>"

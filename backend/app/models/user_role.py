import uuid

from sqlalchemy import ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(Base):
    """
    Associates a user with a role, optionally scoped to a project.
    - project_id = NULL  → global role (e.g. admin across all projects)
    - project_id = <id>  → role only within that project
    """

    __tablename__ = "user_roles"
    __table_args__ = (
        # prevent assigning the same role to a user twice in the same scope
        UniqueConstraint("user_id", "role_id", "project_id", name="uq_user_role_project"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        scope = f"project={self.project_id}" if self.project_id else "global"
        return f"<UserRole user={self.user_id} role={self.role_id} {scope}>"

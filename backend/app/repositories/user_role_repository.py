import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role, RoleName, UserRole


class UserRoleRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def has_any_role_in_any_scope(
        self,
        user_id: uuid.UUID,
        role_names: set[RoleName],
    ) -> bool:
        statement = (
            select(UserRole.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                UserRole.user_id == user_id,
                Role.name.in_(role_names),
            )
            .limit(1)
        )
        result = await self.db.execute(statement)
        return result.scalar_one_or_none() is not None

    async def has_any_role(
        self,
        user_id: uuid.UUID,
        role_names: set[RoleName],
        project_id: uuid.UUID,
    ) -> bool:
        statement = (
            select(UserRole.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                UserRole.user_id == user_id,
                Role.name.in_(role_names),
                or_(UserRole.project_id == project_id, UserRole.project_id.is_(None)),
            )
            .limit(1)
        )
        result = await self.db.execute(statement)
        return result.scalar_one_or_none() is not None

    async def has_global_any_role(self, user_id: uuid.UUID, role_names: set[RoleName]) -> bool:
        statement = (
            select(UserRole.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                UserRole.user_id == user_id,
                Role.name.in_(role_names),
                UserRole.project_id.is_(None),
            )
            .limit(1)
        )
        result = await self.db.execute(statement)
        return result.scalar_one_or_none() is not None

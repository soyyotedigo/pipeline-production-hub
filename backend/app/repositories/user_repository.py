import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role, RoleName, User, UserRole


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        statement = select(User).where(User.id == user_id)
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def list_users(
        self,
        offset: int,
        limit: int,
        is_active: bool | None = None,
    ) -> tuple[list[User], int]:
        query = select(User)
        count_query = select(func.count()).select_from(User)

        if is_active is not None:
            query = query.where(User.is_active == is_active)
            count_query = count_query.where(User.is_active == is_active)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(User.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def create(
        self,
        email: str,
        hashed_password: str,
        first_name: str | None = None,
        last_name: str | None = None,
        display_name: str | None = None,
        department: str | None = None,
        timezone: str | None = None,
        phone: str | None = None,
    ) -> User:
        user = User(
            email=email,
            hashed_password=hashed_password,
            first_name=first_name,
            last_name=last_name,
            display_name=display_name,
            department=department,
            timezone=timezone,
            phone=phone,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update(self, user: User, **fields: object) -> User:
        for key, value in fields.items():
            setattr(user, key, value)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def list_user_roles(self, user_id: uuid.UUID) -> list[tuple[str, uuid.UUID | None]]:
        statement = (
            select(Role.name, UserRole.project_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        result = await self.db.execute(statement)
        rows = result.all()
        return [(role_name.value, project_id) for role_name, project_id in rows]

    async def get_role_by_name(self, role_name: RoleName) -> Role | None:
        result = await self.db.execute(select(Role).where(Role.name == role_name))
        return result.scalar_one_or_none()

    async def assign_role(
        self,
        user_id: uuid.UUID,
        role_id: int,
        project_id: uuid.UUID | None,
    ) -> UserRole:
        user_role = UserRole(user_id=user_id, role_id=role_id, project_id=project_id)
        self.db.add(user_role)
        await self.db.flush()
        return user_role

    async def remove_role(
        self,
        user_id: uuid.UUID,
        role_id: int,
        project_id: uuid.UUID | None,
    ) -> bool:
        statement = select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
            UserRole.project_id == project_id,
        )
        result = await self.db.execute(statement)
        user_role = result.scalar_one_or_none()
        if user_role is None:
            return False
        await self.db.delete(user_role)
        await self.db.flush()
        return True

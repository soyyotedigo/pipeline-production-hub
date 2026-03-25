import builtins
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department, UserDepartment
from app.models.user import User


class DepartmentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(
        self, dept_id: uuid.UUID, include_archived: bool = False
    ) -> Department | None:
        statement = select(Department).where(Department.id == dept_id)
        if not include_archived:
            statement = statement.where(Department.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Department | None:
        result = await self.db.execute(select(Department).where(Department.name == name))
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Department | None:
        result = await self.db.execute(select(Department).where(Department.code == code))
        return result.scalar_one_or_none()

    async def create(
        self,
        name: str,
        code: str,
        color: str | None = None,
        description: str | None = None,
    ) -> Department:
        dept = Department(name=name, code=code, color=color, description=description)
        self.db.add(dept)
        await self.db.flush()
        await self.db.refresh(dept)
        return dept

    async def update(self, dept: Department, **kwargs: object) -> Department:
        for key, value in kwargs.items():
            setattr(dept, key, value)
        self.db.add(dept)
        await self.db.flush()
        await self.db.refresh(dept)
        return dept

    async def archive(self, dept: Department) -> Department:
        dept.archived_at = datetime.now(timezone.utc)
        self.db.add(dept)
        await self.db.flush()
        await self.db.refresh(dept)
        return dept

    async def delete(self, dept: Department) -> None:
        await self.db.delete(dept)
        await self.db.flush()

    async def list(
        self,
        offset: int,
        limit: int,
        include_archived: bool = False,
    ) -> tuple[builtins.list[Department], int]:
        statement = select(Department)
        count_statement = select(func.count(Department.id))
        if not include_archived:
            statement = statement.where(Department.archived_at.is_(None))
            count_statement = count_statement.where(Department.archived_at.is_(None))
        statement = statement.order_by(Department.name.asc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())
        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

    async def add_member(self, dept_id: uuid.UUID, user_id: uuid.UUID) -> UserDepartment:
        ud = UserDepartment(department_id=dept_id, user_id=user_id)
        self.db.add(ud)
        await self.db.flush()
        await self.db.refresh(ud)
        return ud

    async def get_member_by_id(self, member_id: uuid.UUID) -> UserDepartment | None:
        result = await self.db.execute(select(UserDepartment).where(UserDepartment.id == member_id))
        return result.scalar_one_or_none()

    async def get_member(self, dept_id: uuid.UUID, user_id: uuid.UUID) -> UserDepartment | None:
        result = await self.db.execute(
            select(UserDepartment).where(
                UserDepartment.department_id == dept_id,
                UserDepartment.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def remove_member(self, user_dept: UserDepartment) -> None:
        await self.db.delete(user_dept)
        await self.db.flush()

    async def get_members(self, dept_id: uuid.UUID) -> builtins.list[User]:
        statement = (
            select(User)
            .join(UserDepartment, UserDepartment.user_id == User.id)
            .where(UserDepartment.department_id == dept_id)
            .order_by(User.email.asc())
        )
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def get_user_departments(self, user_id: uuid.UUID) -> builtins.list[Department]:
        statement = (
            select(Department)
            .join(UserDepartment, UserDepartment.department_id == Department.id)
            .where(UserDepartment.user_id == user_id)
            .order_by(Department.name.asc())
        )
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def has_members(self, dept_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(func.count(UserDepartment.id)).where(UserDepartment.department_id == dept_id)
        )
        return int(result.scalar_one()) > 0

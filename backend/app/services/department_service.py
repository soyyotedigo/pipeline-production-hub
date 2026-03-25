import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, UnprocessableError
from app.models.user import User
from app.repositories.department_repository import DepartmentRepository
from app.schemas.department import (
    DepartmentCreate,
    DepartmentListResponse,
    DepartmentResponse,
    DepartmentUpdate,
    UserDepartmentResponse,
    UserResponse,
)


class DepartmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = DepartmentRepository(db)

    async def create_department(self, payload: DepartmentCreate) -> DepartmentResponse:
        if await self.repository.get_by_name(payload.name) is not None:
            raise ConflictError(f"Department with name '{payload.name}' already exists")
        if await self.repository.get_by_code(payload.code) is not None:
            raise ConflictError(f"Department with code '{payload.code}' already exists")

        dept = await self.repository.create(
            name=payload.name,
            code=payload.code,
            color=payload.color,
            description=payload.description,
        )
        await self.db.commit()
        await self.db.refresh(dept)
        return DepartmentResponse.model_validate(dept)

    async def get_department(
        self, dept_id: uuid.UUID, include_archived: bool = True
    ) -> DepartmentResponse:
        dept = await self.repository.get_by_id(dept_id, include_archived=include_archived)
        if dept is None:
            raise NotFoundError("Department not found")
        return DepartmentResponse.model_validate(dept)

    async def list_departments(
        self, offset: int, limit: int, include_archived: bool = False
    ) -> DepartmentListResponse:
        items, total = await self.repository.list(
            offset=offset, limit=limit, include_archived=include_archived
        )
        return DepartmentListResponse(
            items=[DepartmentResponse.model_validate(d) for d in items],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def update_department(
        self, dept_id: uuid.UUID, payload: DepartmentUpdate
    ) -> DepartmentResponse:
        dept = await self.repository.get_by_id(dept_id, include_archived=True)
        if dept is None:
            raise NotFoundError("Department not found")

        update_data: dict[str, object] = {}

        if payload.name is not None:
            existing = await self.repository.get_by_name(payload.name)
            if existing is not None and existing.id != dept_id:
                raise ConflictError(f"Department with name '{payload.name}' already exists")
            update_data["name"] = payload.name

        if payload.code is not None:
            existing = await self.repository.get_by_code(payload.code)
            if existing is not None and existing.id != dept_id:
                raise ConflictError(f"Department with code '{payload.code}' already exists")
            update_data["code"] = payload.code

        if payload.color is not None:
            update_data["color"] = payload.color

        if payload.description is not None:
            update_data["description"] = payload.description

        # Unarchive if any field is updated
        if update_data and dept.archived_at is not None:
            update_data["archived_at"] = None

        if update_data:
            dept = await self.repository.update(dept, **update_data)

        await self.db.commit()
        await self.db.refresh(dept)
        return DepartmentResponse.model_validate(dept)

    async def archive_department(self, dept_id: uuid.UUID) -> DepartmentResponse:
        dept = await self.repository.get_by_id(dept_id, include_archived=True)
        if dept is None:
            raise NotFoundError("Department not found")

        dept = await self.repository.archive(dept)
        await self.db.commit()
        return DepartmentResponse.model_validate(dept)

    async def delete_department(self, dept_id: uuid.UUID) -> None:
        dept = await self.repository.get_by_id(dept_id, include_archived=True)
        if dept is None:
            raise NotFoundError("Department not found")

        if await self.repository.has_members(dept_id):
            raise UnprocessableError("Cannot delete a department that still has members")

        await self.repository.delete(dept)
        await self.db.commit()

    async def add_member(self, dept_id: uuid.UUID, user_id: uuid.UUID) -> UserDepartmentResponse:
        dept = await self.repository.get_by_id(dept_id)
        if dept is None:
            raise NotFoundError("Department not found")

        user = await self.db.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found")

        if await self.repository.get_member(dept_id, user_id) is not None:
            raise ConflictError("User is already a member of this department")

        ud = await self.repository.add_member(dept_id=dept_id, user_id=user_id)
        await self.db.commit()
        await self.db.refresh(ud)
        return UserDepartmentResponse.model_validate(ud)

    async def remove_member(self, dept_id: uuid.UUID, user_id: uuid.UUID) -> None:
        dept = await self.repository.get_by_id(dept_id)
        if dept is None:
            raise NotFoundError("Department not found")

        ud = await self.repository.get_member(dept_id, user_id)
        if ud is None:
            raise NotFoundError("User is not a member of this department")

        await self.repository.remove_member(ud)
        await self.db.commit()

    async def remove_member_by_id(self, member_id: uuid.UUID) -> None:
        ud = await self.repository.get_member_by_id(member_id)
        if ud is None:
            raise NotFoundError("Department member not found")
        await self.repository.remove_member(ud)
        await self.db.commit()

    async def get_members(self, dept_id: uuid.UUID) -> list[UserResponse]:
        dept = await self.repository.get_by_id(dept_id)
        if dept is None:
            raise NotFoundError("Department not found")

        users = await self.repository.get_members(dept_id)
        return [UserResponse.model_validate(user) for user in users]

    async def get_user_departments(self, user_id: uuid.UUID) -> list[DepartmentResponse]:
        user = await self.db.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found")

        depts = await self.repository.get_user_departments(user_id)
        return [DepartmentResponse.model_validate(d) for d in depts]

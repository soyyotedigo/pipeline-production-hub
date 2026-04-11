import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password
from app.models import RoleName, User
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    AssignRoleRequest,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserRoleResponse,
    UserUpdate,
)


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = UserRepository(db)

    async def list_users(
        self,
        offset: int,
        limit: int,
        is_active: bool | None,
    ) -> UserListResponse:
        users, total = await self.repo.list_users(offset=offset, limit=limit, is_active=is_active)
        return UserListResponse(
            items=[UserResponse.model_validate(u) for u in users],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def get_user(self, user_id: uuid.UUID) -> UserResponse:
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return UserResponse.model_validate(user)

    async def create_user(self, payload: UserCreate) -> UserResponse:
        existing = await self.repo.get_by_email(payload.email)
        if existing is not None:
            raise ConflictError(f"Email already registered: {payload.email}")

        user = await self.repo.create(
            email=payload.email,
            hashed_password=hash_password(payload.password),
            first_name=payload.first_name,
            last_name=payload.last_name,
            display_name=payload.display_name,
            department=payload.department,
            timezone=payload.timezone,
            phone=payload.phone,
        )
        return UserResponse.model_validate(user)

    async def update_user(
        self,
        user_id: uuid.UUID,
        payload: UserUpdate,
        current_user: User,
    ) -> UserResponse:
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")

        # Only the user themselves or an admin can update
        if current_user.id != user.id:
            from app.repositories.user_role_repository import UserRoleRepository

            is_admin = await UserRoleRepository(self.db).has_global_any_role(
                user_id=current_user.id,
                role_names={RoleName.admin},
            )
            if not is_admin:
                raise ForbiddenError("You can only update your own profile")

        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return UserResponse.model_validate(user)

        updated = await self.repo.update(user, **updates)
        return UserResponse.model_validate(updated)

    async def deactivate_user(self, user_id: uuid.UUID) -> UserResponse:
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        updated = await self.repo.update(user, is_active=False)
        return UserResponse.model_validate(updated)

    async def list_roles(self, user_id: uuid.UUID) -> list[UserRoleResponse]:
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        role_rows = await self.repo.list_user_roles(user_id)
        return [
            UserRoleResponse(role_name=name, project_id=project_id)
            for name, project_id in role_rows
        ]

    async def assign_role(
        self,
        user_id: uuid.UUID,
        payload: AssignRoleRequest,
    ) -> UserRoleResponse:
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")

        try:
            role_name_enum = RoleName(payload.role_name)
        except ValueError as exc:
            from app.core.exceptions import UnprocessableError

            raise UnprocessableError(f"Invalid role name: {payload.role_name}") from exc

        role = await self.repo.get_role_by_name(role_name_enum)
        if role is None:
            raise NotFoundError(f"Role '{payload.role_name}' not found in database")

        try:
            await self.repo.assign_role(
                user_id=user_id,
                role_id=role.id,
                project_id=payload.project_id,
            )
        except Exception as exc:
            raise ConflictError(
                f"User already has role '{payload.role_name}' in this scope"
            ) from exc

        return UserRoleResponse(role_name=payload.role_name, project_id=payload.project_id)

    async def remove_role(
        self,
        user_id: uuid.UUID,
        role_name: str,
        project_id: uuid.UUID | None,
    ) -> None:
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")

        try:
            role_name_enum = RoleName(role_name)
        except ValueError as exc:
            from app.core.exceptions import UnprocessableError

            raise UnprocessableError(f"Invalid role name: {role_name}") from exc

        role = await self.repo.get_role_by_name(role_name_enum)
        if role is None:
            raise NotFoundError(f"Role '{role_name}' not found in database")

        removed = await self.repo.remove_role(
            user_id=user_id,
            role_id=role.id,
            project_id=project_id,
        )
        if not removed:
            raise NotFoundError(f"User does not have role '{role_name}' in this scope")

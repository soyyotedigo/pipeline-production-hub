import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_role
from app.db.session import get_db
from app.models import User
from app.schemas.user import (
    AssignRoleRequest,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserRoleResponse,
    UserUpdate,
)
from app.services.user_service import UserService

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
AdminDep = Annotated[User, Depends(require_role("admin"))]


@router.get(
    "",
    response_model=UserListResponse,
    summary="List Users",
    description="List all users. Requires admin or supervisor role.",
)
async def list_users(
    current_user: Annotated[User, Depends(require_role("supervisor"))],
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = Query(default=None),
) -> UserListResponse:
    return await UserService(db).list_users(offset=offset, limit=limit, is_active=is_active)


@router.post(
    "",
    response_model=UserResponse,
    status_code=201,
    summary="Create User",
    description="Create a new user account. Requires admin role.",
)
async def create_user(
    payload: UserCreate,
    _: AdminDep,
    db: DbDep,
) -> UserResponse:
    return await UserService(db).create_user(payload=payload)


@router.get(
    "/{id}",
    response_model=UserResponse,
    summary="Get User",
    description="Get a user by ID. Requires authentication.",
)
async def get_user(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> UserResponse:
    return await UserService(db).get_user(user_id=id)


@router.patch(
    "/{id}",
    response_model=UserResponse,
    summary="Update User",
    description="Update user profile fields. Users can update their own profile; admins can update any user.",
)
async def update_user(
    id: uuid.UUID,
    payload: UserUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> UserResponse:
    return await UserService(db).update_user(user_id=id, payload=payload, current_user=current_user)


@router.post(
    "/{id}/deactivate",
    response_model=UserResponse,
    summary="Deactivate User",
    description="Deactivate a user account. Requires admin role.",
)
async def deactivate_user(
    id: uuid.UUID,
    _: AdminDep,
    db: DbDep,
) -> UserResponse:
    return await UserService(db).deactivate_user(user_id=id)


@router.get(
    "/{id}/roles",
    response_model=list[UserRoleResponse],
    summary="List User Roles",
    description="List all role assignments for a user.",
)
async def list_user_roles(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> list[UserRoleResponse]:
    return await UserService(db).list_roles(user_id=id)


@router.post(
    "/{id}/roles",
    response_model=UserRoleResponse,
    status_code=201,
    summary="Assign Role",
    description="Assign a role to a user, optionally scoped to a project. Requires admin role.",
)
async def assign_role(
    id: uuid.UUID,
    payload: AssignRoleRequest,
    _: AdminDep,
    db: DbDep,
) -> UserRoleResponse:
    return await UserService(db).assign_role(user_id=id, payload=payload)


@router.delete(
    "/{id}/roles/{role_name}",
    status_code=204,
    summary="Remove Role",
    description="Remove a role from a user. Pass project_id query param for project-scoped roles. Requires admin role.",
)
async def remove_role(
    id: uuid.UUID,
    role_name: str,
    _: AdminDep,
    db: DbDep,
    project_id: uuid.UUID | None = Query(default=None),
) -> None:
    await UserService(db).remove_role(user_id=id, role_name=role_name, project_id=project_id)

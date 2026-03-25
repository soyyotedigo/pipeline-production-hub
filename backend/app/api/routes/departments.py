import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.department import (
    AddMemberRequest,
    DepartmentCreate,
    DepartmentListResponse,
    DepartmentResponse,
    DepartmentUpdate,
    UserDepartmentResponse,
    UserResponse,
)
from app.services.department_service import DepartmentService

router = APIRouter()
users_router = APIRouter()
department_members_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post(
    "",
    response_model=DepartmentResponse,
    status_code=201,
    summary="Create Department",
    description="Create a new department. The code is stored in UPPERCASE.",
)
async def create_department(
    payload: DepartmentCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> DepartmentResponse:
    service = DepartmentService(db)
    return await service.create_department(payload=payload)


@router.get(
    "",
    response_model=DepartmentListResponse,
    summary="List Departments",
    description="List all departments with optional pagination and archived filter.",
)
async def list_departments(
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_archived: bool = Query(default=False),
) -> DepartmentListResponse:
    service = DepartmentService(db)
    return await service.list_departments(
        offset=offset, limit=limit, include_archived=include_archived
    )


@router.get(
    "/{id}",
    response_model=DepartmentResponse,
    summary="Get Department",
    description="Get a department by ID.",
)
async def get_department(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> DepartmentResponse:
    service = DepartmentService(db)
    return await service.get_department(dept_id=id)


@router.patch(
    "/{id}",
    response_model=DepartmentResponse,
    summary="Update Department",
    description="Update department fields. Updating any field also unarchives the department.",
)
async def update_department(
    id: uuid.UUID,
    payload: DepartmentUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> DepartmentResponse:
    service = DepartmentService(db)
    return await service.update_department(dept_id=id, payload=payload)


@router.post(
    "/{id}/archive",
    response_model=DepartmentResponse,
    summary="Archive Department",
    description="Soft-delete a department by setting archived_at.",
)
async def archive_department(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> DepartmentResponse:
    service = DepartmentService(db)
    return await service.archive_department(dept_id=id)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Delete Department",
    description="Hard-delete a department. Fails with 400 if the department still has members.",
)
async def delete_department(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> None:
    service = DepartmentService(db)
    await service.delete_department(dept_id=id)


@router.get(
    "/{id}/members",
    response_model=list[UserResponse],
    summary="Get Department Members",
    description="List all users that belong to a department.",
)
async def get_members(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> list[UserResponse]:
    service = DepartmentService(db)
    users = await service.get_members(dept_id=id)
    return [UserResponse.model_validate(u) for u in users]


@router.post(
    "/{id}/members",
    response_model=UserDepartmentResponse,
    status_code=201,
    summary="Add Department Member",
    description="Add a user to a department.",
)
async def add_member(
    id: uuid.UUID,
    payload: AddMemberRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> UserDepartmentResponse:
    service = DepartmentService(db)
    return await service.add_member(dept_id=id, user_id=payload.user_id)


# ── Users sub-router ──────────────────────────────────────────────────────────


@users_router.get(
    "/{id}/departments",
    response_model=list[DepartmentResponse],
    summary="Get User Departments",
    description="List all departments a user belongs to.",
)
async def get_user_departments(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> list[DepartmentResponse]:
    service = DepartmentService(db)
    return await service.get_user_departments(user_id=id)


@department_members_router.delete("/{id}", status_code=204)
async def remove_department_member(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> Response:
    service = DepartmentService(db)
    await service.remove_member_by_id(member_id=id)
    return Response(status_code=204)

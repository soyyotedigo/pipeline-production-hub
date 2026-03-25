from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.active_users import mark_user_active
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models import Role, RoleName, User, UserRole
from app.repositories.user_repository import UserRepository

DbDep = Annotated[AsyncSession, Depends(get_db)]
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DbDep,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Authentication required")

    payload = decode_token(credentials.credentials)
    token_type = payload.get("typ")
    if token_type != "access":
        raise UnauthorizedError("Invalid access token")

    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise UnauthorizedError("Invalid access token")

    try:
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise UnauthorizedError("Invalid access token") from exc

    user = await UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid access token")

    await mark_user_active(user.id)

    return user


def _normalize_role_name(required_role: RoleName | str) -> RoleName:
    if isinstance(required_role, RoleName):
        return required_role

    try:
        return RoleName(required_role)
    except ValueError as exc:
        raise ValueError(f"Invalid role name: {required_role}") from exc


async def _user_has_role(
    db: AsyncSession,
    user_id: uuid.UUID,
    role_name: RoleName,
    project_id: uuid.UUID | None,
) -> bool:
    statement = (
        select(UserRole.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            and_(
                UserRole.user_id == user_id,
                Role.name == role_name,
                UserRole.project_id == project_id,
            )
        )
        .limit(1)
    )
    result = await db.execute(statement)
    return result.scalar_one_or_none() is not None


def require_role(required_role: RoleName | str) -> object:
    normalized_role = _normalize_role_name(required_role)

    async def dependency(
        current_user: Annotated[User, Depends(get_current_user)],
        db: DbDep,
    ) -> User:
        has_global_role = await _user_has_role(
            db=db,
            user_id=current_user.id,
            role_name=normalized_role,
            project_id=None,
        )
        if not has_global_role:
            raise ForbiddenError(f"Required global role: {normalized_role.value}")

        return current_user

    return dependency


def require_project_role(project_param_name: str, required_role: RoleName | str) -> object:
    normalized_role = _normalize_role_name(required_role)

    async def dependency(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: DbDep,
    ) -> User:
        raw_project_id = request.path_params.get(project_param_name)
        if raw_project_id is None:
            raise ForbiddenError(f"Missing project parameter: {project_param_name}")

        try:
            project_id = uuid.UUID(str(raw_project_id))
        except ValueError as exc:
            raise ForbiddenError(f"Invalid project_id for parameter: {project_param_name}") from exc

        has_project_role = await _user_has_role(
            db=db,
            user_id=current_user.id,
            role_name=normalized_role,
            project_id=project_id,
        )
        if has_project_role:
            return current_user

        has_global_role = await _user_has_role(
            db=db,
            user_id=current_user.id,
            role_name=normalized_role,
            project_id=None,
        )
        if not has_global_role:
            raise ForbiddenError(
                f"Required role '{normalized_role.value}' for project '{project_id}'"
            )

        return current_user

    return dependency

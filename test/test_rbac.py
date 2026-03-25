from __future__ import annotations

import sys
import uuid
from importlib import import_module
from pathlib import Path

import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

dependencies_module = import_module("app.core.dependencies")
exceptions_module = import_module("app.core.exceptions")
security_module = import_module("app.core.security")
role_module = import_module("app.models.role")
project_module = import_module("app.models.project")
user_module = import_module("app.models.user")
user_role_module = import_module("app.models.user_role")

require_project_role = dependencies_module.require_project_role
require_role = dependencies_module.require_role
ForbiddenError = exceptions_module.ForbiddenError
hash_password = security_module.hash_password
Role = role_module.Role
RoleName = role_module.RoleName
Project = project_module.Project
ProjectStatus = project_module.ProjectStatus
User = user_module.User
UserRole = user_role_module.UserRole


def _make_request(path_params: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "path_params": path_params,
    }
    return Request(scope)


async def _create_user(db_session: AsyncSession, email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password("secret123"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _ensure_role(db_session: AsyncSession, role_name: RoleName) -> Role:
    result = await db_session.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()
    if role is not None:
        return role

    role = Role(name=role_name, description=f"{role_name.value} role")
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)
    return role


async def _assign_role(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    role_name: RoleName,
    project_id: uuid.UUID | None,
) -> None:
    role = await _ensure_role(db_session, role_name)
    if project_id is not None:
        result = await db_session.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if project is None:
            project = Project(
                id=project_id,
                name=f"Project {str(project_id)[:8]}",
                code=f"P{str(project_id).replace('-', '')[:10].upper()}",
                status=ProjectStatus.pending,
            )
            db_session.add(project)
            await db_session.flush()

    db_session.add(UserRole(user_id=user_id, role_id=role.id, project_id=project_id))
    await db_session.commit()


@pytest.mark.asyncio
async def test_require_role_passes_for_global_admin(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "admin-global@vfxhub.dev")
    await _assign_role(db_session, user.id, RoleName.admin, None)

    dependency = require_role("admin")
    resolved_user = await dependency(current_user=user, db=db_session)

    assert resolved_user.id == user.id


@pytest.mark.asyncio
async def test_require_role_fails_without_global_admin(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "artist@vfxhub.dev")
    await _assign_role(db_session, user.id, RoleName.artist, None)

    dependency = require_role("admin")
    with pytest.raises(ForbiddenError):
        await dependency(current_user=user, db=db_session)


@pytest.mark.asyncio
async def test_require_role_passes_for_global_supervisor(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "supervisor-global@vfxhub.dev")
    await _assign_role(db_session, user.id, RoleName.supervisor, None)

    dependency = require_role("supervisor")
    resolved_user = await dependency(current_user=user, db=db_session)

    assert resolved_user.id == user.id


@pytest.mark.asyncio
async def test_require_role_fails_without_global_supervisor(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "lead-global@vfxhub.dev")
    await _assign_role(db_session, user.id, RoleName.lead, None)

    dependency = require_role("supervisor")
    with pytest.raises(ForbiddenError):
        await dependency(current_user=user, db=db_session)


@pytest.mark.asyncio
async def test_require_project_role_passes_for_matching_project_role(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "lead-a@vfxhub.dev")
    project_a = uuid.uuid4()
    await _assign_role(db_session, user.id, RoleName.lead, project_a)

    dependency = require_project_role("project_id", "lead")
    request = _make_request({"project_id": str(project_a)})
    resolved_user = await dependency(request=request, current_user=user, db=db_session)

    assert resolved_user.id == user.id


@pytest.mark.asyncio
async def test_require_project_role_fails_for_different_project_scope(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "lead-only-a@vfxhub.dev")
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    await _assign_role(db_session, user.id, RoleName.lead, project_a)

    dependency = require_project_role("project_id", "lead")
    request = _make_request({"project_id": str(project_b)})

    with pytest.raises(ForbiddenError):
        await dependency(request=request, current_user=user, db=db_session)


@pytest.mark.asyncio
async def test_require_project_role_passes_with_global_role(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "lead-global@vfxhub.dev")
    project_b = uuid.uuid4()
    await _assign_role(db_session, user.id, RoleName.lead, None)

    dependency = require_project_role("project_id", "lead")
    request = _make_request({"project_id": str(project_b)})
    resolved_user = await dependency(request=request, current_user=user, db=db_session)

    assert resolved_user.id == user.id


@pytest.mark.asyncio
async def test_require_project_role_rejects_missing_or_invalid_project_param(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "lead-param@vfxhub.dev")
    dependency = require_project_role("project_id", "lead")

    with pytest.raises(ForbiddenError):
        await dependency(request=_make_request({}), current_user=user, db=db_session)

    with pytest.raises(ForbiddenError):
        await dependency(
            request=_make_request({"project_id": "not-a-uuid"}),
            current_user=user,
            db=db_session,
        )


@pytest.mark.asyncio
async def test_project_scoped_roles_can_differ_by_project(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "scoped-multi-role@vfxhub.dev")
    project_a = uuid.uuid4()
    project_b = uuid.uuid4()

    await _assign_role(db_session, user.id, RoleName.lead, project_a)
    await _assign_role(db_session, user.id, RoleName.artist, project_b)

    lead_dependency = require_project_role("project_id", "lead")
    artist_dependency = require_project_role("project_id", "artist")

    resolved_lead = await lead_dependency(
        request=_make_request({"project_id": str(project_a)}),
        current_user=user,
        db=db_session,
    )
    assert resolved_lead.id == user.id

    resolved_artist = await artist_dependency(
        request=_make_request({"project_id": str(project_b)}),
        current_user=user,
        db=db_session,
    )
    assert resolved_artist.id == user.id

    with pytest.raises(ForbiddenError):
        await lead_dependency(
            request=_make_request({"project_id": str(project_b)}),
            current_user=user,
            db=db_session,
        )

from __future__ import annotations

import sys
import uuid
from importlib import import_module
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

security_module = import_module("app.core.security")
models_module = import_module("app.models")

create_access_token = security_module.create_access_token
hash_password = security_module.hash_password
Project = models_module.Project
ProjectStatus = models_module.ProjectStatus
Role = models_module.Role
RoleName = models_module.RoleName
Shot = models_module.Shot
ShotStatus = models_module.ShotStatus
StatusLog = models_module.StatusLog
StatusLogEntityType = models_module.StatusLogEntityType
User = models_module.User
UserRole = models_module.UserRole


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


async def _create_project(db_session: AsyncSession, owner: User) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name="Workflow Project",
        code=f"WF{str(uuid.uuid4()).replace('-', '')[:8].upper()}",
        status=ProjectStatus.pending,
        created_by=owner.id,
    )
    db_session.add(project)
    await db_session.commit()
    return project


async def _create_shot(
    db_session: AsyncSession,
    project_id: uuid.UUID,
    status: ShotStatus,
    assigned_to: uuid.UUID | None,
) -> Shot:
    shot = Shot(
        id=uuid.uuid4(),
        project_id=project_id,
        name="Shot Workflow",
        code=f"SH{str(uuid.uuid4()).replace('-', '')[:6].upper()}",
        status=status,
        frame_start=1001,
        frame_end=1050,
        assigned_to=assigned_to,
    )
    db_session.add(shot)
    await db_session.commit()
    return shot


async def _assign_role(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    role_name: RoleName,
    project_id: uuid.UUID | None,
) -> None:
    role = await _ensure_role(db_session, role_name)
    db_session.add(UserRole(user_id=user_id, role_id=role.id, project_id=project_id))
    await db_session.commit()


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_patch_shot_status_requires_authentication(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    owner = await _create_user(db_session, "owner-auth@vfxhub.dev")
    project = await _create_project(db_session, owner)
    shot = await _create_shot(db_session, project.id, ShotStatus.pending, owner.id)

    response = await client.patch(
        f"/shots/{shot.id}/status",
        json={"status": "in_progress", "comment": "start"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_artist_owner_can_transition_to_in_progress_and_create_status_log(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    artist = await _create_user(db_session, "artist-owner@vfxhub.dev")
    project = await _create_project(db_session, artist)
    shot = await _create_shot(db_session, project.id, ShotStatus.pending, artist.id)
    await _assign_role(db_session, artist.id, RoleName.artist, project.id)

    response = await client.patch(
        f"/shots/{shot.id}/status",
        json={"status": "in_progress", "comment": "Ready to work"},
        headers=_auth_headers(artist),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["old_status"] == "pending"
    assert payload["new_status"] == "in_progress"
    assert payload["comment"] == "Ready to work"

    refreshed_shot = await db_session.get(Shot, shot.id)
    assert refreshed_shot is not None
    await db_session.refresh(refreshed_shot)
    assert refreshed_shot.status == ShotStatus.in_progress

    logs_result = await db_session.execute(
        select(StatusLog)
        .where(StatusLog.entity_id == shot.id)
        .order_by(StatusLog.changed_at.desc())
    )
    status_log = logs_result.scalar_one_or_none()
    assert status_log is not None
    assert status_log.entity_type == StatusLogEntityType.shot
    assert status_log.old_status == "pending"
    assert status_log.new_status == "in_progress"
    assert status_log.comment == "Ready to work"


@pytest.mark.asyncio
async def test_invalid_status_transition_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    lead = await _create_user(db_session, "lead-invalid-transition@vfxhub.dev")
    project = await _create_project(db_session, lead)
    shot = await _create_shot(db_session, project.id, ShotStatus.pending, lead.id)
    await _assign_role(db_session, lead.id, RoleName.lead, project.id)

    response = await client.patch(
        f"/shots/{shot.id}/status",
        json={"status": "review", "comment": "skip steps"},
        headers=_auth_headers(lead),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_review_transition_allows_only_artist_owner_or_lead(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    owner = await _create_user(db_session, "artist-owner-review@vfxhub.dev")
    other_artist = await _create_user(db_session, "artist-other-review@vfxhub.dev")
    lead = await _create_user(db_session, "lead-review@vfxhub.dev")
    project = await _create_project(db_session, owner)
    shot = await _create_shot(db_session, project.id, ShotStatus.in_progress, owner.id)

    await _assign_role(db_session, owner.id, RoleName.artist, project.id)
    await _assign_role(db_session, other_artist.id, RoleName.artist, project.id)
    await _assign_role(db_session, lead.id, RoleName.lead, project.id)

    denied = await client.patch(
        f"/shots/{shot.id}/status",
        json={"status": "review", "comment": "try review"},
        headers=_auth_headers(other_artist),
    )
    assert denied.status_code == 403

    allowed = await client.patch(
        f"/shots/{shot.id}/status",
        json={"status": "review", "comment": "lead review"},
        headers=_auth_headers(lead),
    )
    assert allowed.status_code == 200
    assert allowed.json()["new_status"] == "review"


@pytest.mark.asyncio
async def test_approved_transition_allows_only_supervisor_or_admin(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    lead = await _create_user(db_session, "lead-approve@vfxhub.dev")
    supervisor = await _create_user(db_session, "supervisor-approve@vfxhub.dev")
    project = await _create_project(db_session, lead)
    shot = await _create_shot(db_session, project.id, ShotStatus.revision, lead.id)

    await _assign_role(db_session, lead.id, RoleName.lead, project.id)
    await _assign_role(db_session, supervisor.id, RoleName.supervisor, project.id)

    denied = await client.patch(
        f"/shots/{shot.id}/status",
        json={"status": "approved", "comment": "lead approve"},
        headers=_auth_headers(lead),
    )
    assert denied.status_code == 403

    allowed = await client.patch(
        f"/shots/{shot.id}/status",
        json={"status": "approved", "comment": "supervisor approve"},
        headers=_auth_headers(supervisor),
    )
    assert allowed.status_code == 200
    assert allowed.json()["new_status"] == "approved"


@pytest.mark.asyncio
async def test_delivered_transition_allows_only_admin(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    supervisor = await _create_user(db_session, "supervisor-deliver@vfxhub.dev")
    admin = await _create_user(db_session, "admin-deliver@vfxhub.dev")
    project = await _create_project(db_session, admin)
    shot = await _create_shot(db_session, project.id, ShotStatus.approved, supervisor.id)

    await _assign_role(db_session, supervisor.id, RoleName.supervisor, project.id)
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    denied = await client.patch(
        f"/shots/{shot.id}/status",
        json={"status": "delivered", "comment": "supervisor deliver"},
        headers=_auth_headers(supervisor),
    )
    assert denied.status_code == 403

    allowed = await client.patch(
        f"/shots/{shot.id}/status",
        json={"status": "delivered", "comment": "admin deliver"},
        headers=_auth_headers(admin),
    )
    assert allowed.status_code == 200
    assert allowed.json()["new_status"] == "delivered"


@pytest.mark.asyncio
async def test_revision_loop_approved_to_revision_and_revision_to_in_progress(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    supervisor = await _create_user(db_session, "supervisor-loop@vfxhub.dev")
    lead = await _create_user(db_session, "lead-loop@vfxhub.dev")
    owner = await _create_user(db_session, "owner-loop@vfxhub.dev")
    project = await _create_project(db_session, supervisor)
    shot = await _create_shot(db_session, project.id, ShotStatus.approved, owner.id)

    await _assign_role(db_session, supervisor.id, RoleName.supervisor, project.id)
    await _assign_role(db_session, lead.id, RoleName.lead, project.id)

    to_revision = await client.patch(
        f"/shots/{shot.id}/status",
        json={"status": "revision", "comment": "needs changes"},
        headers=_auth_headers(supervisor),
    )
    assert to_revision.status_code == 200
    assert to_revision.json()["new_status"] == "revision"

    to_in_progress = await client.patch(
        f"/shots/{shot.id}/status",
        json={"status": "in_progress", "comment": "back to work"},
        headers=_auth_headers(lead),
    )
    assert to_in_progress.status_code == 200
    assert to_in_progress.json()["new_status"] == "in_progress"

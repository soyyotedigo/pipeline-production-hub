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
Role = models_module.Role
RoleName = models_module.RoleName
User = models_module.User
UserRole = models_module.UserRole

pytestmark = [pytest.mark.episodes, pytest.mark.sequences]


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
    db_session.add(UserRole(user_id=user_id, role_id=role.id, project_id=project_id))
    await db_session.commit()


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_episode_and_sequence_lifecycle_with_archive_restore_and_force_delete(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-epseq@vfxhub.dev")
    lead = await _create_user(db_session, "lead-epseq@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    create_project = await client.post(
        "/projects",
        json={"name": "Episode Seq Project", "code": "ESP23"},
        headers=_auth_headers(admin),
    )
    assert create_project.status_code == 200
    project_id = create_project.json()["id"]
    await _assign_role(db_session, lead.id, RoleName.lead, uuid.UUID(project_id))

    create_episode = await client.post(
        f"/projects/{project_id}/episodes",
        json={"name": "Episode 1", "code": "EP01"},
        headers=_auth_headers(lead),
    )
    assert create_episode.status_code == 200
    episode_id = create_episode.json()["id"]

    patch_episode = await client.patch(
        f"/episodes/{episode_id}",
        json={"name": "Episode 01"},
        headers=_auth_headers(lead),
    )
    assert patch_episode.status_code == 200
    assert patch_episode.json()["name"] == "Episode 01"

    archive_episode = await client.post(
        f"/episodes/{episode_id}/archive",
        headers=_auth_headers(lead),
    )
    assert archive_episode.status_code == 200
    assert archive_episode.json()["archived_at"] is not None

    list_episodes_hidden = await client.get(
        f"/projects/{project_id}/episodes",
        headers=_auth_headers(lead),
    )
    assert list_episodes_hidden.status_code == 200
    assert list_episodes_hidden.json()["total"] == 0

    restore_episode = await client.post(
        f"/episodes/{episode_id}/restore",
        headers=_auth_headers(lead),
    )
    assert restore_episode.status_code == 200
    assert restore_episode.json()["archived_at"] is None

    create_sequence = await client.post(
        f"/projects/{project_id}/sequences",
        json={
            "name": "Sequence 1",
            "code": "SQ01",
            "episode_id": episode_id,
            "scope_type": "sequence",
        },
        headers=_auth_headers(lead),
    )
    assert create_sequence.status_code == 200
    sequence_id = create_sequence.json()["id"]

    patch_sequence = await client.patch(
        f"/sequences/{sequence_id}",
        json={"name": "Sequence 01", "scope_type": "spot"},
        headers=_auth_headers(lead),
    )
    assert patch_sequence.status_code == 200
    assert patch_sequence.json()["name"] == "Sequence 01"

    archive_sequence = await client.post(
        f"/sequences/{sequence_id}/archive",
        headers=_auth_headers(lead),
    )
    assert archive_sequence.status_code == 200
    assert archive_sequence.json()["archived_at"] is not None

    restore_sequence = await client.post(
        f"/sequences/{sequence_id}/restore",
        headers=_auth_headers(lead),
    )
    assert restore_sequence.status_code == 200
    assert restore_sequence.json()["archived_at"] is None

    deny_sequence_delete = await client.delete(
        f"/sequences/{sequence_id}?force=true",
        headers=_auth_headers(lead),
    )
    assert deny_sequence_delete.status_code == 403

    allow_sequence_delete = await client.delete(
        f"/sequences/{sequence_id}?force=true",
        headers=_auth_headers(admin),
    )
    assert allow_sequence_delete.status_code == 204

    deny_episode_delete = await client.delete(
        f"/episodes/{episode_id}?force=true",
        headers=_auth_headers(lead),
    )
    assert deny_episode_delete.status_code == 403

    allow_episode_delete = await client.delete(
        f"/episodes/{episode_id}?force=true",
        headers=_auth_headers(admin),
    )
    assert allow_episode_delete.status_code == 204

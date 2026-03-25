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

config_module = import_module("app.core.config")
security_module = import_module("app.core.security")
models_module = import_module("app.models")

settings = config_module.settings
create_access_token = security_module.create_access_token
hash_password = security_module.hash_password
Asset = models_module.Asset
AssetType = models_module.AssetType
Project = models_module.Project
Role = models_module.Role
RoleName = models_module.RoleName
Shot = models_module.Shot
User = models_module.User
UserRole = models_module.UserRole


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


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


async def _seed_project_context(db_session: AsyncSession) -> tuple[User, User, Project, Shot]:
    admin = await _create_user(db_session, f"tasks-admin-{uuid.uuid4().hex[:8]}@vfxhub.dev")
    artist = await _create_user(db_session, f"tasks-artist-{uuid.uuid4().hex[:8]}@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    project = Project(name="Tasks Project", code=f"TSK{uuid.uuid4().hex[:4]}", created_by=admin.id)
    db_session.add(project)
    await db_session.flush()

    shot = Shot(project_id=project.id, name="Shot 020", code="SH020")
    asset = Asset(
        project_id=project.id,
        name="Tree",
        code="TREE",
        asset_type=AssetType.environment,
    )
    db_session.add(shot)
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(shot)

    await _assign_role(db_session, artist.id, RoleName.artist, project.id)
    await _assign_role(db_session, admin.id, RoleName.lead, project.id)

    return admin, artist, project, shot


@pytest.mark.asyncio
async def test_get_task_status_owner_can_read(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_root", str(tmp_path))

    _, artist, _, shot = await _seed_project_context(db_session)

    upload_response = await client.post(
        "/files/upload",
        files={"upload": ("taskable.exr", b"task-payload", "image/x-exr")},
        data={"shot_id": str(shot.id)},
        headers=_auth_headers(artist),
    )
    assert upload_response.status_code == 200
    task_ids = upload_response.json()["metadata_json"]["task_ids"]
    task_id = task_ids[0]

    status_response = await client.get(f"/tasks/{task_id}", headers=_auth_headers(artist))
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["id"] == task_id
    assert payload["task_type"] in {"thumbnail", "checksum_large_file"}
    assert payload["status"] in {"pending", "running", "completed", "failed"}


@pytest.mark.asyncio
async def test_get_task_status_forbidden_for_non_owner(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_root", str(tmp_path))

    admin, artist, _, shot = await _seed_project_context(db_session)

    upload_response = await client.post(
        "/files/upload",
        files={"upload": ("taskable.exr", b"task-payload", "image/x-exr")},
        data={"shot_id": str(shot.id)},
        headers=_auth_headers(artist),
    )
    assert upload_response.status_code == 200
    task_id = upload_response.json()["metadata_json"]["task_ids"][0]

    status_response = await client.get(f"/tasks/{task_id}", headers=_auth_headers(admin))
    assert status_response.status_code == 403
    assert status_response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_get_task_status_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, f"tasks-notfound-{uuid.uuid4().hex[:8]}@vfxhub.dev")

    response = await client.get(f"/tasks/{uuid.uuid4()}", headers=_auth_headers(admin))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"

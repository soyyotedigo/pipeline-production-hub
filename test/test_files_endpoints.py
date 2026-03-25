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
File = models_module.File
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


async def _seed_project_context(
    db_session: AsyncSession,
) -> tuple[User, User, Project, Shot, Asset]:
    admin = await _create_user(db_session, f"files-admin-{uuid.uuid4().hex[:8]}@vfxhub.dev")
    artist = await _create_user(db_session, f"files-artist-{uuid.uuid4().hex[:8]}@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    project = Project(name="Files Project", code=f"FLS{uuid.uuid4().hex[:4]}", created_by=admin.id)
    db_session.add(project)
    await db_session.flush()

    shot = Shot(project_id=project.id, name="Shot 010", code="SH010")
    asset = Asset(
        project_id=project.id,
        name="Robot",
        code="ROBOT",
        asset_type=AssetType.character,
    )
    db_session.add(shot)
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(shot)
    await db_session.refresh(asset)

    await _assign_role(db_session, artist.id, RoleName.artist, project.id)
    await _assign_role(db_session, admin.id, RoleName.lead, project.id)

    return admin, artist, project, shot, asset


@pytest.mark.asyncio
async def test_files_upload_metadata_download_and_versions(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_root", str(tmp_path))

    _, artist, project, shot, _ = await _seed_project_context(db_session)

    upload_v1 = await client.post(
        "/files/upload",
        files={"upload": ("plate.exr", b"plate-v1", "image/x-exr")},
        data={"shot_id": str(shot.id)},
        headers=_auth_headers(artist),
    )
    assert upload_v1.status_code == 200
    file_v1 = upload_v1.json()
    assert file_v1["version"] == 1
    assert file_v1["storage_path"].startswith(
        f"projects/{project.code}/shots/SH/SH010/publish/general/v001/"
    )

    upload_v2 = await client.post(
        "/files/upload",
        files={"upload": ("plate.exr", b"plate-v2", "image/x-exr")},
        data={"shot_id": str(shot.id)},
        headers=_auth_headers(artist),
    )
    assert upload_v2.status_code == 200
    file_v2 = upload_v2.json()
    assert file_v2["version"] == 2

    get_metadata = await client.get(f"/files/{file_v2['id']}", headers=_auth_headers(artist))
    assert get_metadata.status_code == 200
    assert get_metadata.json()["original_name"] == "plate.exr"

    list_files = await client.get(f"/files?shot_id={shot.id}", headers=_auth_headers(artist))
    assert list_files.status_code == 200
    list_payload = list_files.json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["version"] == 2

    versions = await client.get(f"/files/{file_v2['id']}/versions", headers=_auth_headers(artist))
    assert versions.status_code == 200
    versions_payload = versions.json()
    assert [item["version"] for item in versions_payload["items"]] == [2, 1]

    download = await client.get(f"/files/{file_v2['id']}/download", headers=_auth_headers(artist))
    assert download.status_code == 200
    assert download.content == b"plate-v2"


@pytest.mark.asyncio
async def test_files_upload_requires_exactly_one_parent(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_root", str(tmp_path))

    _, artist, _, shot, asset = await _seed_project_context(db_session)

    response = await client.post(
        "/files/upload",
        files={"upload": ("asset.ma", b"maya", "application/octet-stream")},
        data={"shot_id": str(shot.id), "asset_id": str(asset.id)},
        headers=_auth_headers(artist),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNPROCESSABLE"


@pytest.mark.asyncio
async def test_files_soft_delete_hides_file(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_root", str(tmp_path))

    admin, artist, _, shot, _ = await _seed_project_context(db_session)

    upload_response = await client.post(
        "/files/upload",
        files={"upload": ("cache.bin", b"cache", "application/octet-stream")},
        data={"shot_id": str(shot.id)},
        headers=_auth_headers(artist),
    )
    file_id = upload_response.json()["id"]

    delete_response = await client.delete(f"/files/{file_id}", headers=_auth_headers(admin))
    assert delete_response.status_code == 204

    metadata_response = await client.get(f"/files/{file_id}", headers=_auth_headers(artist))
    assert metadata_response.status_code == 404

    db_file = await db_session.get(File, uuid.UUID(file_id))
    assert db_file is not None
    assert db_file.deleted_at is not None


@pytest.mark.asyncio
async def test_files_upload_dedup_reuses_storage_path(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_root", str(tmp_path))

    _, artist, _, shot, _ = await _seed_project_context(db_session)

    upload_v1 = await client.post(
        "/files/upload",
        files={"upload": ("plate.exr", b"same-binary-data", "image/x-exr")},
        data={"shot_id": str(shot.id)},
        headers=_auth_headers(artist),
    )
    assert upload_v1.status_code == 200
    file_v1 = upload_v1.json()

    upload_v2 = await client.post(
        "/files/upload",
        files={"upload": ("plate.exr", b"same-binary-data", "image/x-exr")},
        data={"shot_id": str(shot.id)},
        headers=_auth_headers(artist),
    )
    assert upload_v2.status_code == 200
    file_v2 = upload_v2.json()

    assert file_v1["storage_path"] == file_v2["storage_path"]

    db_file_v1 = await db_session.get(File, uuid.UUID(file_v1["id"]))
    db_file_v2 = await db_session.get(File, uuid.UUID(file_v2["id"]))
    assert db_file_v1 is not None
    assert db_file_v2 is not None
    assert db_file_v1.storage_path == db_file_v2.storage_path


@pytest.mark.asyncio
async def test_files_upload_rejects_payload_over_size_limit(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_root", str(tmp_path))
    monkeypatch.setattr(settings, "storage_max_upload_size_bytes", 4)

    _, artist, _, shot, _ = await _seed_project_context(db_session)

    response = await client.post(
        "/files/upload",
        files={"upload": ("oversize.exr", b"12345", "image/x-exr")},
        data={"shot_id": str(shot.id)},
        headers=_auth_headers(artist),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNPROCESSABLE"

from __future__ import annotations

import sys
import uuid
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

security_module = import_module("app.core.security")
models_module = import_module("app.models")

create_access_token = security_module.create_access_token
hash_password = security_module.hash_password

Asset = models_module.Asset
AssetStatus = models_module.AssetStatus
AssetType = models_module.AssetType
Project = models_module.Project
ProjectStatus = models_module.ProjectStatus
Role = models_module.Role
RoleName = models_module.RoleName
Shot = models_module.Shot
ShotStatus = models_module.ShotStatus
User = models_module.User
UserRole = models_module.UserRole

pytestmark = pytest.mark.versions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    project_id: uuid.UUID | None = None,
) -> None:
    role = await _ensure_role(db_session, role_name)
    db_session.add(UserRole(user_id=user_id, role_id=role.id, project_id=project_id))
    await db_session.commit()


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


async def _create_project(db_session: AsyncSession, owner: User) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name="Version Project",
        code=f"VP{uuid.uuid4().hex[:6].upper()}",
        status=ProjectStatus.pending,
        created_by=owner.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _create_shot(db_session: AsyncSession, project: Project) -> Shot:
    shot = Shot(
        id=uuid.uuid4(),
        project_id=project.id,
        name="VersionShot",
        code=f"VS{uuid.uuid4().hex[:4].upper()}",
        status=ShotStatus.pending,
        frame_start=1001,
        frame_end=1040,
    )
    db_session.add(shot)
    await db_session.commit()
    await db_session.refresh(shot)
    return shot


async def _create_asset(db_session: AsyncSession, project: Project) -> Asset:
    asset = Asset(
        id=uuid.uuid4(),
        project_id=project.id,
        name=f"VersionAsset-{uuid.uuid4().hex[:4]}",
        asset_type=AssetType.prop,
        status=AssetStatus.pending,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)
    return asset


async def _create_pipeline_task_via_api(
    client: AsyncClient,
    shot_id: uuid.UUID,
    headers: dict[str, str],
) -> dict:
    resp = await client.post(
        f"/api/v1/shots/{shot_id}/tasks",
        json={"step_name": "Compositing", "step_type": "compositing", "order": 1},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_version_via_api(
    client: AsyncClient,
    task_id: uuid.UUID,
    headers: dict[str, str],
    *,
    description: str | None = None,
) -> dict:
    payload: dict = {}
    if description:
        payload["description"] = description
    resp = await client.post(
        f"/api/v1/pipeline-tasks/{task_id}/versions", json=payload, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


class TestCreateVersion:
    async def test_create_via_task_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-create@ver.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)

        resp = await client.post(
            f"/api/v1/pipeline-tasks/{task['id']}/versions",
            json={"description": "First submission"},
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["version_number"] == 1
        assert data["status"] == "pending_review"
        assert data["description"] == "First submission"
        assert data["submitted_by"] == str(admin.id)
        assert "code" in data

    async def test_version_number_auto_increments(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-inc@ver.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)

        v1 = await _create_version_via_api(client, task["id"], headers)
        v2 = await _create_version_via_api(client, task["id"], headers)

        assert v1["version_number"] == 1
        assert v2["version_number"] == 2

    async def test_create_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-noauth@ver.test")
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        task = await _create_pipeline_task_via_api(client, shot.id, _auth_headers(admin))

        resp = await client.post(f"/api/v1/pipeline-tasks/{task['id']}/versions", json={})

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET / UPDATE / ARCHIVE
# ---------------------------------------------------------------------------


class TestGetUpdateVersion:
    async def test_get_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get@ver.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)
        version = await _create_version_via_api(client, task["id"], headers)

        resp = await client.get(f"/api/v1/versions/{version['id']}", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["id"] == version["id"]

    async def test_get_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get404@ver.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.get(f"/api/v1/versions/{uuid.uuid4()}", headers=_auth_headers(admin))

        assert resp.status_code == 404

    async def test_update_description(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd@ver.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)
        version = await _create_version_via_api(client, task["id"], headers)

        resp = await client.patch(
            f"/api/v1/versions/{version['id']}",
            json={"description": "Updated description"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    async def test_archive_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-arch@ver.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)
        version = await _create_version_via_api(client, task["id"], headers)

        resp = await client.delete(f"/api/v1/versions/{version['id']}", headers=headers)

        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# STATUS TRANSITIONS
# ---------------------------------------------------------------------------


class TestVersionStatus:
    async def test_update_status_pending_to_approved(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-approve@ver.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)
        version = await _create_version_via_api(client, task["id"], headers)

        resp = await client.patch(
            f"/api/v1/versions/{version['id']}/status",
            json={"status": "approved"},
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["new_status"] == "approved"
        assert data["old_status"] == "pending_review"

    async def test_update_status_with_comment(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-comment@ver.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)
        version = await _create_version_via_api(client, task["id"], headers)

        resp = await client.patch(
            f"/api/v1/versions/{version['id']}/status",
            json={"status": "revision_requested", "comment": "Please fix the lighting"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["comment"] == "Please fix the lighting"
        assert resp.json()["new_status"] == "revision_requested"


# ---------------------------------------------------------------------------
# LIST VERSIONS
# ---------------------------------------------------------------------------


class TestListVersions:
    async def test_list_task_versions(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-tasklist@ver.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)
        await _create_version_via_api(client, task["id"], headers)
        await _create_version_via_api(client, task["id"], headers)

        resp = await client.get(f"/api/v1/pipeline-tasks/{task['id']}/versions", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    async def test_list_shot_versions(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-shotlist@ver.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)
        await _create_version_via_api(client, task["id"], headers)

        resp = await client.get(f"/api/v1/shots/{shot.id}/versions", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_list_project_versions(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-prjlist@ver.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)
        await _create_version_via_api(client, task["id"], headers)

        resp = await client.get(f"/api/v1/projects/{project.id}/versions", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

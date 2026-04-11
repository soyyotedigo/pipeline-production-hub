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

Project = models_module.Project
ProjectStatus = models_module.ProjectStatus
Role = models_module.Role
RoleName = models_module.RoleName
Shot = models_module.Shot
ShotStatus = models_module.ShotStatus
User = models_module.User
UserRole = models_module.UserRole

pytestmark = pytest.mark.playlists


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
        name="Playlist Project",
        code=f"PL{uuid.uuid4().hex[:6].upper()}",
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
        name="PlaylistShot",
        code=f"PP{uuid.uuid4().hex[:4].upper()}",
        status=ShotStatus.pending,
        frame_start=1001,
        frame_end=1040,
    )
    db_session.add(shot)
    await db_session.commit()
    await db_session.refresh(shot)
    return shot


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
) -> dict:
    resp = await client.post(f"/api/v1/pipeline-tasks/{task_id}/versions", json={}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_playlist_via_api(
    client: AsyncClient,
    project_id: uuid.UUID,
    headers: dict[str, str],
    *,
    name: str = "Daily Review",
) -> dict:
    resp = await client.post(
        "/api/v1/playlists",
        json={"project_id": str(project_id), "name": name},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


class TestCreatePlaylist:
    async def test_create_returns_201_with_correct_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-create@pl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)

        resp = await client.post(
            "/api/v1/playlists",
            json={"project_id": str(project.id), "name": "Monday Dailies"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Monday Dailies"
        assert data["project_id"] == str(project.id)
        assert data["status"] == "draft"
        assert data["created_by"] == str(admin.id)
        assert "id" in data

    async def test_create_with_optional_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-full@pl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)

        resp = await client.post(
            "/api/v1/playlists",
            json={
                "project_id": str(project.id),
                "name": "Full Playlist",
                "description": "End of week review",
                "date": "2026-03-21",
            },
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["description"] == "End of week review"
        assert data["date"] == "2026-03-21"

    async def test_create_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-noauth@pl.test")
        project = await _create_project(db_session, admin)

        resp = await client.post(
            "/api/v1/playlists",
            json={"project_id": str(project.id), "name": "No Auth"},
        )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET / UPDATE / ARCHIVE
# ---------------------------------------------------------------------------


class TestGetUpdatePlaylist:
    async def test_get_returns_200_with_items_field(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get@pl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        pl = await _create_playlist_via_api(client, project.id, headers)

        resp = await client.get(f"/api/v1/playlists/{pl['id']}", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == pl["id"]
        assert "items" in data

    async def test_get_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get404@pl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.get(f"/api/v1/playlists/{uuid.uuid4()}", headers=_auth_headers(admin))

        assert resp.status_code == 404

    async def test_update_name_and_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd@pl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        pl = await _create_playlist_via_api(client, project.id, headers)

        resp = await client.patch(
            f"/api/v1/playlists/{pl['id']}",
            json={"name": "Updated Name", "status": "in_progress"},
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Name"
        assert data["status"] == "in_progress"

    async def test_archive_sets_archived_at(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-arch@pl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        pl = await _create_playlist_via_api(client, project.id, headers)

        resp = await client.delete(f"/api/v1/playlists/{pl['id']}", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["archived_at"] is not None


# ---------------------------------------------------------------------------
# ITEMS
# ---------------------------------------------------------------------------


class TestPlaylistItems:
    async def test_add_item_returns_200_with_item(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-additem@pl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)
        version = await _create_version_via_api(client, task["id"], headers)
        pl = await _create_playlist_via_api(client, project.id, headers)

        resp = await client.post(
            f"/api/v1/playlists/{pl['id']}/items",
            json={"version_id": version["id"]},
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["version_id"] == version["id"]
        assert data["items"][0]["review_status"] == "pending"

    async def test_add_duplicate_version_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-dupitem@pl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)
        version = await _create_version_via_api(client, task["id"], headers)
        pl = await _create_playlist_via_api(client, project.id, headers)
        await client.post(
            f"/api/v1/playlists/{pl['id']}/items",
            json={"version_id": version["id"]},
            headers=headers,
        )

        resp = await client.post(
            f"/api/v1/playlists/{pl['id']}/items",
            json={"version_id": version["id"]},
            headers=headers,
        )

        assert resp.status_code == 409

    async def test_remove_item_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-rmitem@pl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)
        version = await _create_version_via_api(client, task["id"], headers)
        pl = await _create_playlist_via_api(client, project.id, headers)
        add_resp = await client.post(
            f"/api/v1/playlists/{pl['id']}/items",
            json={"version_id": version["id"]},
            headers=headers,
        )
        item_id = add_resp.json()["items"][0]["id"]

        resp = await client.delete(f"/api/v1/playlist-items/{item_id}", headers=headers)

        assert resp.status_code == 204

    async def test_review_item(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-review@pl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)
        version = await _create_version_via_api(client, task["id"], headers)
        pl = await _create_playlist_via_api(client, project.id, headers)
        add_resp = await client.post(
            f"/api/v1/playlists/{pl['id']}/items",
            json={"version_id": version["id"]},
            headers=headers,
        )
        item_id = add_resp.json()["items"][0]["id"]

        resp = await client.patch(
            f"/api/v1/playlist-items/{item_id}",
            json={"review_status": "approved", "reviewer_notes": "Looks great"},
            headers=headers,
        )

        assert resp.status_code == 200
        items = resp.json()["items"]
        reviewed = next(i for i in items if i["id"] == item_id)
        assert reviewed["review_status"] == "approved"
        assert reviewed["reviewer_notes"] == "Looks great"

    async def test_reorder_items(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-reorder@pl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task = await _create_pipeline_task_via_api(client, shot.id, headers)
        v1 = await _create_version_via_api(client, task["id"], headers)
        v2 = await _create_version_via_api(client, task["id"], headers)
        pl = await _create_playlist_via_api(client, project.id, headers)
        add1 = await client.post(
            f"/api/v1/playlists/{pl['id']}/items", json={"version_id": v1["id"]}, headers=headers
        )
        add2 = await client.post(
            f"/api/v1/playlists/{pl['id']}/items", json={"version_id": v2["id"]}, headers=headers
        )
        item1_id = add1.json()["items"][0]["id"]
        item2_id = add2.json()["items"][-1]["id"]

        resp = await client.patch(
            f"/api/v1/playlists/{pl['id']}/items/reorder",
            json={"items": [{"item_id": item1_id, "order": 2}, {"item_id": item2_id, "order": 1}]},
            headers=headers,
        )

        assert resp.status_code == 200
        items = {i["id"]: i["order"] for i in resp.json()["items"]}
        assert items[item1_id] == 2
        assert items[item2_id] == 1


# ---------------------------------------------------------------------------
# LIST PROJECT PLAYLISTS
# ---------------------------------------------------------------------------


class TestListProjectPlaylists:
    async def test_list_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-list@pl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        await _create_playlist_via_api(client, project.id, headers, name="PL1")
        await _create_playlist_via_api(client, project.id, headers, name="PL2")

        resp = await client.get(f"/api/v1/projects/{project.id}/playlists", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    async def test_list_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-page@pl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        for i in range(4):
            await _create_playlist_via_api(client, project.id, headers, name=f"P{i}")

        resp = await client.get(f"/api/v1/projects/{project.id}/playlists?limit=2", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 4

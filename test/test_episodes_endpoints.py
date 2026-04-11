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
User = models_module.User
UserRole = models_module.UserRole

pytestmark = pytest.mark.episodes


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
    project_id: uuid.UUID | None,
) -> None:
    role = await _ensure_role(db_session, role_name)
    db_session.add(UserRole(user_id=user_id, role_id=role.id, project_id=project_id))
    await db_session.commit()


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


async def _create_project(
    db_session: AsyncSession,
    owner: User,
    *,
    name: str = "Episode Test Project",
    code: str | None = None,
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=name,
        code=code or f"EP{uuid.uuid4().hex[:6].upper()}",
        status=ProjectStatus.pending,
        created_by=owner.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _create_episode_via_api(
    client: AsyncClient,
    project_id: uuid.UUID,
    headers: dict[str, str],
    *,
    name: str = "Episode 01",
    code: str | None = None,
) -> dict:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/episodes",
        json={"name": name, "code": code or f"EP{uuid.uuid4().hex[:4].upper()}"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


class TestCreateEpisode:
    async def test_create_returns_200_with_correct_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-create@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)

        resp = await client.post(
            f"/api/v1/projects/{project.id}/episodes",
            json={"name": "Pilot", "code": "EP01"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Pilot"
        assert data["code"] == "EP01"
        assert data["project_id"] == str(project.id)
        assert data["status"] == "active"
        assert data["archived_at"] is None
        assert "id" in data
        assert "created_at" in data

    async def test_create_with_all_optional_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-full@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)

        resp = await client.post(
            f"/api/v1/projects/{project.id}/episodes",
            json={
                "name": "Full Episode",
                "code": "FE01",
                "status": "in_progress",
                "description": "A fully-spec'd episode",
                "order": 2,
            },
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "in_progress"
        assert data["description"] == "A fully-spec'd episode"
        assert data["order"] == 2

    async def test_create_duplicate_code_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-dup@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        await _create_episode_via_api(client, project.id, headers, name="E1", code="DUP1")

        resp = await client.post(
            f"/api/v1/projects/{project.id}/episodes",
            json={"name": "E2", "code": "DUP1"},
            headers=headers,
        )

        assert resp.status_code == 409

    async def test_create_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-noauth@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)

        resp = await client.post(
            f"/api/v1/projects/{project.id}/episodes",
            json={"name": "No Auth", "code": "NA01"},
        )

        assert resp.status_code == 401

    async def test_create_by_artist_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-artcreate@ep.test")
        artist = await _create_user(db_session, "artist-create@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, artist.id, RoleName.artist, project.id)

        resp = await client.post(
            f"/api/v1/projects/{project.id}/episodes",
            json={"name": "Artist Ep", "code": "AE01"},
            headers=_auth_headers(artist),
        )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------


class TestListEpisodes:
    async def test_list_returns_200_with_items(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-list@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        await _create_episode_via_api(client, project.id, headers, name="E1", code="LE01")
        await _create_episode_via_api(client, project.id, headers, name="E2", code="LE02")

        resp = await client.get(f"/api/v1/projects/{project.id}/episodes", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_list_excludes_archived_by_default(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-listarch@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        active = await _create_episode_via_api(
            client, project.id, headers, name="Active", code="ACT1"
        )
        archived = await _create_episode_via_api(
            client, project.id, headers, name="Archived", code="ARC1"
        )
        await client.post(f"/api/v1/episodes/{archived['id']}/archive", headers=headers)

        resp = await client.get(f"/api/v1/projects/{project.id}/episodes", headers=headers)

        ids = [e["id"] for e in resp.json()["items"]]
        assert active["id"] in ids
        assert archived["id"] not in ids

    async def test_list_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-page@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        for i in range(5):
            await _create_episode_via_api(
                client, project.id, headers, name=f"E{i}", code=f"PG{i:02d}"
            )

        resp = await client.get(
            f"/api/v1/projects/{project.id}/episodes?offset=0&limit=3", headers=headers
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 3
        assert data["total"] == 5

    async def test_artist_can_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-artlist@ep.test")
        artist = await _create_user(db_session, "artist-list@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        await _assign_role(db_session, artist.id, RoleName.artist, project.id)
        headers_admin = _auth_headers(admin)
        await _create_episode_via_api(
            client, project.id, headers_admin, name="Visible", code="VIS1"
        )

        resp = await client.get(
            f"/api/v1/projects/{project.id}/episodes", headers=_auth_headers(artist)
        )

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_list_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-listnoauth@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)

        resp = await client.get(f"/api/v1/projects/{project.id}/episodes")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


class TestGetEpisode:
    async def test_get_returns_200_with_correct_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)
        created = await _create_episode_via_api(
            client, project.id, headers, name="Get Me", code="GM01"
        )

        resp = await client.get(f"/api/v1/episodes/{created['id']}", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == created["id"]
        assert data["name"] == "Get Me"
        assert data["code"] == "GM01"

    async def test_get_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get404@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.get(f"/api/v1/episodes/{uuid.uuid4()}", headers=_auth_headers(admin))

        assert resp.status_code == 404

    async def test_get_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-getnoauth@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)
        created = await _create_episode_via_api(
            client, project.id, headers, name="Secret", code="SC01"
        )

        resp = await client.get(f"/api/v1/episodes/{created['id']}")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------


class TestUpdateEpisode:
    async def test_update_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)
        created = await _create_episode_via_api(
            client, project.id, headers, name="Before", code="BF01"
        )

        resp = await client.patch(
            f"/api/v1/episodes/{created['id']}",
            json={"name": "After"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "After"

    async def test_update_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-updstatus@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)
        created = await _create_episode_via_api(client, project.id, headers, name="E", code="ST01")

        resp = await client.patch(
            f"/api/v1/episodes/{created['id']}",
            json={"status": "in_progress"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

    async def test_code_is_immutable(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-immut@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)
        created = await _create_episode_via_api(client, project.id, headers, name="E", code="IM01")

        # Code is not in the update schema — send it and confirm it's ignored
        resp = await client.patch(
            f"/api/v1/episodes/{created['id']}",
            json={"name": "Updated", "code": "CHANGED"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["code"] == "IM01"

    async def test_artist_cannot_update_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-artupd@ep.test")
        artist = await _create_user(db_session, "artist-upd@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        await _assign_role(db_session, artist.id, RoleName.artist, project.id)
        headers = _auth_headers(admin)
        created = await _create_episode_via_api(client, project.id, headers, name="E", code="AR01")

        resp = await client.patch(
            f"/api/v1/episodes/{created['id']}",
            json={"name": "Artist Edit"},
            headers=_auth_headers(artist),
        )

        assert resp.status_code == 403

    async def test_update_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd404@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.patch(
            f"/api/v1/episodes/{uuid.uuid4()}",
            json={"name": "Ghost"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# ARCHIVE / RESTORE
# ---------------------------------------------------------------------------


class TestArchiveRestoreEpisode:
    async def test_archive_sets_archived_at(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-archive@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)
        created = await _create_episode_via_api(client, project.id, headers, name="E", code="AC01")

        resp = await client.post(f"/api/v1/episodes/{created['id']}/archive", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["archived_at"] is not None

    async def test_restore_clears_archived_at(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-restore@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)
        created = await _create_episode_via_api(client, project.id, headers, name="E", code="RE01")
        await client.post(f"/api/v1/episodes/{created['id']}/archive", headers=headers)

        resp = await client.post(f"/api/v1/episodes/{created['id']}/restore", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["archived_at"] is None

    async def test_archived_not_in_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-arlist@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)
        created = await _create_episode_via_api(client, project.id, headers, name="E", code="AL01")
        await client.post(f"/api/v1/episodes/{created['id']}/archive", headers=headers)

        resp = await client.get(f"/api/v1/projects/{project.id}/episodes", headers=headers)

        assert resp.json()["total"] == 0

    async def test_archive_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-arch404@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.post(
            f"/api/v1/episodes/{uuid.uuid4()}/archive", headers=_auth_headers(admin)
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


class TestDeleteEpisode:
    async def test_admin_can_delete_with_force(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)
        created = await _create_episode_via_api(client, project.id, headers, name="E", code="DL01")

        resp = await client.delete(f"/api/v1/episodes/{created['id']}?force=true", headers=headers)

        assert resp.status_code == 204

        get_resp = await client.get(f"/api/v1/episodes/{created['id']}", headers=headers)
        assert get_resp.status_code == 404

    async def test_delete_without_force_returns_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-noforce@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)
        created = await _create_episode_via_api(client, project.id, headers, name="E", code="NF01")

        resp = await client.delete(f"/api/v1/episodes/{created['id']}", headers=headers)

        assert resp.status_code == 422

    async def test_lead_cannot_delete_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-leadel@ep.test")
        lead = await _create_user(db_session, "lead-del@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        await _assign_role(db_session, lead.id, RoleName.lead, project.id)
        headers_admin = _auth_headers(admin)
        created = await _create_episode_via_api(
            client, project.id, headers_admin, name="E", code="LD01"
        )

        resp = await client.delete(
            f"/api/v1/episodes/{created['id']}?force=true", headers=_auth_headers(lead)
        )

        assert resp.status_code == 403

    async def test_delete_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del404@ep.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.delete(
            f"/api/v1/episodes/{uuid.uuid4()}?force=true", headers=_auth_headers(admin)
        )

        assert resp.status_code == 404

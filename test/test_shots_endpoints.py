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

config_module = import_module("app.core.config")
security_module = import_module("app.core.security")
models_module = import_module("app.models")

settings = config_module.settings
create_access_token = security_module.create_access_token
hash_password = security_module.hash_password
Project = models_module.Project
ProjectStatus = models_module.ProjectStatus
Role = models_module.Role
RoleName = models_module.RoleName
Shot = models_module.Shot
ShotStatus = models_module.ShotStatus
StatusLog = models_module.StatusLog
User = models_module.User
UserRole = models_module.UserRole

pytestmark = pytest.mark.shots


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
    name: str = "Shot Test Project",
    code: str | None = None,
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=name,
        code=code or f"STP{uuid.uuid4().hex[:6].upper()}",
        status=ProjectStatus.pending,
        created_by=owner.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _create_shot_via_api(
    client: AsyncClient,
    project_id: uuid.UUID,
    headers: dict[str, str],
    *,
    name: str = "Shot 010",
    code: str | None = None,
    frame_start: int = 1001,
    frame_end: int = 1040,
    assigned_to: uuid.UUID | None = None,
) -> dict:
    payload: dict = {
        "name": name,
        "code": code or f"SH{uuid.uuid4().hex[:6].upper()}",
        "frame_start": frame_start,
        "frame_end": frame_end,
    }
    if assigned_to is not None:
        payload["assigned_to"] = str(assigned_to)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/shots",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


class TestCreateShot:
    async def test_create_shot_returns_shot_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-create@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)

        data = await _create_shot_via_api(
            client,
            project.id,
            _auth_headers(admin),
            name="Hero Shot",
            code="HERO01",
            frame_start=1001,
            frame_end=1120,
        )

        assert data["name"] == "Hero Shot"
        assert data["code"] == "HERO01"
        assert data["frame_start"] == 1001
        assert data["frame_end"] == 1120
        assert data["status"] == "pending"
        assert data["project_id"] == str(project.id)
        assert "id" in data
        assert "created_at" in data
        assert data["archived_at"] is None

    async def test_create_shot_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-noauth@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)

        resp = await client.post(
            f"/api/v1/projects/{project.id}/shots",
            json={"name": "Shot X", "code": "SHX01"},
        )

        assert resp.status_code == 401

    async def test_create_shot_with_invalid_project_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-badproj@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.post(
            f"/api/v1/projects/{uuid.uuid4()}/shots",
            json={"name": "Shot X", "code": "SHX01"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404

    async def test_create_shot_with_empty_name_returns_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-emptyname@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)

        resp = await client.post(
            f"/api/v1/projects/{project.id}/shots",
            json={"name": "", "code": "SHX01"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 422

    async def test_create_shot_with_short_code_returns_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-shortcode@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)

        resp = await client.post(
            f"/api/v1/projects/{project.id}/shots",
            json={"name": "Shot X", "code": "X"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 422

    async def test_create_shot_with_duplicate_code_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-dupcode@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        await _create_shot_via_api(
            client,
            project.id,
            headers,
            name="Shot A",
            code="DUP01",
        )

        resp = await client.post(
            f"/api/v1/projects/{project.id}/shots",
            json={"name": "Shot B", "code": "DUP01"},
            headers=headers,
        )

        assert resp.status_code == 409

    async def test_create_shot_with_assigned_to(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-assign@test.dev")
        artist = await _create_user(db_session, "artist-assign@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)

        data = await _create_shot_via_api(
            client,
            project.id,
            _auth_headers(admin),
            assigned_to=artist.id,
        )

        assert data["assigned_to"] == str(artist.id)


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


class TestGetShot:
    async def test_get_shot_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        shot = await _create_shot_via_api(
            client,
            project.id,
            headers,
            name="Get Me",
            code="GET01",
        )

        resp = await client.get(f"/api/v1/shots/{shot['id']}", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == shot["id"]
        assert data["name"] == "Get Me"
        assert data["code"] == "GET01"
        assert data["status"] == "pending"

    async def test_get_shot_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get401@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)

        shot = await _create_shot_via_api(
            client,
            project.id,
            _auth_headers(admin),
        )

        resp = await client.get(f"/api/v1/shots/{shot['id']}")

        assert resp.status_code == 401

    async def test_get_shot_with_invalid_id_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get404@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.get(
            f"/api/v1/shots/{uuid.uuid4()}",
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# UPDATE (PATCH)
# ---------------------------------------------------------------------------


class TestUpdateShot:
    async def test_update_shot_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-patch@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        shot = await _create_shot_via_api(client, project.id, headers)

        resp = await client.patch(
            f"/api/v1/shots/{shot['id']}",
            json={"name": "Updated Name"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    async def test_update_shot_frame_range(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-frames@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        shot = await _create_shot_via_api(client, project.id, headers)

        resp = await client.patch(
            f"/api/v1/shots/{shot['id']}",
            json={"frame_start": 1050, "frame_end": 1200},
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["frame_start"] == 1050
        assert data["frame_end"] == 1200

    async def test_update_shot_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-patch401@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)

        shot = await _create_shot_via_api(
            client,
            project.id,
            _auth_headers(admin),
        )

        resp = await client.patch(
            f"/api/v1/shots/{shot['id']}",
            json={"name": "Nope"},
        )

        assert resp.status_code == 401

    async def test_update_shot_with_invalid_id_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-patch404@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.patch(
            f"/api/v1/shots/{uuid.uuid4()}",
            json={"name": "Ghost"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------


class TestListShots:
    async def test_list_shots_returns_paginated_results(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-list@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        for i in range(3):
            await _create_shot_via_api(
                client,
                project.id,
                headers,
                name=f"Shot {i}",
                code=f"LST{i:02d}",
            )

        resp = await client.get(
            f"/api/v1/projects/{project.id}/shots?offset=0&limit=10",
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        assert "offset" in data
        assert "limit" in data

    async def test_list_shots_respects_limit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-limit@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        for i in range(5):
            await _create_shot_via_api(
                client,
                project.id,
                headers,
                name=f"Shot {i}",
                code=f"LIM{i:02d}",
            )

        resp = await client.get(
            f"/api/v1/projects/{project.id}/shots?offset=0&limit=2",
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    async def test_list_shots_respects_offset(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-offset@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        for i in range(3):
            await _create_shot_via_api(
                client,
                project.id,
                headers,
                name=f"Shot {i}",
                code=f"OFF{i:02d}",
            )

        resp = await client.get(
            f"/api/v1/projects/{project.id}/shots?offset=2&limit=10",
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 1

    async def test_list_shots_filters_by_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-filterstatus@test.dev")
        artist = await _create_user(db_session, "artist-filterstatus@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        await _assign_role(db_session, artist.id, RoleName.artist, project.id)
        headers = _auth_headers(admin)

        shot = await _create_shot_via_api(
            client,
            project.id,
            headers,
            assigned_to=artist.id,
        )
        await _create_shot_via_api(
            client,
            project.id,
            headers,
            name="Other",
            code="OTH01",
        )

        # Transition first shot to in_progress
        await client.patch(
            f"/api/v1/shots/{shot['id']}/status",
            json={"status": "in_progress"},
            headers=_auth_headers(artist),
        )

        resp = await client.get(
            f"/api/v1/projects/{project.id}/shots?status=in_progress",
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == shot["id"]

    async def test_list_shots_filters_by_assigned_to(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-filterassign@test.dev")
        artist = await _create_user(db_session, "artist-filterassign@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        await _create_shot_via_api(
            client,
            project.id,
            headers,
            name="Assigned",
            code="ASN01",
            assigned_to=artist.id,
        )
        await _create_shot_via_api(
            client,
            project.id,
            headers,
            name="Unassigned",
            code="UNA01",
        )

        resp = await client.get(
            f"/api/v1/projects/{project.id}/shots?assigned_to={artist.id}",
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["assigned_to"] == str(artist.id)

    async def test_list_shots_default_excludes_archived(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-archived@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        shot = await _create_shot_via_api(client, project.id, headers)
        await _create_shot_via_api(
            client,
            project.id,
            headers,
            name="Visible",
            code="VIS01",
        )

        # Archive one shot
        await client.post(f"/api/v1/shots/{shot['id']}/archive", headers=headers)

        resp = await client.get(
            f"/api/v1/projects/{project.id}/shots",
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        shot_ids = [s["id"] for s in data["items"]]
        assert shot["id"] not in shot_ids

    async def test_list_shots_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-list401@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)

        resp = await client.get(f"/api/v1/projects/{project.id}/shots")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# ARCHIVE / RESTORE
# ---------------------------------------------------------------------------


class TestArchiveRestoreShot:
    async def test_archive_shot_sets_archived_at(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-archive@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        shot = await _create_shot_via_api(client, project.id, headers)

        resp = await client.post(
            f"/api/v1/shots/{shot['id']}/archive",
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["archived_at"] is not None

    async def test_restore_shot_clears_archived_at(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-restore@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        shot = await _create_shot_via_api(client, project.id, headers)
        await client.post(f"/api/v1/shots/{shot['id']}/archive", headers=headers)

        resp = await client.post(
            f"/api/v1/shots/{shot['id']}/restore",
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["archived_at"] is None

    async def test_archive_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-archive401@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)

        shot = await _create_shot_via_api(
            client,
            project.id,
            _auth_headers(admin),
        )

        resp = await client.post(f"/api/v1/shots/{shot['id']}/archive")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE (force)
# ---------------------------------------------------------------------------


class TestDeleteShot:
    async def test_force_delete_requires_admin(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del@test.dev")
        lead = await _create_user(db_session, "lead-del@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, lead.id, RoleName.lead, project.id)
        headers_lead = _auth_headers(lead)

        shot = await _create_shot_via_api(
            client,
            project.id,
            _auth_headers(admin),
        )

        resp = await client.delete(
            f"/api/v1/shots/{shot['id']}?force=true",
            headers=headers_lead,
        )

        assert resp.status_code == 403

    async def test_force_delete_as_admin_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del204@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        shot = await _create_shot_via_api(client, project.id, headers)

        resp = await client.delete(
            f"/api/v1/shots/{shot['id']}?force=true",
            headers=headers,
        )

        assert resp.status_code == 204

        # Verify shot is gone
        get_resp = await client.get(
            f"/api/v1/shots/{shot['id']}",
            headers=headers,
        )
        assert get_resp.status_code == 404

    async def test_delete_with_invalid_id_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del404@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.delete(
            f"/api/v1/shots/{uuid.uuid4()}?force=true",
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404

    async def test_delete_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del401@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)

        shot = await _create_shot_via_api(
            client,
            project.id,
            _auth_headers(admin),
        )

        resp = await client.delete(f"/api/v1/shots/{shot['id']}?force=true")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# STATUS HISTORY
# ---------------------------------------------------------------------------


class TestShotStatusHistory:
    async def test_history_returns_transitions(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-hist@test.dev")
        artist = await _create_user(db_session, "artist-hist@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        await _assign_role(db_session, artist.id, RoleName.artist, project.id)
        headers = _auth_headers(admin)

        shot = await _create_shot_via_api(
            client,
            project.id,
            headers,
            assigned_to=artist.id,
        )

        # pending → in_progress
        await client.patch(
            f"/api/v1/shots/{shot['id']}/status",
            json={"status": "in_progress", "comment": "start"},
            headers=_auth_headers(artist),
        )
        # in_progress → review
        await client.patch(
            f"/api/v1/shots/{shot['id']}/status",
            json={"status": "review", "comment": "done"},
            headers=_auth_headers(artist),
        )

        resp = await client.get(
            f"/api/v1/shots/{shot['id']}/history?offset=0&limit=20",
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["shot_id"] == shot["id"]
        assert data["total"] >= 2
        assert len(data["items"]) >= 2

    async def test_history_respects_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-histpage@test.dev")
        artist = await _create_user(db_session, "artist-histpage@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        await _assign_role(db_session, artist.id, RoleName.artist, project.id)
        headers = _auth_headers(admin)

        shot = await _create_shot_via_api(
            client,
            project.id,
            headers,
            assigned_to=artist.id,
        )

        await client.patch(
            f"/api/v1/shots/{shot['id']}/status",
            json={"status": "in_progress"},
            headers=_auth_headers(artist),
        )
        await client.patch(
            f"/api/v1/shots/{shot['id']}/status",
            json={"status": "review"},
            headers=_auth_headers(artist),
        )

        resp = await client.get(
            f"/api/v1/shots/{shot['id']}/history?offset=0&limit=1",
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert len(data["items"]) == 1

    async def test_history_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-hist401@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)

        shot = await _create_shot_via_api(
            client,
            project.id,
            _auth_headers(admin),
        )

        resp = await client.get(f"/api/v1/shots/{shot['id']}/history")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# LIST SHOT FILES
# ---------------------------------------------------------------------------


class TestListShotFiles:
    async def test_list_shot_files_returns_uploaded_files(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(settings, "storage_backend", "local")
        monkeypatch.setattr(settings, "local_storage_root", str(tmp_path))

        admin = await _create_user(db_session, "admin-files@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        shot = await _create_shot_via_api(client, project.id, headers)

        upload_resp = await client.post(
            f"/api/v1/projects/{project.id}/files/upload",
            files={"upload": ("render.exr", b"fake exr data", "image/x-exr")},
            data={"shot_id": shot["id"]},
            headers=headers,
        )
        assert upload_resp.status_code == 200

        resp = await client.get(
            f"/api/v1/shots/{shot['id']}/files",
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 1
        assert data["items"][0]["shot_id"] == shot["id"]

    async def test_list_shot_files_empty_returns_empty_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-nofiles@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)
        headers = _auth_headers(admin)

        shot = await _create_shot_via_api(client, project.id, headers)

        resp = await client.get(
            f"/api/v1/shots/{shot['id']}/files",
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 0
        assert data["total"] == 0

    async def test_list_shot_files_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-files401@test.dev")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        project = await _create_project(db_session, admin)
        await _assign_role(db_session, admin.id, RoleName.lead, project.id)

        shot = await _create_shot_via_api(
            client,
            project.id,
            _auth_headers(admin),
        )

        resp = await client.get(f"/api/v1/shots/{shot['id']}/files")

        assert resp.status_code == 401

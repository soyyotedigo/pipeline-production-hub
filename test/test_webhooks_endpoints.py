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

pytestmark = pytest.mark.webhooks


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


async def _create_project(
    db_session: AsyncSession,
    owner: User,
    *,
    name: str = "Webhook Test Project",
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=name,
        code=f"WH{uuid.uuid4().hex[:6].upper()}",
        status=ProjectStatus.pending,
        created_by=owner.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _create_webhook_via_api(
    client: AsyncClient,
    project_id: uuid.UUID,
    headers: dict[str, str],
    *,
    url: str = "https://example.com/hook",
    events: list[str] | None = None,
) -> dict:
    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "project_id": str(project_id),
            "url": url,
            "events": events or ["status.changed"],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


class TestCreateWebhook:
    async def test_create_returns_201_with_signing_secret(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-create@wh.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)

        resp = await client.post(
            "/api/v1/webhooks",
            json={
                "project_id": str(project.id),
                "url": "https://example.com/hook",
                "events": ["status.changed", "file.uploaded"],
            },
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == str(project.id)
        assert data["url"] == "https://example.com/hook"
        assert "status.changed" in data["events"]
        assert data["is_active"] is True
        assert "signing_secret" in data
        assert data["signing_secret"] is not None

    async def test_create_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-noauth@wh.test")
        project = await _create_project(db_session, admin)

        resp = await client.post(
            "/api/v1/webhooks",
            json={
                "project_id": str(project.id),
                "url": "https://example.com/h",
                "events": ["status.changed"],
            },
        )

        assert resp.status_code == 401

    async def test_create_via_project_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-projhook@wh.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)

        resp = await client.post(
            f"/api/v1/projects/{project.id}/webhooks",
            json={"url": "https://example.com/proj-hook", "events": ["assignment.changed"]},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["project_id"] == str(project.id)
        assert "signing_secret" in data


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------


class TestListWebhooks:
    async def test_list_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-list@wh.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        await _create_webhook_via_api(client, project.id, headers, url="https://example.com/h1")
        await _create_webhook_via_api(client, project.id, headers, url="https://example.com/h2")

        resp = await client.get("/api/v1/webhooks", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    async def test_list_filter_by_project(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-filter@wh.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project_a = await _create_project(db_session, admin, name="Project A")
        project_b = await _create_project(db_session, admin, name="Project B")
        headers = _auth_headers(admin)
        await _create_webhook_via_api(client, project_a.id, headers, url="https://example.com/ha")
        await _create_webhook_via_api(client, project_b.id, headers, url="https://example.com/hb")

        resp = await client.get(f"/api/v1/webhooks?project_id={project_a.id}", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_list_project_webhooks_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-projlist@wh.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        await _create_webhook_via_api(client, project.id, headers)

        resp = await client.get(f"/api/v1/projects/{project.id}/webhooks", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_list_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.get("/api/v1/webhooks")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------


class TestUpdateWebhook:
    async def test_update_url_and_events(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd@wh.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        created = await _create_webhook_via_api(client, project.id, headers)

        resp = await client.patch(
            f"/api/v1/webhooks/{created['id']}",
            json={"url": "https://updated.com/hook", "events": ["file.uploaded"]},
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "https://updated.com/hook"
        assert data["events"] == ["file.uploaded"]

    async def test_update_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd404@wh.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.patch(
            f"/api/v1/webhooks/{uuid.uuid4()}",
            json={"url": "https://ghost.com/hook"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# ARCHIVE / RESTORE
# ---------------------------------------------------------------------------


class TestArchiveRestoreWebhook:
    async def test_archive_sets_inactive(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-arch@wh.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        created = await _create_webhook_via_api(client, project.id, headers)

        resp = await client.post(f"/api/v1/webhooks/{created['id']}/archive", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    async def test_restore_sets_active(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-restore@wh.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        created = await _create_webhook_via_api(client, project.id, headers)
        await client.post(f"/api/v1/webhooks/{created['id']}/archive", headers=headers)

        resp = await client.post(f"/api/v1/webhooks/{created['id']}/restore", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["is_active"] is True


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


class TestDeleteWebhook:
    async def test_admin_delete_with_force_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del@wh.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        created = await _create_webhook_via_api(client, project.id, headers)

        resp = await client.delete(f"/api/v1/webhooks/{created['id']}?force=true", headers=headers)

        assert resp.status_code == 204

    async def test_delete_without_force_returns_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-noforce@wh.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        created = await _create_webhook_via_api(client, project.id, headers)

        resp = await client.delete(f"/api/v1/webhooks/{created['id']}", headers=headers)

        assert resp.status_code == 422

    async def test_non_admin_cannot_delete_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-artdel@wh.test")
        artist = await _create_user(db_session, "artist-del@wh.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        await _assign_role(db_session, artist.id, RoleName.artist)
        project = await _create_project(db_session, admin)
        headers_admin = _auth_headers(admin)
        created = await _create_webhook_via_api(client, project.id, headers_admin)

        resp = await client.delete(
            f"/api/v1/webhooks/{created['id']}?force=true",
            headers=_auth_headers(artist),
        )

        assert resp.status_code == 403

    async def test_delete_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del404@wh.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.delete(
            f"/api/v1/webhooks/{uuid.uuid4()}?force=true",
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404

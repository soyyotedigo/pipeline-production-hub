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

Delivery = models_module.Delivery
DeliveryItem = models_module.DeliveryItem
DeliveryStatus = models_module.DeliveryStatus
Project = models_module.Project
ProjectStatus = models_module.ProjectStatus
Role = models_module.Role
RoleName = models_module.RoleName
Shot = models_module.Shot
ShotStatus = models_module.ShotStatus
User = models_module.User
UserRole = models_module.UserRole
Version = models_module.Version
VersionStatus = models_module.VersionStatus

pytestmark = pytest.mark.deliveries


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
    name: str = "Delivery Project",
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=name,
        code=f"DL{uuid.uuid4().hex[:6].upper()}",
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
        name="DeliveryShot",
        code=f"DS{uuid.uuid4().hex[:4].upper()}",
        status=ShotStatus.pending,
        frame_start=1001,
        frame_end=1040,
    )
    db_session.add(shot)
    await db_session.commit()
    await db_session.refresh(shot)
    return shot


async def _create_version(
    db_session: AsyncSession,
    project: Project,
    shot: Shot,
    user: User,
) -> Version:
    version = Version(
        id=uuid.uuid4(),
        project_id=project.id,
        shot_id=shot.id,
        code=f"v{uuid.uuid4().hex[:4].upper()}",
        version_number=1,
        status=VersionStatus.pending_review,
        submitted_by=user.id,
    )
    db_session.add(version)
    await db_session.commit()
    await db_session.refresh(version)
    return version


async def _create_delivery_via_api(
    client: AsyncClient,
    project_id: uuid.UUID,
    headers: dict[str, str],
    *,
    name: str = "Test Delivery",
    recipient: str | None = None,
    notes: str | None = None,
) -> dict:
    payload: dict = {"name": name}
    if recipient:
        payload["recipient"] = recipient
    if notes:
        payload["notes"] = notes
    resp = await client.post(
        f"/api/v1/projects/{project_id}/deliveries", json=payload, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _add_item_via_api(
    client: AsyncClient,
    delivery_id: uuid.UUID,
    version_id: uuid.UUID,
    headers: dict[str, str],
) -> dict:
    resp = await client.post(
        f"/api/v1/deliveries/{delivery_id}/items",
        json={"version_id": str(version_id)},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


class TestCreateDelivery:
    async def test_create_returns_201_with_correct_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-create@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)

        resp = await client.post(
            f"/api/v1/projects/{project.id}/deliveries",
            json={"name": "Monday Delivery"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Monday Delivery"
        assert data["status"] == "preparing"
        assert data["project_id"] == str(project.id)
        assert data["created_by"] == str(admin.id)
        assert "id" in data

    async def test_create_with_all_optional_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-full@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)

        resp = await client.post(
            f"/api/v1/projects/{project.id}/deliveries",
            json={
                "name": "Full Delivery",
                "delivery_date": "2026-04-01",
                "recipient": "client@studio.com",
                "notes": "Reviewed and approved.",
            },
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["recipient"] == "client@studio.com"
        assert data["notes"] == "Reviewed and approved."
        assert data["delivery_date"] == "2026-04-01"

    async def test_create_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-noauth@del.test")
        project = await _create_project(db_session, admin)

        resp = await client.post(
            f"/api/v1/projects/{project.id}/deliveries",
            json={"name": "No Auth"},
        )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------


class TestListDeliveries:
    async def test_list_returns_200_with_deliveries(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-list@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        await _create_delivery_via_api(client, project.id, headers, name="D1")
        await _create_delivery_via_api(client, project.id, headers, name="D2")

        resp = await client.get(f"/api/v1/projects/{project.id}/deliveries", headers=headers)

        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    async def test_list_filter_by_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-filterstatus@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers, name="ToSend")
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status",
            json={"status": "sent"},
            headers=headers,
        )
        await _create_delivery_via_api(client, project.id, headers, name="StillPreparing")

        resp = await client.get(
            f"/api/v1/projects/{project.id}/deliveries?status=sent", headers=headers
        )

        assert resp.status_code == 200
        assert all(d["status"] == "sent" for d in resp.json())

    async def test_list_filter_by_recipient(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-filterrecip@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        await _create_delivery_via_api(client, project.id, headers, name="R1", recipient="studio-a")
        await _create_delivery_via_api(client, project.id, headers, name="R2", recipient="studio-b")

        resp = await client.get(
            f"/api/v1/projects/{project.id}/deliveries?recipient=studio-a", headers=headers
        )

        assert resp.status_code == 200
        names = [d["name"] for d in resp.json()]
        assert "R1" in names
        assert "R2" not in names

    async def test_list_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-listnoauth@del.test")
        project = await _create_project(db_session, admin)

        resp = await client.get(f"/api/v1/projects/{project.id}/deliveries")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


class TestGetDelivery:
    async def test_get_returns_200_with_correct_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        created = await _create_delivery_via_api(client, project.id, headers, name="GetMe")

        resp = await client.get(f"/api/v1/deliveries/{created['id']}", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == created["id"]
        assert data["name"] == "GetMe"

    async def test_get_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get404@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.get(f"/api/v1/deliveries/{uuid.uuid4()}", headers=_auth_headers(admin))

        assert resp.status_code == 404

    async def test_get_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-getauth@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        created = await _create_delivery_via_api(
            client, project.id, _auth_headers(admin), name="AuthGet"
        )

        resp = await client.get(f"/api/v1/deliveries/{created['id']}")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------


class TestUpdateDelivery:
    async def test_update_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        created = await _create_delivery_via_api(client, project.id, headers, name="OldName")

        resp = await client.patch(
            f"/api/v1/deliveries/{created['id']}",
            json={"name": "NewName"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "NewName"

    async def test_update_all_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-updall@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        created = await _create_delivery_via_api(client, project.id, headers, name="Before")

        resp = await client.patch(
            f"/api/v1/deliveries/{created['id']}",
            json={
                "name": "After",
                "delivery_date": "2026-05-01",
                "recipient": "updated@client.com",
                "notes": "Updated notes",
            },
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "After"
        assert data["delivery_date"] == "2026-05-01"
        assert data["recipient"] == "updated@client.com"
        assert data["notes"] == "Updated notes"

    async def test_update_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd404@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.patch(
            f"/api/v1/deliveries/{uuid.uuid4()}",
            json={"name": "Ghost"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# STATUS TRANSITIONS
# ---------------------------------------------------------------------------


class TestUpdateDeliveryStatus:
    async def test_transition_preparing_to_sent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-tosent@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)

        resp = await client.patch(
            f"/api/v1/deliveries/{d['id']}/status",
            json={"status": "sent"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "sent"

    async def test_transition_sent_to_acknowledged(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-toacknow@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "sent"}, headers=headers
        )

        resp = await client.patch(
            f"/api/v1/deliveries/{d['id']}/status",
            json={"status": "acknowledged"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "acknowledged"

    async def test_transition_acknowledged_to_accepted(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-toaccepted@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "sent"}, headers=headers
        )
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "acknowledged"}, headers=headers
        )

        resp = await client.patch(
            f"/api/v1/deliveries/{d['id']}/status",
            json={"status": "accepted"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    async def test_transition_acknowledged_to_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-torejected@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "sent"}, headers=headers
        )
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "acknowledged"}, headers=headers
        )

        resp = await client.patch(
            f"/api/v1/deliveries/{d['id']}/status",
            json={"status": "rejected"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    async def test_transition_rejected_to_preparing(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-topreparing@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "sent"}, headers=headers
        )
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "acknowledged"}, headers=headers
        )
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "rejected"}, headers=headers
        )

        resp = await client.patch(
            f"/api/v1/deliveries/{d['id']}/status",
            json={"status": "preparing"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "preparing"

    async def test_invalid_transition_preparing_to_acknowledged_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-badjump@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)

        resp = await client.patch(
            f"/api/v1/deliveries/{d['id']}/status",
            json={"status": "acknowledged"},
            headers=headers,
        )

        assert resp.status_code == 403

    async def test_accepted_is_terminal_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-terminal@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "sent"}, headers=headers
        )
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "acknowledged"}, headers=headers
        )
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "accepted"}, headers=headers
        )

        resp = await client.patch(
            f"/api/v1/deliveries/{d['id']}/status",
            json={"status": "rejected"},
            headers=headers,
        )

        assert resp.status_code == 403

    async def test_status_update_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-status404@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.patch(
            f"/api/v1/deliveries/{uuid.uuid4()}/status",
            json={"status": "sent"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


class TestDeleteDelivery:
    async def test_delete_preparing_delivery_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers, name="DeleteMe")

        resp = await client.delete(f"/api/v1/deliveries/{d['id']}", headers=headers)

        assert resp.status_code == 204

    async def test_delete_sent_delivery_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-delsent@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers, name="SentDelete")
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "sent"}, headers=headers
        )

        resp = await client.delete(f"/api/v1/deliveries/{d['id']}", headers=headers)

        assert resp.status_code == 403

    async def test_delete_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del404@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.delete(
            f"/api/v1/deliveries/{uuid.uuid4()}", headers=_auth_headers(admin)
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELIVERY ITEMS
# ---------------------------------------------------------------------------


class TestDeliveryItems:
    async def test_add_item_returns_201_with_correct_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-additem@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        version = await _create_version(db_session, project, shot, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)

        resp = await client.post(
            f"/api/v1/deliveries/{d['id']}/items",
            json={"version_id": str(version.id)},
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["version_id"] == str(version.id)
        assert data["delivery_id"] == d["id"]
        assert data["shot_id"] == str(shot.id)

    async def test_add_duplicate_version_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-dupitem@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        version = await _create_version(db_session, project, shot, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)
        await _add_item_via_api(client, d["id"], version.id, headers)

        resp = await client.post(
            f"/api/v1/deliveries/{d['id']}/items",
            json={"version_id": str(version.id)},
            headers=headers,
        )

        assert resp.status_code == 409

    async def test_add_item_to_sent_delivery_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-lockeditem@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        version = await _create_version(db_session, project, shot, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "sent"}, headers=headers
        )

        resp = await client.post(
            f"/api/v1/deliveries/{d['id']}/items",
            json={"version_id": str(version.id)},
            headers=headers,
        )

        assert resp.status_code == 403

    async def test_add_item_version_from_different_project_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-crossitem@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project_a = await _create_project(db_session, admin, name="Project A")
        project_b = await _create_project(db_session, admin, name="Project B")
        shot_b = await _create_shot(db_session, project_b)
        version_b = await _create_version(db_session, project_b, shot_b, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project_a.id, headers)

        resp = await client.post(
            f"/api/v1/deliveries/{d['id']}/items",
            json={"version_id": str(version_b.id)},
            headers=headers,
        )

        assert resp.status_code == 403

    async def test_add_item_nonexistent_version_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-noversion@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)

        resp = await client.post(
            f"/api/v1/deliveries/{d['id']}/items",
            json={"version_id": str(uuid.uuid4())},
            headers=headers,
        )

        assert resp.status_code == 404

    async def test_add_item_nonexistent_delivery_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-nodelivery@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        version = await _create_version(db_session, project, shot, admin)

        resp = await client.post(
            f"/api/v1/deliveries/{uuid.uuid4()}/items",
            json={"version_id": str(version.id)},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404

    async def test_list_items_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-listitems@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        version = await _create_version(db_session, project, shot, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)
        await _add_item_via_api(client, d["id"], version.id, headers)

        resp = await client.get(f"/api/v1/deliveries/{d['id']}/items", headers=headers)

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_remove_item_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-rmitem@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        version = await _create_version(db_session, project, shot, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)
        item = await _add_item_via_api(client, d["id"], version.id, headers)

        resp = await client.delete(f"/api/v1/delivery-items/{item['id']}", headers=headers)

        assert resp.status_code == 204

    async def test_remove_item_from_sent_delivery_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-rmlockeditem@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        version = await _create_version(db_session, project, shot, admin)
        headers = _auth_headers(admin)
        d = await _create_delivery_via_api(client, project.id, headers)
        item = await _add_item_via_api(client, d["id"], version.id, headers)
        await client.patch(
            f"/api/v1/deliveries/{d['id']}/status", json={"status": "sent"}, headers=headers
        )

        resp = await client.delete(f"/api/v1/delivery-items/{item['id']}", headers=headers)

        assert resp.status_code == 403

    async def test_remove_nonexistent_item_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-rmitem404@del.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.delete(
            f"/api/v1/delivery-items/{uuid.uuid4()}", headers=_auth_headers(admin)
        )

        assert resp.status_code == 404

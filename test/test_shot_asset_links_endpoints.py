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

pytestmark = pytest.mark.shot_asset_links


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
    db_session: AsyncSession, owner: User, *, name: str = "Link Project"
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=name,
        code=f"LK{uuid.uuid4().hex[:6].upper()}",
        status=ProjectStatus.pending,
        created_by=owner.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _create_shot(db_session: AsyncSession, project: Project, *, suffix: str = "") -> Shot:
    shot = Shot(
        id=uuid.uuid4(),
        project_id=project.id,
        name=f"Shot{suffix}",
        code=f"SH{uuid.uuid4().hex[:4].upper()}",
        status=ShotStatus.pending,
        frame_start=1001,
        frame_end=1040,
    )
    db_session.add(shot)
    await db_session.commit()
    await db_session.refresh(shot)
    return shot


async def _create_asset(
    db_session: AsyncSession,
    project: Project,
    *,
    name: str | None = None,
) -> Asset:
    asset = Asset(
        id=uuid.uuid4(),
        project_id=project.id,
        name=name or f"Asset-{uuid.uuid4().hex[:6]}",
        asset_type=AssetType.prop,
        status=AssetStatus.pending,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)
    return asset


# ---------------------------------------------------------------------------
# CREATE LINK
# ---------------------------------------------------------------------------


class TestCreateLink:
    async def test_create_link_returns_201_with_default_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-create@sal.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        asset = await _create_asset(db_session, project)
        headers = _auth_headers(admin)

        resp = await client.post(
            f"/api/v1/shots/{shot.id}/assets",
            json={"asset_id": str(asset.id)},
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["shot_id"] == str(shot.id)
        assert data["asset_id"] == str(asset.id)
        assert data["link_type"] == "uses"

    async def test_create_link_with_explicit_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-type@sal.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        asset = await _create_asset(db_session, project)
        headers = _auth_headers(admin)

        resp = await client.post(
            f"/api/v1/shots/{shot.id}/assets",
            json={"asset_id": str(asset.id), "link_type": "references"},
            headers=headers,
        )

        assert resp.status_code == 201
        assert resp.json()["link_type"] == "references"

    async def test_duplicate_link_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-dup@sal.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        asset = await _create_asset(db_session, project)
        headers = _auth_headers(admin)

        await client.post(
            f"/api/v1/shots/{shot.id}/assets", json={"asset_id": str(asset.id)}, headers=headers
        )
        resp = await client.post(
            f"/api/v1/shots/{shot.id}/assets",
            json={"asset_id": str(asset.id)},
            headers=headers,
        )

        assert resp.status_code == 409

    async def test_cross_project_link_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-cross@sal.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project_a = await _create_project(db_session, admin, name="Project A")
        project_b = await _create_project(db_session, admin, name="Project B")
        shot = await _create_shot(db_session, project_a)
        asset = await _create_asset(db_session, project_b)
        headers = _auth_headers(admin)

        resp = await client.post(
            f"/api/v1/shots/{shot.id}/assets",
            json={"asset_id": str(asset.id)},
            headers=headers,
        )

        assert resp.status_code == 422

    async def test_create_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-noauth@sal.test")
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        asset = await _create_asset(db_session, project)

        resp = await client.post(
            f"/api/v1/shots/{shot.id}/assets",
            json={"asset_id": str(asset.id)},
        )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# LIST SHOT ASSETS
# ---------------------------------------------------------------------------


class TestListShotAssets:
    async def test_list_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-list@sal.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        asset_a = await _create_asset(db_session, project, name="AssetA")
        asset_b = await _create_asset(db_session, project, name="AssetB")
        headers = _auth_headers(admin)
        await client.post(
            f"/api/v1/shots/{shot.id}/assets", json={"asset_id": str(asset_a.id)}, headers=headers
        )
        await client.post(
            f"/api/v1/shots/{shot.id}/assets", json={"asset_id": str(asset_b.id)}, headers=headers
        )

        resp = await client.get(f"/api/v1/shots/{shot.id}/assets", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_list_filter_by_link_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-typefilter@sal.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        asset_a = await _create_asset(db_session, project, name="FilterA")
        asset_b = await _create_asset(db_session, project, name="FilterB")
        headers = _auth_headers(admin)
        await client.post(
            f"/api/v1/shots/{shot.id}/assets",
            json={"asset_id": str(asset_a.id), "link_type": "uses"},
            headers=headers,
        )
        await client.post(
            f"/api/v1/shots/{shot.id}/assets",
            json={"asset_id": str(asset_b.id), "link_type": "references"},
            headers=headers,
        )

        resp = await client.get(f"/api/v1/shots/{shot.id}/assets?link_type=uses", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["total"] == 1


# ---------------------------------------------------------------------------
# BULK LINK
# ---------------------------------------------------------------------------


class TestBulkLink:
    async def test_bulk_link_creates_multiple(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-bulk@sal.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        asset_a = await _create_asset(db_session, project, name="BulkA")
        asset_b = await _create_asset(db_session, project, name="BulkB")
        headers = _auth_headers(admin)

        resp = await client.post(
            f"/api/v1/shots/{shot.id}/assets/bulk",
            json={"links": [{"asset_id": str(asset_a.id)}, {"asset_id": str(asset_b.id)}]},
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert len(data["created"]) == 2
        assert data["skipped"] == []

    async def test_bulk_link_skips_duplicates(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-bulkdup@sal.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        asset = await _create_asset(db_session, project, name="BulkDup")
        headers = _auth_headers(admin)
        await client.post(
            f"/api/v1/shots/{shot.id}/assets", json={"asset_id": str(asset.id)}, headers=headers
        )

        resp = await client.post(
            f"/api/v1/shots/{shot.id}/assets/bulk",
            json={"links": [{"asset_id": str(asset.id)}]},
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert len(data["skipped"]) == 1
        assert data["created"] == []


# ---------------------------------------------------------------------------
# LIST ASSET SHOTS (IMPACT ANALYSIS)
# ---------------------------------------------------------------------------


class TestListAssetShots:
    async def test_list_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-impact@sal.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot_a = await _create_shot(db_session, project, suffix="A")
        shot_b = await _create_shot(db_session, project, suffix="B")
        asset = await _create_asset(db_session, project, name="SharedAsset")
        headers = _auth_headers(admin)
        await client.post(
            f"/api/v1/shots/{shot_a.id}/assets", json={"asset_id": str(asset.id)}, headers=headers
        )
        await client.post(
            f"/api/v1/shots/{shot_b.id}/assets", json={"asset_id": str(asset.id)}, headers=headers
        )

        resp = await client.get(f"/api/v1/assets/{asset.id}/shots", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2


# ---------------------------------------------------------------------------
# DELETE LINK
# ---------------------------------------------------------------------------


class TestDeleteLink:
    async def test_delete_link_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del@sal.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        asset = await _create_asset(db_session, project, name="DelAsset")
        headers = _auth_headers(admin)
        link_resp = await client.post(
            f"/api/v1/shots/{shot.id}/assets", json={"asset_id": str(asset.id)}, headers=headers
        )
        link_id = link_resp.json()["id"]

        resp = await client.delete(f"/api/v1/shot-asset-links/{link_id}", headers=headers)

        assert resp.status_code == 204

    async def test_delete_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del404@sal.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.delete(
            f"/api/v1/shot-asset-links/{uuid.uuid4()}", headers=_auth_headers(admin)
        )

        assert resp.status_code == 404

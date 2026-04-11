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
AssetStatus = models_module.AssetStatus
Role = models_module.Role
RoleName = models_module.RoleName
User = models_module.User
UserRole = models_module.UserRole

pytestmark = pytest.mark.assets


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
async def test_project_assets_crud_filters_asset_status_and_overview(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-assets23@vfxhub.dev")
    lead = await _create_user(db_session, "lead-assets23@vfxhub.dev")
    artist = await _create_user(db_session, "artist-assets23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    create_project = await client.post(
        "/api/v1/projects",
        json={"name": "Assets Project", "code": "AST23"},
        headers=_auth_headers(admin),
    )
    project_id = create_project.json()["id"]

    await _assign_role(db_session, lead.id, RoleName.lead, uuid.UUID(project_id))
    await _assign_role(db_session, artist.id, RoleName.artist, uuid.UUID(project_id))

    create_asset = await client.post(
        f"/api/v1/projects/{project_id}/assets",
        json={
            "name": "Dragon",
            "asset_type": "character",
            "assigned_to": str(artist.id),
        },
        headers=_auth_headers(lead),
    )
    assert create_asset.status_code == 200
    create_asset_payload = create_asset.json()
    asset_id = create_asset_payload["id"]
    assert create_asset_payload["code"] == "DRAGON"

    patch_asset = await client.patch(
        f"/api/v1/assets/{asset_id}",
        json={"name": "Dragon Hero", "asset_type": "character"},
        headers=_auth_headers(lead),
    )
    assert patch_asset.status_code == 200
    assert patch_asset.json()["name"] == "Dragon Hero"

    to_in_progress = await client.patch(
        f"/api/v1/assets/{asset_id}/status",
        json={"status": "in_progress", "comment": "start asset"},
        headers=_auth_headers(artist),
    )
    assert to_in_progress.status_code == 200

    to_review = await client.patch(
        f"/api/v1/assets/{asset_id}/status",
        json={"status": "review", "comment": "ready for lead"},
        headers=_auth_headers(artist),
    )
    assert to_review.status_code == 200

    list_assets = await client.get(
        f"/api/v1/projects/{project_id}/assets?status=review&assigned_to={artist.id}&asset_type=character",
        headers=_auth_headers(lead),
    )
    assert list_assets.status_code == 200
    asset_payload = list_assets.json()
    assert asset_payload["total"] == 1
    assert asset_payload["items"][0]["id"] == asset_id

    overview = await client.get(
        f"/api/v1/projects/{project_id}/overview", headers=_auth_headers(artist)
    )
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["project_id"] == project_id
    assert overview_payload["total_assets"] >= 1

    # No single-asset GET route exists; status already confirmed by the list filter above.


@pytest.mark.asyncio
async def test_asset_archive_restore_and_force_delete(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-lifecycle-asset@vfxhub.dev")
    lead = await _create_user(db_session, "lead-lifecycle-asset@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    project_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Lifecycle Asset", "code": "LAS23"},
        headers=_auth_headers(admin),
    )
    assert project_resp.status_code == 200
    project_id = project_resp.json()["id"]
    await _assign_role(db_session, lead.id, RoleName.lead, uuid.UUID(project_id))

    asset_resp = await client.post(
        f"/api/v1/projects/{project_id}/assets",
        json={"name": "Asset Life", "asset_type": "prop"},
        headers=_auth_headers(lead),
    )
    assert asset_resp.status_code == 200
    asset_id = asset_resp.json()["id"]

    archive_asset = await client.post(
        f"/api/v1/assets/{asset_id}/archive", headers=_auth_headers(lead)
    )
    assert archive_asset.status_code == 200
    assert archive_asset.json()["archived_at"] is not None

    restore_asset = await client.post(
        f"/api/v1/assets/{asset_id}/restore", headers=_auth_headers(lead)
    )
    assert restore_asset.status_code == 200
    assert restore_asset.json()["archived_at"] is None

    deny_asset_delete = await client.delete(
        f"/api/v1/assets/{asset_id}?force=true",
        headers=_auth_headers(lead),
    )
    assert deny_asset_delete.status_code == 403

    allow_asset_delete = await client.delete(
        f"/api/v1/assets/{asset_id}?force=true",
        headers=_auth_headers(admin),
    )
    assert allow_asset_delete.status_code == 204


@pytest.mark.asyncio
async def test_asset_status_delivered_requires_admin(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-assetdeliver23@vfxhub.dev")
    supervisor = await _create_user(db_session, "supervisor-assetdeliver23@vfxhub.dev")
    artist = await _create_user(db_session, "artist-assetdeliver23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    create_project = await client.post(
        "/api/v1/projects",
        json={"name": "Deliver Asset Project", "code": "DEL23"},
        headers=_auth_headers(admin),
    )
    project_id = create_project.json()["id"]

    await _assign_role(db_session, supervisor.id, RoleName.supervisor, uuid.UUID(project_id))
    await _assign_role(db_session, artist.id, RoleName.artist, uuid.UUID(project_id))

    create_asset = await client.post(
        f"/api/v1/projects/{project_id}/assets",
        json={"name": "Spaceship", "asset_type": "prop", "assigned_to": str(artist.id)},
        headers=_auth_headers(supervisor),
    )
    asset_id = create_asset.json()["id"]

    await client.patch(
        f"/api/v1/assets/{asset_id}/status",
        json={"status": "in_progress", "comment": "start"},
        headers=_auth_headers(artist),
    )
    await client.patch(
        f"/api/v1/assets/{asset_id}/status",
        json={"status": "review", "comment": "review"},
        headers=_auth_headers(artist),
    )
    await client.patch(
        f"/api/v1/assets/{asset_id}/status",
        json={"status": "revision", "comment": "fixes"},
        headers=_auth_headers(supervisor),
    )
    await client.patch(
        f"/api/v1/assets/{asset_id}/status",
        json={"status": "in_progress", "comment": "rework"},
        headers=_auth_headers(artist),
    )
    await client.patch(
        f"/api/v1/assets/{asset_id}/status",
        json={"status": "review", "comment": "ready"},
        headers=_auth_headers(artist),
    )
    await client.patch(
        f"/api/v1/assets/{asset_id}/status",
        json={"status": "revision", "comment": "minor fix"},
        headers=_auth_headers(supervisor),
    )
    await client.patch(
        f"/api/v1/assets/{asset_id}/status",
        json={"status": "approved", "comment": "approved"},
        headers=_auth_headers(supervisor),
    )

    denied = await client.patch(
        f"/api/v1/assets/{asset_id}/status",
        json={"status": "delivered", "comment": "supervisor deliver"},
        headers=_auth_headers(supervisor),
    )
    assert denied.status_code == 403

    allowed = await client.patch(
        f"/api/v1/assets/{asset_id}/status",
        json={"status": "delivered", "comment": "admin deliver"},
        headers=_auth_headers(admin),
    )
    assert allowed.status_code == 200
    assert allowed.json()["new_status"] == AssetStatus.delivered.value

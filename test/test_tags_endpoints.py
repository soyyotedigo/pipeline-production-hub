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

    from app.models.sequence import Sequence

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

pytestmark = pytest.mark.tags


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
    db_session: AsyncSession, owner: User, *, name: str = "Tag Project"
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=name,
        code=f"TG{uuid.uuid4().hex[:6].upper()}",
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
        name="TagShot",
        code=f"TS{uuid.uuid4().hex[:4].upper()}",
        status=ShotStatus.pending,
        frame_start=1001,
        frame_end=1040,
    )
    db_session.add(shot)
    await db_session.commit()
    await db_session.refresh(shot)
    return shot


async def _create_sequence(db_session: AsyncSession, project: Project) -> Sequence:
    from app.models.sequence import Sequence, SequenceStatus

    seq = Sequence(
        id=uuid.uuid4(),
        project_id=project.id,
        name="TagSeq",
        code=f"SQ{uuid.uuid4().hex[:4].upper()}",
        status=SequenceStatus.active,
    )
    db_session.add(seq)
    await db_session.commit()
    await db_session.refresh(seq)
    return seq


async def _create_asset(db_session: AsyncSession, project: Project) -> Asset:
    asset = Asset(
        id=uuid.uuid4(),
        project_id=project.id,
        name=f"TagAsset-{uuid.uuid4().hex[:4]}",
        asset_type=AssetType.prop,
        status=AssetStatus.pending,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)
    return asset


async def _create_tag_via_api(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str,
    project_id: uuid.UUID | None = None,
    color: str | None = None,
) -> dict:
    payload: dict = {"name": name}
    if project_id is not None:
        payload["project_id"] = str(project_id)
    if color is not None:
        payload["color"] = color
    resp = await client.post("/tags", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


class TestCreateTag:
    async def test_create_global_tag_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-create@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.post(
            "/tags",
            json={"name": "hero"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "hero"
        assert data["project_id"] is None

    async def test_create_project_tag(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-prjtag@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)

        resp = await client.post(
            "/tags",
            json={"name": "wip", "project_id": str(project.id)},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        assert resp.json()["project_id"] == str(project.id)

    async def test_name_normalized_to_lowercase(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-lower@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.post(
            "/tags",
            json={"name": "HERO_SHOT"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        assert resp.json()["name"] == "hero_shot"

    async def test_duplicate_name_in_same_project_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-dup@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)

        await _create_tag_via_api(client, headers, name="dupname", project_id=project.id)
        resp = await client.post(
            "/tags",
            json={"name": "dupname", "project_id": str(project.id)},
            headers=headers,
        )

        assert resp.status_code == 409

    async def test_create_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.post("/tags", json={"name": "noauth"})

        assert resp.status_code == 401

    async def test_create_project_tag_via_project_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-prjep@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)

        resp = await client.post(
            f"/projects/{project.id}/tags",
            json={"name": "projep"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        assert resp.json()["project_id"] == str(project.id)


# ---------------------------------------------------------------------------
# LIST / SEARCH / GET
# ---------------------------------------------------------------------------


class TestListAndGetTags:
    async def test_list_all_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-list@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        headers = _auth_headers(admin)
        await _create_tag_via_api(client, headers, name="listtag1")
        await _create_tag_via_api(client, headers, name="listtag2")

        resp = await client.get("/tags", headers=headers)

        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert "listtag1" in names
        assert "listtag2" in names

    async def test_list_filter_by_project(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-prjfilter@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        await _create_tag_via_api(client, headers, name="scopedtag", project_id=project.id)
        await _create_tag_via_api(client, headers, name="globaltag")

        resp = await client.get(f"/tags?project_id={project.id}", headers=headers)

        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert "scopedtag" in names

    async def test_search_tags(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-search@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        headers = _auth_headers(admin)
        await _create_tag_via_api(client, headers, name="searchable")
        await _create_tag_via_api(client, headers, name="other")

        resp = await client.get("/tags/search?q=search", headers=headers)

        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert "searchable" in names
        assert "other" not in names

    async def test_get_tag_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        headers = _auth_headers(admin)
        created = await _create_tag_via_api(client, headers, name="gettag")

        resp = await client.get(f"/tags/{created['id']}", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["name"] == "gettag"

    async def test_get_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get404@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.get(f"/tags/{uuid.uuid4()}", headers=_auth_headers(admin))

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# UPDATE / DELETE
# ---------------------------------------------------------------------------


class TestUpdateDeleteTag:
    async def test_update_tag(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        headers = _auth_headers(admin)
        created = await _create_tag_via_api(client, headers, name="oldname")

        resp = await client.patch(
            f"/tags/{created['id']}",
            json={"name": "newname", "color": "#FF0000"},
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "newname"
        assert data["color"] == "#FF0000"

    async def test_delete_tag_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        headers = _auth_headers(admin)
        created = await _create_tag_via_api(client, headers, name="deltag")

        resp = await client.delete(f"/tags/{created['id']}", headers=headers)

        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# ENTITY ATTACHMENT (Shot)
# ---------------------------------------------------------------------------


class TestShotTags:
    async def test_attach_tag_to_shot_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-shottag@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        tag = await _create_tag_via_api(client, headers, name="shotatag")

        resp = await client.post(
            f"/shots/{shot.id}/tags",
            json={"tag_id": tag["id"]},
            headers=headers,
        )

        assert resp.status_code == 201

    async def test_list_shot_tags(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-shottag-list@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        tag = await _create_tag_via_api(client, headers, name="shotlistag")
        await client.post(f"/shots/{shot.id}/tags", json={"tag_id": tag["id"]}, headers=headers)

        resp = await client.get(f"/shots/{shot.id}/tags", headers=headers)

        assert resp.status_code == 200
        tag_ids = [t["id"] for t in resp.json()]
        assert tag["id"] in tag_ids

    async def test_detach_entity_tag_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-detach@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        tag = await _create_tag_via_api(client, headers, name="detachtag")
        attach_resp = await client.post(
            f"/shots/{shot.id}/tags", json={"tag_id": tag["id"]}, headers=headers
        )
        entity_tag_id = attach_resp.json()["id"]

        resp = await client.delete(f"/entity-tags/{entity_tag_id}", headers=headers)

        assert resp.status_code == 204

    async def test_duplicate_attach_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-dupattach@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        tag = await _create_tag_via_api(client, headers, name="duptag")
        await client.post(f"/shots/{shot.id}/tags", json={"tag_id": tag["id"]}, headers=headers)

        resp = await client.post(
            f"/shots/{shot.id}/tags",
            json={"tag_id": tag["id"]},
            headers=headers,
        )

        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# ENTITY ATTACHMENT (Asset)
# ---------------------------------------------------------------------------


class TestAssetTags:
    async def test_attach_tag_to_asset(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-assettag@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        asset = await _create_asset(db_session, project)
        headers = _auth_headers(admin)
        tag = await _create_tag_via_api(client, headers, name="assettag")

        resp = await client.post(
            f"/assets/{asset.id}/tags",
            json={"tag_id": tag["id"]},
            headers=headers,
        )

        assert resp.status_code == 201

    async def test_list_asset_tags(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-assetlist@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        asset = await _create_asset(db_session, project)
        headers = _auth_headers(admin)
        tag = await _create_tag_via_api(client, headers, name="assetlisttag")
        await client.post(f"/assets/{asset.id}/tags", json={"tag_id": tag["id"]}, headers=headers)

        resp = await client.get(f"/assets/{asset.id}/tags", headers=headers)

        assert resp.status_code == 200
        assert len(resp.json()) >= 1


# ---------------------------------------------------------------------------
# ENTITY ATTACHMENT (Sequence)
# ---------------------------------------------------------------------------


class TestSequenceTags:
    async def test_attach_tag_to_sequence(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-seqtag@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        seq = await _create_sequence(db_session, project)
        headers = _auth_headers(admin)
        tag = await _create_tag_via_api(client, headers, name="seqtag")

        resp = await client.post(
            f"/sequences/{seq.id}/tags",
            json={"tag_id": tag["id"]},
            headers=headers,
        )

        assert resp.status_code == 201

    async def test_list_sequence_tags(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-seqtaglist@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        seq = await _create_sequence(db_session, project)
        headers = _auth_headers(admin)
        tag = await _create_tag_via_api(client, headers, name="seqlisttag")
        await client.post(f"/sequences/{seq.id}/tags", json={"tag_id": tag["id"]}, headers=headers)

        resp = await client.get(f"/sequences/{seq.id}/tags", headers=headers)

        assert resp.status_code == 200
        assert len(resp.json()) >= 1


# ---------------------------------------------------------------------------
# PROJECT TAGS via project endpoint
# ---------------------------------------------------------------------------


class TestProjectTagsEndpoint:
    async def test_list_project_tags_via_project_route(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-prjtaglist@tag.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        await _create_tag_via_api(client, headers, name="prjrouttag", project_id=project.id)

        resp = await client.get(f"/projects/{project.id}/tags", headers=headers)

        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert "prjrouttag" in names

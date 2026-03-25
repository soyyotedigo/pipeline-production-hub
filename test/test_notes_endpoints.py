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

pytestmark = pytest.mark.notes


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
        name="Note Project",
        code=f"NT{uuid.uuid4().hex[:6].upper()}",
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
        name="NoteShot",
        code=f"NS{uuid.uuid4().hex[:4].upper()}",
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
        name=f"NoteAsset-{uuid.uuid4().hex[:4]}",
        asset_type=AssetType.prop,
        status=AssetStatus.pending,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)
    return asset


async def _create_note_via_api(
    client: AsyncClient,
    project_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    headers: dict[str, str],
    *,
    body: str = "A test note",
    subject: str | None = None,
    is_client_visible: bool = False,
) -> dict:
    payload: dict = {
        "project_id": str(project_id),
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "body": body,
        "is_client_visible": is_client_visible,
    }
    if subject is not None:
        payload["subject"] = subject
    resp = await client.post("/notes", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


class TestCreateNote:
    async def test_create_project_note_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-create@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)

        resp = await client.post(
            "/notes",
            json={
                "project_id": str(project.id),
                "entity_type": "project",
                "entity_id": str(project.id),
                "body": "Project note body",
                "subject": "Project kick-off",
            },
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["body"] == "Project note body"
        assert data["subject"] == "Project kick-off"
        assert data["entity_type"] == "project"
        assert data["author_id"] == str(admin.id)
        assert data["archived_at"] is None

    async def test_create_shot_note_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-shotnote@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)

        resp = await client.post(
            f"/shots/{shot.id}/notes",
            json={"project_id": str(project.id), "body": "Shot feedback"},
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["entity_type"] == "shot"
        assert data["entity_id"] == str(shot.id)

    async def test_create_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-noauth@note.test")
        project = await _create_project(db_session, admin)

        resp = await client.post(
            "/notes",
            json={
                "project_id": str(project.id),
                "entity_type": "project",
                "entity_id": str(project.id),
                "body": "No auth",
            },
        )

        assert resp.status_code == 401

    async def test_create_with_client_visible_flag(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-clientvis@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)

        resp = await client.post(
            "/notes",
            json={
                "project_id": str(project.id),
                "entity_type": "project",
                "entity_id": str(project.id),
                "body": "Client can see this",
                "is_client_visible": True,
            },
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        assert resp.json()["is_client_visible"] is True


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


class TestGetNote:
    async def test_get_returns_200_with_replies_field(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        note = await _create_note_via_api(client, project.id, "project", project.id, headers)

        resp = await client.get(f"/notes/{note['id']}", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == note["id"]
        assert "replies" in data

    async def test_get_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get404@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.get(f"/notes/{uuid.uuid4()}", headers=_auth_headers(admin))

        assert resp.status_code == 404

    async def test_get_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-getauth@note.test")
        project = await _create_project(db_session, admin)
        note = await _create_note_via_api(
            client, project.id, "project", project.id, _auth_headers(admin)
        )

        resp = await client.get(f"/notes/{note['id']}")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------


class TestUpdateNote:
    async def test_update_body(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        note = await _create_note_via_api(client, project.id, "project", project.id, headers)

        resp = await client.patch(
            f"/notes/{note['id']}",
            json={"body": "Updated body"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["body"] == "Updated body"

    async def test_update_client_visible(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd-vis@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        note = await _create_note_via_api(
            client, project.id, "project", project.id, headers, is_client_visible=False
        )

        resp = await client.patch(
            f"/notes/{note['id']}",
            json={"is_client_visible": True},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["is_client_visible"] is True


# ---------------------------------------------------------------------------
# ARCHIVE (soft delete)
# ---------------------------------------------------------------------------


class TestArchiveNote:
    async def test_archive_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        note = await _create_note_via_api(client, project.id, "project", project.id, headers)

        resp = await client.delete(f"/notes/{note['id']}", headers=headers)

        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# REPLY
# ---------------------------------------------------------------------------


class TestReplyToNote:
    async def test_reply_creates_child_note(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-reply@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        parent = await _create_note_via_api(
            client, project.id, "project", project.id, headers, body="Parent note"
        )

        resp = await client.post(
            f"/notes/{parent['id']}/reply",
            json={"body": "This is a reply"},
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["body"] == "This is a reply"
        assert data["parent_note_id"] == parent["id"]

    async def test_replies_appear_in_get_thread(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-thread@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        parent = await _create_note_via_api(
            client, project.id, "project", project.id, headers, body="Thread parent"
        )
        await client.post(
            f"/notes/{parent['id']}/reply",
            json={"body": "Reply 1"},
            headers=headers,
        )
        await client.post(
            f"/notes/{parent['id']}/reply",
            json={"body": "Reply 2"},
            headers=headers,
        )

        resp = await client.get(f"/notes/{parent['id']}", headers=headers)

        assert resp.status_code == 200
        assert len(resp.json()["replies"]) == 2


# ---------------------------------------------------------------------------
# SHOT NOTE LISTING
# ---------------------------------------------------------------------------


class TestShotNotes:
    async def test_list_shot_notes(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-shotlist@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)

        await client.post(
            f"/shots/{shot.id}/notes",
            json={"project_id": str(project.id), "body": "Note 1"},
            headers=headers,
        )
        await client.post(
            f"/shots/{shot.id}/notes",
            json={"project_id": str(project.id), "body": "Note 2"},
            headers=headers,
        )

        resp = await client.get(f"/shots/{shot.id}/notes", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2


# ---------------------------------------------------------------------------
# PROJECT NOTE LISTING
# ---------------------------------------------------------------------------


class TestProjectNotes:
    async def test_list_project_notes(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-prjlist@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)

        await client.post(
            f"/projects/{project.id}/notes",
            json={"body": "Project note 1"},
            headers=headers,
        )
        await client.post(
            f"/projects/{project.id}/notes",
            json={"body": "Project note 2"},
            headers=headers,
        )

        resp = await client.get(f"/projects/{project.id}/notes", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2


# ---------------------------------------------------------------------------
# ASSET NOTE ENDPOINTS
# ---------------------------------------------------------------------------


class TestAssetNotes:
    async def test_create_asset_note_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-assetnote@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        asset = await _create_asset(db_session, project)
        headers = _auth_headers(admin)

        resp = await client.post(
            f"/assets/{asset.id}/notes",
            json={"project_id": str(project.id), "body": "Asset feedback note"},
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["entity_type"] == "asset"
        assert data["entity_id"] == str(asset.id)
        assert data["body"] == "Asset feedback note"

    async def test_list_asset_notes_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-assetnotelist@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        asset = await _create_asset(db_session, project)
        headers = _auth_headers(admin)

        await client.post(
            f"/assets/{asset.id}/notes",
            json={"project_id": str(project.id), "body": "Asset note 1"},
            headers=headers,
        )
        await client.post(
            f"/assets/{asset.id}/notes",
            json={"project_id": str(project.id), "body": "Asset note 2"},
            headers=headers,
        )

        resp = await client.get(f"/assets/{asset.id}/notes", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2


# ---------------------------------------------------------------------------
# PIPELINE TASK NOTE ENDPOINTS
# ---------------------------------------------------------------------------


class TestPipelineTaskNotes:
    async def test_create_pipeline_task_note_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        from app.models.pipeline_task import PipelineStepType, PipelineTask, PipelineTaskStatus

        admin = await _create_user(db_session, "admin-tasknote@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)

        task = PipelineTask(
            id=uuid.uuid4(),
            shot_id=shot.id,
            step_name="Lighting",
            step_type=PipelineStepType.lighting,
            order=1,
            status=PipelineTaskStatus.pending,
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        resp = await client.post(
            f"/pipeline-tasks/{task.id}/notes",
            json={"project_id": str(project.id), "body": "Task feedback note"},
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["entity_type"] == "pipeline_task"
        assert data["entity_id"] == str(task.id)

    async def test_list_pipeline_task_notes_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        from app.models.pipeline_task import PipelineStepType, PipelineTask, PipelineTaskStatus

        admin = await _create_user(db_session, "admin-tasknotelist@note.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)

        task = PipelineTask(
            id=uuid.uuid4(),
            shot_id=shot.id,
            step_name="Animation",
            step_type=PipelineStepType.animation,
            order=1,
            status=PipelineTaskStatus.pending,
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        await client.post(
            f"/pipeline-tasks/{task.id}/notes",
            json={"project_id": str(project.id), "body": "Task note 1"},
            headers=headers,
        )
        await client.post(
            f"/pipeline-tasks/{task.id}/notes",
            json={"project_id": str(project.id), "body": "Task note 2"},
            headers=headers,
        )

        resp = await client.get(f"/pipeline-tasks/{task.id}/notes", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

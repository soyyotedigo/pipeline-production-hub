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

pytestmark = pytest.mark.pipeline_tasks

STEP_PAYLOAD = [
    {"step_name": "Layout", "step_type": "layout", "order": 1, "applies_to": "shot"},
    {"step_name": "Animation", "step_type": "animation", "order": 2, "applies_to": "shot"},
]


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
    name: str = "PT Project",
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=name,
        code=f"PT{uuid.uuid4().hex[:6].upper()}",
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
        name="PTShot",
        code=f"PS{uuid.uuid4().hex[:4].upper()}",
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
        name=f"PTAsset-{uuid.uuid4().hex[:4]}",
        asset_type=AssetType.prop,
        status=AssetStatus.pending,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)
    return asset


async def _create_template_via_api(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str = "Test Template",
    project_type: str = "film",
    steps: list[dict] | None = None,
) -> dict:
    resp = await client.post(
        "/pipeline-templates",
        json={
            "name": name,
            "project_type": project_type,
            "steps": steps or STEP_PAYLOAD,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# PIPELINE TEMPLATES
# ---------------------------------------------------------------------------


class TestCreateTemplate:
    async def test_create_returns_201_with_steps(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-create@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.post(
            "/pipeline-templates",
            json={
                "name": "VFX Film Pipeline",
                "project_type": "film",
                "steps": STEP_PAYLOAD,
            },
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "VFX Film Pipeline"
        assert data["project_type"] == "film"
        assert len(data["steps"]) == 2

    async def test_create_without_steps_returns_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-nostep@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.post(
            "/pipeline-templates",
            json={"name": "Empty", "project_type": "film", "steps": []},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 422

    async def test_create_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.post(
            "/pipeline-templates",
            json={"name": "No Auth", "project_type": "film", "steps": STEP_PAYLOAD},
        )

        assert resp.status_code == 401


class TestListGetTemplate:
    async def test_list_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-list@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        headers = _auth_headers(admin)
        await _create_template_via_api(client, headers, name="T1")
        await _create_template_via_api(client, headers, name="T2")

        resp = await client.get("/pipeline-templates", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    async def test_list_filter_by_project_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-typefilter@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        headers = _auth_headers(admin)
        await _create_template_via_api(client, headers, name="FilmT", project_type="film")
        await _create_template_via_api(client, headers, name="GameT", project_type="game")

        resp = await client.get("/pipeline-templates?project_type=film", headers=headers)

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(t["project_type"] == "film" for t in items)

    async def test_get_template_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        headers = _auth_headers(admin)
        created = await _create_template_via_api(client, headers, name="GetMe")

        resp = await client.get(f"/pipeline-templates/{created['id']}", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["name"] == "GetMe"

    async def test_get_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get404@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.get(f"/pipeline-templates/{uuid.uuid4()}", headers=_auth_headers(admin))

        assert resp.status_code == 404


class TestUpdateArchiveDeleteTemplate:
    async def test_update_template_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        headers = _auth_headers(admin)
        created = await _create_template_via_api(client, headers, name="Before")

        resp = await client.patch(
            f"/pipeline-templates/{created['id']}",
            json={"name": "After"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "After"

    async def test_archive_template(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-arch@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        headers = _auth_headers(admin)
        created = await _create_template_via_api(client, headers, name="ArchMe")

        resp = await client.post(
            f"/pipeline-templates/{created['id']}/archive",
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["archived_at"] is not None

    async def test_delete_template_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        headers = _auth_headers(admin)
        created = await _create_template_via_api(client, headers, name="DelMe")

        resp = await client.delete(f"/pipeline-templates/{created['id']}", headers=headers)

        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# APPLY TEMPLATE
# ---------------------------------------------------------------------------


class TestApplyTemplate:
    async def test_apply_to_shot_creates_tasks(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-apply@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        template = await _create_template_via_api(client, headers, name="ApplyT")

        resp = await client.post(
            f"/pipeline-templates/{template['id']}/apply",
            json={"entity_type": "shot", "entity_id": str(shot.id)},
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["entity_type"] == "shot"
        assert data["tasks_created"] == len(STEP_PAYLOAD)
        assert len(data["tasks"]) == len(STEP_PAYLOAD)


# ---------------------------------------------------------------------------
# SHOT TASKS
# ---------------------------------------------------------------------------


class TestShotTasks:
    async def test_create_task_on_shot(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-shottask@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)

        resp = await client.post(
            f"/shots/{shot.id}/tasks",
            json={"step_name": "Layout", "step_type": "layout", "order": 1},
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["step_name"] == "Layout"
        assert data["shot_id"] == str(shot.id)
        assert data["status"] == "pending"

    async def test_list_shot_tasks(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-shotlist@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        await client.post(
            f"/shots/{shot.id}/tasks",
            json={"step_name": "Layout", "step_type": "layout", "order": 1},
            headers=headers,
        )
        await client.post(
            f"/shots/{shot.id}/tasks",
            json={"step_name": "Animation", "step_type": "animation", "order": 2},
            headers=headers,
        )

        resp = await client.get(f"/shots/{shot.id}/tasks", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    async def test_list_shot_tasks_filter_by_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-taskstatus@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        await client.post(
            f"/shots/{shot.id}/tasks",
            json={"step_name": "Layout", "step_type": "layout", "order": 1},
            headers=headers,
        )

        resp = await client.get(f"/shots/{shot.id}/tasks?status=pending", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["total"] == 1


# ---------------------------------------------------------------------------
# ASSET TASKS
# ---------------------------------------------------------------------------


class TestAssetTasks:
    async def test_create_task_on_asset(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-assettask@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        asset = await _create_asset(db_session, project)
        headers = _auth_headers(admin)

        resp = await client.post(
            f"/assets/{asset.id}/tasks",
            json={"step_name": "Modeling", "step_type": "modeling", "order": 1},
            headers=headers,
        )

        assert resp.status_code == 201
        assert resp.json()["asset_id"] == str(asset.id)


# ---------------------------------------------------------------------------
# TASK OPERATIONS
# ---------------------------------------------------------------------------


class TestTaskOperations:
    async def test_get_task_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-taskget@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task_resp = await client.post(
            f"/shots/{shot.id}/tasks",
            json={"step_name": "Layout", "step_type": "layout", "order": 1},
            headers=headers,
        )
        task_id = task_resp.json()["id"]

        resp = await client.get(f"/pipeline-tasks/{task_id}", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["id"] == task_id

    async def test_get_nonexistent_task_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-task404@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)

        resp = await client.get(f"/pipeline-tasks/{uuid.uuid4()}", headers=_auth_headers(admin))

        assert resp.status_code == 404

    async def test_update_task(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-taskupd@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task_resp = await client.post(
            f"/shots/{shot.id}/tasks",
            json={"step_name": "Layout", "step_type": "layout", "order": 1},
            headers=headers,
        )
        task_id = task_resp.json()["id"]

        resp = await client.patch(
            f"/pipeline-tasks/{task_id}",
            json={"notes": "Updated notes"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["notes"] == "Updated notes"

    async def test_update_task_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-taskstatus-upd@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task_resp = await client.post(
            f"/shots/{shot.id}/tasks",
            json={"step_name": "Layout", "step_type": "layout", "order": 1},
            headers=headers,
        )
        task_id = task_resp.json()["id"]

        resp = await client.patch(
            f"/pipeline-tasks/{task_id}/status",
            json={"status": "in_progress"},
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["new_status"] == "in_progress"
        assert data["old_status"] == "pending"

    async def test_archive_task(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-taskarch@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task_resp = await client.post(
            f"/shots/{shot.id}/tasks",
            json={"step_name": "Layout", "step_type": "layout", "order": 1},
            headers=headers,
        )
        task_id = task_resp.json()["id"]

        resp = await client.post(f"/pipeline-tasks/{task_id}/archive", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["archived_at"] is not None

    async def test_delete_task_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-taskdel@pt.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        shot = await _create_shot(db_session, project)
        headers = _auth_headers(admin)
        task_resp = await client.post(
            f"/shots/{shot.id}/tasks",
            json={"step_name": "Layout", "step_type": "layout", "order": 1},
            headers=headers,
        )
        task_id = task_resp.json()["id"]

        resp = await client.delete(f"/pipeline-tasks/{task_id}", headers=headers)

        assert resp.status_code == 204

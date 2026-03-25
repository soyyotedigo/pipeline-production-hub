from __future__ import annotations

import sys
import uuid
from datetime import date, timedelta
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

pytestmark = pytest.mark.time_logs

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


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
    db_session: AsyncSession, owner: User, *, name: str = "TL Project"
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=name,
        code=f"TL{uuid.uuid4().hex[:6].upper()}",
        status=ProjectStatus.pending,
        created_by=owner.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _create_timelog_via_api(
    client: AsyncClient,
    project_id: uuid.UUID,
    headers: dict[str, str],
    *,
    duration_minutes: int = 60,
    log_date: str | None = None,
    description: str | None = None,
) -> dict:
    payload: dict = {
        "project_id": str(project_id),
        "date": log_date or TODAY,
        "duration_minutes": duration_minutes,
    }
    if description:
        payload["description"] = description
    resp = await client.post("/timelogs", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


class TestCreateTimeLog:
    async def test_create_returns_201_with_correct_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-create@tl.test")
        await _assign_role(db_session, user.id, RoleName.artist)
        project = await _create_project(db_session, user)

        resp = await client.post(
            "/timelogs",
            json={"project_id": str(project.id), "date": TODAY, "duration_minutes": 120},
            headers=_auth_headers(user),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["project_id"] == str(project.id)
        assert data["duration_minutes"] == 120
        assert data["date"] == TODAY
        assert data["user_id"] == str(user.id)
        assert "id" in data

    async def test_create_with_description(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-desc@tl.test")
        project = await _create_project(db_session, user)

        resp = await client.post(
            "/timelogs",
            json={
                "project_id": str(project.id),
                "date": TODAY,
                "duration_minutes": 90,
                "description": "Worked on compositing",
            },
            headers=_auth_headers(user),
        )

        assert resp.status_code == 201
        assert resp.json()["description"] == "Worked on compositing"

    async def test_future_date_returns_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-future@tl.test")
        project = await _create_project(db_session, user)

        resp = await client.post(
            "/timelogs",
            json={"project_id": str(project.id), "date": TOMORROW, "duration_minutes": 60},
            headers=_auth_headers(user),
        )

        assert resp.status_code == 422

    async def test_duration_zero_returns_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-zero@tl.test")
        project = await _create_project(db_session, user)

        resp = await client.post(
            "/timelogs",
            json={"project_id": str(project.id), "date": TODAY, "duration_minutes": 0},
            headers=_auth_headers(user),
        )

        assert resp.status_code == 422

    async def test_duration_over_1440_returns_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-over@tl.test")
        project = await _create_project(db_session, user)

        resp = await client.post(
            "/timelogs",
            json={"project_id": str(project.id), "date": TODAY, "duration_minutes": 1441},
            headers=_auth_headers(user),
        )

        assert resp.status_code == 422

    async def test_create_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-noauth@tl.test")
        project = await _create_project(db_session, user)

        resp = await client.post(
            "/timelogs",
            json={"project_id": str(project.id), "date": TODAY, "duration_minutes": 60},
        )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


class TestGetTimeLog:
    async def test_get_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-get@tl.test")
        project = await _create_project(db_session, user)
        headers = _auth_headers(user)
        log = await _create_timelog_via_api(client, project.id, headers)

        resp = await client.get(f"/timelogs/{log['id']}", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["id"] == log["id"]

    async def test_get_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-get404@tl.test")

        resp = await client.get(f"/timelogs/{uuid.uuid4()}", headers=_auth_headers(user))

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------


class TestUpdateTimeLog:
    async def test_user_can_update_own_log(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-upd@tl.test")
        project = await _create_project(db_session, user)
        headers = _auth_headers(user)
        log = await _create_timelog_via_api(client, project.id, headers, duration_minutes=60)

        resp = await client.patch(
            f"/timelogs/{log['id']}",
            json={"duration_minutes": 90, "description": "Updated"},
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["duration_minutes"] == 90
        assert data["description"] == "Updated"

    async def test_other_user_cannot_update_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        owner = await _create_user(db_session, "owner-upd@tl.test")
        other = await _create_user(db_session, "other-upd@tl.test")
        project = await _create_project(db_session, owner)
        log = await _create_timelog_via_api(client, project.id, _auth_headers(owner))

        resp = await client.patch(
            f"/timelogs/{log['id']}",
            json={"duration_minutes": 200},
            headers=_auth_headers(other),
        )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


class TestDeleteTimeLog:
    async def test_user_can_delete_own_log(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-del@tl.test")
        project = await _create_project(db_session, user)
        headers = _auth_headers(user)
        log = await _create_timelog_via_api(client, project.id, headers)

        resp = await client.delete(f"/timelogs/{log['id']}", headers=headers)

        assert resp.status_code == 204

    async def test_other_user_cannot_delete_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        owner = await _create_user(db_session, "owner-del@tl.test")
        other = await _create_user(db_session, "other-del@tl.test")
        project = await _create_project(db_session, owner)
        log = await _create_timelog_via_api(client, project.id, _auth_headers(owner))

        resp = await client.delete(f"/timelogs/{log['id']}", headers=_auth_headers(other))

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# LIST PROJECT TIMELOGS
# ---------------------------------------------------------------------------


class TestListProjectTimeLogs:
    async def test_list_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-prjlist@tl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        await _create_timelog_via_api(client, project.id, headers, duration_minutes=60)
        await _create_timelog_via_api(client, project.id, headers, duration_minutes=120)

        resp = await client.get(f"/projects/{project.id}/timelogs", headers=headers)

        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    async def test_filter_by_date_from(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-datefilter@tl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        await _create_timelog_via_api(client, project.id, headers, log_date=YESTERDAY)
        await _create_timelog_via_api(client, project.id, headers, log_date=TODAY)

        resp = await client.get(
            f"/projects/{project.id}/timelogs?date_from={TODAY}", headers=headers
        )

        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# PROJECT SUMMARY
# ---------------------------------------------------------------------------


class TestProjectTimeLogSummary:
    async def test_summary_returns_totals(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-summary@tl.test")
        await _assign_role(db_session, admin.id, RoleName.admin)
        project = await _create_project(db_session, admin)
        headers = _auth_headers(admin)
        await _create_timelog_via_api(client, project.id, headers, duration_minutes=480)
        await _create_timelog_via_api(client, project.id, headers, duration_minutes=240)

        resp = await client.get(f"/projects/{project.id}/timelogs/summary", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_minutes"] == 720
        assert "by_user" in data


# ---------------------------------------------------------------------------
# USER TIMELOGS
# ---------------------------------------------------------------------------


class TestUserTimeLogs:
    async def test_list_own_timelogs(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-own@tl.test")
        project = await _create_project(db_session, user)
        headers = _auth_headers(user)
        await _create_timelog_via_api(client, project.id, headers)
        await _create_timelog_via_api(client, project.id, headers)

        resp = await client.get(f"/users/{user.id}/timelogs", headers=headers)

        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_list_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        user = await _create_user(db_session, "user-noauth@tl.test")

        resp = await client.get(f"/users/{user.id}/timelogs")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PIPELINE TASK TIMELOGS
# ---------------------------------------------------------------------------


class TestTaskTimeLogs:
    async def test_list_task_timelogs_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        from app.models.pipeline_task import PipelineStepType, PipelineTask, PipelineTaskStatus
        from app.models.shot import Shot, ShotStatus

        user = await _create_user(db_session, "user-tasktl@tl.test")
        project = await _create_project(db_session, user)

        shot = Shot(
            id=uuid.uuid4(),
            project_id=project.id,
            name="TLShot",
            code=f"TL{uuid.uuid4().hex[:4].upper()}",
            status=ShotStatus.pending,
            frame_start=1001,
            frame_end=1040,
        )
        db_session.add(shot)
        await db_session.commit()
        await db_session.refresh(shot)

        task = PipelineTask(
            id=uuid.uuid4(),
            shot_id=shot.id,
            step_name="Compositing",
            step_type=PipelineStepType.compositing,
            order=1,
            status=PipelineTaskStatus.pending,
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        headers = _auth_headers(user)
        await client.post(
            "/timelogs",
            json={
                "project_id": str(project.id),
                "pipeline_task_id": str(task.id),
                "date": TODAY,
                "duration_minutes": 90,
            },
            headers=headers,
        )

        resp = await client.get(f"/pipeline-tasks/{task.id}/timelogs", headers=headers)

        assert resp.status_code == 200
        assert len(resp.json()) >= 1

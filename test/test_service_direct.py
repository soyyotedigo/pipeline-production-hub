"""
Direct service tests — call services without HTTP/ASGI transport.

These tests exist specifically to improve coverage tracking, which is limited
for service-layer code called through httpx's ASGITransport (because async
tasks spawned by the transport do not inherit sys.settrace from the test
runner, so those lines are not recorded by coverage.py on Python 3.11).

Calling services directly within a pytest-asyncio test DOES preserve the
trace, so these tests unlock accurate measurement of service-layer branches.
"""

# ruff: noqa: E402
from __future__ import annotations

import sys
import uuid
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.pipeline_task import PipelineStepType, PipelineTask, PipelineTaskStatus
from app.models.project import Project, ProjectStatus
from app.models.role import Role, RoleName
from app.models.shot import Shot, ShotStatus
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.tag import EntityTagResponse, TagCreate, TagUpdate
from app.services.tag_service import TagService

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _make_user(db: AsyncSession, email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password("test123"),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_project(db: AsyncSession, owner_id: uuid.UUID, code: str = "") -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=f"Project {code}",
        code=code or f"PRJ{uuid.uuid4().hex[:6].upper()}",
        status=ProjectStatus.pending,
        created_by=owner_id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def _make_shot(db: AsyncSession, project_id: uuid.UUID) -> Shot:
    shot = Shot(
        id=uuid.uuid4(),
        project_id=project_id,
        name="SvcShot",
        code=f"SH{uuid.uuid4().hex[:4].upper()}",
        status=ShotStatus.pending,
        frame_start=1001,
        frame_end=1040,
    )
    db.add(shot)
    await db.commit()
    await db.refresh(shot)
    return shot


async def _make_task(db: AsyncSession, shot_id: uuid.UUID) -> PipelineTask:
    task = PipelineTask(
        id=uuid.uuid4(),
        shot_id=shot_id,
        step_name="Compositing",
        step_type=PipelineStepType.compositing,
        order=1,
        status=PipelineTaskStatus.pending,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def _ensure_role(db: AsyncSession, role_name: RoleName) -> Role:
    result = await db.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()
    if role is None:
        role = Role(name=role_name, description=f"{role_name.value}")
        db.add(role)
        await db.commit()
        await db.refresh(role)
    return role


async def _assign_role(
    db: AsyncSession,
    user_id: uuid.UUID,
    role_name: RoleName,
    project_id: uuid.UUID | None = None,
) -> None:
    role = await _ensure_role(db, role_name)
    db.add(UserRole(user_id=user_id, role_id=role.id, project_id=project_id))
    await db.commit()


# ---------------------------------------------------------------------------
# TagService — full method coverage
# ---------------------------------------------------------------------------


async def test_tag_service_full_lifecycle(db_session: AsyncSession) -> None:
    service = TagService(db_session)

    # create
    tag = await service.create_tag(TagCreate(name="svc-tag-1"))
    assert tag.name == "svc-tag-1"

    # duplicate raises conflict
    with pytest.raises(ConflictError):
        await service.create_tag(TagCreate(name="svc-tag-1"))

    # get
    fetched = await service.get_tag(tag.id)
    assert fetched.id == tag.id

    # get 404
    with pytest.raises(NotFoundError):
        await service.get_tag(uuid.uuid4())

    # list
    tags = await service.list_tags()
    assert any(t.id == tag.id for t in tags)

    # search
    found = await service.search_tags(q="svc-tag")
    assert any(t.id == tag.id for t in found)

    # update
    updated = await service.update_tag(tag.id, TagUpdate(name="svc-tag-upd", color="#abc123"))
    assert updated.name == "svc-tag-upd"

    # delete
    await service.delete_tag(updated.id)

    # confirm gone
    with pytest.raises(NotFoundError):
        await service.get_tag(updated.id)


async def test_tag_service_entity_attachment(db_session: AsyncSession) -> None:
    from app.models.tag import TagEntityType

    service = TagService(db_session)
    user = await _make_user(db_session, "tagsvc-attach@svc.test")
    project = await _make_project(db_session, user.id)
    shot = await _make_shot(db_session, project.id)

    tag = await service.create_tag(TagCreate(name="attach-tag-svc"))

    # attach to shot
    entity_tag: EntityTagResponse = await service.attach_tag(TagEntityType.shot, shot.id, tag.id)
    assert entity_tag.tag_id == tag.id

    # duplicate attach raises conflict
    with pytest.raises(ConflictError):
        await service.attach_tag(TagEntityType.shot, shot.id, tag.id)

    # attach nonexistent tag raises 404
    with pytest.raises(NotFoundError):
        await service.attach_tag(TagEntityType.shot, shot.id, uuid.uuid4())

    # list entity tags
    entity_tags = await service.list_entity_tags(TagEntityType.shot, shot.id)
    assert any(t.id == tag.id for t in entity_tags)

    # detach via entity_tag id
    await service.detach_entity_tag(entity_tag.id)
    after = await service.list_entity_tags(TagEntityType.shot, shot.id)
    assert not any(t.id == tag.id for t in after)

    # detach_entity_tag 404
    with pytest.raises(NotFoundError):
        await service.detach_entity_tag(uuid.uuid4())


# ---------------------------------------------------------------------------
# TimeLogService — key paths
# ---------------------------------------------------------------------------


async def test_time_log_service_create_get_update_delete(db_session: AsyncSession) -> None:
    from app.schemas.time_log import TimeLogCreate, TimeLogUpdate
    from app.services.time_log_service import TimeLogService

    user = await _make_user(db_session, "tlsvc@svc.test")
    project = await _make_project(db_session, user.id)
    service = TimeLogService(db_session)

    log = await service.create(
        TimeLogCreate(project_id=project.id, date=date.today(), duration_minutes=90),
        user_id=user.id,
    )
    assert log.duration_minutes == 90

    # get
    fetched = await service.get(log.id)
    assert fetched.id == log.id

    # 404
    with pytest.raises(NotFoundError):
        await service.get(uuid.uuid4())

    # update (owner)
    updated = await service.update(
        log.id,
        TimeLogUpdate(duration_minutes=120, description="updated"),
        user_id=user.id,
        is_admin=False,
    )
    assert updated.duration_minutes == 120

    # update by wrong user → 403
    from app.core.exceptions import ForbiddenError

    other = await _make_user(db_session, "tlsvc-other@svc.test")
    with pytest.raises(ForbiddenError):
        await service.update(
            log.id,
            TimeLogUpdate(duration_minutes=200),
            user_id=other.id,
            is_admin=False,
        )

    # delete
    await service.delete(log.id, user_id=user.id, is_admin=False)

    # delete wrong user
    log2 = await service.create(
        TimeLogCreate(project_id=project.id, date=date.today(), duration_minutes=60),
        user_id=user.id,
    )
    with pytest.raises(ForbiddenError):
        await service.delete(log2.id, user_id=other.id, is_admin=False)

    # admin can delete
    await service.delete(log2.id, user_id=other.id, is_admin=True)


async def test_time_log_service_list_by_project_task_user(db_session: AsyncSession) -> None:
    from app.schemas.time_log import TimeLogCreate
    from app.services.time_log_service import TimeLogService

    user = await _make_user(db_session, "tlsvc-list@svc.test")
    project = await _make_project(db_session, user.id)
    shot = await _make_shot(db_session, project.id)
    task = await _make_task(db_session, shot.id)
    service = TimeLogService(db_session)

    await service.create(
        TimeLogCreate(
            project_id=project.id,
            pipeline_task_id=task.id,
            date=date.today(),
            duration_minutes=60,
        ),
        user_id=user.id,
    )

    # list by project
    _logs, total = await service.list_by_project(project.id)
    assert total >= 1

    # list by task
    _logs2, total2 = await service.list_by_task(task.id)
    assert total2 >= 1

    # list by user
    _logs3, total3 = await service.list_by_user(user.id)
    assert total3 >= 1

    # project summary
    summary = await service.get_project_summary(project.id)
    assert summary.total_minutes >= 60


# ---------------------------------------------------------------------------
# VersionService — create, get, update, status, archive, list_by_asset
# ---------------------------------------------------------------------------


async def test_version_service_lifecycle(db_session: AsyncSession) -> None:
    from app.models.asset import Asset, AssetStatus, AssetType
    from app.schemas.version import VersionCreate, VersionStatusUpdate, VersionUpdate
    from app.services.version_service import VersionService

    user = await _make_user(db_session, "versvc@svc.test")
    project = await _make_project(db_session, user.id)
    shot = await _make_shot(db_session, project.id)
    task = await _make_task(db_session, shot.id)
    service = VersionService(db_session)

    # create via task (shot-linked)
    resp = await service.create_for_task(
        task.id,
        VersionCreate(description="first version"),
        current_user=user,
    )
    assert resp.version_number == 1
    version_id = resp.id

    # get version
    fetched = await service.get_version(version_id)
    assert fetched.id == version_id

    # get 404
    with pytest.raises(NotFoundError):
        await service.get_version(uuid.uuid4())

    # update
    updated = await service.update_version(
        version_id,
        VersionUpdate(description="updated desc"),
        current_user=user,
    )
    assert updated.description == "updated desc"

    # update 404
    with pytest.raises(NotFoundError):
        await service.update_version(
            uuid.uuid4(), VersionUpdate(description="x"), current_user=user
        )

    # status transition: pending_review → approved
    from app.models.version import VersionStatus

    status_resp = await service.update_status(
        version_id,
        VersionStatusUpdate(status=VersionStatus.approved, comment="looks great"),
        current_user=user,
    )
    assert status_resp.new_status == VersionStatus.approved

    # invalid transition raises
    from app.core.exceptions import UnprocessableError

    with pytest.raises(UnprocessableError):
        await service.update_status(
            version_id,
            VersionStatusUpdate(status=VersionStatus.revision_requested),
            current_user=user,
        )

    # list by shot (before archive)
    shot_list = await service.list_by_shot(shot.id, offset=0, limit=10)
    assert shot_list.total >= 1

    # list by task (before archive)
    task_list = await service.list_by_task(task.id, offset=0, limit=10)
    assert task_list.total >= 1

    # list by project (before archive)
    project_list = await service.list_by_project(project.id, offset=0, limit=10)
    assert project_list.total >= 1

    # archive
    archived = await service.archive_version(version_id, current_user=user)
    assert archived.archived_at is not None

    # archive 404
    with pytest.raises(NotFoundError):
        await service.archive_version(uuid.uuid4(), current_user=user)

    # list by asset (asset-linked task)
    asset = Asset(
        id=uuid.uuid4(),
        project_id=project.id,
        name="SvcAsset",
        code="SVCA",
        asset_type=AssetType.prop,
        status=AssetStatus.pending,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)

    asset_task = PipelineTask(
        id=uuid.uuid4(),
        asset_id=asset.id,
        step_name="Modeling",
        step_type=PipelineStepType.modeling,
        order=1,
        status=PipelineTaskStatus.pending,
    )
    db_session.add(asset_task)
    await db_session.commit()
    await db_session.refresh(asset_task)

    await service.create_for_task(
        asset_task.id,
        VersionCreate(description="asset version"),
        current_user=user,
    )
    asset_list = await service.list_by_asset(asset.id, offset=0, limit=10)
    assert asset_list.total >= 1


# ---------------------------------------------------------------------------
# NoteService — create, get, update, archive, reply, list
# ---------------------------------------------------------------------------


async def test_note_service_lifecycle(db_session: AsyncSession) -> None:
    from app.models.note import NoteEntityType
    from app.schemas.note import (
        NoteCreate,
        NoteReplyCreate,
        NoteUpdate,
    )
    from app.services.note_service import NoteService

    user = await _make_user(db_session, "notesvc@svc.test")
    project = await _make_project(db_session, user.id)
    service = NoteService(db_session)

    # create project note
    note = await service.create_note(
        payload=NoteCreate(
            entity_type=NoteEntityType.project,
            entity_id=project.id,
            project_id=project.id,
            body="Direct service note",
        ),
        current_user=user,
    )
    assert note.body == "Direct service note"

    # get note
    thread = await service.get_note(note.id)
    assert thread.id == note.id
    assert thread.replies == []

    # get 404
    with pytest.raises(NotFoundError):
        await service.get_note(uuid.uuid4())

    # update
    updated = await service.update_note(
        note_id=note.id,
        payload=NoteUpdate(body="Updated body", is_client_visible=True),
        current_user=user,
    )
    assert updated.body == "Updated body"

    # reply
    reply = await service.create_reply(
        parent_note_id=note.id,
        payload=NoteReplyCreate(body="Reply body"),
        current_user=user,
    )
    assert reply.parent_note_id == note.id

    # thread has reply
    thread2 = await service.get_note(note.id)
    assert len(thread2.replies) == 1

    # list by entity (project)
    listing = await service.list_by_entity(
        entity_type=NoteEntityType.project,
        entity_id=project.id,
        project_id=project.id,
        current_user=user,
        offset=0,
        limit=10,
        include_replies=False,
        client_visible_only=False,
        author_id=None,
    )
    assert listing.total >= 1

    # list by project
    proj_listing = await service.list_by_project(
        project_id=project.id,
        current_user=user,
        offset=0,
        limit=10,
        include_replies=True,
        client_visible_only=False,
        author_id=None,
    )
    assert proj_listing.total >= 1

    # archive
    await service.archive_note(note_id=note.id, current_user=user)
    with pytest.raises(NotFoundError):
        await service.get_note(note.id)


# ---------------------------------------------------------------------------
# Pipeline task service — create task, status transitions, list
# ---------------------------------------------------------------------------


async def test_pipeline_task_service_basic(db_session: AsyncSession) -> None:
    from app.schemas.pipeline_task import (
        PipelineTaskCreateRequest,
        PipelineTaskStatusUpdateRequest,
        PipelineTaskUpdateRequest,
    )
    from app.services.pipeline_task_service import PipelineTaskService

    user = await _make_user(db_session, "ptsvc@svc.test")
    project = await _make_project(db_session, user.id)
    shot = await _make_shot(db_session, project.id)
    service = PipelineTaskService(db_session)

    # create task (shot-linked)
    task_resp = await service.create_task(
        shot_id=shot.id,
        asset_id=None,
        payload=PipelineTaskCreateRequest(
            step_name="Layout",
            step_type=PipelineStepType.layout,
            order=1,
        ),
    )
    assert task_resp.step_name == "Layout"
    task_id = task_resp.id

    # get
    fetched = await service.get_task(task_id)
    assert fetched.id == task_id

    # get 404
    with pytest.raises(NotFoundError):
        await service.get_task(uuid.uuid4())

    # list by shot
    shot_tasks = await service.list_tasks_for_shot(shot.id, offset=0, limit=10)
    assert shot_tasks.total >= 1

    # update task (only notes/due_date/assigned_to are updatable)
    updated = await service.update_task(
        task_id,
        PipelineTaskUpdateRequest(notes="task note updated"),
        actor_id=user.id,
    )
    assert updated.notes == "task note updated"

    # status transition: pending → in_progress
    status_resp = await service.update_task_status(
        task_id,
        PipelineTaskStatusUpdateRequest(status=PipelineTaskStatus.in_progress, comment="starting"),
        changed_by=user.id,
    )
    assert status_resp.new_status == PipelineTaskStatus.in_progress


# ---------------------------------------------------------------------------
# DepartmentService — full lifecycle
# ---------------------------------------------------------------------------


async def test_department_service_lifecycle(db_session: AsyncSession) -> None:
    from app.schemas.department import DepartmentCreate, DepartmentUpdate
    from app.services.department_service import DepartmentService

    service = DepartmentService(db_session)
    suffix = uuid.uuid4().hex[:6].upper()

    # create
    dept = await service.create_department(
        DepartmentCreate(name=f"Compositing-{suffix}", code=f"COMP{suffix}")
    )
    assert dept.name == f"Compositing-{suffix}"

    # duplicate name raises conflict
    with pytest.raises(ConflictError):
        await service.create_department(
            DepartmentCreate(name=f"Compositing-{suffix}", code=f"COMP{suffix}X")
        )

    # duplicate code raises conflict
    with pytest.raises(ConflictError):
        await service.create_department(
            DepartmentCreate(name=f"Compositing-{suffix}-Y", code=f"COMP{suffix}")
        )

    # get
    fetched = await service.get_department(dept.id)
    assert fetched.id == dept.id

    # get 404
    with pytest.raises(NotFoundError):
        await service.get_department(uuid.uuid4())

    # list
    listing = await service.list_departments(offset=0, limit=50)
    assert listing.total >= 1

    # update name
    updated = await service.update_department(
        dept.id,
        DepartmentUpdate(name=f"Comp-Updated-{suffix}", description="desc"),
    )
    assert updated.name == f"Comp-Updated-{suffix}"

    # update 404
    with pytest.raises(NotFoundError):
        await service.update_department(uuid.uuid4(), DepartmentUpdate(name="x"))

    # update with conflicting name (same dept — no error, just updates to same value)
    other_dept = await service.create_department(
        DepartmentCreate(name=f"Lighting-{suffix}", code=f"LGT{suffix}")
    )
    # rename other to conflict with updated dept — should raise ConflictError
    with pytest.raises(ConflictError):
        await service.update_department(
            other_dept.id,
            DepartmentUpdate(name=f"Comp-Updated-{suffix}"),
        )

    # archive
    archived = await service.archive_department(dept.id)
    assert archived.id == dept.id

    # archive 404
    with pytest.raises(NotFoundError):
        await service.archive_department(uuid.uuid4())

    # delete (no members) — use other_dept which has no members
    await service.delete_department(other_dept.id)

    # delete 404
    with pytest.raises(NotFoundError):
        await service.delete_department(uuid.uuid4())


async def test_department_service_members(db_session: AsyncSession) -> None:
    from app.core.exceptions import UnprocessableError
    from app.schemas.department import DepartmentCreate
    from app.services.department_service import DepartmentService

    service = DepartmentService(db_session)
    suffix = uuid.uuid4().hex[:6].upper()

    dept = await service.create_department(
        DepartmentCreate(name=f"FX-{suffix}", code=f"FX{suffix}")
    )
    user = await _make_user(db_session, f"dept-member-{suffix}@svc.test")

    # add member
    membership = await service.add_member(dept.id, user.id)
    assert membership.user_id == user.id

    # add member again → conflict
    with pytest.raises(ConflictError):
        await service.add_member(dept.id, user.id)

    # add member to nonexistent dept → 404
    with pytest.raises(NotFoundError):
        await service.add_member(uuid.uuid4(), user.id)

    # add nonexistent user → 404
    with pytest.raises(NotFoundError):
        await service.add_member(dept.id, uuid.uuid4())

    # get members
    members = await service.get_members(dept.id)
    assert any(m.id == user.id for m in members)

    # get members of nonexistent dept → 404
    with pytest.raises(NotFoundError):
        await service.get_members(uuid.uuid4())

    # get user departments
    user_depts = await service.get_user_departments(user.id)
    assert any(d.id == dept.id for d in user_depts)

    # get_user_departments for nonexistent user → 404
    with pytest.raises(NotFoundError):
        await service.get_user_departments(uuid.uuid4())

    # cannot delete department with members
    with pytest.raises(UnprocessableError):
        await service.delete_department(dept.id)

    # remove member
    await service.remove_member(dept.id, user.id)

    # remove nonexistent member → 404
    with pytest.raises(NotFoundError):
        await service.remove_member(dept.id, user.id)

    # remove member from nonexistent dept → 404
    with pytest.raises(NotFoundError):
        await service.remove_member(uuid.uuid4(), user.id)

    # remove_member_by_id 404
    with pytest.raises(NotFoundError):
        await service.remove_member_by_id(uuid.uuid4())

    # now delete is OK (no members)
    await service.delete_department(dept.id)


# ---------------------------------------------------------------------------
# ShotWorkflowService — status transitions and history
# ---------------------------------------------------------------------------


async def test_shot_workflow_service_transitions(db_session: AsyncSession) -> None:
    from app.services.shot_workflow_service import ShotWorkflowService

    service = ShotWorkflowService(db_session)
    user = await _make_user(db_session, "shotflow-svc@svc.test")
    project = await _make_project(db_session, user.id)
    # admin covers in_progress/approved/delivered/revision; lead covers review
    await _assign_role(db_session, user.id, RoleName.admin, project.id)
    await _assign_role(db_session, user.id, RoleName.lead, project.id)
    shot = await _make_shot(db_session, project.id)

    # valid transition: pending → in_progress (admin allowed)
    resp = await service.update_status(
        shot_id=shot.id,
        target_status=ShotStatus.in_progress,
        comment="starting work",
        current_user=user,
        project_id=project.id,
    )
    assert resp.new_status == ShotStatus.in_progress

    # invalid transition: in_progress → approved (not valid)
    with pytest.raises(ConflictError):
        await service.update_status(
            shot_id=shot.id,
            target_status=ShotStatus.approved,
            comment=None,
            current_user=user,
        )

    # not found
    with pytest.raises(NotFoundError):
        await service.update_status(
            shot_id=uuid.uuid4(),
            target_status=ShotStatus.in_progress,
            comment=None,
            current_user=user,
        )

    # project_id mismatch → 404
    other_project = await _make_project(db_session, user.id)
    with pytest.raises(NotFoundError):
        await service.update_status(
            shot_id=shot.id,
            target_status=ShotStatus.review,
            comment=None,
            current_user=user,
            project_id=other_project.id,
        )

    # move to review (lead role allows this)
    await service.update_status(
        shot_id=shot.id,
        target_status=ShotStatus.review,
        comment=None,
        current_user=user,
    )

    # list status history
    history = await service.list_status_history(
        shot_id=shot.id,
        current_user=user,
        offset=0,
        limit=10,
        project_id=project.id,
    )
    assert history.total >= 2

    # list history for nonexistent shot → 404
    with pytest.raises(NotFoundError):
        await service.list_status_history(
            shot_id=uuid.uuid4(),
            current_user=user,
            offset=0,
            limit=10,
        )


async def test_shot_workflow_permission_branches(db_session: AsyncSession) -> None:
    from app.core.exceptions import ForbiddenError
    from app.services.shot_workflow_service import ShotWorkflowService

    service = ShotWorkflowService(db_session)

    # user with no role tries to move pending → in_progress
    no_role_user = await _make_user(db_session, "shotflow-norole@svc.test")
    project = await _make_project(db_session, no_role_user.id)
    shot = await _make_shot(db_session, project.id)

    with pytest.raises(ForbiddenError):
        await service.update_status(
            shot_id=shot.id,
            target_status=ShotStatus.in_progress,
            comment=None,
            current_user=no_role_user,
        )

    # give admin+lead roles and advance through workflow to test other permission branches
    admin_user = await _make_user(db_session, "shotflow-admin@svc.test")
    await _assign_role(db_session, admin_user.id, RoleName.admin, project.id)
    await _assign_role(db_session, admin_user.id, RoleName.lead, project.id)

    # pending → in_progress (admin ok)
    await service.update_status(
        shot_id=shot.id,
        target_status=ShotStatus.in_progress,
        comment=None,
        current_user=admin_user,
    )

    # in_progress → review (lead role required — non-artist-owner path)
    await service.update_status(
        shot_id=shot.id,
        target_status=ShotStatus.review,
        comment=None,
        current_user=admin_user,
    )

    # artist with no supervisor/admin role tries to move review → revision → ForbiddenError
    # (revision requires supervisor/admin)
    artist_user = await _make_user(db_session, "shotflow-artist@svc.test")
    await _assign_role(db_session, artist_user.id, RoleName.artist, project.id)
    with pytest.raises(ForbiddenError):
        await service.update_status(
            shot_id=shot.id,
            target_status=ShotStatus.revision,
            comment=None,
            current_user=artist_user,
        )

    # review → revision (admin ok)
    await service.update_status(
        shot_id=shot.id,
        target_status=ShotStatus.revision,
        comment=None,
        current_user=admin_user,
    )

    # revision → approved (admin ok)
    await service.update_status(
        shot_id=shot.id,
        target_status=ShotStatus.approved,
        comment=None,
        current_user=admin_user,
    )

    # approved → delivered (admin ok)
    await service.update_status(
        shot_id=shot.id,
        target_status=ShotStatus.delivered,
        comment=None,
        current_user=admin_user,
    )


# ---------------------------------------------------------------------------
# AssetWorkflowService — status transitions
# ---------------------------------------------------------------------------


async def test_asset_workflow_service_transitions(db_session: AsyncSession) -> None:
    from app.core.exceptions import ForbiddenError
    from app.models.asset import Asset, AssetStatus, AssetType
    from app.services.asset_workflow_service import AssetWorkflowService

    service = AssetWorkflowService(db_session)
    user = await _make_user(db_session, "assetflow-svc@svc.test")
    project = await _make_project(db_session, user.id)
    await _assign_role(db_session, user.id, RoleName.admin, project.id)
    await _assign_role(db_session, user.id, RoleName.lead, project.id)

    asset = Asset(
        id=uuid.uuid4(),
        project_id=project.id,
        name="FlowAsset",
        code=f"FA{uuid.uuid4().hex[:4].upper()}",
        asset_type=AssetType.prop,
        status=AssetStatus.pending,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)

    # valid transition: pending → in_progress
    resp = await service.update_status(
        asset_id=asset.id,
        target_status=AssetStatus.in_progress,
        comment="starting",
        current_user=user,
        project_id=project.id,
    )
    assert resp.new_status == AssetStatus.in_progress

    # invalid transition raises conflict
    with pytest.raises(ConflictError):
        await service.update_status(
            asset_id=asset.id,
            target_status=AssetStatus.approved,
            comment=None,
            current_user=user,
        )

    # not found
    with pytest.raises(NotFoundError):
        await service.update_status(
            asset_id=uuid.uuid4(),
            target_status=AssetStatus.in_progress,
            comment=None,
            current_user=user,
        )

    # project_id mismatch → 404
    other_project = await _make_project(db_session, user.id)
    with pytest.raises(NotFoundError):
        await service.update_status(
            asset_id=asset.id,
            target_status=AssetStatus.review,
            comment=None,
            current_user=user,
            project_id=other_project.id,
        )

    # advance through workflow
    await service.update_status(
        asset_id=asset.id,
        target_status=AssetStatus.review,
        comment=None,
        current_user=user,
    )

    # review → revision (admin)
    await service.update_status(
        asset_id=asset.id,
        target_status=AssetStatus.revision,
        comment=None,
        current_user=user,
    )

    # revision → approved (admin)
    await service.update_status(
        asset_id=asset.id,
        target_status=AssetStatus.approved,
        comment=None,
        current_user=user,
    )

    # approved → delivered (admin)
    await service.update_status(
        asset_id=asset.id,
        target_status=AssetStatus.delivered,
        comment=None,
        current_user=user,
    )

    # no-role user tries any transition → ForbiddenError
    no_role_user = await _make_user(db_session, "assetflow-norole@svc.test")
    asset2 = Asset(
        id=uuid.uuid4(),
        project_id=project.id,
        name="FlowAsset2",
        code=f"FB{uuid.uuid4().hex[:4].upper()}",
        asset_type=AssetType.prop,
        status=AssetStatus.pending,
    )
    db_session.add(asset2)
    await db_session.commit()
    await db_session.refresh(asset2)

    with pytest.raises(ForbiddenError):
        await service.update_status(
            asset_id=asset2.id,
            target_status=AssetStatus.in_progress,
            comment=None,
            current_user=no_role_user,
        )


# ---------------------------------------------------------------------------
# DeliveryService — full lifecycle
# ---------------------------------------------------------------------------


async def test_delivery_service_lifecycle(db_session: AsyncSession) -> None:
    from app.core.exceptions import ForbiddenError
    from app.models.delivery import DeliveryStatus
    from app.schemas.delivery import DeliveryCreate, DeliveryUpdate
    from app.services.delivery_service import DeliveryService

    service = DeliveryService(db_session)
    user = await _make_user(db_session, "delsvc@svc.test")
    project = await _make_project(db_session, user.id)

    # create delivery
    delivery = await service.create(
        project_id=project.id,
        data=DeliveryCreate(name="First Delivery", recipient="Client A"),
        created_by=user.id,
    )
    assert delivery.name == "First Delivery"
    delivery_id = delivery.id

    # get
    fetched = await service.get(delivery_id)
    assert fetched.id == delivery_id

    # get 404
    with pytest.raises(NotFoundError):
        await service.get(uuid.uuid4())

    # list by project
    _items, total = await service.list_by_project(project.id)
    assert total >= 1

    # update
    updated = await service.update(
        delivery_id,
        DeliveryUpdate(name="Updated Delivery", notes="revised"),
    )
    assert updated.name == "Updated Delivery"

    # status transition: preparing → sent
    sent = await service.update_status(delivery_id, DeliveryStatus.sent)
    assert sent.status == DeliveryStatus.sent

    # invalid transition from sent → preparing raises
    with pytest.raises(ForbiddenError):
        await service.update_status(delivery_id, DeliveryStatus.preparing)

    # sent → acknowledged
    await service.update_status(delivery_id, DeliveryStatus.acknowledged)

    # acknowledged → accepted
    await service.update_status(delivery_id, DeliveryStatus.accepted)

    # create another delivery to test delete
    del2 = await service.create(
        project_id=project.id,
        data=DeliveryCreate(name="Delete Me"),
        created_by=user.id,
    )

    # cannot delete non-preparing delivery (move it first)
    await service.update_status(del2.id, DeliveryStatus.sent)
    with pytest.raises(ForbiddenError):
        await service.delete(del2.id)

    # create a fresh one and delete it
    del3 = await service.create(
        project_id=project.id,
        data=DeliveryCreate(name="Delete Fresh"),
        created_by=user.id,
    )
    await service.delete(del3.id)

    # delete 404 via get()
    with pytest.raises(NotFoundError):
        await service.delete(uuid.uuid4())


async def test_delivery_service_items(db_session: AsyncSession) -> None:
    from app.core.exceptions import ForbiddenError
    from app.models.delivery import DeliveryStatus
    from app.schemas.delivery import DeliveryCreate, DeliveryItemCreate
    from app.schemas.version import VersionCreate
    from app.services.delivery_service import DeliveryService
    from app.services.version_service import VersionService

    del_service = DeliveryService(db_session)
    ver_service = VersionService(db_session)

    user = await _make_user(db_session, "delsvc-items@svc.test")
    project = await _make_project(db_session, user.id)
    shot = await _make_shot(db_session, project.id)
    task = await _make_task(db_session, shot.id)

    # create a version linked to the task
    version = await ver_service.create_for_task(
        task.id,
        VersionCreate(description="delivery version"),
        current_user=user,
    )

    delivery = await del_service.create(
        project_id=project.id,
        data=DeliveryCreate(name="Items Delivery"),
        created_by=user.id,
    )
    delivery_id = delivery.id

    # add item
    item = await del_service.add_item(
        delivery_id,
        DeliveryItemCreate(version_id=version.id, notes="item note"),
    )
    assert item.version_id == version.id

    # duplicate → conflict
    with pytest.raises(ConflictError):
        await del_service.add_item(
            delivery_id,
            DeliveryItemCreate(version_id=version.id),
        )

    # add item for nonexistent version → 404
    with pytest.raises(NotFoundError):
        await del_service.add_item(
            delivery_id,
            DeliveryItemCreate(version_id=uuid.uuid4()),
        )

    # list items
    items = await del_service.list_items(delivery_id)
    assert len(items) >= 1

    # list items for nonexistent delivery → 404 (via get())
    with pytest.raises(NotFoundError):
        await del_service.list_items(uuid.uuid4())

    # remove item
    await del_service.remove_item(item.id)

    # remove item 404
    with pytest.raises(NotFoundError):
        await del_service.remove_item(uuid.uuid4())

    # lock delivery and try to add/remove items
    await del_service.update_status(delivery_id, DeliveryStatus.sent)

    # create a second version for adding to locked delivery
    task2 = await _make_task(db_session, shot.id)
    version2 = await ver_service.create_for_task(
        task2.id,
        VersionCreate(description="v2"),
        current_user=user,
    )
    with pytest.raises(ForbiddenError):
        await del_service.add_item(
            delivery_id,
            DeliveryItemCreate(version_id=version2.id),
        )

    # add item to locked delivery → ForbiddenError on remove too
    # first add item before locking by using a fresh delivery
    fresh_delivery = await del_service.create(
        project_id=project.id,
        data=DeliveryCreate(name="Lock Test"),
        created_by=user.id,
    )
    item2 = await del_service.add_item(
        fresh_delivery.id,
        DeliveryItemCreate(version_id=version2.id),
    )
    await del_service.update_status(fresh_delivery.id, DeliveryStatus.sent)
    with pytest.raises(ForbiddenError):
        await del_service.remove_item(item2.id)

    # version from different project → ForbiddenError
    other_project = await _make_project(db_session, user.id)
    other_shot = await _make_shot(db_session, other_project.id)
    other_task = await _make_task(db_session, other_shot.id)
    other_version = await ver_service.create_for_task(
        other_task.id,
        VersionCreate(description="other project version"),
        current_user=user,
    )
    fresh2 = await del_service.create(
        project_id=project.id,
        data=DeliveryCreate(name="Wrong Project Delivery"),
        created_by=user.id,
    )
    with pytest.raises(ForbiddenError):
        await del_service.add_item(
            fresh2.id,
            DeliveryItemCreate(version_id=other_version.id),
        )


# ---------------------------------------------------------------------------
# ShotAssetLinkService — full lifecycle
# ---------------------------------------------------------------------------


async def test_shot_asset_link_service_lifecycle(db_session: AsyncSession) -> None:
    from app.core.exceptions import UnprocessableError
    from app.models.asset import Asset, AssetStatus, AssetType
    from app.schemas.shot_asset_link import BulkLinkCreate, LinkCreate
    from app.services.shot_asset_link_service import ShotAssetLinkService

    service = ShotAssetLinkService(db_session)
    user = await _make_user(db_session, "salservice@svc.test")
    project = await _make_project(db_session, user.id)
    await _assign_role(db_session, user.id, RoleName.artist, project.id)
    other_project = await _make_project(db_session, user.id)
    shot = await _make_shot(db_session, project.id)

    asset = Asset(
        id=uuid.uuid4(),
        project_id=project.id,
        name="LinkAsset",
        code=f"LA{uuid.uuid4().hex[:4].upper()}",
        asset_type=AssetType.prop,
        status=AssetStatus.pending,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)

    # create link
    link = await service.create_link(shot.id, LinkCreate(asset_id=asset.id), current_user=user)
    assert link.shot_id == shot.id
    assert link.asset_id == asset.id

    # duplicate link → conflict
    with pytest.raises(ConflictError):
        await service.create_link(shot.id, LinkCreate(asset_id=asset.id), current_user=user)

    # link nonexistent asset → 404
    with pytest.raises(NotFoundError):
        await service.create_link(shot.id, LinkCreate(asset_id=uuid.uuid4()), current_user=user)

    # link shot to asset in different project → UnprocessableError
    other_asset = Asset(
        id=uuid.uuid4(),
        project_id=other_project.id,
        name="OtherAsset",
        code=f"OA{uuid.uuid4().hex[:4].upper()}",
        asset_type=AssetType.prop,
        status=AssetStatus.pending,
    )
    db_session.add(other_asset)
    await db_session.commit()
    await db_session.refresh(other_asset)

    with pytest.raises(UnprocessableError):
        await service.create_link(shot.id, LinkCreate(asset_id=other_asset.id), current_user=user)

    # get_assets_for_shot
    result = await service.get_assets_for_shot(shot.id)
    assert result.total >= 1

    # get_assets_for_shot — nonexistent shot → 404
    with pytest.raises(NotFoundError):
        await service.get_assets_for_shot(uuid.uuid4())

    # get_shots_for_asset
    result2 = await service.get_shots_for_asset(asset.id)
    assert result2.total >= 1

    # get_shots_for_asset — nonexistent asset → 404
    with pytest.raises(NotFoundError):
        await service.get_shots_for_asset(uuid.uuid4())

    # delete_link_by_id
    await service.delete_link_by_id(link.id)

    # delete_link_by_id nonexistent → 404
    with pytest.raises(NotFoundError):
        await service.delete_link_by_id(uuid.uuid4())

    # delete_link (by shot+asset) — create fresh link first
    await service.create_link(shot.id, LinkCreate(asset_id=asset.id), current_user=user)
    await service.delete_link(shot.id, asset.id)

    # delete_link nonexistent → 404
    with pytest.raises(NotFoundError):
        await service.delete_link(shot.id, asset.id)

    # bulk_create_links
    asset2 = Asset(
        id=uuid.uuid4(),
        project_id=project.id,
        name="BulkAsset",
        code=f"BA{uuid.uuid4().hex[:4].upper()}",
        asset_type=AssetType.prop,
        status=AssetStatus.pending,
    )
    db_session.add(asset2)
    await db_session.commit()
    await db_session.refresh(asset2)

    bulk_resp = await service.bulk_create_links(
        shot.id,
        BulkLinkCreate(
            links=[
                LinkCreate(asset_id=asset.id),  # new link
                LinkCreate(asset_id=asset2.id),  # new link
            ]
        ),
        current_user=user,
    )
    assert len(bulk_resp.created) == 2

    # bulk with already-linked asset → goes to skipped
    bulk_resp2 = await service.bulk_create_links(
        shot.id,
        BulkLinkCreate(links=[LinkCreate(asset_id=asset.id)]),
        current_user=user,
    )
    assert asset.id in bulk_resp2.skipped

    # bulk with asset from wrong project → goes to errors
    bulk_resp3 = await service.bulk_create_links(
        shot.id,
        BulkLinkCreate(links=[LinkCreate(asset_id=other_asset.id)]),
        current_user=user,
    )
    assert other_asset.id in bulk_resp3.errors


# ---------------------------------------------------------------------------
# UserService — full lifecycle
# ---------------------------------------------------------------------------


async def test_user_service_lifecycle(db_session: AsyncSession) -> None:
    from app.core.exceptions import ForbiddenError, UnprocessableError
    from app.schemas.user import AssignRoleRequest, UserCreate, UserUpdate
    from app.services.user_service import UserService

    service = UserService(db_session)
    suffix = uuid.uuid4().hex[:8]

    # create user (use example.com — a real TLD that email-validator accepts)
    user_resp = await service.create_user(
        UserCreate(
            email=f"usrsvc-{suffix}@example.com",
            password="Secret123!",
            first_name="Svc",
            last_name="User",
        )
    )
    assert user_resp.email == f"usrsvc-{suffix}@example.com"
    user_id = user_resp.id

    # duplicate email → conflict
    with pytest.raises(ConflictError):
        await service.create_user(
            UserCreate(email=f"usrsvc-{suffix}@example.com", password="Secret123!")
        )

    # get user
    fetched = await service.get_user(user_id)
    assert fetched.id == user_id

    # get 404
    with pytest.raises(NotFoundError):
        await service.get_user(uuid.uuid4())

    # list users
    listing = await service.list_users(offset=0, limit=50, is_active=True)
    assert listing.total >= 1

    # update self (allowed)
    user_orm = await db_session.get(User, user_id)
    assert user_orm is not None
    updated = await service.update_user(
        user_id,
        UserUpdate(first_name="Updated"),
        current_user=user_orm,
    )
    assert updated.first_name == "Updated"

    # update with no changes (empty payload) → same user returned
    same = await service.update_user(user_id, UserUpdate(), current_user=user_orm)
    assert same.id == user_id

    # update 404
    with pytest.raises(NotFoundError):
        await service.update_user(uuid.uuid4(), UserUpdate(first_name="X"), current_user=user_orm)

    # other non-admin user cannot update → ForbiddenError
    other_orm = await _make_user(db_session, f"usrsvc-other-{suffix}@example.com")
    with pytest.raises(ForbiddenError):
        await service.update_user(user_id, UserUpdate(first_name="Hack"), current_user=other_orm)

    # deactivate
    deactivated = await service.deactivate_user(user_id)
    assert deactivated.is_active is False

    # deactivate 404
    with pytest.raises(NotFoundError):
        await service.deactivate_user(uuid.uuid4())

    # ensure a role exists in DB so assign_role can find it
    await _ensure_role(db_session, RoleName.artist)

    # list_roles 404
    with pytest.raises(NotFoundError):
        await service.list_roles(uuid.uuid4())

    # pre-assign the role via our test helper (committed to DB)
    project = await _make_project(db_session, user_id)
    await _assign_role(db_session, user_id, RoleName.artist, project.id)

    # list_roles — now has one role
    roles = await service.list_roles(user_id)
    assert any(r.role_name == "artist" for r in roles)

    # assign invalid role name → UnprocessableError (no DB operation, session stays clean)
    with pytest.raises(UnprocessableError):
        await service.assign_role(user_id, AssignRoleRequest(role_name="not_a_role"))

    # assign_role 404 user (NotFoundError before any DB write, session stays clean)
    with pytest.raises(NotFoundError):
        await service.assign_role(uuid.uuid4(), AssignRoleRequest(role_name="artist"))

    # assign a different role (supervisor) via service (no conflict)
    await _ensure_role(db_session, RoleName.supervisor)
    role_resp = await service.assign_role(user_id, AssignRoleRequest(role_name="supervisor"))
    assert role_resp.role_name == "supervisor"

    # remove_role (project-scoped artist)
    await service.remove_role(user_id, "artist", project_id=project.id)

    # remove_role nonexistent role assignment → 404
    with pytest.raises(NotFoundError):
        await service.remove_role(user_id, "artist", project_id=project.id)

    # remove_role invalid name → UnprocessableError
    with pytest.raises(UnprocessableError):
        await service.remove_role(user_id, "not_a_role", project_id=None)

    # remove_role 404 user
    with pytest.raises(NotFoundError):
        await service.remove_role(uuid.uuid4(), "artist", project_id=None)


# ---------------------------------------------------------------------------
# PipelineTaskService — template CRUD
# ---------------------------------------------------------------------------


async def test_pipeline_task_service_templates(db_session: AsyncSession) -> None:
    from app.models.pipeline_task import PipelineStepAppliesTo
    from app.schemas.pipeline_task import (
        PipelineTemplateCreateRequest,
        PipelineTemplateStepCreate,
        PipelineTemplateUpdateRequest,
    )
    from app.services.pipeline_task_service import PipelineTaskService

    service = PipelineTaskService(db_session)
    suffix = uuid.uuid4().hex[:6]

    # create template with steps — project_type must be a valid DB enum value
    tmpl = await service.create_template(
        PipelineTemplateCreateRequest(
            project_type="film",
            name=f"Film Pipeline {suffix}",
            description="Test template",
            steps=[
                PipelineTemplateStepCreate(
                    step_name="Animation",
                    step_type=PipelineStepType.animation,
                    order=1,
                    applies_to=PipelineStepAppliesTo.shot,
                ),
                PipelineTemplateStepCreate(
                    step_name="Compositing",
                    step_type=PipelineStepType.compositing,
                    order=2,
                    applies_to=PipelineStepAppliesTo.shot,
                ),
            ],
        )
    )
    assert tmpl.name == f"Film Pipeline {suffix}"
    assert len(tmpl.steps) == 2
    tmpl_id = tmpl.id

    # get template
    fetched = await service.get_template(tmpl_id)
    assert fetched.id == tmpl_id

    # get 404
    with pytest.raises(NotFoundError):
        await service.get_template(uuid.uuid4())

    # list templates
    listing = await service.list_templates(offset=0, limit=50)
    assert listing.total >= 1

    # update template
    updated = await service.update_template(
        tmpl_id,
        PipelineTemplateUpdateRequest(name=f"Updated Pipeline {suffix}", description="updated"),
    )
    assert updated.name == f"Updated Pipeline {suffix}"

    # update 404
    with pytest.raises(NotFoundError):
        await service.update_template(uuid.uuid4(), PipelineTemplateUpdateRequest(name="x"))

    # archive
    archived = await service.archive_template(tmpl_id)
    assert archived.archived_at is not None

    # archive 404
    with pytest.raises(NotFoundError):
        await service.archive_template(uuid.uuid4())

    # delete
    await service.delete_template(tmpl_id)

    # delete 404
    with pytest.raises(NotFoundError):
        await service.delete_template(uuid.uuid4())

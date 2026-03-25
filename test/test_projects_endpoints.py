from __future__ import annotations

import csv
import sys
import uuid
from datetime import datetime
from importlib import import_module
from io import StringIO
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
ProjectStatus = models_module.ProjectStatus
Role = models_module.Role
RoleName = models_module.RoleName
User = models_module.User
UserRole = models_module.UserRole

pytestmark = pytest.mark.projects


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


CSV_EXPORT_HEADERS = [
    "entity_type",
    "entity_id",
    "project_id",
    "code",
    "name",
    "status",
    "assigned_to",
    "frame_start",
    "frame_end",
    "asset_type",
    "created_at",
]


def _parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_project_export_csv(csv_text: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(StringIO(csv_text))
    return list(reader.fieldnames or []), list(reader)


def _activity_signature(
    item: dict[str, str],
) -> tuple[str, str, str | None, str, str | None, str | None]:
    return (
        item["entity_type"],
        item["entity_id"],
        item["old_status"],
        item["new_status"],
        item["changed_by"],
        item["comment"],
    )


@pytest.mark.asyncio
async def test_projects_crud_and_delete_admin_only(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-area23@vfxhub.dev")
    supervisor = await _create_user(db_session, "supervisor-area23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)
    await _assign_role(db_session, supervisor.id, RoleName.supervisor, None)

    create_response = await client.post(
        "/projects",
        json={"name": "Project A", "code": "PRA", "description": "Area 2.3"},
        headers=_auth_headers(admin),
    )
    assert create_response.status_code == 200
    project = create_response.json()
    project_id = project["id"]

    list_response = await client.get("/projects?status=pending", headers=_auth_headers(supervisor))
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] >= 1

    denied_delete = await client.delete(
        f"/projects/{project_id}?force=true",
        headers=_auth_headers(supervisor),
    )
    assert denied_delete.status_code == 403

    allowed_delete = await client.delete(
        f"/projects/{project_id}?force=true",
        headers=_auth_headers(admin),
    )
    assert allowed_delete.status_code == 204


@pytest.mark.asyncio
async def test_project_archive_and_restore_requires_management_role(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-archive23@vfxhub.dev")
    lead = await _create_user(db_session, "lead-archive23@vfxhub.dev")
    artist = await _create_user(db_session, "artist-archive23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    create_project = await client.post(
        "/projects",
        json={"name": "Archive Project", "code": "ARC23"},
        headers=_auth_headers(admin),
    )
    assert create_project.status_code == 200
    project_id = create_project.json()["id"]

    project_uuid = uuid.UUID(project_id)
    await _assign_role(db_session, lead.id, RoleName.lead, project_uuid)
    await _assign_role(db_session, artist.id, RoleName.artist, project_uuid)

    denied_archive = await client.post(
        f"/projects/{project_id}/archive",
        headers=_auth_headers(artist),
    )
    assert denied_archive.status_code == 403

    archived = await client.post(
        f"/projects/{project_id}/archive",
        headers=_auth_headers(lead),
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None

    hidden_after_archive = await client.get(
        f"/projects/{project_id}",
        headers=_auth_headers(lead),
    )
    assert hidden_after_archive.status_code == 404

    denied_restore = await client.post(
        f"/projects/{project_id}/restore",
        headers=_auth_headers(artist),
    )
    assert denied_restore.status_code == 403

    restored = await client.post(
        f"/projects/{project_id}/restore",
        headers=_auth_headers(admin),
    )
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None


@pytest.mark.asyncio
async def test_list_projects_can_include_archived_items(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-listarchived23@vfxhub.dev")
    supervisor = await _create_user(db_session, "supervisor-listarchived23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)
    await _assign_role(db_session, supervisor.id, RoleName.supervisor, None)

    archived_response = await client.post(
        "/projects",
        json={"name": "Archived List Project", "code": "ALP23", "description": "archived target"},
        headers=_auth_headers(admin),
    )
    assert archived_response.status_code == 200
    archived_project = archived_response.json()
    archived_project_id = archived_project["id"]

    active_response = await client.post(
        "/projects",
        json={"name": "Active List Project", "code": "ACT23", "description": "active target"},
        headers=_auth_headers(admin),
    )
    assert active_response.status_code == 200
    active_project = active_response.json()
    active_project_id = active_project["id"]

    archive_response = await client.post(
        f"/projects/{archived_project_id}/archive",
        headers=_auth_headers(admin),
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["archived_at"] is not None

    default_list = await client.get("/projects", headers=_auth_headers(supervisor))
    assert default_list.status_code == 200
    default_payload = default_list.json()
    default_items = {item["id"]: item for item in default_payload["items"]}

    assert archived_project_id not in default_items
    assert active_project_id in default_items

    include_archived_list = await client.get(
        "/projects?include_archived=true",
        headers=_auth_headers(supervisor),
    )
    assert include_archived_list.status_code == 200
    include_archived_payload = include_archived_list.json()
    include_archived_items = {item["id"]: item for item in include_archived_payload["items"]}

    assert active_project_id in include_archived_items
    assert archived_project_id in include_archived_items
    assert include_archived_items[archived_project_id]["archived_at"] is not None
    assert include_archived_payload["total"] >= default_payload["total"] + 1


@pytest.mark.asyncio
async def test_list_projects_include_archived_respects_project_visibility(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-scopedarchived23@vfxhub.dev")
    artist = await _create_user(db_session, "artist-scopedarchived23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    visible_project_response = await client.post(
        "/projects",
        json={"name": "Scoped Archived Visible", "code": "SAV23"},
        headers=_auth_headers(admin),
    )
    assert visible_project_response.status_code == 200
    visible_project_id = visible_project_response.json()["id"]

    hidden_project_response = await client.post(
        "/projects",
        json={"name": "Scoped Archived Hidden", "code": "SAH23"},
        headers=_auth_headers(admin),
    )
    assert hidden_project_response.status_code == 200
    hidden_project_id = hidden_project_response.json()["id"]

    await _assign_role(db_session, artist.id, RoleName.artist, uuid.UUID(visible_project_id))

    archive_visible = await client.post(
        f"/projects/{visible_project_id}/archive",
        headers=_auth_headers(admin),
    )
    assert archive_visible.status_code == 200

    archive_hidden = await client.post(
        f"/projects/{hidden_project_id}/archive",
        headers=_auth_headers(admin),
    )
    assert archive_hidden.status_code == 200

    list_resp = await client.get(
        "/projects?include_archived=true",
        headers=_auth_headers(artist),
    )
    assert list_resp.status_code == 200
    items = {item["id"]: item for item in list_resp.json()["items"]}

    assert visible_project_id in items
    assert items[visible_project_id]["archived_at"] is not None
    assert hidden_project_id not in items


@pytest.mark.asyncio
async def test_project_overview_returns_aggregated_counts_and_completion(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-overview23@vfxhub.dev")
    lead = await _create_user(db_session, "lead-overview23@vfxhub.dev")
    artist = await _create_user(db_session, "artist-overview23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    create_project = await client.post(
        "/projects",
        json={"name": "Overview Project", "code": "OVW23"},
        headers=_auth_headers(admin),
    )
    assert create_project.status_code == 200
    project_id = create_project.json()["id"]

    project_uuid = uuid.UUID(project_id)
    await _assign_role(db_session, lead.id, RoleName.lead, project_uuid)
    await _assign_role(db_session, artist.id, RoleName.artist, project_uuid)

    shot_response = await client.post(
        f"/projects/{project_id}/shots",
        json={"name": "Shot OVW", "code": "SOVW01", "assigned_to": str(artist.id)},
        headers=_auth_headers(lead),
    )
    assert shot_response.status_code == 200
    shot_id = shot_response.json()["id"]

    asset_response = await client.post(
        f"/projects/{project_id}/assets",
        json={"name": "Asset OVW", "asset_type": "prop", "assigned_to": str(artist.id)},
        headers=_auth_headers(lead),
    )
    assert asset_response.status_code == 200
    asset_id = asset_response.json()["id"]

    denied_overview = await client.get(
        f"/projects/{project_id}/overview",
        headers={"Authorization": "Bearer invalid"},
    )
    assert denied_overview.status_code == 401

    shot_status = await client.patch(
        f"/shots/{shot_id}/status",
        json={"status": "in_progress", "comment": "start"},
        headers=_auth_headers(artist),
    )
    assert shot_status.status_code == 200

    asset_status = await client.patch(
        f"/assets/{asset_id}/status",
        json={"status": "in_progress", "comment": "start"},
        headers=_auth_headers(artist),
    )
    assert asset_status.status_code == 200

    overview = await client.get(
        f"/projects/{project_id}/overview",
        headers=_auth_headers(artist),
    )
    assert overview.status_code == 200
    payload = overview.json()

    assert payload["project_id"] == project_id
    assert payload["total_shots"] == 1
    assert payload["total_assets"] == 1
    assert payload["shot_status_counts"].get("in_progress") == 1
    assert payload["asset_status_counts"].get("in_progress") == 1
    assert payload["completion_percent"] == 0.0


@pytest.mark.asyncio
async def test_patch_project_allows_project_lead(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-projectpatch23@vfxhub.dev")
    lead = await _create_user(db_session, "lead-projectpatch23@vfxhub.dev")
    artist = await _create_user(db_session, "artist-projectpatch23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    create_project = await client.post(
        "/projects",
        json={"name": "Patch Project", "code": "PCH23", "description": "before"},
        headers=_auth_headers(admin),
    )
    project_id = create_project.json()["id"]

    await _assign_role(db_session, lead.id, RoleName.lead, uuid.UUID(project_id))
    await _assign_role(db_session, artist.id, RoleName.artist, uuid.UUID(project_id))

    denied = await client.patch(
        f"/projects/{project_id}",
        json={"description": "artist change"},
        headers=_auth_headers(artist),
    )
    assert denied.status_code == 403

    allowed = await client.patch(
        f"/projects/{project_id}",
        json={"description": "lead change", "status": "in_progress"},
        headers=_auth_headers(lead),
    )
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["description"] == "lead change"
    assert payload["status"] == ProjectStatus.in_progress.value


@pytest.mark.asyncio
async def test_create_project_generates_unique_code_when_omitted(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-autocode23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    first_response = await client.post(
        "/projects",
        json={"name": "Auto Code Project"},
        headers=_auth_headers(admin),
    )
    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["code"] == "AUTO_CODE_PROJECT"

    second_response = await client.post(
        "/projects",
        json={"name": "Auto Code Project"},
        headers=_auth_headers(admin),
    )
    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["code"] == "AUTO_CODE_PROJECT_2"


@pytest.mark.asyncio
async def test_project_report_includes_storage_and_recent_activity(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_root", str(tmp_path))

    admin = await _create_user(db_session, "admin-report23@vfxhub.dev")
    lead = await _create_user(db_session, "lead-report23@vfxhub.dev")
    artist = await _create_user(db_session, "artist-report23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    create_project = await client.post(
        "/projects",
        json={"name": "Report Project", "code": "RPT23"},
        headers=_auth_headers(admin),
    )
    assert create_project.status_code == 200
    project_id = create_project.json()["id"]

    project_uuid = uuid.UUID(project_id)
    await _assign_role(db_session, lead.id, RoleName.lead, project_uuid)
    await _assign_role(db_session, artist.id, RoleName.artist, project_uuid)

    create_shot = await client.post(
        f"/projects/{project_id}/shots",
        json={"name": "Shot Report", "code": "SREP01", "assigned_to": str(artist.id)},
        headers=_auth_headers(lead),
    )
    assert create_shot.status_code == 200
    shot_id = create_shot.json()["id"]

    create_asset = await client.post(
        f"/projects/{project_id}/assets",
        json={"name": "Asset Report", "asset_type": "prop", "assigned_to": str(artist.id)},
        headers=_auth_headers(lead),
    )
    assert create_asset.status_code == 200
    asset_id = create_asset.json()["id"]

    shot_in_progress = await client.patch(
        f"/shots/{shot_id}/status",
        json={"status": "in_progress", "comment": "start shot"},
        headers=_auth_headers(artist),
    )
    assert shot_in_progress.status_code == 200
    shot_in_progress_payload = shot_in_progress.json()

    shot_review = await client.patch(
        f"/shots/{shot_id}/status",
        json={"status": "review", "comment": "review shot"},
        headers=_auth_headers(artist),
    )
    assert shot_review.status_code == 200
    shot_review_payload = shot_review.json()

    shot_revision = await client.patch(
        f"/shots/{shot_id}/status",
        json={"status": "revision", "comment": "request changes"},
        headers=_auth_headers(admin),
    )
    assert shot_revision.status_code == 200
    shot_revision_payload = shot_revision.json()

    shot_status = await client.patch(
        f"/shots/{shot_id}/status",
        json={"status": "approved", "comment": "approved shot"},
        headers=_auth_headers(admin),
    )
    assert shot_status.status_code == 200
    shot_status_payload = shot_status.json()

    asset_in_progress = await client.patch(
        f"/assets/{asset_id}/status",
        json={"status": "in_progress", "comment": "start asset"},
        headers=_auth_headers(artist),
    )
    assert asset_in_progress.status_code == 200
    asset_in_progress_payload = asset_in_progress.json()

    asset_review = await client.patch(
        f"/assets/{asset_id}/status",
        json={"status": "review", "comment": "review asset"},
        headers=_auth_headers(artist),
    )
    assert asset_review.status_code == 200
    asset_review_payload = asset_review.json()

    asset_revision = await client.patch(
        f"/assets/{asset_id}/status",
        json={"status": "revision", "comment": "request changes"},
        headers=_auth_headers(admin),
    )
    assert asset_revision.status_code == 200
    asset_revision_payload = asset_revision.json()

    asset_approved = await client.patch(
        f"/assets/{asset_id}/status",
        json={"status": "approved", "comment": "approved asset"},
        headers=_auth_headers(admin),
    )
    assert asset_approved.status_code == 200
    asset_approved_payload = asset_approved.json()

    asset_status = await client.patch(
        f"/assets/{asset_id}/status",
        json={"status": "delivered", "comment": "delivered asset"},
        headers=_auth_headers(admin),
    )
    assert asset_status.status_code == 200
    asset_status_payload = asset_status.json()

    shot_bytes = b"shot-data"
    shot_upload = await client.post(
        f"/projects/{project_id}/files/upload",
        files={"upload": ("shot.exr", shot_bytes, "image/x-exr")},
        data={"shot_id": shot_id},
        headers=_auth_headers(artist),
    )
    assert shot_upload.status_code == 200

    asset_bytes = b"asset-data"
    asset_upload = await client.post(
        f"/projects/{project_id}/files/upload",
        files={"upload": ("asset.exr", asset_bytes, "image/x-exr")},
        data={"asset_id": asset_id},
        headers=_auth_headers(artist),
    )
    assert asset_upload.status_code == 200

    report = await client.get(f"/projects/{project_id}/report", headers=_auth_headers(artist))
    assert report.status_code == 200
    payload = report.json()

    assert payload["project_id"] == project_id
    assert payload["total_shots"] == 1
    assert payload["total_assets"] == 1
    assert payload["shot_status_counts"].get("approved") == 1
    assert payload["asset_status_counts"].get("delivered") == 1
    assert payload["completion_percent"] == 100.0
    assert payload["uploaded_files_total"] == 2
    assert payload["storage_used_bytes"] == len(shot_bytes) + len(asset_bytes)

    expected_activity = [
        {
            "entity_type": "shot",
            "entity_id": shot_id,
            "old_status": shot_in_progress_payload["old_status"],
            "new_status": shot_in_progress_payload["new_status"],
            "changed_by": str(artist.id),
            "comment": shot_in_progress_payload["comment"],
        },
        {
            "entity_type": "shot",
            "entity_id": shot_id,
            "old_status": shot_review_payload["old_status"],
            "new_status": shot_review_payload["new_status"],
            "changed_by": str(artist.id),
            "comment": shot_review_payload["comment"],
        },
        {
            "entity_type": "shot",
            "entity_id": shot_id,
            "old_status": shot_revision_payload["old_status"],
            "new_status": shot_revision_payload["new_status"],
            "changed_by": str(admin.id),
            "comment": shot_revision_payload["comment"],
        },
        {
            "entity_type": "shot",
            "entity_id": shot_id,
            "old_status": shot_status_payload["old_status"],
            "new_status": shot_status_payload["new_status"],
            "changed_by": str(admin.id),
            "comment": shot_status_payload["comment"],
        },
        {
            "entity_type": "asset",
            "entity_id": asset_id,
            "old_status": asset_in_progress_payload["old_status"],
            "new_status": asset_in_progress_payload["new_status"],
            "changed_by": str(artist.id),
            "comment": asset_in_progress_payload["comment"],
        },
        {
            "entity_type": "asset",
            "entity_id": asset_id,
            "old_status": asset_review_payload["old_status"],
            "new_status": asset_review_payload["new_status"],
            "changed_by": str(artist.id),
            "comment": asset_review_payload["comment"],
        },
        {
            "entity_type": "asset",
            "entity_id": asset_id,
            "old_status": asset_revision_payload["old_status"],
            "new_status": asset_revision_payload["new_status"],
            "changed_by": str(admin.id),
            "comment": asset_revision_payload["comment"],
        },
        {
            "entity_type": "asset",
            "entity_id": asset_id,
            "old_status": asset_approved_payload["old_status"],
            "new_status": asset_approved_payload["new_status"],
            "changed_by": str(admin.id),
            "comment": asset_approved_payload["comment"],
        },
        {
            "entity_type": "asset",
            "entity_id": asset_id,
            "old_status": asset_status_payload["old_status"],
            "new_status": asset_status_payload["new_status"],
            "changed_by": str(admin.id),
            "comment": asset_status_payload["comment"],
        },
    ]

    recent_activity = payload["recent_activity"]
    assert len(recent_activity) == len(expected_activity)
    assert {_activity_signature(item) for item in recent_activity} == {
        _activity_signature(item) for item in expected_activity
    }

    changed_at_values = [_parse_iso8601(item["changed_at"]) for item in recent_activity]
    assert changed_at_values == sorted(changed_at_values, reverse=True)


@pytest.mark.asyncio
async def test_project_export_csv_sync_and_async_modes(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = await _create_user(db_session, "admin-export23@vfxhub.dev")
    lead = await _create_user(db_session, "lead-export23@vfxhub.dev")
    artist = await _create_user(db_session, "artist-export23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    create_project = await client.post(
        "/projects",
        json={"name": "Export Project", "code": "EXP23"},
        headers=_auth_headers(admin),
    )
    assert create_project.status_code == 200
    project_id = create_project.json()["id"]

    project_uuid = uuid.UUID(project_id)
    await _assign_role(db_session, lead.id, RoleName.lead, project_uuid)
    await _assign_role(db_session, artist.id, RoleName.artist, project_uuid)

    create_shot = await client.post(
        f"/projects/{project_id}/shots",
        json={"name": "Shot Export", "code": "SEXP01"},
        headers=_auth_headers(lead),
    )
    assert create_shot.status_code == 200
    shot_payload = create_shot.json()

    create_asset = await client.post(
        f"/projects/{project_id}/assets",
        json={"name": "Asset Export", "asset_type": "environment"},
        headers=_auth_headers(lead),
    )
    assert create_asset.status_code == 200
    asset_payload = create_asset.json()

    monkeypatch.setattr(settings, "project_export_async_threshold_entities", 100)
    sync_response = await client.get(
        f"/projects/{project_id}/export?format=csv",
        headers=_auth_headers(artist),
    )
    assert sync_response.status_code == 200
    assert sync_response.headers["content-type"].startswith("text/csv")
    assert sync_response.headers["content-disposition"] == 'attachment; filename="exp23_export.csv"'
    headers, rows = _parse_project_export_csv(sync_response.text)
    assert headers == CSV_EXPORT_HEADERS
    assert len(rows) == 2

    rows_by_type = {row["entity_type"]: row for row in rows}
    assert set(rows_by_type) == {"shot", "asset"}

    shot_row = rows_by_type["shot"]
    assert shot_row["entity_id"] == shot_payload["id"]
    assert shot_row["project_id"] == project_id
    assert shot_row["code"] == "SEXP01"
    assert shot_row["name"] == "Shot Export"
    assert shot_row["status"] == "pending"
    assert shot_row["assigned_to"] == ""
    assert shot_row["frame_start"] == ""
    assert shot_row["frame_end"] == ""
    assert shot_row["asset_type"] == ""
    assert _parse_iso8601(shot_row["created_at"])

    asset_row = rows_by_type["asset"]
    assert asset_row["entity_id"] == asset_payload["id"]
    assert asset_row["project_id"] == project_id
    assert asset_row["code"] == "ASSET_EXPORT"
    assert asset_row["name"] == "Asset Export"
    assert asset_row["status"] == "pending"
    assert asset_row["assigned_to"] == ""
    assert asset_row["frame_start"] == ""
    assert asset_row["frame_end"] == ""
    assert asset_row["asset_type"] == "environment"
    assert _parse_iso8601(asset_row["created_at"])

    monkeypatch.setattr(settings, "project_export_async_threshold_entities", 1)
    async_response = await client.get(
        f"/projects/{project_id}/export?format=csv",
        headers=_auth_headers(artist),
    )
    assert async_response.status_code == 202
    async_payload = async_response.json()
    assert async_payload["status"] == "pending"
    assert async_payload["task_id"]

    task_id = async_payload["task_id"]
    task_status = await client.get(f"/tasks/{task_id}", headers=_auth_headers(artist))
    assert task_status.status_code == 200
    task_payload = task_status.json()
    assert task_payload["id"] == task_id
    assert task_payload["task_type"] == "project_export_csv"
    assert task_payload["status"] in {"pending", "running"}
    assert task_payload["created_by"] == str(artist.id)
    assert task_payload["result"] is None
    assert task_payload["error"] is None


@pytest.mark.asyncio
async def test_project_export_rejects_unsupported_format(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-export-invalid23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    create_project = await client.post(
        "/projects",
        json={"name": "Export Invalid", "code": "EXI23"},
        headers=_auth_headers(admin),
    )
    assert create_project.status_code == 200
    project_id = create_project.json()["id"]

    response = await client.get(
        f"/projects/{project_id}/export?format=xlsx",
        headers=_auth_headers(admin),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_single_project(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-getone23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    create_resp = await client.post(
        "/projects",
        json={"name": "Get Single Project", "code": "GSP23"},
        headers=_auth_headers(admin),
    )
    assert create_resp.status_code == 200
    project_id = create_resp.json()["id"]

    get_resp = await client.get(f"/projects/{project_id}", headers=_auth_headers(admin))
    assert get_resp.status_code == 200
    payload = get_resp.json()
    assert payload["id"] == project_id
    assert payload["name"] == "Get Single Project"
    assert payload["code"] == "GSP23"


@pytest.mark.asyncio
async def test_list_projects_pagination(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-pagination23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    for i in range(3):
        r = await client.post(
            "/projects",
            json={"name": f"Pagination Project {i}", "code": f"PAG2{i}"},
            headers=_auth_headers(admin),
        )
        assert r.status_code == 200

    page1 = await client.get(
        "/projects?offset=0&limit=2",
        headers=_auth_headers(admin),
    )
    assert page1.status_code == 200
    page1_payload = page1.json()
    assert len(page1_payload["items"]) == 2
    assert page1_payload["total"] >= 3

    page2 = await client.get(
        "/projects?offset=2&limit=2",
        headers=_auth_headers(admin),
    )
    assert page2.status_code == 200
    page2_payload = page2.json()
    assert len(page2_payload["items"]) >= 1

    page1_ids = {item["id"] for item in page1_payload["items"]}
    page2_ids = {item["id"] for item in page2_payload["items"]}
    assert page1_ids.isdisjoint(page2_ids)


@pytest.mark.asyncio
async def test_list_projects_role_visibility(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(db_session, "admin-visibility23@vfxhub.dev")
    artist_a = await _create_user(db_session, "artist-a-visibility23@vfxhub.dev")
    await _create_user(db_session, "artist-b-visibility23@vfxhub.dev")
    await _assign_role(db_session, admin.id, RoleName.admin, None)

    proj_a = await client.post(
        "/projects",
        json={"name": "Visible Project A", "code": "VPA23"},
        headers=_auth_headers(admin),
    )
    assert proj_a.status_code == 200
    proj_a_id = proj_a.json()["id"]

    proj_b = await client.post(
        "/projects",
        json={"name": "Visible Project B", "code": "VPB23"},
        headers=_auth_headers(admin),
    )
    assert proj_b.status_code == 200
    proj_b_id = proj_b.json()["id"]

    # artist_a is only assigned to project A
    await _assign_role(db_session, artist_a.id, RoleName.artist, uuid.UUID(proj_a_id))

    list_resp = await client.get("/projects", headers=_auth_headers(artist_a))
    assert list_resp.status_code == 200
    visible_ids = {item["id"] for item in list_resp.json()["items"]}

    assert proj_a_id in visible_ids
    assert proj_b_id not in visible_ids

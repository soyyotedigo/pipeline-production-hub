from __future__ import annotations

import csv
import sys
import uuid
from importlib import import_module
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

exceptions_module = import_module("app.core.exceptions")
service_module = import_module("app.services.project_service")
schema_module = import_module("app.schemas.project")
asset_schema_module = import_module("app.schemas.asset")
shot_schema_module = import_module("app.schemas.shot")
models_module = import_module("app.models")

ProjectService = service_module.ProjectService
NotFoundError = exceptions_module.NotFoundError
ForbiddenError = exceptions_module.ForbiddenError
ConflictError = exceptions_module.ConflictError
UnprocessableError = exceptions_module.UnprocessableError
ProjectExportAcceptedResponse = schema_module.ProjectExportAcceptedResponse
ProjectCreateRequest = schema_module.ProjectCreateRequest
ScaffoldRequest = schema_module.ScaffoldRequest
AssetCreateRequest = asset_schema_module.AssetCreateRequest
AssetUpdateRequest = asset_schema_module.AssetUpdateRequest
ShotCreateRequest = shot_schema_module.ShotCreateRequest
ShotUpdateRequest = shot_schema_module.ShotUpdateRequest
ShotStatus = models_module.ShotStatus
AssetStatus = models_module.AssetStatus
AssetType = models_module.AssetType
ProjectStatus = models_module.ProjectStatus
Priority = models_module.Priority
RoleName = models_module.RoleName

pytestmark = pytest.mark.projects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


def _make_service(db: AsyncMock) -> ProjectService:
    svc = ProjectService.__new__(ProjectService)
    svc.db = db
    svc.project_repository = AsyncMock()
    svc.shot_repository = AsyncMock()
    svc.asset_repository = AsyncMock()
    svc.file_repository = AsyncMock()
    svc.status_log_repository = AsyncMock()
    svc.episode_repository = AsyncMock()
    svc.sequence_repository = AsyncMock()
    svc.user_role_repository = AsyncMock()
    svc.task_service = AsyncMock()
    svc.webhook_service = AsyncMock()
    return svc


def _make_project(code: str = "TST", name: str = "Test Project") -> MagicMock:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    project = MagicMock()
    project.id = uuid.uuid4()
    project.code = code
    project.name = name
    project.client = None
    project.project_type = None
    project.status = ProjectStatus.in_progress
    project.description = None
    project.start_date = None
    project.end_date = None
    project.fps = None
    project.resolution_width = None
    project.resolution_height = None
    project.thumbnail_url = None
    project.color_space = None
    project.created_by = uuid.uuid4()
    project.naming_rules = None
    project.path_templates = None
    project.created_at = now
    project.updated_at = now
    project.archived_at = None
    return project


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _make_shot(
    project_id: uuid.UUID,
    sequence_id: uuid.UUID | None = None,
    code: str = "SH010",
) -> MagicMock:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    shot = MagicMock()
    shot.id = uuid.uuid4()
    shot.project_id = project_id
    shot.sequence_id = sequence_id
    shot.code = code
    shot.name = code
    shot.status = ShotStatus.pending
    shot.assigned_to = None
    shot.frame_start = 1001
    shot.frame_end = 1024
    shot.description = None
    shot.thumbnail_url = None
    shot.priority = Priority.normal
    shot.difficulty = None
    shot.handle_head = None
    shot.handle_tail = None
    shot.cut_in = None
    shot.cut_out = None
    shot.bid_days = None
    shot.sort_order = None
    shot.created_at = now
    shot.updated_at = now
    shot.archived_at = None
    return shot


def _make_asset(
    project_id: uuid.UUID,
    code: str = "CHAR_HERO",
    asset_type: AssetType = AssetType.character,
) -> MagicMock:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    asset = MagicMock()
    asset.id = uuid.uuid4()
    asset.project_id = project_id
    asset.code = code
    asset.name = "Hero"
    asset.status = AssetStatus.pending
    asset.asset_type = asset_type
    asset.assigned_to = None
    asset.description = None
    asset.thumbnail_url = None
    asset.priority = Priority.normal
    asset.created_at = now
    asset.updated_at = now
    asset.archived_at = None
    return asset


def _make_sequence(
    project_id: uuid.UUID,
    code: str = "SQ010",
    episode_id: uuid.UUID | None = None,
) -> MagicMock:
    seq = MagicMock()
    seq.id = uuid.uuid4()
    seq.project_id = project_id
    seq.code = code
    seq.episode_id = episode_id
    return seq


def _make_episode(code: str = "EP010") -> MagicMock:
    ep = MagicMock()
    ep.id = uuid.uuid4()
    ep.code = code
    return ep


# ---------------------------------------------------------------------------
# get_project_overview
# ---------------------------------------------------------------------------


class TestGetProjectOverview:
    async def test_overview_with_shots_and_assets_returns_correct_counts(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project()
        user = _make_user()

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = True
        svc.project_repository.count_shots.return_value = 10
        svc.project_repository.count_assets.return_value = 5
        svc.project_repository.shot_status_counts.return_value = {
            ShotStatus.approved.value: 2,
            ShotStatus.delivered.value: 1,
            ShotStatus.final.value: 0,
            ShotStatus.in_progress.value: 7,
        }
        svc.project_repository.asset_status_counts.return_value = {
            AssetStatus.approved.value: 1,
            AssetStatus.pending.value: 4,
        }

        result = await svc.get_project_overview(project.id, user)

        assert result.project_id == project.id
        assert result.total_shots == 10
        assert result.total_assets == 5
        # completed = shots(approved=2 + delivered=1 + final=0) + assets(approved=1) = 4
        # completion_percent = 4 / 15 * 100 ≈ 26.67
        assert result.completion_percent == round(4 / 15 * 100, 2)

    async def test_overview_with_zero_entities_returns_zero_completion(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project()
        user = _make_user()

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = True
        svc.project_repository.count_shots.return_value = 0
        svc.project_repository.count_assets.return_value = 0
        svc.project_repository.shot_status_counts.return_value = {}
        svc.project_repository.asset_status_counts.return_value = {}

        result = await svc.get_project_overview(project.id, user)

        assert result.total_shots == 0
        assert result.total_assets == 0
        assert result.completion_percent == 0.0

    async def test_overview_raises_not_found_when_project_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.project_repository.get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await svc.get_project_overview(uuid.uuid4(), user)

    async def test_overview_raises_forbidden_when_user_lacks_role(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project()
        user = _make_user()

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = False

        with pytest.raises(ForbiddenError):
            await svc.get_project_overview(project.id, user)

    async def test_overview_all_completed_gives_100_percent(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project()
        user = _make_user()

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = True
        svc.project_repository.count_shots.return_value = 3
        svc.project_repository.count_assets.return_value = 2
        svc.project_repository.shot_status_counts.return_value = {
            ShotStatus.approved.value: 3,
        }
        svc.project_repository.asset_status_counts.return_value = {
            AssetStatus.final.value: 2,
        }

        result = await svc.get_project_overview(project.id, user)

        assert result.completion_percent == 100.0


# ---------------------------------------------------------------------------
# export_project_csv
# ---------------------------------------------------------------------------


class TestExportProjectCsv:
    async def test_sync_export_returns_filename_and_bytes(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project(code="EXP")
        user = _make_user()

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = True
        svc.project_repository.count_shots.return_value = 1
        svc.project_repository.count_assets.return_value = 1
        shot = _make_shot(project.id)
        asset = _make_asset(project.id)
        svc.shot_repository.list_all_for_project.return_value = [shot]
        svc.asset_repository.list_all_for_project.return_value = [asset]

        with patch(
            "app.core.config.settings.project_export_async_threshold_entities",
            new=100,
        ):
            result = await svc.export_project_csv(project.id, user)

        assert isinstance(result, tuple)
        filename, csv_bytes = result
        assert filename == "exp_export.csv"
        assert isinstance(csv_bytes, bytes)

    async def test_sync_export_csv_contains_expected_headers(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project(code="EXP")
        user = _make_user()

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = True
        svc.project_repository.count_shots.return_value = 0
        svc.project_repository.count_assets.return_value = 0
        svc.shot_repository.list_all_for_project.return_value = []
        svc.asset_repository.list_all_for_project.return_value = []

        with patch(
            "app.core.config.settings.project_export_async_threshold_entities",
            new=100,
        ):
            _, csv_bytes = await svc.export_project_csv(project.id, user)

        reader = csv.DictReader(StringIO(csv_bytes.decode("utf-8")))
        expected_headers = [
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
        assert list(reader.fieldnames or []) == expected_headers

    async def test_sync_export_includes_shot_and_asset_rows(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project(code="EXP")
        user = _make_user()

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = True
        svc.project_repository.count_shots.return_value = 1
        svc.project_repository.count_assets.return_value = 1
        shot = _make_shot(project.id, code="SH010")
        asset = _make_asset(project.id, code="CHAR_HERO")
        svc.shot_repository.list_all_for_project.return_value = [shot]
        svc.asset_repository.list_all_for_project.return_value = [asset]

        with patch(
            "app.core.config.settings.project_export_async_threshold_entities",
            new=100,
        ):
            _, csv_bytes = await svc.export_project_csv(project.id, user)

        reader = csv.DictReader(StringIO(csv_bytes.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 2
        entity_types = {row["entity_type"] for row in rows}
        assert entity_types == {"shot", "asset"}
        shot_row = next(r for r in rows if r["entity_type"] == "shot")
        assert shot_row["code"] == "SH010"
        asset_row = next(r for r in rows if r["entity_type"] == "asset")
        assert asset_row["code"] == "CHAR_HERO"

    async def test_async_export_returns_accepted_response_when_above_threshold(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project(code="BIG")
        user = _make_user()
        fake_task_id = uuid.uuid4()

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = True
        svc.project_repository.count_shots.return_value = 5
        svc.project_repository.count_assets.return_value = 5
        svc.task_service.enqueue_task = AsyncMock(return_value=fake_task_id)

        with patch(
            "app.core.config.settings.project_export_async_threshold_entities",
            new=1,
        ):
            result = await svc.export_project_csv(project.id, user)

        assert isinstance(result, ProjectExportAcceptedResponse)
        assert result.task_id == fake_task_id
        assert result.status == "pending"

    async def test_export_raises_not_found_when_project_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.project_repository.get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await svc.export_project_csv(uuid.uuid4(), user)

    async def test_export_raises_forbidden_when_user_lacks_role(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project()
        user = _make_user()

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = False

        with pytest.raises(ForbiddenError):
            await svc.export_project_csv(project.id, user)


# ---------------------------------------------------------------------------
# scaffold_project_filesystem
# ---------------------------------------------------------------------------


class TestScaffoldProjectFilesystem:
    async def test_scaffold_returns_base_dirs_for_empty_project(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project(code="TST")
        user = _make_user()

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = True
        svc.episode_repository.list_all_for_project.return_value = []
        svc.sequence_repository.list_all_for_project.return_value = []
        svc.shot_repository.list_all_for_project.return_value = []
        svc.asset_repository.list_all_for_project.return_value = []

        payload = ScaffoldRequest(root="/projects")

        result = await svc.scaffold_project_filesystem(project.id, payload, user)

        assert result.project_code == "TST"
        assert result.root == "/projects"
        # Base dirs: project_root, assets, shots, references, deliveries
        base_dirs = set(result.created_dirs)
        assert any("TST" in d and d.endswith("TST") for d in base_dirs)
        assert any(d.endswith("assets") for d in base_dirs)
        assert any(d.endswith("shots") for d in base_dirs)
        assert any(d.endswith("references") for d in base_dirs)
        assert any(d.endswith("deliveries") for d in base_dirs)

    async def test_scaffold_creates_shot_dirs_with_department_subdirs(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project(code="TST")
        user = _make_user()
        shot = _make_shot(project.id, sequence_id=None, code="SH010")

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = True
        svc.episode_repository.list_all_for_project.return_value = []
        svc.sequence_repository.list_all_for_project.return_value = []
        svc.shot_repository.list_all_for_project.return_value = [shot]
        svc.asset_repository.list_all_for_project.return_value = []

        payload = ScaffoldRequest(root="/projects")

        result = await svc.scaffold_project_filesystem(project.id, payload, user)

        shot_dirs = [d for d in result.created_dirs if "SH010" in d]
        assert len(shot_dirs) > 0
        # Each shot gets work/ and publish/ subdirs for each department
        departments = ["anim", "comp", "fx", "light", "model", "rig", "layout"]
        for dept in departments:
            assert any(f"work/{dept}" in d or f"work\\{dept}" in d for d in result.created_dirs)
            assert any(
                f"publish/{dept}" in d or f"publish\\{dept}" in d for d in result.created_dirs
            )

    async def test_scaffold_creates_asset_dirs_by_type(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project(code="TST")
        user = _make_user()
        asset = _make_asset(project.id, code="HERO", asset_type=AssetType.character)

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = True
        svc.episode_repository.list_all_for_project.return_value = []
        svc.sequence_repository.list_all_for_project.return_value = []
        svc.shot_repository.list_all_for_project.return_value = []
        svc.asset_repository.list_all_for_project.return_value = [asset]

        payload = ScaffoldRequest(root="/projects")

        result = await svc.scaffold_project_filesystem(project.id, payload, user)

        asset_dirs = [d for d in result.created_dirs if "HERO" in d]
        assert len(asset_dirs) > 0
        assert any("character" in d for d in result.created_dirs)
        assert any(d.endswith("work") for d in asset_dirs)
        assert any(d.endswith("publish") for d in asset_dirs)

    async def test_scaffold_places_shot_under_sequence_dir(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project(code="TST")
        user = _make_user()
        seq = _make_sequence(project.id, code="SQ010")
        shot = _make_shot(project.id, sequence_id=seq.id, code="SH010")

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = True
        svc.episode_repository.list_all_for_project.return_value = []
        svc.sequence_repository.list_all_for_project.return_value = [seq]
        svc.shot_repository.list_all_for_project.return_value = [shot]
        svc.asset_repository.list_all_for_project.return_value = []

        payload = ScaffoldRequest(root="/projects")

        result = await svc.scaffold_project_filesystem(project.id, payload, user)

        shot_root_dirs = [
            d
            for d in result.created_dirs
            if "SH010" in d and "work" not in d and "publish" not in d
        ]
        assert len(shot_root_dirs) == 1
        assert "SQ010" in shot_root_dirs[0]

    async def test_scaffold_total_matches_created_dirs_length(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project(code="TST")
        user = _make_user()

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = True
        svc.episode_repository.list_all_for_project.return_value = []
        svc.sequence_repository.list_all_for_project.return_value = []
        svc.shot_repository.list_all_for_project.return_value = []
        svc.asset_repository.list_all_for_project.return_value = []

        payload = ScaffoldRequest(root="/projects")

        result = await svc.scaffold_project_filesystem(project.id, payload, user)

        assert result.total == len(result.created_dirs)

    async def test_scaffold_raises_not_found_when_project_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.project_repository.get_by_id.return_value = None

        payload = ScaffoldRequest(root="/projects")

        with pytest.raises(NotFoundError):
            await svc.scaffold_project_filesystem(uuid.uuid4(), payload, user)

    async def test_scaffold_raises_forbidden_when_user_lacks_role(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project()
        user = _make_user()

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = False

        payload = ScaffoldRequest(root="/projects")

        with pytest.raises(ForbiddenError):
            await svc.scaffold_project_filesystem(project.id, payload, user)


# ---------------------------------------------------------------------------
# create_project
# ---------------------------------------------------------------------------


class TestCreateProject:
    async def test_create_project_with_explicit_code_commits_and_returns_response(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project(code="EXP")

        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        svc.project_repository.get_by_code = AsyncMock(return_value=None)
        svc.project_repository.create = AsyncMock(return_value=project)

        payload = ProjectCreateRequest(name="Explicit Project", code="EXP")
        result = await svc.create_project(payload, user)

        svc.project_repository.create.assert_awaited_once()
        db.commit.assert_awaited_once()
        assert result.code == "EXP"

    async def test_create_project_auto_generates_code_from_name(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project(code="AUTO_PROJECT")

        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        svc.project_repository.get_by_code = AsyncMock(return_value=None)
        svc.project_repository.create = AsyncMock(return_value=project)

        payload = ProjectCreateRequest(name="Auto Project")
        result = await svc.create_project(payload, user)

        svc.project_repository.create.assert_awaited_once()
        assert result.code == "AUTO_PROJECT"

    async def test_create_project_raises_conflict_on_duplicate_code(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        existing = _make_project(code="DUP")

        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        svc.project_repository.get_by_code = AsyncMock(return_value=existing)

        payload = ProjectCreateRequest(name="Duplicate", code="DUP")
        with pytest.raises(ConflictError):
            await svc.create_project(payload, user)

    async def test_create_project_raises_forbidden_without_role(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=False)

        payload = ProjectCreateRequest(name="No Access")
        with pytest.raises(ForbiddenError):
            await svc.create_project(payload, user)


# ---------------------------------------------------------------------------
# list_projects / get_project / patch_project / archive / restore / delete
# ---------------------------------------------------------------------------


class TestProjectCrud:
    async def test_list_projects_returns_paginated_response(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        p1 = _make_project(code="P1")
        p2 = _make_project(code="P2")

        svc.user_role_repository.has_any_role_in_any_scope = AsyncMock(return_value=True)
        svc.project_repository.list_visible_to_user = AsyncMock(return_value=([p1, p2], 2))

        result = await svc.list_projects(user, offset=0, limit=20, status=None)

        assert result.total == 2
        assert len(result.items) == 2

    async def test_list_projects_raises_forbidden_without_role(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.user_role_repository.has_any_role_in_any_scope = AsyncMock(return_value=False)

        with pytest.raises(ForbiddenError):
            await svc.list_projects(user, offset=0, limit=20, status=None)

    async def test_get_project_returns_response(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)

        result = await svc.get_project(project.id, user)

        assert result.id == project.id

    async def test_get_project_raises_not_found(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.project_repository.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.get_project(uuid.uuid4(), user)

    async def test_patch_project_updates_name_and_commits(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        db.refresh = AsyncMock()

        project_schema_ref = import_module("app.schemas.project")
        ProjectUpdateRequest = project_schema_ref.ProjectUpdateRequest
        payload = ProjectUpdateRequest(name="Updated Name")
        await svc.patch_project(project.id, payload, user)

        assert project.name == "Updated Name"
        db.commit.assert_awaited_once()

    async def test_archive_project_calls_repository_and_commits(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        archived = _make_project(code=project.code)

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        svc.project_repository.archive = AsyncMock(return_value=archived)

        await svc.archive_project(project.id, user)

        svc.project_repository.archive.assert_awaited_once_with(project)
        db.commit.assert_awaited_once()

    async def test_restore_project_calls_repository_and_commits(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        restored = _make_project(code=project.code)

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        svc.project_repository.restore = AsyncMock(return_value=restored)

        await svc.restore_project(project.id, user)

        svc.project_repository.restore.assert_awaited_once_with(project)
        db.commit.assert_awaited_once()

    async def test_delete_project_hard_deletes_with_force_true(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()

        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.project_repository.hard_delete = AsyncMock()

        await svc.delete_project(project.id, user, force=True)

        svc.project_repository.hard_delete.assert_awaited_once_with(project)
        db.commit.assert_awaited_once()

    async def test_delete_project_raises_unprocessable_without_force(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        with pytest.raises(UnprocessableError):
            await svc.delete_project(uuid.uuid4(), user, force=False)


# ---------------------------------------------------------------------------
# Shot CRUD
# ---------------------------------------------------------------------------


class TestShotCrud:
    async def test_create_project_shot_with_explicit_code(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        shot = _make_shot(project.id, code="SH010")

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.shot_repository.get_by_project_and_code = AsyncMock(return_value=None)
        svc.shot_repository.create_for_project = AsyncMock(return_value=shot)

        with patch("app.services.pipeline_task_service.PipelineTaskService") as MockPTS:
            MockPTS.return_value.generate_tasks_for_shot = AsyncMock()
            payload = ShotCreateRequest(name="Shot 010", code="SH010")
            result = await svc.create_project_shot(project.id, payload, user)

        assert result.code == "SH010"
        db.commit.assert_awaited_once()

    async def test_create_project_shot_raises_conflict_on_duplicate_code(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        existing_shot = _make_shot(project.id, code="SH010")

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.shot_repository.get_by_project_and_code = AsyncMock(return_value=existing_shot)

        payload = ShotCreateRequest(name="Dup Shot", code="SH010")
        with pytest.raises(ConflictError):
            await svc.create_project_shot(project.id, payload, user)

    async def test_create_project_shot_raises_conflict_without_code_or_sequence(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)

        payload = ShotCreateRequest(name="No Code Shot")
        with pytest.raises(ConflictError):
            await svc.create_project_shot(project.id, payload, user)

    async def test_list_project_shots_returns_paginated_response(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        shot = _make_shot(project.id)

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.shot_repository.list_for_project = AsyncMock(return_value=([shot], 1))

        result = await svc.list_project_shots(
            project.id, user, offset=0, limit=20, status=None, assigned_to=None
        )

        assert result.total == 1
        assert len(result.items) == 1

    async def test_get_shot_returns_response(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        shot = _make_shot(project.id)

        svc.shot_repository.get_by_id = AsyncMock(return_value=shot)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)

        result = await svc.get_shot(shot.id, user)

        assert result.id == shot.id

    async def test_get_shot_raises_not_found(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.shot_repository.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.get_shot(uuid.uuid4(), user)

    async def test_archive_shot_commits_and_returns_response(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        shot = _make_shot(project.id)
        archived = _make_shot(project.id, code=shot.code)

        svc.shot_repository.get_by_id = AsyncMock(return_value=shot)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.shot_repository.archive = AsyncMock(return_value=archived)

        await svc.archive_shot(shot.id, user)

        svc.shot_repository.archive.assert_awaited_once_with(shot)
        db.commit.assert_awaited_once()

    async def test_archive_shot_raises_not_found(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.shot_repository.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.archive_shot(uuid.uuid4(), user)

    async def test_restore_shot_commits_and_returns_response(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        shot = _make_shot(project.id)
        restored = _make_shot(project.id, code=shot.code)

        svc.shot_repository.get_by_id = AsyncMock(return_value=shot)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.shot_repository.restore = AsyncMock(return_value=restored)

        await svc.restore_shot(shot.id, user)

        svc.shot_repository.restore.assert_awaited_once_with(shot)
        db.commit.assert_awaited_once()

    async def test_delete_shot_hard_deletes_with_force_true(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        shot = _make_shot(project.id)

        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        svc.shot_repository.get_by_id = AsyncMock(return_value=shot)
        svc.shot_repository.hard_delete = AsyncMock()

        await svc.delete_shot(shot.id, user, force=True)

        svc.shot_repository.hard_delete.assert_awaited_once_with(shot)
        db.commit.assert_awaited_once()

    async def test_delete_shot_raises_unprocessable_without_force(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        with pytest.raises(UnprocessableError):
            await svc.delete_shot(uuid.uuid4(), user, force=False)

    async def test_patch_shot_updates_name_and_commits(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        shot = _make_shot(project.id)

        svc.shot_repository.get_by_id = AsyncMock(return_value=shot)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        db.refresh = AsyncMock()

        payload = ShotUpdateRequest(name="Renamed Shot")
        await svc.patch_shot(shot.id, payload, user)

        assert shot.name == "Renamed Shot"
        db.commit.assert_awaited_once()

    async def test_patch_shot_raises_forbidden_without_role(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        shot = _make_shot(project.id)

        svc.shot_repository.get_by_id = AsyncMock(return_value=shot)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=False)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=False)

        payload = ShotUpdateRequest(name="Forbidden")
        with pytest.raises(ForbiddenError):
            await svc.patch_shot(shot.id, payload, user)

    async def test_patch_shot_raises_not_found(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.shot_repository.get_by_id = AsyncMock(return_value=None)

        payload = ShotUpdateRequest(name="Ghost")
        with pytest.raises(NotFoundError):
            await svc.patch_shot(uuid.uuid4(), payload, user)


# ---------------------------------------------------------------------------
# Asset CRUD
# ---------------------------------------------------------------------------


class TestAssetCrud:
    async def test_create_project_asset_with_explicit_code(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        asset = _make_asset(project.id, code="HERO")

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.asset_repository.get_by_project_and_code = AsyncMock(return_value=None)
        svc.asset_repository.create_for_project = AsyncMock(return_value=asset)

        with patch("app.services.pipeline_task_service.PipelineTaskService") as MockPTS:
            MockPTS.return_value.generate_tasks_for_asset = AsyncMock()
            payload = AssetCreateRequest(name="Hero", code="HERO", asset_type=AssetType.character)
            result = await svc.create_project_asset(project.id, payload, user)

        assert result.code == "HERO"
        db.commit.assert_awaited_once()

    async def test_create_project_asset_raises_conflict_on_duplicate_code(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        existing = _make_asset(project.id, code="HERO")

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.asset_repository.get_by_project_and_code = AsyncMock(return_value=existing)

        payload = AssetCreateRequest(name="Dup Asset", code="HERO", asset_type=AssetType.character)
        with pytest.raises(ConflictError):
            await svc.create_project_asset(project.id, payload, user)

    async def test_list_project_assets_returns_paginated_response(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        asset = _make_asset(project.id)

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.asset_repository.list_for_project = AsyncMock(return_value=([asset], 1))

        result = await svc.list_project_assets(
            project.id,
            user,
            offset=0,
            limit=20,
            status=None,
            assigned_to=None,
            asset_type=None,
        )

        assert result.total == 1
        assert len(result.items) == 1

    async def test_archive_asset_commits_and_returns_response(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        asset = _make_asset(project.id)
        archived = _make_asset(project.id, code=asset.code)

        svc.asset_repository.get_by_id = AsyncMock(return_value=asset)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.asset_repository.archive = AsyncMock(return_value=archived)

        await svc.archive_asset(asset.id, user)

        svc.asset_repository.archive.assert_awaited_once_with(asset)
        db.commit.assert_awaited_once()

    async def test_archive_asset_raises_not_found(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.asset_repository.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.archive_asset(uuid.uuid4(), user)

    async def test_restore_asset_commits_and_returns_response(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        asset = _make_asset(project.id)
        restored = _make_asset(project.id, code=asset.code)

        svc.asset_repository.get_by_id = AsyncMock(return_value=asset)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.asset_repository.restore = AsyncMock(return_value=restored)

        await svc.restore_asset(asset.id, user)

        svc.asset_repository.restore.assert_awaited_once_with(asset)
        db.commit.assert_awaited_once()

    async def test_delete_asset_hard_deletes_with_force_true(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        asset = _make_asset(project.id)

        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        svc.asset_repository.get_by_id = AsyncMock(return_value=asset)
        svc.asset_repository.hard_delete = AsyncMock()

        await svc.delete_asset(asset.id, user, force=True)

        svc.asset_repository.hard_delete.assert_awaited_once_with(asset)
        db.commit.assert_awaited_once()

    async def test_delete_asset_raises_unprocessable_without_force(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        with pytest.raises(UnprocessableError):
            await svc.delete_asset(uuid.uuid4(), user, force=False)

    async def test_patch_asset_updates_name_and_commits(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        asset = _make_asset(project.id)

        svc.asset_repository.get_by_id = AsyncMock(return_value=asset)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        db.refresh = AsyncMock()

        payload = AssetUpdateRequest(name="Renamed Asset")
        await svc.patch_asset(asset.id, payload, user)

        assert asset.name == "Renamed Asset"
        db.commit.assert_awaited_once()

    async def test_patch_asset_raises_forbidden_without_role(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        asset = _make_asset(project.id)

        svc.asset_repository.get_by_id = AsyncMock(return_value=asset)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=False)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=False)

        payload = AssetUpdateRequest(name="Forbidden")
        with pytest.raises(ForbiddenError):
            await svc.patch_asset(asset.id, payload, user)

    async def test_patch_asset_raises_not_found(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.asset_repository.get_by_id = AsyncMock(return_value=None)

        payload = AssetUpdateRequest(name="Ghost")
        with pytest.raises(NotFoundError):
            await svc.patch_asset(uuid.uuid4(), payload, user)


# ---------------------------------------------------------------------------
# patch_project — field update branches
# ---------------------------------------------------------------------------


class TestPatchProjectFields:
    async def test_patch_project_updates_multiple_fields(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        db.refresh = AsyncMock()

        project_schema_ref = import_module("app.schemas.project")
        ProjectUpdateRequest = project_schema_ref.ProjectUpdateRequest
        payload = ProjectUpdateRequest(
            name="New Name",
            client="New Client",
            description="Updated desc",
            status=ProjectStatus.in_progress,
        )
        await svc.patch_project(project.id, payload, user)

        assert project.name == "New Name"
        assert project.client == "New Client"
        assert project.description == "Updated desc"
        assert project.status == ProjectStatus.in_progress

    async def test_patch_project_updates_fps_and_resolution(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        db.refresh = AsyncMock()

        project_schema_ref = import_module("app.schemas.project")
        ProjectUpdateRequest = project_schema_ref.ProjectUpdateRequest
        payload = ProjectUpdateRequest(fps=24.0, resolution_width=1920, resolution_height=1080)
        await svc.patch_project(project.id, payload, user)

        assert project.fps == 24.0
        assert project.resolution_width == 1920
        assert project.resolution_height == 1080


# ---------------------------------------------------------------------------
# create_project_shot — with sequence_id
# ---------------------------------------------------------------------------


class TestCreateShotWithSequence:
    async def test_create_project_shot_with_valid_sequence_id(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        seq = _make_sequence(project.id, code="SQ010")
        shot = _make_shot(project.id, sequence_id=seq.id, code="SQ010_0010")

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.sequence_repository.get_by_id = AsyncMock(return_value=seq)
        svc.shot_repository.get_last_sort_order_for_sequence = AsyncMock(return_value=0)
        svc.shot_repository.get_by_project_and_code = AsyncMock(return_value=None)
        svc.shot_repository.create_for_project = AsyncMock(return_value=shot)

        with patch("app.services.pipeline_task_service.PipelineTaskService") as MockPTS:
            MockPTS.return_value.generate_tasks_for_shot = AsyncMock()
            payload = ShotCreateRequest(name="First Shot", sequence_id=seq.id)
            result = await svc.create_project_shot(project.id, payload, user)

        assert result.sequence_id == seq.id

    async def test_create_project_shot_raises_not_found_for_invalid_sequence(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.sequence_repository.get_by_id = AsyncMock(return_value=None)

        payload = ShotCreateRequest(name="Bad Seq Shot", sequence_id=uuid.uuid4())
        with pytest.raises(NotFoundError):
            await svc.create_project_shot(project.id, payload, user)


# ---------------------------------------------------------------------------
# patch_shot — field update branches
# ---------------------------------------------------------------------------


class TestPatchShotFields:
    async def test_patch_shot_updates_frame_range(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        shot = _make_shot(project.id)

        svc.shot_repository.get_by_id = AsyncMock(return_value=shot)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        db.refresh = AsyncMock()

        payload = ShotUpdateRequest(frame_start=1001, frame_end=1100, bid_days=2.5)
        await svc.patch_shot(shot.id, payload, user)

        assert shot.frame_start == 1001
        assert shot.frame_end == 1100
        assert shot.bid_days == 2.5

    async def test_patch_shot_updates_assigned_to_triggers_webhook(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        shot = _make_shot(project.id)
        shot.assigned_to = None
        new_assignee = uuid.uuid4()

        svc.shot_repository.get_by_id = AsyncMock(return_value=shot)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        svc.webhook_service.enqueue_event = AsyncMock()
        db.refresh = AsyncMock()

        # Simulate Pydantic refresh updating assigned_to after commit
        async def _refresh(obj: object) -> None:
            shot.assigned_to = new_assignee

        db.refresh = _refresh

        payload = ShotUpdateRequest(assigned_to=new_assignee)
        await svc.patch_shot(shot.id, payload, user)

        assert shot.assigned_to == new_assignee


# ---------------------------------------------------------------------------
# patch_asset — field update branches
# ---------------------------------------------------------------------------


class TestPatchAssetFields:
    async def test_patch_asset_updates_asset_type_and_priority(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        asset = _make_asset(project.id)

        svc.asset_repository.get_by_id = AsyncMock(return_value=asset)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        db.refresh = AsyncMock()

        payload = AssetUpdateRequest(
            asset_type=AssetType.prop, priority=Priority.high, description="Updated desc"
        )
        await svc.patch_asset(asset.id, payload, user)

        assert asset.asset_type == AssetType.prop
        assert asset.priority == Priority.high
        assert asset.description == "Updated desc"


# ---------------------------------------------------------------------------
# get_project_report
# ---------------------------------------------------------------------------


class TestGetProjectReport:
    async def test_report_returns_aggregated_data(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project()
        user = _make_user()

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.project_repository.count_shots = AsyncMock(return_value=5)
        svc.project_repository.count_assets = AsyncMock(return_value=3)
        svc.project_repository.shot_status_counts = AsyncMock(
            return_value={ShotStatus.approved.value: 2}
        )
        svc.project_repository.asset_status_counts = AsyncMock(
            return_value={AssetStatus.approved.value: 1}
        )
        svc.file_repository.count_active_for_project = AsyncMock(return_value=10)
        svc.file_repository.storage_used_bytes_for_project = AsyncMock(return_value=1024)
        svc.status_log_repository.list_recent_for_project = AsyncMock(return_value=[])

        result = await svc.get_project_report(project.id, user)

        assert result.project_id == project.id
        assert result.total_shots == 5
        assert result.total_assets == 3
        assert result.uploaded_files_total == 10
        assert result.storage_used_bytes == 1024
        assert result.recent_activity == []

    async def test_report_raises_not_found_when_project_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.project_repository.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.get_project_report(uuid.uuid4(), user)

    async def test_report_raises_forbidden_without_role(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project()
        user = _make_user()

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=False)

        with pytest.raises(ForbiddenError):
            await svc.get_project_report(project.id, user)


# ---------------------------------------------------------------------------
# scaffold — episode hierarchy
# ---------------------------------------------------------------------------


class TestScaffoldEpisodeHierarchy:
    async def test_scaffold_places_shot_under_episode_sequence_dir(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        project = _make_project(code="TST")
        user = _make_user()
        ep = _make_episode(code="EP010")
        seq = _make_sequence(project.id, code="SQ010", episode_id=ep.id)
        shot = _make_shot(project.id, sequence_id=seq.id, code="SH010")

        svc.project_repository.get_by_id.return_value = project
        svc.user_role_repository.has_any_role.return_value = True
        svc.episode_repository.list_all_for_project.return_value = [ep]
        svc.sequence_repository.list_all_for_project.return_value = [seq]
        svc.shot_repository.list_all_for_project.return_value = [shot]
        svc.asset_repository.list_all_for_project.return_value = []

        payload = ScaffoldRequest(root="/projects")
        result = await svc.scaffold_project_filesystem(project.id, payload, user)

        shot_dirs = [
            d
            for d in result.created_dirs
            if "SH010" in d and "work" not in d and "publish" not in d
        ]
        assert len(shot_dirs) == 1
        assert "EP010" in shot_dirs[0]
        assert "SQ010" in shot_dirs[0]


# ---------------------------------------------------------------------------
# create_project_episode / list_project_episodes
# ---------------------------------------------------------------------------


class TestEpisodeCrud:
    async def test_create_project_episode_with_explicit_code(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        ep = _make_episode(code="EP010")
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        ep.id = uuid.uuid4()
        ep.project_id = project.id
        ep.name = "Episode 010"
        ep.status = "active"
        ep.description = None
        ep.production_number = None
        ep.order = None
        ep.created_at = now
        ep.updated_at = now
        ep.archived_at = None

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.episode_repository.get_by_project_and_code = AsyncMock(return_value=None)
        svc.episode_repository.create_for_project = AsyncMock(return_value=ep)

        episode_schema = import_module("app.schemas.project")
        EpisodeCreateRequest = episode_schema.EpisodeCreateRequest
        payload = EpisodeCreateRequest(name="Episode 010", code="EP010")
        await svc.create_project_episode(project.id, payload, user)

        svc.episode_repository.create_for_project.assert_awaited_once()
        db.commit.assert_awaited_once()

    async def test_create_project_episode_raises_conflict_on_duplicate_code(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        existing = _make_episode(code="EP010")

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)
        svc.episode_repository.get_by_project_and_code = AsyncMock(return_value=existing)

        episode_schema = import_module("app.schemas.project")
        EpisodeCreateRequest = episode_schema.EpisodeCreateRequest
        payload = EpisodeCreateRequest(name="Dup Episode", code="EP010")
        with pytest.raises(ConflictError):
            await svc.create_project_episode(project.id, payload, user)

    async def test_create_project_episode_raises_conflict_without_code_or_production_number(
        self,
    ) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_any_role = AsyncMock(return_value=True)

        episode_schema = import_module("app.schemas.project")
        EpisodeCreateRequest = episode_schema.EpisodeCreateRequest
        payload = EpisodeCreateRequest(name="No Code")
        with pytest.raises(ConflictError):
            await svc.create_project_episode(project.id, payload, user)


# ---------------------------------------------------------------------------
# patch_project — remaining optional field branches
# ---------------------------------------------------------------------------


class TestPatchProjectMoreFields:
    async def test_patch_project_updates_thumbnail_and_color_space(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()

        svc.project_repository.get_by_id = AsyncMock(return_value=project)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        db.refresh = AsyncMock()

        project_schema_ref = import_module("app.schemas.project")
        ProjectUpdateRequest = project_schema_ref.ProjectUpdateRequest
        payload = ProjectUpdateRequest(
            thumbnail_url="https://example.com/thumb.png",
            color_space="ACES",
            naming_rules={"episode": "EP{n:03d}"},
            path_templates={"shot": "/projects/{code}"},
        )
        await svc.patch_project(project.id, payload, user)

        assert project.thumbnail_url == "https://example.com/thumb.png"
        assert project.color_space == "ACES"
        assert project.naming_rules == {"episode": "EP{n:03d}"}
        assert project.path_templates == {"shot": "/projects/{code}"}


# ---------------------------------------------------------------------------
# patch_shot — more field branches
# ---------------------------------------------------------------------------


class TestPatchShotMoreFields:
    async def test_patch_shot_updates_difficulty_and_handles(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        shot = _make_shot(project.id)

        svc.shot_repository.get_by_id = AsyncMock(return_value=shot)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        db.refresh = AsyncMock()

        models_ref = import_module("app.models")
        Difficulty = models_ref.Difficulty
        payload = ShotUpdateRequest(
            description="Updated desc",
            thumbnail_url="https://example.com/shot.png",
            priority=Priority.high,
            difficulty=Difficulty.hard,
            handle_head=8,
            handle_tail=8,
            cut_in=1001,
            cut_out=1048,
            sort_order=10,
        )
        await svc.patch_shot(shot.id, payload, user)

        assert shot.description == "Updated desc"
        assert shot.thumbnail_url == "https://example.com/shot.png"
        assert shot.priority == Priority.high
        assert shot.difficulty == Difficulty.hard
        assert shot.handle_head == 8
        assert shot.handle_tail == 8
        assert shot.cut_in == 1001
        assert shot.cut_out == 1048
        assert shot.sort_order == 10


# ---------------------------------------------------------------------------
# restore_asset / delete_asset — not found paths
# ---------------------------------------------------------------------------


class TestAssetNotFoundPaths:
    async def test_restore_asset_raises_not_found(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.asset_repository.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.restore_asset(uuid.uuid4(), user)

    async def test_delete_asset_raises_not_found_when_asset_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        svc.asset_repository.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.delete_asset(uuid.uuid4(), user, force=True)


# ---------------------------------------------------------------------------
# patch_asset — more field branches
# ---------------------------------------------------------------------------


class TestPatchAssetMoreFields:
    async def test_patch_asset_updates_thumbnail_and_description(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        asset = _make_asset(project.id)

        svc.asset_repository.get_by_id = AsyncMock(return_value=asset)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        db.refresh = AsyncMock()

        payload = AssetUpdateRequest(
            thumbnail_url="https://example.com/asset.png",
            priority=Priority.urgent,
            description="New description",
        )
        await svc.patch_asset(asset.id, payload, user)

        assert asset.thumbnail_url == "https://example.com/asset.png"
        assert asset.priority == Priority.urgent
        assert asset.description == "New description"

    async def test_patch_asset_code_conflict_raises_conflict_error(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        project = _make_project()
        asset = _make_asset(project.id, code="OLD")
        conflicting = _make_asset(project.id, code="TAKEN")

        svc.asset_repository.get_by_id = AsyncMock(return_value=asset)
        svc.user_role_repository.has_global_any_role = AsyncMock(return_value=True)
        svc.asset_repository.get_by_project_and_code = AsyncMock(return_value=conflicting)

        payload = AssetUpdateRequest(code="TAKEN")
        with pytest.raises(ConflictError):
            await svc.patch_asset(asset.id, payload, user)

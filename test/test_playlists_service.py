from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

exceptions_module = import_module("app.core.exceptions")
service_module = import_module("app.services.playlist_service")
schema_module = import_module("app.schemas.playlist")
models_module = import_module("app.models")
playlist_models = import_module("app.models.playlist")
version_models = import_module("app.models.version")

PlaylistService = service_module.PlaylistService
NotFoundError = exceptions_module.NotFoundError
ForbiddenError = exceptions_module.ForbiddenError
ConflictError = exceptions_module.ConflictError
UnprocessableError = exceptions_module.UnprocessableError

PlaylistCreate = schema_module.PlaylistCreate
PlaylistUpdate = schema_module.PlaylistUpdate
PlaylistItemAdd = schema_module.PlaylistItemAdd
PlaylistItemReview = schema_module.PlaylistItemReview
PlaylistItemsReorder = schema_module.PlaylistItemsReorder
ReorderEntry = schema_module.ReorderEntry

PlaylistStatus = playlist_models.PlaylistStatus
ReviewStatus = playlist_models.ReviewStatus
VersionStatus = version_models.VersionStatus

pytestmark = pytest.mark.playlists


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _make_service(db: AsyncMock) -> PlaylistService:
    svc = PlaylistService.__new__(PlaylistService)
    svc.db = db
    svc.repository = AsyncMock()
    return svc


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _make_playlist(
    status: PlaylistStatus = PlaylistStatus.draft,
    project_id: uuid.UUID | None = None,
) -> MagicMock:
    now = datetime.now(timezone.utc)
    pl = MagicMock()
    pl.id = uuid.uuid4()
    pl.project_id = project_id or uuid.uuid4()
    pl.name = "Daily Review"
    pl.description = None
    pl.created_by = uuid.uuid4()
    pl.date = None
    pl.status = status
    pl.created_at = now
    pl.updated_at = None
    pl.archived_at = None
    return pl


def _make_item(
    playlist_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
    review_status: ReviewStatus = ReviewStatus.pending,
) -> MagicMock:
    now = datetime.now(timezone.utc)
    item = MagicMock()
    item.id = uuid.uuid4()
    item.playlist_id = playlist_id
    item.version_id = version_id or uuid.uuid4()
    item.order = 1
    item.review_status = review_status
    item.reviewer_notes = None
    item.reviewed_by = None
    item.reviewed_at = None
    item.created_at = now
    return item


def _make_version(project_id: uuid.UUID | None = None) -> MagicMock:
    v = MagicMock()
    v.id = uuid.uuid4()
    v.project_id = project_id or uuid.uuid4()
    v.status = VersionStatus.pending_review
    v.archived_at = None
    return v


# ---------------------------------------------------------------------------
# create_playlist
# ---------------------------------------------------------------------------


class TestCreatePlaylist:
    async def test_create_playlist_commits_and_returns_response(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()

        svc.repository.create = AsyncMock(return_value=playlist)

        with patch(
            "app.repositories.user_role_repository.UserRoleRepository.has_any_role",
            new=AsyncMock(return_value=True),
        ):
            payload = PlaylistCreate(project_id=playlist.project_id, name="Daily Review")
            result = await svc.create_playlist(payload, user)

        svc.repository.create.assert_awaited_once()
        db.commit.assert_awaited_once()
        assert result.name == "Daily Review"

    async def test_create_playlist_raises_forbidden_without_role(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        with patch(
            "app.repositories.user_role_repository.UserRoleRepository.has_any_role",
            new=AsyncMock(return_value=False),
        ):
            payload = PlaylistCreate(project_id=uuid.uuid4(), name="No Access")
            with pytest.raises(ForbiddenError):
                await svc.create_playlist(payload, user)


# ---------------------------------------------------------------------------
# get_playlist
# ---------------------------------------------------------------------------


class TestGetPlaylist:
    async def test_get_playlist_returns_response_with_items(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        playlist = _make_playlist()
        item = _make_item(playlist.id)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_items = AsyncMock(return_value=[item])

        result = await svc.get_playlist(playlist.id)

        assert result.id == playlist.id
        assert len(result.items) == 1

    async def test_get_playlist_raises_not_found_when_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)

        svc.repository.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.get_playlist(uuid.uuid4())


# ---------------------------------------------------------------------------
# update_playlist
# ---------------------------------------------------------------------------


class TestUpdatePlaylist:
    async def test_update_playlist_name_and_description(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()
        updated = _make_playlist(project_id=playlist.project_id)
        updated.name = "Updated Name"

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.update = AsyncMock(return_value=updated)
        svc.repository.get_items = AsyncMock(return_value=[])

        with patch(
            "app.repositories.user_role_repository.UserRoleRepository.has_any_role",
            new=AsyncMock(return_value=True),
        ):
            payload = PlaylistUpdate(name="Updated Name", description="New desc")
            await svc.update_playlist(playlist.id, payload, user)

        svc.repository.update.assert_awaited_once()
        db.commit.assert_awaited_once()

    async def test_update_playlist_valid_status_transition(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist(status=PlaylistStatus.draft)
        updated = _make_playlist(status=PlaylistStatus.in_progress, project_id=playlist.project_id)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.update = AsyncMock(return_value=updated)
        svc.repository.get_items = AsyncMock(return_value=[])

        with patch(
            "app.repositories.user_role_repository.UserRoleRepository.has_any_role",
            new=AsyncMock(return_value=True),
        ):
            payload = PlaylistUpdate(status=PlaylistStatus.in_progress)
            result = await svc.update_playlist(playlist.id, payload, user)

        assert result.status == PlaylistStatus.in_progress

    async def test_update_playlist_invalid_status_transition_raises_unprocessable(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        # draft -> completed is invalid (must go draft -> in_progress first)
        playlist = _make_playlist(status=PlaylistStatus.draft)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)

        with patch(
            "app.repositories.user_role_repository.UserRoleRepository.has_any_role",
            new=AsyncMock(return_value=True),
        ):
            payload = PlaylistUpdate(status=PlaylistStatus.completed)
            with pytest.raises(UnprocessableError):
                await svc.update_playlist(playlist.id, payload, user)

    async def test_update_playlist_raises_not_found_when_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.repository.get_by_id = AsyncMock(return_value=None)

        payload = PlaylistUpdate(name="Ghost")
        with pytest.raises(NotFoundError):
            await svc.update_playlist(uuid.uuid4(), payload, user)

    async def test_update_playlist_no_fields_skips_repository_update(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_items = AsyncMock(return_value=[])

        with patch(
            "app.repositories.user_role_repository.UserRoleRepository.has_any_role",
            new=AsyncMock(return_value=True),
        ):
            payload = PlaylistUpdate()
            await svc.update_playlist(playlist.id, payload, user)

        svc.repository.update.assert_not_awaited()
        db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# archive_playlist
# ---------------------------------------------------------------------------


class TestArchivePlaylist:
    async def test_archive_playlist_commits_and_returns_response(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()
        archived = _make_playlist(project_id=playlist.project_id)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.archive = AsyncMock(return_value=archived)
        svc.repository.get_items = AsyncMock(return_value=[])

        with patch(
            "app.repositories.user_role_repository.UserRoleRepository.has_any_role",
            new=AsyncMock(return_value=True),
        ):
            await svc.archive_playlist(playlist.id, user)

        svc.repository.archive.assert_awaited_once_with(playlist)
        db.commit.assert_awaited_once()

    async def test_archive_playlist_raises_not_found_when_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.repository.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.archive_playlist(uuid.uuid4(), user)


# ---------------------------------------------------------------------------
# list_for_project
# ---------------------------------------------------------------------------


class TestListForProject:
    async def test_list_for_project_returns_paginated_response(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        pl1 = _make_playlist()
        pl2 = _make_playlist()

        svc.repository.list_for_project = AsyncMock(return_value=([pl1, pl2], 2))
        svc.repository.get_items = AsyncMock(return_value=[])

        result = await svc.list_for_project(uuid.uuid4(), offset=0, limit=20)

        assert result.total == 2
        assert len(result.items) == 2
        # get_items should be called once per playlist
        assert svc.repository.get_items.await_count == 2

    async def test_list_for_project_returns_empty_when_no_playlists(self) -> None:
        db = _make_db()
        svc = _make_service(db)

        svc.repository.list_for_project = AsyncMock(return_value=([], 0))

        result = await svc.list_for_project(uuid.uuid4(), offset=0, limit=20)

        assert result.total == 0
        assert result.items == []


# ---------------------------------------------------------------------------
# add_item
# ---------------------------------------------------------------------------


class TestAddItem:
    async def test_add_item_appends_version_and_commits(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()
        version = _make_version(project_id=playlist.project_id)
        item = _make_item(playlist.id, version_id=version.id)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item = AsyncMock(return_value=None)  # no duplicate
        svc.repository.get_max_order = AsyncMock(return_value=0)
        svc.repository.add_item = AsyncMock()
        svc.repository.get_items = AsyncMock(return_value=[item])

        # Mock the DB execute to return the version
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = version
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.repositories.user_role_repository.UserRoleRepository.has_any_role",
            new=AsyncMock(return_value=True),
        ):
            payload = PlaylistItemAdd(version_id=version.id)
            result = await svc.add_item(playlist.id, payload, user)

        svc.repository.add_item.assert_awaited_once_with(
            playlist_id=playlist.id,
            version_id=version.id,
            order=1,
        )
        db.commit.assert_awaited_once()
        assert len(result.items) == 1

    async def test_add_item_raises_not_found_for_missing_version(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()

        svc.repository.get_by_id = AsyncMock(return_value=playlist)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.repositories.user_role_repository.UserRoleRepository.has_any_role",
            new=AsyncMock(return_value=True),
        ):
            payload = PlaylistItemAdd(version_id=uuid.uuid4())
            with pytest.raises(NotFoundError):
                await svc.add_item(playlist.id, payload, user)

    async def test_add_item_raises_not_found_for_archived_version(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()
        version = _make_version(project_id=playlist.project_id)
        version.archived_at = datetime.now(timezone.utc)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = version
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.repositories.user_role_repository.UserRoleRepository.has_any_role",
            new=AsyncMock(return_value=True),
        ):
            payload = PlaylistItemAdd(version_id=version.id)
            with pytest.raises(NotFoundError):
                await svc.add_item(playlist.id, payload, user)

    async def test_add_item_raises_unprocessable_when_version_project_mismatch(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()
        version = _make_version(project_id=uuid.uuid4())  # different project

        svc.repository.get_by_id = AsyncMock(return_value=playlist)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = version
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.repositories.user_role_repository.UserRoleRepository.has_any_role",
            new=AsyncMock(return_value=True),
        ):
            payload = PlaylistItemAdd(version_id=version.id)
            with pytest.raises(UnprocessableError):
                await svc.add_item(playlist.id, payload, user)

    async def test_add_item_raises_conflict_on_duplicate_version(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()
        version = _make_version(project_id=playlist.project_id)
        existing_item = _make_item(playlist.id, version_id=version.id)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item = AsyncMock(return_value=existing_item)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = version
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.repositories.user_role_repository.UserRoleRepository.has_any_role",
            new=AsyncMock(return_value=True),
        ):
            payload = PlaylistItemAdd(version_id=version.id)
            with pytest.raises(ConflictError):
                await svc.add_item(playlist.id, payload, user)

    async def test_add_item_raises_not_found_when_playlist_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.repository.get_by_id = AsyncMock(return_value=None)

        payload = PlaylistItemAdd(version_id=uuid.uuid4())
        with pytest.raises(NotFoundError):
            await svc.add_item(uuid.uuid4(), payload, user)


# ---------------------------------------------------------------------------
# remove_item / remove_item_by_id
# ---------------------------------------------------------------------------


class TestRemoveItem:
    async def test_remove_item_deletes_and_commits(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()
        item = _make_item(playlist.id)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item_by_id = AsyncMock(return_value=item)
        svc.repository.delete_item = AsyncMock()

        await svc.remove_item(playlist.id, item.id, user)

        svc.repository.delete_item.assert_awaited_once_with(item)
        db.commit.assert_awaited_once()

    async def test_remove_item_raises_not_found_for_wrong_playlist(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()
        item = _make_item(uuid.uuid4())  # belongs to a different playlist

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item_by_id = AsyncMock(return_value=item)

        with pytest.raises(NotFoundError):
            await svc.remove_item(playlist.id, item.id, user)

    async def test_remove_item_raises_not_found_when_playlist_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.repository.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.remove_item(uuid.uuid4(), uuid.uuid4(), user)

    async def test_remove_item_by_id_deletes_and_commits(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        item = _make_item(uuid.uuid4())

        svc.repository.get_item_by_id = AsyncMock(return_value=item)
        svc.repository.delete_item = AsyncMock()

        await svc.remove_item_by_id(item.id)

        svc.repository.delete_item.assert_awaited_once_with(item)
        db.commit.assert_awaited_once()

    async def test_remove_item_by_id_raises_not_found_when_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)

        svc.repository.get_item_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await svc.remove_item_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# review_item  —  core review workflow
# ---------------------------------------------------------------------------


class TestReviewItem:
    async def test_review_item_sets_review_status_and_commits(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist(status=PlaylistStatus.in_progress)
        item = _make_item(playlist.id, review_status=ReviewStatus.pending)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item_by_id = AsyncMock(return_value=item)
        svc.repository.update_item = AsyncMock()
        svc.repository.count_pending_items = AsyncMock(return_value=1)  # still pending
        svc.repository.get_items = AsyncMock(return_value=[item])

        payload = PlaylistItemReview(
            review_status=ReviewStatus.approved, propagate_to_version=False
        )
        await svc.review_item(playlist.id, item.id, payload, user)

        svc.repository.update_item.assert_awaited_once()
        call_kwargs = svc.repository.update_item.call_args
        assert call_kwargs[1]["review_status"] == ReviewStatus.approved
        assert call_kwargs[1]["reviewed_by"] == user.id
        db.commit.assert_awaited_once()

    async def test_review_item_with_notes_includes_reviewer_notes(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist(status=PlaylistStatus.draft)
        item = _make_item(playlist.id)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item_by_id = AsyncMock(return_value=item)
        svc.repository.update_item = AsyncMock()
        svc.repository.get_items = AsyncMock(return_value=[item])

        payload = PlaylistItemReview(
            review_status=ReviewStatus.revision_requested,
            reviewer_notes="Needs colour fix",
            propagate_to_version=False,
        )
        await svc.review_item(playlist.id, item.id, payload, user)

        call_kwargs = svc.repository.update_item.call_args
        assert call_kwargs[1]["reviewer_notes"] == "Needs colour fix"

    async def test_review_item_auto_completes_playlist_when_no_pending_remain(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist(status=PlaylistStatus.in_progress)
        item = _make_item(playlist.id, review_status=ReviewStatus.pending)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item_by_id = AsyncMock(return_value=item)
        svc.repository.update_item = AsyncMock()
        svc.repository.count_pending_items = AsyncMock(return_value=0)  # all reviewed
        svc.repository.update = AsyncMock(return_value=playlist)
        svc.repository.get_items = AsyncMock(return_value=[item])

        payload = PlaylistItemReview(
            review_status=ReviewStatus.approved, propagate_to_version=False
        )
        await svc.review_item(playlist.id, item.id, payload, user)

        svc.repository.update.assert_awaited_once_with(playlist, status=PlaylistStatus.completed)

    async def test_review_item_does_not_auto_complete_when_not_in_progress(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        # playlist is draft — auto-complete should not trigger
        playlist = _make_playlist(status=PlaylistStatus.draft)
        item = _make_item(playlist.id)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item_by_id = AsyncMock(return_value=item)
        svc.repository.update_item = AsyncMock()
        svc.repository.get_items = AsyncMock(return_value=[item])

        payload = PlaylistItemReview(
            review_status=ReviewStatus.approved, propagate_to_version=False
        )
        await svc.review_item(playlist.id, item.id, payload, user)

        svc.repository.count_pending_items.assert_not_awaited()
        svc.repository.update.assert_not_awaited()

    async def test_review_item_propagates_approved_status_to_version(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist(status=PlaylistStatus.in_progress)
        version = _make_version()
        item = _make_item(playlist.id, version_id=version.id)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item_by_id = AsyncMock(return_value=item)
        svc.repository.update_item = AsyncMock()
        svc.repository.count_pending_items = AsyncMock(return_value=1)
        svc.repository.get_items = AsyncMock(return_value=[item])

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = version
        db.execute = AsyncMock(return_value=mock_result)

        payload = PlaylistItemReview(review_status=ReviewStatus.approved, propagate_to_version=True)
        await svc.review_item(playlist.id, item.id, payload, user)

        assert version.status == VersionStatus.approved
        db.add.assert_called_with(version)
        db.flush.assert_awaited_once()

    async def test_review_item_propagates_revision_requested_to_version(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist(status=PlaylistStatus.in_progress)
        version = _make_version()
        item = _make_item(playlist.id, version_id=version.id)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item_by_id = AsyncMock(return_value=item)
        svc.repository.update_item = AsyncMock()
        svc.repository.count_pending_items = AsyncMock(return_value=1)
        svc.repository.get_items = AsyncMock(return_value=[item])

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = version
        db.execute = AsyncMock(return_value=mock_result)

        payload = PlaylistItemReview(
            review_status=ReviewStatus.revision_requested, propagate_to_version=True
        )
        await svc.review_item(playlist.id, item.id, payload, user)

        assert version.status == VersionStatus.revision_requested

    async def test_review_item_pending_status_does_not_propagate_to_version(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist(status=PlaylistStatus.in_progress)
        item = _make_item(playlist.id)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item_by_id = AsyncMock(return_value=item)
        svc.repository.update_item = AsyncMock()
        svc.repository.count_pending_items = AsyncMock(return_value=1)
        svc.repository.get_items = AsyncMock(return_value=[item])

        payload = PlaylistItemReview(
            review_status=ReviewStatus.pending,
            propagate_to_version=True,  # propagate=True but status is pending
        )
        await svc.review_item(playlist.id, item.id, payload, user)

        # DB execute should NOT have been called for version propagation
        db.execute.assert_not_awaited()
        db.flush.assert_not_awaited()

    async def test_review_item_raises_not_found_when_playlist_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.repository.get_by_id = AsyncMock(return_value=None)

        payload = PlaylistItemReview(review_status=ReviewStatus.approved)
        with pytest.raises(NotFoundError):
            await svc.review_item(uuid.uuid4(), uuid.uuid4(), payload, user)

    async def test_review_item_raises_not_found_for_wrong_playlist(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()
        item = _make_item(uuid.uuid4())  # belongs to a different playlist

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item_by_id = AsyncMock(return_value=item)

        payload = PlaylistItemReview(review_status=ReviewStatus.approved)
        with pytest.raises(NotFoundError):
            await svc.review_item(playlist.id, item.id, payload, user)


# ---------------------------------------------------------------------------
# review_item_by_id  —  proxy method
# ---------------------------------------------------------------------------


class TestReviewItemById:
    async def test_review_item_by_id_delegates_to_review_item(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist(status=PlaylistStatus.in_progress)
        item = _make_item(playlist.id)

        svc.repository.get_item_by_id = AsyncMock(return_value=item)
        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.update_item = AsyncMock()
        svc.repository.count_pending_items = AsyncMock(return_value=1)
        svc.repository.get_items = AsyncMock(return_value=[item])

        payload = PlaylistItemReview(review_status=ReviewStatus.approved)
        await svc.review_item_by_id(item.id, payload, user)

        svc.repository.update_item.assert_awaited_once()

    async def test_review_item_by_id_raises_not_found_when_item_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.repository.get_item_by_id = AsyncMock(return_value=None)

        payload = PlaylistItemReview(review_status=ReviewStatus.approved)
        with pytest.raises(NotFoundError):
            await svc.review_item_by_id(uuid.uuid4(), payload, user)


# ---------------------------------------------------------------------------
# reorder_items
# ---------------------------------------------------------------------------


class TestReorderItems:
    async def test_reorder_items_updates_order_and_commits(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()
        item1 = _make_item(playlist.id)
        item2 = _make_item(playlist.id)

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item_by_id = AsyncMock(side_effect=[item1, item2])
        svc.repository.update_item = AsyncMock()
        svc.repository.get_items = AsyncMock(return_value=[item1, item2])

        payload = PlaylistItemsReorder(
            items=[
                ReorderEntry(item_id=item1.id, order=2),
                ReorderEntry(item_id=item2.id, order=1),
            ]
        )
        await svc.reorder_items(playlist.id, payload, user)

        assert svc.repository.update_item.await_count == 2
        db.commit.assert_awaited_once()

    async def test_reorder_items_raises_not_found_for_wrong_item(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()
        playlist = _make_playlist()
        item = _make_item(uuid.uuid4())  # different playlist

        svc.repository.get_by_id = AsyncMock(return_value=playlist)
        svc.repository.get_item_by_id = AsyncMock(return_value=item)

        payload = PlaylistItemsReorder(items=[ReorderEntry(item_id=item.id, order=1)])
        with pytest.raises(NotFoundError):
            await svc.reorder_items(playlist.id, payload, user)

    async def test_reorder_items_raises_not_found_when_playlist_missing(self) -> None:
        db = _make_db()
        svc = _make_service(db)
        user = _make_user()

        svc.repository.get_by_id = AsyncMock(return_value=None)

        payload = PlaylistItemsReorder(items=[])
        with pytest.raises(NotFoundError):
            await svc.reorder_items(uuid.uuid4(), payload, user)

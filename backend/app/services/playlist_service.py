import uuid
from collections.abc import Sequence
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.models import RoleName, User
from app.models.playlist import Playlist, PlaylistItem, PlaylistStatus, ReviewStatus
from app.models.version import Version, VersionStatus
from app.repositories.playlist_repository import PlaylistRepository
from app.schemas.playlist import (
    PlaylistCreate,
    PlaylistItemAdd,
    PlaylistItemResponse,
    PlaylistItemReview,
    PlaylistItemsReorder,
    PlaylistListResponse,
    PlaylistResponse,
    PlaylistUpdate,
)

# Valid playlist status transitions
VALID_PLAYLIST_TRANSITIONS: dict[PlaylistStatus, set[PlaylistStatus]] = {
    PlaylistStatus.draft: {PlaylistStatus.in_progress},
    PlaylistStatus.in_progress: {PlaylistStatus.completed},
    PlaylistStatus.completed: {PlaylistStatus.in_progress},
}

# Map review status to version status
REVIEW_TO_VERSION_STATUS: dict[ReviewStatus, VersionStatus] = {
    ReviewStatus.approved: VersionStatus.approved,
    ReviewStatus.revision_requested: VersionStatus.revision_requested,
}


_PLAYLIST_MANAGE_ROLES = {RoleName.admin, RoleName.supervisor, RoleName.lead}


class PlaylistService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = PlaylistRepository(db)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _require_project_role(self, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        from app.repositories.user_role_repository import UserRoleRepository

        if not await UserRoleRepository(self.db).has_any_role(
            user_id, _PLAYLIST_MANAGE_ROLES, project_id
        ):
            raise ForbiddenError("Insufficient permissions to manage playlists")

    def _build_response(
        self, playlist: Playlist, items: Sequence[PlaylistItem]
    ) -> PlaylistResponse:
        return PlaylistResponse(
            id=playlist.id,
            project_id=playlist.project_id,
            name=playlist.name,
            description=playlist.description,
            created_by=playlist.created_by,
            date=playlist.date,
            status=playlist.status,
            created_at=playlist.created_at,
            updated_at=playlist.updated_at,
            archived_at=playlist.archived_at,
            items=[PlaylistItemResponse.model_validate(i) for i in items],
        )

    # ── Playlist CRUD ─────────────────────────────────────────────────────────

    async def create_playlist(
        self, payload: PlaylistCreate, current_user: User
    ) -> PlaylistResponse:
        await self._require_project_role(current_user.id, payload.project_id)
        playlist = await self.repository.create(
            project_id=payload.project_id,
            name=payload.name,
            description=payload.description,
            created_by=current_user.id,
            date=payload.date,
        )
        await self.db.commit()
        await self.db.refresh(playlist)
        return self._build_response(playlist, [])

    async def get_playlist(self, playlist_id: uuid.UUID) -> PlaylistResponse:
        playlist = await self.repository.get_by_id(playlist_id)
        if playlist is None:
            raise NotFoundError("Playlist not found")
        items = await self.repository.get_items(playlist_id)
        return self._build_response(playlist, items)

    async def update_playlist(
        self, playlist_id: uuid.UUID, payload: PlaylistUpdate, current_user: User
    ) -> PlaylistResponse:
        playlist = await self.repository.get_by_id(playlist_id)
        if playlist is None:
            raise NotFoundError("Playlist not found")

        await self._require_project_role(current_user.id, playlist.project_id)

        update_data: dict[str, object] = {}
        if payload.name is not None:
            update_data["name"] = payload.name
        if payload.description is not None:
            update_data["description"] = payload.description
        if payload.date is not None:
            update_data["date"] = payload.date
        if payload.status is not None:
            allowed = VALID_PLAYLIST_TRANSITIONS.get(playlist.status, set())
            if payload.status not in allowed:
                raise UnprocessableError(
                    f"Invalid status transition: {playlist.status.value} -> {payload.status.value}"
                )
            update_data["status"] = payload.status

        if update_data:
            playlist = await self.repository.update(playlist, **update_data)

        await self.db.commit()
        await self.db.refresh(playlist)
        items = await self.repository.get_items(playlist_id)
        return self._build_response(playlist, items)

    async def archive_playlist(
        self, playlist_id: uuid.UUID, current_user: User
    ) -> PlaylistResponse:
        playlist = await self.repository.get_by_id(playlist_id)
        if playlist is None:
            raise NotFoundError("Playlist not found")
        await self._require_project_role(current_user.id, playlist.project_id)
        playlist = await self.repository.archive(playlist)
        await self.db.commit()
        items = await self.repository.get_items(playlist_id)
        return self._build_response(playlist, items)

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        offset: int,
        limit: int,
        status: PlaylistStatus | None = None,
        filter_date: date | None = None,
        created_by: uuid.UUID | None = None,
    ) -> PlaylistListResponse:
        playlists, total = await self.repository.list_for_project(
            project_id=project_id,
            offset=offset,
            limit=limit,
            status=status,
            filter_date=filter_date,
            created_by=created_by,
        )
        items_list = []
        for pl in playlists:
            items = await self.repository.get_items(pl.id)
            items_list.append(self._build_response(pl, items))

        return PlaylistListResponse(items=items_list, offset=offset, limit=limit, total=total)

    # ── Playlist Items ────────────────────────────────────────────────────────

    async def add_item(
        self, playlist_id: uuid.UUID, payload: PlaylistItemAdd, current_user: User
    ) -> PlaylistResponse:
        playlist = await self.repository.get_by_id(playlist_id)
        if playlist is None:
            raise NotFoundError("Playlist not found")

        await self._require_project_role(current_user.id, playlist.project_id)

        # Validate version exists and belongs to same project
        result = await self.db.execute(select(Version).where(Version.id == payload.version_id))
        version = result.scalar_one_or_none()
        if version is None or version.archived_at is not None:
            raise NotFoundError("Version not found")
        if version.project_id != playlist.project_id:
            raise UnprocessableError("Version must belong to the same project as the playlist")

        # Check for duplicate
        existing = await self.repository.get_item(playlist_id, payload.version_id)
        if existing is not None:
            raise ConflictError("Version is already in this playlist")

        max_order = await self.repository.get_max_order(playlist_id)
        await self.repository.add_item(
            playlist_id=playlist_id,
            version_id=payload.version_id,
            order=max_order + 1,
        )
        await self.db.commit()
        await self.db.refresh(playlist)
        items = await self.repository.get_items(playlist_id)
        return self._build_response(playlist, items)

    async def remove_item(
        self, playlist_id: uuid.UUID, item_id: uuid.UUID, current_user: User
    ) -> None:
        playlist = await self.repository.get_by_id(playlist_id)
        if playlist is None:
            raise NotFoundError("Playlist not found")
        item = await self.repository.get_item_by_id(item_id)
        if item is None or item.playlist_id != playlist_id:
            raise NotFoundError("Playlist item not found")
        await self.repository.delete_item(item)
        await self.db.commit()

    async def remove_item_by_id(self, item_id: uuid.UUID) -> None:
        item = await self.repository.get_item_by_id(item_id)
        if item is None:
            raise NotFoundError("Playlist item not found")
        await self.repository.delete_item(item)
        await self.db.commit()

    async def review_item_by_id(
        self, item_id: uuid.UUID, payload: PlaylistItemReview, current_user: User
    ) -> PlaylistResponse:
        item = await self.repository.get_item_by_id(item_id)
        if item is None:
            raise NotFoundError("Playlist item not found")
        return await self.review_item(item.playlist_id, item_id, payload, current_user)

    async def review_item(
        self,
        playlist_id: uuid.UUID,
        item_id: uuid.UUID,
        payload: PlaylistItemReview,
        current_user: User,
    ) -> PlaylistResponse:
        playlist = await self.repository.get_by_id(playlist_id)
        if playlist is None:
            raise NotFoundError("Playlist not found")
        item = await self.repository.get_item_by_id(item_id)
        if item is None or item.playlist_id != playlist_id:
            raise NotFoundError("Playlist item not found")

        update_data: dict[str, object] = {
            "review_status": payload.review_status,
            "reviewed_by": current_user.id,
            "reviewed_at": datetime.now(timezone.utc),
        }
        if payload.reviewer_notes is not None:
            update_data["reviewer_notes"] = payload.reviewer_notes

        await self.repository.update_item(item, **update_data)

        # Optionally propagate review to version
        if payload.propagate_to_version and payload.review_status != ReviewStatus.pending:
            target_status = REVIEW_TO_VERSION_STATUS.get(payload.review_status)
            if target_status is not None:
                result = await self.db.execute(select(Version).where(Version.id == item.version_id))
                version = result.scalar_one_or_none()
                if version is not None:
                    version.status = target_status
                    self.db.add(version)
                    await self.db.flush()

        # Auto-complete playlist if no pending items remain
        if playlist.status == PlaylistStatus.in_progress:
            pending_count = await self.repository.count_pending_items(playlist_id)
            if pending_count == 0:
                await self.repository.update(playlist, status=PlaylistStatus.completed)

        await self.db.commit()
        await self.db.refresh(playlist)
        items = await self.repository.get_items(playlist_id)
        return self._build_response(playlist, items)

    async def reorder_items(
        self,
        playlist_id: uuid.UUID,
        payload: PlaylistItemsReorder,
        current_user: User,
    ) -> PlaylistResponse:
        playlist = await self.repository.get_by_id(playlist_id)
        if playlist is None:
            raise NotFoundError("Playlist not found")

        for entry in payload.items:
            item = await self.repository.get_item_by_id(entry.item_id)
            if item is None or item.playlist_id != playlist_id:
                raise NotFoundError(f"Playlist item {entry.item_id} not found")
            await self.repository.update_item(item, order=entry.order)

        await self.db.commit()
        await self.db.refresh(playlist)
        items = await self.repository.get_items(playlist_id)
        return self._build_response(playlist, items)

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playlist import Playlist, PlaylistItem, PlaylistStatus, ReviewStatus


class PlaylistRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Playlist ──────────────────────────────────────────────────────────

    async def get_by_id(
        self, playlist_id: uuid.UUID, include_archived: bool = False
    ) -> Playlist | None:
        statement = select(Playlist).where(Playlist.id == playlist_id)
        if not include_archived:
            statement = statement.where(Playlist.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def create(
        self,
        project_id: uuid.UUID,
        name: str,
        created_by: uuid.UUID,
        description: str | None = None,
        date: date | None = None,
    ) -> Playlist:
        playlist = Playlist(
            project_id=project_id,
            name=name,
            description=description,
            created_by=created_by,
            date=date,
        )
        self.db.add(playlist)
        await self.db.flush()
        await self.db.refresh(playlist)
        return playlist

    async def update(self, playlist: Playlist, **kwargs: object) -> Playlist:
        for key, value in kwargs.items():
            setattr(playlist, key, value)
        self.db.add(playlist)
        await self.db.flush()
        await self.db.refresh(playlist)
        return playlist

    async def archive(self, playlist: Playlist) -> Playlist:
        playlist.archived_at = datetime.now(timezone.utc)
        self.db.add(playlist)
        await self.db.flush()
        await self.db.refresh(playlist)
        return playlist

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        offset: int,
        limit: int,
        status: PlaylistStatus | None = None,
        filter_date: date | None = None,
        created_by: uuid.UUID | None = None,
    ) -> tuple[list[Playlist], int]:
        statement = select(Playlist).where(
            Playlist.project_id == project_id,
            Playlist.archived_at.is_(None),
        )
        count_stmt = select(func.count(Playlist.id)).where(
            Playlist.project_id == project_id,
            Playlist.archived_at.is_(None),
        )
        if status is not None:
            statement = statement.where(Playlist.status == status)
            count_stmt = count_stmt.where(Playlist.status == status)
        if filter_date is not None:
            statement = statement.where(Playlist.date == filter_date)
            count_stmt = count_stmt.where(Playlist.date == filter_date)
        if created_by is not None:
            statement = statement.where(Playlist.created_by == created_by)
            count_stmt = count_stmt.where(Playlist.created_by == created_by)

        statement = statement.order_by(Playlist.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())
        total = int((await self.db.execute(count_stmt)).scalar_one())
        return rows, total

    # ── Playlist Items ────────────────────────────────────────────────────

    async def get_item_by_id(self, item_id: uuid.UUID) -> PlaylistItem | None:
        result = await self.db.execute(select(PlaylistItem).where(PlaylistItem.id == item_id))
        return result.scalar_one_or_none()

    async def get_item(self, playlist_id: uuid.UUID, version_id: uuid.UUID) -> PlaylistItem | None:
        result = await self.db.execute(
            select(PlaylistItem).where(
                PlaylistItem.playlist_id == playlist_id,
                PlaylistItem.version_id == version_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_items(self, playlist_id: uuid.UUID) -> list[PlaylistItem]:
        result = await self.db.execute(
            select(PlaylistItem)
            .where(PlaylistItem.playlist_id == playlist_id)
            .order_by(PlaylistItem.order.asc())
        )
        return list(result.scalars().all())

    async def get_max_order(self, playlist_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.max(PlaylistItem.order)).where(PlaylistItem.playlist_id == playlist_id)
        )
        max_order = result.scalar_one_or_none()
        return int(max_order) if max_order is not None else 0

    async def add_item(
        self,
        playlist_id: uuid.UUID,
        version_id: uuid.UUID,
        order: int,
    ) -> PlaylistItem:
        item = PlaylistItem(
            playlist_id=playlist_id,
            version_id=version_id,
            order=order,
        )
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def update_item(self, item: PlaylistItem, **kwargs: object) -> PlaylistItem:
        for key, value in kwargs.items():
            setattr(item, key, value)
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def delete_item(self, item: PlaylistItem) -> None:
        await self.db.delete(item)
        await self.db.flush()

    async def count_pending_items(self, playlist_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(PlaylistItem.id)).where(
                PlaylistItem.playlist_id == playlist_id,
                PlaylistItem.review_status == ReviewStatus.pending,
            )
        )
        return int(result.scalar_one())

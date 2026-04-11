import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Episode, EpisodeStatus


class EpisodeRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_for_project(
        self,
        project_id: uuid.UUID,
        name: str,
        code: str,
        status: EpisodeStatus = EpisodeStatus.active,
        description: str | None = None,
        order: int | None = None,
        production_number: int | None = None,
    ) -> Episode:
        episode = Episode(
            project_id=project_id,
            name=name,
            code=code,
            status=status,
            description=description,
            order=order,
            production_number=production_number,
        )
        self.db.add(episode)
        await self.db.flush()
        await self.db.refresh(episode)
        return episode

    async def get_by_id(
        self, episode_id: uuid.UUID, include_archived: bool = False
    ) -> Episode | None:
        statement = select(Episode).where(Episode.id == episode_id)
        if not include_archived:
            statement = statement.where(Episode.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_project_and_code(
        self,
        project_id: uuid.UUID,
        code: str,
        include_archived: bool = False,
    ) -> Episode | None:
        statement = select(Episode).where(Episode.project_id == project_id, Episode.code == code)
        if not include_archived:
            statement = statement.where(Episode.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_project_and_id(
        self,
        project_id: uuid.UUID,
        episode_id: uuid.UUID,
        include_archived: bool = False,
    ) -> Episode | None:
        statement = select(Episode).where(
            Episode.project_id == project_id, Episode.id == episode_id
        )
        if not include_archived:
            statement = statement.where(Episode.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        offset: int,
        limit: int,
        include_archived: bool = False,
    ) -> tuple[list[Episode], int]:
        statement = (
            select(Episode)
            .where(Episode.project_id == project_id)
            .order_by(Episode.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        count_statement = select(func.count(Episode.id)).where(Episode.project_id == project_id)

        if not include_archived:
            statement = statement.where(Episode.archived_at.is_(None))
            count_statement = count_statement.where(Episode.archived_at.is_(None))

        result = await self.db.execute(statement)
        rows = list(result.scalars().all())

        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

    async def list_all_for_project(self, project_id: uuid.UUID) -> list[Episode]:
        statement = (
            select(Episode)
            .where(Episode.project_id == project_id, Episode.archived_at.is_(None))
            .order_by(Episode.created_at.asc())
        )
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def archive(self, episode: Episode) -> Episode:
        episode.archived_at = datetime.now(timezone.utc)
        self.db.add(episode)
        await self.db.flush()
        await self.db.refresh(episode)
        return episode

    async def restore(self, episode: Episode) -> Episode:
        episode.archived_at = None
        self.db.add(episode)
        await self.db.flush()
        await self.db.refresh(episode)
        return episode

    async def hard_delete(self, episode: Episode) -> None:
        await self.db.delete(episode)

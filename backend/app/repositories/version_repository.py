import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.version import Version, VersionStatus


class VersionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(
        self, version_id: uuid.UUID, include_archived: bool = False
    ) -> Version | None:
        statement = select(Version).where(Version.id == version_id)
        if not include_archived:
            statement = statement.where(Version.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def get_max_version_number(
        self,
        shot_id: uuid.UUID | None,
        asset_id: uuid.UUID | None,
        pipeline_task_id: uuid.UUID | None,
    ) -> int:
        statement = select(func.max(Version.version_number))
        if shot_id is not None:
            statement = statement.where(Version.shot_id == shot_id)
        if asset_id is not None:
            statement = statement.where(Version.asset_id == asset_id)
        if pipeline_task_id is not None:
            statement = statement.where(Version.pipeline_task_id == pipeline_task_id)
        result = await self.db.execute(statement)
        max_num = result.scalar_one_or_none()
        return int(max_num) if max_num is not None else 0

    async def create(
        self,
        project_id: uuid.UUID,
        shot_id: uuid.UUID | None,
        asset_id: uuid.UUID | None,
        pipeline_task_id: uuid.UUID | None,
        code: str,
        version_number: int,
        submitted_by: uuid.UUID,
        description: str | None = None,
        thumbnail_url: str | None = None,
        media_url: str | None = None,
    ) -> Version:
        version = Version(
            project_id=project_id,
            shot_id=shot_id,
            asset_id=asset_id,
            pipeline_task_id=pipeline_task_id,
            code=code,
            version_number=version_number,
            submitted_by=submitted_by,
            description=description,
            thumbnail_url=thumbnail_url,
            media_url=media_url,
        )
        self.db.add(version)
        await self.db.flush()
        await self.db.refresh(version)
        return version

    async def update(self, version: Version, **kwargs: object) -> Version:
        for key, value in kwargs.items():
            setattr(version, key, value)
        self.db.add(version)
        await self.db.flush()
        await self.db.refresh(version)
        return version

    async def archive(self, version: Version) -> Version:
        version.archived_at = datetime.now(timezone.utc)
        self.db.add(version)
        await self.db.flush()
        await self.db.refresh(version)
        return version

    async def list_by_shot(
        self,
        shot_id: uuid.UUID,
        offset: int,
        limit: int,
        status: VersionStatus | None = None,
        pipeline_task_id: uuid.UUID | None = None,
        submitted_by: uuid.UUID | None = None,
    ) -> tuple[list[Version], int]:
        statement = select(Version).where(
            Version.shot_id == shot_id,
            Version.archived_at.is_(None),
        )
        count_statement = select(func.count(Version.id)).where(
            Version.shot_id == shot_id,
            Version.archived_at.is_(None),
        )
        if status is not None:
            statement = statement.where(Version.status == status)
            count_statement = count_statement.where(Version.status == status)
        if pipeline_task_id is not None:
            statement = statement.where(Version.pipeline_task_id == pipeline_task_id)
            count_statement = count_statement.where(Version.pipeline_task_id == pipeline_task_id)
        if submitted_by is not None:
            statement = statement.where(Version.submitted_by == submitted_by)
            count_statement = count_statement.where(Version.submitted_by == submitted_by)

        statement = statement.order_by(Version.version_number.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())
        total = int((await self.db.execute(count_statement)).scalar_one())
        return rows, total

    async def list_by_asset(
        self,
        asset_id: uuid.UUID,
        offset: int,
        limit: int,
        status: VersionStatus | None = None,
        pipeline_task_id: uuid.UUID | None = None,
        submitted_by: uuid.UUID | None = None,
    ) -> tuple[list[Version], int]:
        statement = select(Version).where(
            Version.asset_id == asset_id,
            Version.archived_at.is_(None),
        )
        count_statement = select(func.count(Version.id)).where(
            Version.asset_id == asset_id,
            Version.archived_at.is_(None),
        )
        if status is not None:
            statement = statement.where(Version.status == status)
            count_statement = count_statement.where(Version.status == status)
        if pipeline_task_id is not None:
            statement = statement.where(Version.pipeline_task_id == pipeline_task_id)
            count_statement = count_statement.where(Version.pipeline_task_id == pipeline_task_id)
        if submitted_by is not None:
            statement = statement.where(Version.submitted_by == submitted_by)
            count_statement = count_statement.where(Version.submitted_by == submitted_by)

        statement = statement.order_by(Version.version_number.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())
        total = int((await self.db.execute(count_statement)).scalar_one())
        return rows, total

    async def list_by_task(
        self,
        pipeline_task_id: uuid.UUID,
        offset: int,
        limit: int,
        status: VersionStatus | None = None,
        submitted_by: uuid.UUID | None = None,
    ) -> tuple[list[Version], int]:
        statement = select(Version).where(
            Version.pipeline_task_id == pipeline_task_id,
            Version.archived_at.is_(None),
        )
        count_statement = select(func.count(Version.id)).where(
            Version.pipeline_task_id == pipeline_task_id,
            Version.archived_at.is_(None),
        )
        if status is not None:
            statement = statement.where(Version.status == status)
            count_statement = count_statement.where(Version.status == status)
        if submitted_by is not None:
            statement = statement.where(Version.submitted_by == submitted_by)
            count_statement = count_statement.where(Version.submitted_by == submitted_by)

        statement = statement.order_by(Version.version_number.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())
        total = int((await self.db.execute(count_statement)).scalar_one())
        return rows, total

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        offset: int,
        limit: int,
        status: VersionStatus | None = None,
        submitted_by: uuid.UUID | None = None,
    ) -> tuple[list[Version], int]:
        statement = select(Version).where(
            Version.project_id == project_id,
            Version.archived_at.is_(None),
        )
        count_statement = select(func.count(Version.id)).where(
            Version.project_id == project_id,
            Version.archived_at.is_(None),
        )
        if status is not None:
            statement = statement.where(Version.status == status)
            count_statement = count_statement.where(Version.status == status)
        if submitted_by is not None:
            statement = statement.where(Version.submitted_by == submitted_by)
            count_statement = count_statement.where(Version.submitted_by == submitted_by)

        statement = statement.order_by(Version.version_number.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())
        total = int((await self.db.execute(count_statement)).scalar_one())
        return rows, total

    async def is_latest_for_task(self, version: Version) -> bool:
        """Check if this version has the highest version_number for its shot/asset+task."""
        if version.pipeline_task_id is None:
            return False
        max_num = await self.get_max_version_number(
            shot_id=version.shot_id,
            asset_id=version.asset_id,
            pipeline_task_id=version.pipeline_task_id,
        )
        return version.version_number >= max_num

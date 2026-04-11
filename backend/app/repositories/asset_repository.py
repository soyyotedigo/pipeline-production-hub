import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, AssetStatus, AssetType, Priority


class AssetRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_for_project(
        self,
        project_id: uuid.UUID,
        name: str,
        asset_type: AssetType,
        assigned_to: uuid.UUID | None,
        code: str | None = None,
        description: str | None = None,
        thumbnail_url: str | None = None,
        priority: Priority = Priority.normal,
    ) -> Asset:
        asset = Asset(
            project_id=project_id,
            name=name,
            code=code,
            asset_type=asset_type,
            status=AssetStatus.pending,
            assigned_to=assigned_to,
            description=description,
            thumbnail_url=thumbnail_url,
            priority=priority,
        )
        self.db.add(asset)
        await self.db.flush()
        await self.db.refresh(asset)
        return asset

    async def get_by_id(self, asset_id: uuid.UUID, include_archived: bool = False) -> Asset | None:
        statement = select(Asset).where(Asset.id == asset_id)
        if not include_archived:
            statement = statement.where(Asset.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_project_and_id(
        self,
        project_id: uuid.UUID,
        asset_id: uuid.UUID,
        include_archived: bool = False,
    ) -> Asset | None:
        statement = select(Asset).where(Asset.project_id == project_id, Asset.id == asset_id)
        if not include_archived:
            statement = statement.where(Asset.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_project_and_code(
        self,
        project_id: uuid.UUID,
        code: str,
        include_archived: bool = False,
    ) -> Asset | None:
        statement = select(Asset).where(Asset.project_id == project_id, Asset.code == code)
        if not include_archived:
            statement = statement.where(Asset.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        offset: int,
        limit: int,
        status: AssetStatus | None,
        assigned_to: uuid.UUID | None,
        asset_type: AssetType | None,
        include_archived: bool = False,
    ) -> tuple[list[Asset], int]:
        statement = select(Asset).where(Asset.project_id == project_id)
        count_statement = select(func.count(Asset.id)).where(Asset.project_id == project_id)

        if not include_archived:
            statement = statement.where(Asset.archived_at.is_(None))
            count_statement = count_statement.where(Asset.archived_at.is_(None))

        if status is not None:
            statement = statement.where(Asset.status == status)
            count_statement = count_statement.where(Asset.status == status)
        if assigned_to is not None:
            statement = statement.where(Asset.assigned_to == assigned_to)
            count_statement = count_statement.where(Asset.assigned_to == assigned_to)
        if asset_type is not None:
            statement = statement.where(Asset.asset_type == asset_type)
            count_statement = count_statement.where(Asset.asset_type == asset_type)

        statement = statement.order_by(Asset.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())

        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

    async def set_status(self, asset: Asset, status: AssetStatus) -> Asset:
        asset.status = status
        self.db.add(asset)
        await self.db.flush()
        await self.db.refresh(asset)
        return asset

    async def list_all_for_project(self, project_id: uuid.UUID) -> list[Asset]:
        statement = (
            select(Asset)
            .where(Asset.project_id == project_id, Asset.archived_at.is_(None))
            .order_by(Asset.created_at.asc())
        )
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def archive(self, asset: Asset) -> Asset:
        asset.archived_at = datetime.now(timezone.utc)
        self.db.add(asset)
        await self.db.flush()
        await self.db.refresh(asset)
        return asset

    async def restore(self, asset: Asset) -> Asset:
        asset.archived_at = None
        self.db.add(asset)
        await self.db.flush()
        await self.db.refresh(asset)
        return asset

    async def hard_delete(self, asset: Asset) -> None:
        await self.db.delete(asset)

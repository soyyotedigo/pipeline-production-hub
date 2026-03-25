import uuid
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shot_asset_link import LinkType, ShotAssetLink


class ShotAssetLinkRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, link_id: uuid.UUID) -> ShotAssetLink | None:
        result = await self.db.execute(select(ShotAssetLink).where(ShotAssetLink.id == link_id))
        return result.scalar_one_or_none()

    async def get(self, shot_id: uuid.UUID, asset_id: uuid.UUID) -> ShotAssetLink | None:
        result = await self.db.execute(
            select(ShotAssetLink).where(
                ShotAssetLink.shot_id == shot_id,
                ShotAssetLink.asset_id == asset_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        shot_id: uuid.UUID,
        asset_id: uuid.UUID,
        link_type: LinkType,
        created_by: uuid.UUID | None,
    ) -> ShotAssetLink:
        link = ShotAssetLink(
            shot_id=shot_id,
            asset_id=asset_id,
            link_type=link_type,
            created_by=created_by,
        )
        self.db.add(link)
        await self.db.flush()
        await self.db.refresh(link)
        return link

    async def delete_by_id(self, link: ShotAssetLink) -> None:
        await self.db.delete(link)
        await self.db.flush()

    async def delete(self, shot_id: uuid.UUID, asset_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            delete(ShotAssetLink).where(
                ShotAssetLink.shot_id == shot_id,
                ShotAssetLink.asset_id == asset_id,
            )
        )
        delete_result = cast("CursorResult[object]", result)
        return delete_result.rowcount > 0

    async def get_assets_for_shot(
        self,
        shot_id: uuid.UUID,
        link_type: LinkType | None = None,
    ) -> list[ShotAssetLink]:
        statement = select(ShotAssetLink).where(ShotAssetLink.shot_id == shot_id)
        if link_type is not None:
            statement = statement.where(ShotAssetLink.link_type == link_type)
        statement = statement.order_by(ShotAssetLink.created_at.asc())
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def get_shots_for_asset(
        self,
        asset_id: uuid.UUID,
        link_type: LinkType | None = None,
    ) -> list[ShotAssetLink]:
        statement = select(ShotAssetLink).where(ShotAssetLink.asset_id == asset_id)
        if link_type is not None:
            statement = statement.where(ShotAssetLink.link_type == link_type)
        statement = statement.order_by(ShotAssetLink.created_at.asc())
        result = await self.db.execute(statement)
        return list(result.scalars().all())

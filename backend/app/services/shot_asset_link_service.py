import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.models import Asset, RoleName, Shot, User
from app.models.shot_asset_link import LinkType
from app.repositories.shot_asset_link_repository import ShotAssetLinkRepository
from app.repositories.user_role_repository import UserRoleRepository
from app.schemas.shot_asset_link import (
    AssetShotsResponse,
    BulkLinkCreate,
    BulkLinkResponse,
    LinkCreate,
    LinkResponse,
    ShotAssetsResponse,
)


class ShotAssetLinkService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = ShotAssetLinkRepository(db)
        self.role_repository = UserRoleRepository(db)

    async def _require_project_role(self, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        allowed = {RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist}
        if not await self.role_repository.has_any_role(user_id, allowed, project_id):
            raise ForbiddenError("Insufficient permissions to manage shot-asset links")

    async def _get_shot(self, shot_id: uuid.UUID) -> Shot:
        result = await self.db.execute(
            select(Shot).where(Shot.id == shot_id, Shot.archived_at.is_(None))
        )
        shot = result.scalar_one_or_none()
        if shot is None:
            raise NotFoundError("Shot not found")
        return shot

    async def _get_asset(self, asset_id: uuid.UUID) -> Asset | None:
        result = await self.db.execute(
            select(Asset).where(Asset.id == asset_id, Asset.archived_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def create_link(
        self,
        shot_id: uuid.UUID,
        payload: LinkCreate,
        current_user: User,
    ) -> LinkResponse:
        shot = await self._get_shot(shot_id)
        await self._require_project_role(current_user.id, shot.project_id)

        asset = await self._get_asset(payload.asset_id)
        if asset is None:
            raise NotFoundError("Asset not found")

        if shot.project_id != asset.project_id:
            raise UnprocessableError("Shot and asset must belong to the same project")

        existing = await self.repository.get(shot_id, payload.asset_id)
        if existing is not None:
            raise ConflictError("Link already exists between this shot and asset")

        link = await self.repository.create(
            shot_id=shot_id,
            asset_id=payload.asset_id,
            link_type=payload.link_type,
            created_by=current_user.id,
        )
        await self.db.commit()
        await self.db.refresh(link)
        return LinkResponse.model_validate(link)

    async def delete_link(self, shot_id: uuid.UUID, asset_id: uuid.UUID) -> None:
        deleted = await self.repository.delete(shot_id, asset_id)
        if not deleted:
            raise NotFoundError("Link not found")
        await self.db.commit()

    async def delete_link_by_id(self, link_id: uuid.UUID) -> None:
        link = await self.repository.get_by_id(link_id)
        if link is None:
            raise NotFoundError("Link not found")
        await self.repository.delete_by_id(link)
        await self.db.commit()

    async def get_assets_for_shot(
        self,
        shot_id: uuid.UUID,
        link_type: LinkType | None = None,
    ) -> ShotAssetsResponse:
        await self._get_shot(shot_id)
        links = await self.repository.get_assets_for_shot(shot_id, link_type=link_type)
        return ShotAssetsResponse(
            shot_id=shot_id,
            total=len(links),
            items=[LinkResponse.model_validate(lnk) for lnk in links],
        )

    async def get_shots_for_asset(
        self,
        asset_id: uuid.UUID,
        link_type: LinkType | None = None,
    ) -> AssetShotsResponse:
        asset = await self._get_asset(asset_id)
        if asset is None:
            raise NotFoundError("Asset not found")
        links = await self.repository.get_shots_for_asset(asset_id, link_type=link_type)
        return AssetShotsResponse(
            asset_id=asset_id,
            total=len(links),
            items=[LinkResponse.model_validate(lnk) for lnk in links],
        )

    async def bulk_create_links(
        self,
        shot_id: uuid.UUID,
        payload: BulkLinkCreate,
        current_user: User,
    ) -> BulkLinkResponse:
        shot = await self._get_shot(shot_id)
        await self._require_project_role(current_user.id, shot.project_id)

        created: list[LinkResponse] = []
        skipped: list[uuid.UUID] = []
        errors: list[uuid.UUID] = []

        for item in payload.links:
            asset = await self._get_asset(item.asset_id)
            if asset is None or asset.project_id != shot.project_id:
                errors.append(item.asset_id)
                continue

            existing = await self.repository.get(shot_id, item.asset_id)
            if existing is not None:
                skipped.append(item.asset_id)
                continue

            try:
                link = await self.repository.create(
                    shot_id=shot_id,
                    asset_id=item.asset_id,
                    link_type=item.link_type,
                    created_by=current_user.id,
                )
                created.append(LinkResponse.model_validate(link))
            except IntegrityError:
                await self.db.rollback()
                skipped.append(item.asset_id)

        await self.db.commit()
        return BulkLinkResponse(created=created, skipped=skipped, errors=errors)

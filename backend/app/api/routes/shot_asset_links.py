import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.shot_asset_link import LinkType
from app.schemas.shot_asset_link import (
    AssetShotsResponse,
    BulkLinkCreate,
    BulkLinkResponse,
    LinkCreate,
    LinkResponse,
    ShotAssetsResponse,
)
from app.services.shot_asset_link_service import ShotAssetLinkService

shots_router = APIRouter()
assets_router = APIRouter()
shot_asset_links_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


# ── Shot → Assets ─────────────────────────────────────────────────────────────


@shots_router.post(
    "/{id}/assets",
    response_model=LinkResponse,
    status_code=201,
    summary="Link Asset to Shot",
    description="Create a link between a shot and an asset. Both must be in the same project.",
)
async def link_asset_to_shot(
    id: uuid.UUID,
    payload: LinkCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> LinkResponse:
    return await ShotAssetLinkService(db).create_link(id, payload, current_user)


@shots_router.get(
    "/{id}/assets",
    response_model=ShotAssetsResponse,
    summary="List Shot Assets",
    description="List all assets linked to a shot, optionally filtered by link_type.",
)
async def list_shot_assets(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    link_type: LinkType | None = Query(default=None),
) -> ShotAssetsResponse:
    return await ShotAssetLinkService(db).get_assets_for_shot(id, link_type=link_type)


@shots_router.post(
    "/{id}/assets/bulk",
    response_model=BulkLinkResponse,
    status_code=201,
    summary="Bulk Link Assets to Shot",
    description="Link multiple assets to a shot in one operation. Returns created, skipped, and error lists.",
)
async def bulk_link_assets_to_shot(
    id: uuid.UUID,
    payload: BulkLinkCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> BulkLinkResponse:
    return await ShotAssetLinkService(db).bulk_create_links(id, payload, current_user)


# ── Asset → Shots (impact analysis) ──────────────────────────────────────────


@assets_router.get(
    "/{id}/shots",
    response_model=AssetShotsResponse,
    summary="List Asset Shots (Impact Analysis)",
    description="List all shots that reference this asset. Useful for impact analysis when the asset changes.",
)
async def list_asset_shots(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    link_type: LinkType | None = Query(default=None),
) -> AssetShotsResponse:
    return await ShotAssetLinkService(db).get_shots_for_asset(id, link_type=link_type)


@shot_asset_links_router.delete(
    "/{id}",
    status_code=204,
    summary="Unlink Asset from Shot",
    description="Remove the link between a shot and an asset.",
)
async def unlink_asset_from_shot(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> Response:
    await ShotAssetLinkService(db).delete_link_by_id(id)
    return Response(status_code=204)

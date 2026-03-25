from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.shot_asset_link import LinkType


class LinkCreate(BaseModel):
    asset_id: uuid.UUID
    link_type: LinkType = LinkType.uses


class BulkLinkCreate(BaseModel):
    links: list[LinkCreate]


class LinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shot_id: uuid.UUID
    asset_id: uuid.UUID
    link_type: LinkType
    created_at: datetime
    created_by: uuid.UUID | None


class BulkLinkResponse(BaseModel):
    created: list[LinkResponse]
    skipped: list[uuid.UUID]  # asset_ids already linked
    errors: list[uuid.UUID]  # asset_ids not found or wrong project


class ShotAssetsResponse(BaseModel):
    shot_id: uuid.UUID
    total: int
    items: list[LinkResponse]


class AssetShotsResponse(BaseModel):
    asset_id: uuid.UUID
    total: int
    items: list[LinkResponse]

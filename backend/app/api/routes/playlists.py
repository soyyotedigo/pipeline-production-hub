import uuid
from datetime import date as Date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.playlist import PlaylistStatus
from app.schemas.playlist import (
    PlaylistCreate,
    PlaylistItemAdd,
    PlaylistItemReview,
    PlaylistItemsReorder,
    PlaylistListResponse,
    PlaylistResponse,
    PlaylistUpdate,
)
from app.services.playlist_service import PlaylistService

router = APIRouter()
projects_router = APIRouter()
playlist_items_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


# ── Playlist CRUD ─────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=PlaylistResponse,
    status_code=201,
    summary="Create Playlist",
    description="Create a new playlist (dailies session) for a project.",
)
async def create_playlist(
    payload: PlaylistCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PlaylistResponse:
    return await PlaylistService(db).create_playlist(payload, current_user)


@router.get(
    "/{id}",
    response_model=PlaylistResponse,
    summary="Get Playlist",
    description="Get playlist with all its items.",
)
async def get_playlist(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PlaylistResponse:
    return await PlaylistService(db).get_playlist(id)


@router.patch(
    "/{id}",
    response_model=PlaylistResponse,
    summary="Update Playlist",
    description="Update name, description, date, or status of a playlist.",
)
async def update_playlist(
    id: uuid.UUID,
    payload: PlaylistUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PlaylistResponse:
    return await PlaylistService(db).update_playlist(id, payload, current_user)


@router.delete(
    "/{id}",
    response_model=PlaylistResponse,
    summary="Archive Playlist",
    description="Soft-delete a playlist.",
)
async def archive_playlist(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PlaylistResponse:
    return await PlaylistService(db).archive_playlist(id, current_user)


# ── Items ─────────────────────────────────────────────────────────────────────


@router.post(
    "/{id}/items",
    response_model=PlaylistResponse,
    status_code=201,
    summary="Add Item to Playlist",
    description="Add a version to the playlist. Order is auto-assigned.",
)
async def add_item(
    id: uuid.UUID,
    payload: PlaylistItemAdd,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PlaylistResponse:
    return await PlaylistService(db).add_item(id, payload, current_user)


@router.patch(
    "/{id}/items/reorder",
    response_model=PlaylistResponse,
    summary="Reorder Playlist Items",
    description="Update the order of playlist items.",
)
async def reorder_items(
    id: uuid.UUID,
    payload: PlaylistItemsReorder,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PlaylistResponse:
    return await PlaylistService(db).reorder_items(id, payload, current_user)


# ── Project sub-router ────────────────────────────────────────────────────────


@projects_router.get(
    "/{id}/playlists",
    response_model=PlaylistListResponse,
    summary="List Project Playlists",
    description="List playlists for a project, with optional status/date/creator filters.",
)
async def list_project_playlists(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: PlaylistStatus | None = Query(default=None),
    date: Date | None = Query(default=None),
    created_by: uuid.UUID | None = Query(default=None),
) -> PlaylistListResponse:
    return await PlaylistService(db).list_for_project(
        project_id=id,
        offset=offset,
        limit=limit,
        status=status,
        filter_date=date,
        created_by=created_by,
    )


@playlist_items_router.delete("/{id}", status_code=204, summary="Remove Item from Playlist")
async def remove_playlist_item(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> Response:
    await PlaylistService(db).remove_item_by_id(id)
    return Response(status_code=204)


@playlist_items_router.patch(
    "/{id}",
    response_model=PlaylistResponse,
    summary="Review Playlist Item",
    description="Set review_status on an item. Optionally propagate to the Version status.",
)
async def review_playlist_item(
    id: uuid.UUID,
    payload: PlaylistItemReview,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PlaylistResponse:
    return await PlaylistService(db).review_item_by_id(id, payload, current_user)

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, BinaryIO

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.file import (
    FileListResponse,
    FileResponse,
    FileUpdate,
    FileVersionsResponse,
    PresignedUrlResponse,
)
from app.services.file_service import FileService

router = APIRouter()
project_router = APIRouter()
shots_router = APIRouter()
assets_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post(
    "/upload",
    response_model=FileResponse,
    deprecated=True,
    summary="Upload File (Legacy)",
    description="Legacy upload endpoint kept for backward compatibility.",
)
async def upload_file(
    current_user: CurrentUserDep,
    db: DbDep,
    upload: UploadFile = File(...),
    shot_id: uuid.UUID | None = Form(default=None),
    asset_id: uuid.UUID | None = Form(default=None),
) -> FileResponse:
    service = FileService(db)
    return await service.upload_file(
        original_name=upload.filename or "upload.bin",
        mime_type=upload.content_type,
        data=upload.file,
        shot_id=shot_id,
        asset_id=asset_id,
        current_user=current_user,
    )


@project_router.post(
    "/{id}/files/upload",
    response_model=FileResponse,
    summary="Upload Project File",
    description="Upload a file to a project, optionally linking it to a shot or asset.",
)
async def upload_project_file(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    upload: UploadFile = File(...),
    shot_id: uuid.UUID | None = Form(default=None),
    asset_id: uuid.UUID | None = Form(default=None),
) -> FileResponse:
    service = FileService(db)
    return await service.upload_file(
        original_name=upload.filename or "upload.bin",
        mime_type=upload.content_type,
        data=upload.file,
        shot_id=shot_id,
        asset_id=asset_id,
        current_user=current_user,
        project_id=id,
    )


@project_router.get(
    "/{id}/files",
    response_model=FileListResponse,
    summary="List Project Files",
    description="List all files across all shots and assets in a project.",
)
async def list_project_files(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> FileListResponse:
    return await FileService(db).list_files_for_project(
        project_id=id,
        offset=offset,
        limit=limit,
        current_user=current_user,
    )


@shots_router.get(
    "/{id}/files",
    response_model=FileListResponse,
    summary="List Shot Files",
    description="List files belonging to a shot.",
)
async def list_shot_files(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> FileListResponse:
    return await FileService(db).list_files_for_shot(
        shot_id=id,
        offset=offset,
        limit=limit,
        current_user=current_user,
    )


@assets_router.get(
    "/{id}/files",
    response_model=FileListResponse,
    summary="List Asset Files",
    description="List files belonging to an asset.",
)
async def list_asset_files(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> FileListResponse:
    return await FileService(db).list_files_for_asset(
        asset_id=id,
        offset=offset,
        limit=limit,
        current_user=current_user,
    )


@router.get(
    "/{id}",
    response_model=FileResponse,
    summary="Get File Metadata",
    description="Fetch metadata for a stored file version.",
)
async def get_file(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> FileResponse:
    service = FileService(db)
    return await service.get_file(id, current_user)


@router.patch(
    "/{id}",
    response_model=FileResponse,
    summary="Update File Metadata",
    description="Update file metadata fields: original_name, mime_type, comment, file_type, file_status.",
)
async def update_file(
    id: uuid.UUID,
    payload: FileUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> FileResponse:
    return await FileService(db).update_file(file_id=id, payload=payload, current_user=current_user)


@router.get(
    "/{id}/presigned-url",
    response_model=PresignedUrlResponse,
    summary="Get Presigned URL",
    description="Get a presigned URL for direct S3 access. Only available when STORAGE_BACKEND=s3.",
)
async def get_presigned_url(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PresignedUrlResponse:
    return await FileService(db).get_presigned_url(file_id=id, current_user=current_user)


@router.get(
    "/{id}/download",
    response_model=None,
    summary="Download File",
    description="Download file content as a stream or redirect to storage URL.",
)
async def download_file(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> Response:
    service = FileService(db)
    file_item, payload = await service.download_file(id, current_user)

    if isinstance(payload, str):
        return RedirectResponse(url=payload, status_code=307)

    async def stream_chunks(stream: BinaryIO) -> AsyncIterator[bytes]:
        try:
            while True:
                chunk = await asyncio.to_thread(stream.read, 1024 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            stream.close()

    return StreamingResponse(
        stream_chunks(payload),
        media_type=file_item.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_item.original_name}"',
        },
    )


@router.get(
    "",
    response_model=FileListResponse,
    summary="List Files",
    description="List files with optional shot/asset filters and pagination.",
)
async def list_files(
    current_user: CurrentUserDep,
    db: DbDep,
    shot_id: uuid.UUID | None = Query(default=None),
    asset_id: uuid.UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> FileListResponse:
    service = FileService(db)
    return await service.list_files(
        shot_id=shot_id,
        asset_id=asset_id,
        offset=offset,
        limit=limit,
        current_user=current_user,
    )


@router.get(
    "/{id}/versions",
    response_model=FileVersionsResponse,
    summary="List File Versions",
    description="List all versions for the same logical file lineage.",
)
async def list_file_versions(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> FileVersionsResponse:
    service = FileService(db)
    return await service.list_versions(id, current_user)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Delete File",
    description="Soft-delete file metadata (blob retention depends on backend policy).",
)
async def delete_file(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    force: bool = Query(default=False),
) -> None:
    service = FileService(db)
    await service.delete_file(id, current_user, force=force)


@router.post(
    "/{id}/archive",
    response_model=FileResponse,
    summary="Archive File",
    description="Archive a file (soft delete).",
)
async def archive_file(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> FileResponse:
    service = FileService(db)
    return await service.archive_file(id, current_user)


@router.post(
    "/{id}/restore",
    response_model=FileResponse,
    summary="Restore File",
    description="Restore an archived file.",
)
async def restore_file(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> FileResponse:
    service = FileService(db)
    return await service.restore_file(id, current_user)

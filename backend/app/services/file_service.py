from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from contextlib import suppress
from typing import BinaryIO, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.models import AssetType, File, RoleName, User
from app.repositories.asset_repository import AssetRepository
from app.repositories.episode_repository import EpisodeRepository
from app.repositories.file_repository import FileRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.sequence_repository import SequenceRepository
from app.repositories.shot_repository import ShotRepository
from app.repositories.user_role_repository import UserRoleRepository
from app.schemas.file import (
    FileListResponse,
    FileResponse,
    FileUpdate,
    FileVersionsResponse,
    PresignedUrlResponse,
)
from app.schemas.task import TaskType
from app.schemas.webhook import WebhookEventType
from app.services.path_template_service import PathTemplateService
from app.services.storage import LocalStorage, StorageBackend, get_storage_backend
from app.services.task_service import TaskService
from app.services.webhook_service import WebhookService


class FileService:
    chunk_size_bytes = 1024 * 1024

    def __init__(self, db: AsyncSession, storage: StorageBackend | None = None) -> None:
        self.db = db
        self.storage = storage or get_storage_backend()
        self.file_repository = FileRepository(db)
        self.shot_repository = ShotRepository(db)
        self.asset_repository = AssetRepository(db)
        self.sequence_repository = SequenceRepository(db)
        self.episode_repository = EpisodeRepository(db)
        self.project_repository = ProjectRepository(db)
        self.user_role_repository = UserRoleRepository(db)
        self.path_template_service = PathTemplateService()
        self.task_service = TaskService()
        self.webhook_service = WebhookService(db)

    async def upload_file(
        self,
        *,
        original_name: str,
        mime_type: str | None,
        data: BinaryIO,
        shot_id: uuid.UUID | None,
        asset_id: uuid.UUID | None,
        current_user: User,
        project_id: uuid.UUID | None = None,
    ) -> FileResponse:
        (
            resolved_project_id,
            entity_type,
            entity_code,
            entity_asset_type,
            episode_code,
            sequence_code,
            resolved_shot_id,
            resolved_asset_id,
        ) = await self._resolve_parent_context(shot_id=shot_id, asset_id=asset_id)
        if project_id is not None and project_id != resolved_project_id:
            raise NotFoundError("Project not found")
        await self._require_project_any_role(
            user_id=current_user.id,
            project_id=resolved_project_id,
            roles={RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist},
        )

        project = await self.project_repository.get_by_id(resolved_project_id)
        if project is None:
            raise NotFoundError("Project not found")

        safe_original_name = self._normalize_filename(original_name)
        version = await self.file_repository.get_next_version(
            original_name=safe_original_name,
            shot_id=resolved_shot_id,
            asset_id=resolved_asset_id,
        )
        storage_path, file_name, _ = self.path_template_service.resolve_upload_path(
            project_code=project.code,
            project_type=project.project_type,
            entity_type=entity_type,
            version=version,
            original_name=safe_original_name,
            shot_code=entity_code if entity_type == "shot" else None,
            asset_code=entity_code if entity_type == "asset" else None,
            asset_type=entity_asset_type.value if entity_asset_type is not None else None,
            episode_code=episode_code,
            sequence_code=sequence_code,
            project_path_templates=project.path_templates,
        )
        buffered_stream, checksum_sha256, size_bytes = self._buffer_stream_for_upload(data)

        try:
            duplicate = await self.file_repository.get_latest_active_by_checksum(checksum_sha256)
            if duplicate is not None and await self.storage.exists(duplicate.storage_path):
                storage_path = duplicate.storage_path
            else:
                buffered_stream.seek(0)
                await self.storage.upload(storage_path, buffered_stream)
        finally:
            buffered_stream.close()

        try:
            thumbnail_task_id = uuid.uuid4()
            checksum_task_id = uuid.uuid4()
            created = await self.file_repository.create(
                name=file_name,
                original_name=safe_original_name,
                version=version,
                storage_path=storage_path,
                size_bytes=size_bytes,
                checksum_sha256=checksum_sha256,
                mime_type=mime_type or "application/octet-stream",
                uploaded_by=current_user.id,
                shot_id=resolved_shot_id,
                asset_id=resolved_asset_id,
                metadata_json={
                    "task_ids": [
                        str(thumbnail_task_id),
                        str(checksum_task_id),
                    ]
                },
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictError("Unable to create file version") from exc

        entity_id = resolved_shot_id or resolved_asset_id
        entity_type = "shot" if resolved_shot_id is not None else "asset"
        enqueue_payload = {
            "file_id": str(created.id),
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id is not None else None,
            "storage_path": storage_path,
            "checksum_sha256": checksum_sha256,
            "size_bytes": size_bytes,
        }
        await self.task_service.enqueue_task(
            task_id=thumbnail_task_id,
            task_type=TaskType.thumbnail,
            created_by=current_user.id,
            payload=enqueue_payload,
        )
        await self.task_service.enqueue_task(
            task_id=checksum_task_id,
            task_type=TaskType.checksum_large_file,
            created_by=current_user.id,
            payload=enqueue_payload,
        )

        await self.webhook_service.enqueue_event(
            event_type=WebhookEventType.file_uploaded,
            project_id=resolved_project_id,
            entity_data={
                "id": str(created.id),
                "project_id": str(resolved_project_id),
                "shot_id": str(resolved_shot_id) if resolved_shot_id is not None else None,
                "asset_id": str(resolved_asset_id) if resolved_asset_id is not None else None,
                "name": created.name,
                "original_name": created.original_name,
                "version": created.version,
                "storage_path": created.storage_path,
                "size_bytes": created.size_bytes,
            },
            triggered_by=current_user.id,
        )

        return FileResponse.model_validate(created)

    async def get_file(self, file_id: uuid.UUID, current_user: User) -> FileResponse:
        item = await self._get_file_or_404(file_id)
        project_id = await self._resolve_project_id_for_file(item)
        await self._require_project_any_role(
            user_id=current_user.id,
            project_id=project_id,
            roles={
                RoleName.admin,
                RoleName.supervisor,
                RoleName.lead,
                RoleName.artist,
                RoleName.worker,
            },
        )
        return FileResponse.model_validate(item)

    async def list_files(
        self,
        *,
        shot_id: uuid.UUID | None,
        asset_id: uuid.UUID | None,
        offset: int,
        limit: int,
        current_user: User,
    ) -> FileListResponse:
        (
            project_id,
            _,
            _,
            _,
            _,
            _,
            resolved_shot_id,
            resolved_asset_id,
        ) = await self._resolve_parent_context(
            shot_id=shot_id,
            asset_id=asset_id,
        )
        await self._require_project_any_role(
            user_id=current_user.id,
            project_id=project_id,
            roles={
                RoleName.admin,
                RoleName.supervisor,
                RoleName.lead,
                RoleName.artist,
                RoleName.worker,
            },
        )

        rows, total = await self.file_repository.list_file_versions_with_total(
            shot_id=resolved_shot_id,
            asset_id=resolved_asset_id,
            offset=offset,
            limit=limit,
        )
        return FileListResponse(
            items=[FileResponse.model_validate(item) for item in rows],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def list_versions(self, file_id: uuid.UUID, current_user: User) -> FileVersionsResponse:
        item = await self._get_file_or_404(file_id)
        project_id = await self._resolve_project_id_for_file(item)
        await self._require_project_any_role(
            user_id=current_user.id,
            project_id=project_id,
            roles={
                RoleName.admin,
                RoleName.supervisor,
                RoleName.lead,
                RoleName.artist,
                RoleName.worker,
            },
        )

        versions = await self.file_repository.list_versions_for_file(file_id)
        return FileVersionsResponse(
            file_id=item.id,
            items=[FileResponse.model_validate(version) for version in versions],
        )

    async def archive_file(self, file_id: uuid.UUID, current_user: User) -> FileResponse:
        item = await self._get_file_or_404(file_id)
        project_id = await self._resolve_project_id_for_file(item)
        await self._require_project_any_role(
            user_id=current_user.id,
            project_id=project_id,
            roles={RoleName.admin, RoleName.supervisor, RoleName.lead},
        )

        item = await self.file_repository.soft_delete(item)
        await self.db.commit()
        return FileResponse.model_validate(item)

    async def restore_file(self, file_id: uuid.UUID, current_user: User) -> FileResponse:
        item = await self.file_repository.get_by_id_any(file_id)
        if item is None:
            raise NotFoundError("File not found")

        project_id = await self._resolve_project_id_for_file(item)
        await self._require_project_any_role(
            user_id=current_user.id,
            project_id=project_id,
            roles={RoleName.admin, RoleName.supervisor, RoleName.lead},
        )

        item = await self.file_repository.restore(item)
        await self.db.commit()
        return FileResponse.model_validate(item)

    async def delete_file(
        self, file_id: uuid.UUID, current_user: User, force: bool = False
    ) -> None:
        if force:
            item = await self.file_repository.get_by_id_any(file_id)
            if item is None:
                raise NotFoundError("File not found")

            await self._require_global_any_role(current_user.id, {RoleName.admin})
            await self.file_repository.hard_delete(item)
            await self.db.commit()
            return

        item = await self._get_file_or_404(file_id)
        project_id = await self._resolve_project_id_for_file(item)
        await self._require_project_any_role(
            user_id=current_user.id,
            project_id=project_id,
            roles={RoleName.admin, RoleName.supervisor, RoleName.lead},
        )

        await self.file_repository.soft_delete(item)
        await self.db.commit()

    async def list_files_for_project(
        self,
        *,
        project_id: uuid.UUID,
        offset: int,
        limit: int,
        current_user: User,
    ) -> FileListResponse:
        project = await self.project_repository.get_by_id(project_id)
        if project is None:
            raise NotFoundError("Project not found")
        await self._require_project_any_role(
            user_id=current_user.id,
            project_id=project_id,
            roles={
                RoleName.admin,
                RoleName.supervisor,
                RoleName.lead,
                RoleName.artist,
                RoleName.worker,
            },
        )
        files, total = await self.file_repository.list_for_project(
            project_id=project_id,
            offset=offset,
            limit=limit,
        )
        return FileListResponse(
            items=[FileResponse.model_validate(f) for f in files],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def list_files_for_shot(
        self,
        *,
        shot_id: uuid.UUID,
        offset: int,
        limit: int,
        current_user: User,
    ) -> FileListResponse:
        shot = await self.shot_repository.get_by_id(shot_id)
        if shot is None:
            raise NotFoundError("Shot not found")
        await self._require_project_any_role(
            user_id=current_user.id,
            project_id=shot.project_id,
            roles={
                RoleName.admin,
                RoleName.supervisor,
                RoleName.lead,
                RoleName.artist,
                RoleName.worker,
            },
        )
        rows, total = await self.file_repository.list_file_versions_with_total(
            shot_id=shot_id,
            offset=offset,
            limit=limit,
        )
        return FileListResponse(
            items=[FileResponse.model_validate(f) for f in rows],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def list_files_for_asset(
        self,
        *,
        asset_id: uuid.UUID,
        offset: int,
        limit: int,
        current_user: User,
    ) -> FileListResponse:
        asset = await self.asset_repository.get_by_id(asset_id)
        if asset is None:
            raise NotFoundError("Asset not found")
        await self._require_project_any_role(
            user_id=current_user.id,
            project_id=asset.project_id,
            roles={
                RoleName.admin,
                RoleName.supervisor,
                RoleName.lead,
                RoleName.artist,
                RoleName.worker,
            },
        )
        rows, total = await self.file_repository.list_file_versions_with_total(
            asset_id=asset_id,
            offset=offset,
            limit=limit,
        )
        return FileListResponse(
            items=[FileResponse.model_validate(f) for f in rows],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def update_file(
        self,
        file_id: uuid.UUID,
        payload: FileUpdate,
        current_user: User,
    ) -> FileResponse:
        item = await self._get_file_or_404(file_id)
        project_id = await self._resolve_project_id_for_file(item)
        await self._require_project_any_role(
            user_id=current_user.id,
            project_id=project_id,
            roles={RoleName.admin, RoleName.supervisor, RoleName.lead},
        )
        updates = payload.model_dump(exclude_unset=True)
        if updates:
            item = await self.file_repository.update(item, **updates)
            await self.db.commit()
        return FileResponse.model_validate(item)

    async def get_presigned_url(
        self,
        file_id: uuid.UUID,
        current_user: User,
    ) -> PresignedUrlResponse:
        from app.core.exceptions import UnprocessableError
        from app.services.storage import LocalStorage

        item = await self._get_file_or_404(file_id)
        project_id = await self._resolve_project_id_for_file(item)
        await self._require_project_any_role(
            user_id=current_user.id,
            project_id=project_id,
            roles={
                RoleName.admin,
                RoleName.supervisor,
                RoleName.lead,
                RoleName.artist,
                RoleName.worker,
            },
        )

        if isinstance(self.storage, LocalStorage):
            raise UnprocessableError("Presigned URLs are only available with S3 storage backend")

        expires_in = settings.storage_url_expires_default
        url = await self.storage.get_url(item.storage_path, expires=expires_in)
        return PresignedUrlResponse(
            url=url,
            expires_in=expires_in,
            storage_path=item.storage_path,
        )

    async def download_file(
        self,
        file_id: uuid.UUID,
        current_user: User,
    ) -> tuple[FileResponse, BinaryIO | str]:
        item = await self._get_file_or_404(file_id)
        project_id = await self._resolve_project_id_for_file(item)
        await self._require_project_any_role(
            user_id=current_user.id,
            project_id=project_id,
            roles={
                RoleName.admin,
                RoleName.supervisor,
                RoleName.lead,
                RoleName.artist,
                RoleName.worker,
            },
        )

        if isinstance(self.storage, LocalStorage):
            try:
                stream = await self.storage.download(item.storage_path)
            except FileNotFoundError as exc:
                raise NotFoundError("Stored file not found") from exc
            try:
                checksum = hashlib.sha256()
                while True:
                    chunk = stream.read(self.chunk_size_bytes)
                    if not chunk:
                        break
                    checksum.update(chunk)
                if checksum.hexdigest() != item.checksum_sha256:
                    raise ConflictError("Checksum mismatch for stored file")
                stream.seek(0)
            except Exception:
                stream.close()
                raise

            return FileResponse.model_validate(item), stream

        url = await self.storage.get_url(
            item.storage_path,
            expires=settings.storage_url_expires_default,
        )
        return FileResponse.model_validate(item), url

    async def _resolve_parent_context(
        self,
        *,
        shot_id: uuid.UUID | None,
        asset_id: uuid.UUID | None,
    ) -> tuple[
        uuid.UUID,
        str,
        str,
        AssetType | None,
        str | None,
        str | None,
        uuid.UUID | None,
        uuid.UUID | None,
    ]:
        if (shot_id is None and asset_id is None) or (shot_id is not None and asset_id is not None):
            raise UnprocessableError("Provide exactly one of shot_id or asset_id")

        if shot_id is not None:
            shot = await self.shot_repository.get_by_id(shot_id)
            if shot is None:
                raise NotFoundError("Shot not found")
            sequence_code: str | None = None
            episode_code: str | None = None
            if shot.sequence_id is not None:
                sequence = await self.sequence_repository.get_by_id(shot.sequence_id)
                if sequence is not None:
                    sequence_code = sequence.code
                    if sequence.episode_id is not None:
                        episode = await self.episode_repository.get_by_id(sequence.episode_id)
                        if episode is not None:
                            episode_code = episode.code
            return (
                shot.project_id,
                "shot",
                shot.code or shot.name,
                None,
                episode_code,
                sequence_code,
                shot.id,
                None,
            )

        if asset_id is not None:
            asset = await self.asset_repository.get_by_id(asset_id)
            if asset is None:
                raise NotFoundError("Asset not found")
            asset_code = asset.code or self._normalize_asset_code_fallback(asset.name)
            return (
                asset.project_id,
                "asset",
                asset_code,
                asset.asset_type,
                None,
                None,
                None,
                asset.id,
            )

        raise UnprocessableError("Invalid file parent")

    async def _resolve_project_id_for_file(self, file_item: File) -> uuid.UUID:
        shot_id = file_item.shot_id
        asset_id = file_item.asset_id
        if shot_id is not None:
            shot = await self.shot_repository.get_by_id(shot_id, include_archived=True)
            if shot is None:
                raise NotFoundError("Shot not found")
            return shot.project_id

        if asset_id is not None:
            asset = await self.asset_repository.get_by_id(asset_id, include_archived=True)
            if asset is None:
                raise NotFoundError("Asset not found")
            return asset.project_id

        raise NotFoundError("File parent not found")

    @staticmethod
    def _normalize_asset_code_fallback(name: str) -> str:
        base_code = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
        return base_code or "ASSET"

    async def _get_file_or_404(self, file_id: uuid.UUID) -> File:
        item = await self.file_repository.get_by_id(file_id)
        if item is None:
            raise NotFoundError("File not found")
        return item

    async def _require_project_any_role(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        roles: set[RoleName],
    ) -> None:
        if await self.user_role_repository.has_any_role(user_id, roles, project_id):
            return
        raise ForbiddenError("Insufficient permissions")

    async def _require_global_any_role(self, user_id: uuid.UUID, roles: set[RoleName]) -> None:
        if await self.user_role_repository.has_global_any_role(user_id=user_id, role_names=roles):
            return
        raise ForbiddenError("Insufficient permissions")

    @staticmethod
    def _normalize_filename(name: str) -> str:
        base_name = os.path.basename(name.strip())
        if not base_name:
            raise UnprocessableError("Invalid filename")
        return base_name

    def _buffer_stream_for_upload(self, data: BinaryIO) -> tuple[BinaryIO, str, int]:
        max_size = settings.storage_max_upload_size_bytes
        checksum = hashlib.sha256()
        total_size = 0
        buffered_stream = tempfile.SpooledTemporaryFile(  # noqa: SIM115
            mode="w+b", max_size=self.chunk_size_bytes
        )

        with suppress(AttributeError, OSError):
            data.seek(0)

        while True:
            chunk = data.read(self.chunk_size_bytes)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_size:
                buffered_stream.close()
                raise UnprocessableError(f"File exceeds maximum upload size of {max_size} bytes")
            checksum.update(chunk)
            buffered_stream.write(chunk)

        buffered_stream.seek(0)
        return cast("BinaryIO", buffered_stream), checksum.hexdigest(), total_size

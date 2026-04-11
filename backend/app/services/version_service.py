import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, UnprocessableError
from app.models import User
from app.models.pipeline_task import PipelineTaskStatus
from app.models.status_log import StatusLog, StatusLogEntityType
from app.models.version import Version, VersionStatus
from app.repositories.pipeline_task_repository import PipelineTaskRepository
from app.repositories.version_repository import VersionRepository
from app.schemas.version import (
    VersionCreate,
    VersionListResponse,
    VersionResponse,
    VersionStatusUpdate,
    VersionStatusUpdateResponse,
    VersionUpdate,
)

# Valid status transitions
VALID_TRANSITIONS: dict[VersionStatus, set[VersionStatus]] = {
    VersionStatus.pending_review: {VersionStatus.approved, VersionStatus.revision_requested},
    VersionStatus.revision_requested: {VersionStatus.pending_review},
    VersionStatus.approved: {VersionStatus.final},
}


def _generate_version_code(entity_code: str, step_type: str | None, version_number: int) -> str:
    if step_type:
        return f"{entity_code}_{step_type}_v{version_number:03d}"
    return f"{entity_code}_v{version_number:03d}"


class VersionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = VersionRepository(db)
        self.task_repo = PipelineTaskRepository(db)

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_for_task(
        self,
        task_id: uuid.UUID,
        payload: VersionCreate,
        current_user: User,
    ) -> VersionResponse:
        task = await self.task_repo.get_task_by_id(task_id)
        if task is None:
            raise NotFoundError("Pipeline task not found")

        shot_id = task.shot_id
        asset_id = task.asset_id
        step_type = task.step_type.value if task.step_type else None

        entity_code = await self._resolve_entity_code(shot_id, asset_id)
        project_id = await self._resolve_project_id(shot_id, asset_id)

        max_num = await self.repository.get_max_version_number(
            shot_id=shot_id,
            asset_id=asset_id,
            pipeline_task_id=task_id,
        )
        version_number = max_num + 1
        code = _generate_version_code(entity_code, step_type, version_number)

        version = await self.repository.create(
            project_id=project_id,
            shot_id=shot_id,
            asset_id=asset_id,
            pipeline_task_id=task_id,
            code=code,
            version_number=version_number,
            submitted_by=current_user.id,
            description=payload.description,
            thumbnail_url=payload.thumbnail_url,
            media_url=payload.media_url,
        )

        # Associate any provided file_ids
        if payload.file_ids:
            await self._associate_files(version.id, payload.file_ids)

        await self.db.commit()
        await self.db.refresh(version)
        return VersionResponse.model_validate(version)

    # ── Read ─────────────────────────────────────────────────────────────────

    async def get_version(self, version_id: uuid.UUID) -> VersionResponse:
        version = await self.repository.get_by_id(version_id)
        if version is None:
            raise NotFoundError("Version not found")
        return VersionResponse.model_validate(version)

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_version(
        self,
        version_id: uuid.UUID,
        payload: VersionUpdate,
        current_user: User,
    ) -> VersionResponse:
        version = await self.repository.get_by_id(version_id)
        if version is None:
            raise NotFoundError("Version not found")

        update_data: dict[str, object] = {}
        if payload.description is not None:
            update_data["description"] = payload.description
        if payload.thumbnail_url is not None:
            update_data["thumbnail_url"] = payload.thumbnail_url
        if payload.media_url is not None:
            update_data["media_url"] = payload.media_url

        if update_data:
            version = await self.repository.update(version, **update_data)

        await self.db.commit()
        await self.db.refresh(version)
        return VersionResponse.model_validate(version)

    # ── Status transition ─────────────────────────────────────────────────────

    async def update_status(
        self,
        version_id: uuid.UUID,
        payload: VersionStatusUpdate,
        current_user: User,
    ) -> VersionStatusUpdateResponse:
        version = await self.repository.get_by_id(version_id)
        if version is None:
            raise NotFoundError("Version not found")

        old_status = version.status
        new_status = payload.status

        allowed = VALID_TRANSITIONS.get(old_status, set())
        if new_status not in allowed:
            raise UnprocessableError(
                f"Invalid status transition: {old_status.value} -> {new_status.value}"
            )

        version.status = new_status
        if new_status in (VersionStatus.approved, VersionStatus.final):
            version.reviewed_by = current_user.id
        self.db.add(version)
        await self.db.flush()

        # Log transition
        await self._log_transition(
            version.id, old_status, new_status, current_user.id, payload.comment
        )

        # Auto-approve pipeline task when version is approved and is the latest
        if new_status == VersionStatus.approved and version.pipeline_task_id is not None:
            is_latest = await self.repository.is_latest_for_task(version)
            if is_latest:
                await self._auto_approve_task(version, current_user.id)

        await self.db.commit()
        await self.db.refresh(version)

        return VersionStatusUpdateResponse(
            id=version.id,
            old_status=old_status,
            new_status=new_status,
            comment=payload.comment,
            changed_at=datetime.now(timezone.utc),
        )

    # ── Archive ───────────────────────────────────────────────────────────────

    async def archive_version(self, version_id: uuid.UUID, current_user: User) -> VersionResponse:
        version = await self.repository.get_by_id(version_id)
        if version is None:
            raise NotFoundError("Version not found")
        version = await self.repository.archive(version)
        await self.db.commit()
        return VersionResponse.model_validate(version)

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_by_shot(
        self,
        shot_id: uuid.UUID,
        offset: int,
        limit: int,
        status: VersionStatus | None = None,
        pipeline_task_id: uuid.UUID | None = None,
        submitted_by: uuid.UUID | None = None,
    ) -> VersionListResponse:
        rows, total = await self.repository.list_by_shot(
            shot_id=shot_id,
            offset=offset,
            limit=limit,
            status=status,
            pipeline_task_id=pipeline_task_id,
            submitted_by=submitted_by,
        )
        return VersionListResponse(
            items=[VersionResponse.model_validate(v) for v in rows],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def list_by_asset(
        self,
        asset_id: uuid.UUID,
        offset: int,
        limit: int,
        status: VersionStatus | None = None,
        pipeline_task_id: uuid.UUID | None = None,
        submitted_by: uuid.UUID | None = None,
    ) -> VersionListResponse:
        rows, total = await self.repository.list_by_asset(
            asset_id=asset_id,
            offset=offset,
            limit=limit,
            status=status,
            pipeline_task_id=pipeline_task_id,
            submitted_by=submitted_by,
        )
        return VersionListResponse(
            items=[VersionResponse.model_validate(v) for v in rows],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        offset: int,
        limit: int,
        status: VersionStatus | None = None,
        submitted_by: uuid.UUID | None = None,
    ) -> VersionListResponse:
        rows, total = await self.repository.list_by_project(
            project_id=project_id,
            offset=offset,
            limit=limit,
            status=status,
            submitted_by=submitted_by,
        )
        return VersionListResponse(
            items=[VersionResponse.model_validate(v) for v in rows],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def list_by_task(
        self,
        task_id: uuid.UUID,
        offset: int,
        limit: int,
        status: VersionStatus | None = None,
        submitted_by: uuid.UUID | None = None,
    ) -> VersionListResponse:
        rows, total = await self.repository.list_by_task(
            pipeline_task_id=task_id,
            offset=offset,
            limit=limit,
            status=status,
            submitted_by=submitted_by,
        )
        return VersionListResponse(
            items=[VersionResponse.model_validate(v) for v in rows],
            offset=offset,
            limit=limit,
            total=total,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _resolve_entity_code(
        self, shot_id: uuid.UUID | None, asset_id: uuid.UUID | None
    ) -> str:
        from app.models import Asset, Shot

        if shot_id is not None:
            result = await self.db.execute(select(Shot).where(Shot.id == shot_id))
            shot = result.scalar_one_or_none()
            if shot is None:
                raise NotFoundError("Shot not found")
            return shot.code

        if asset_id is not None:
            result = await self.db.execute(select(Asset).where(Asset.id == asset_id))
            asset = result.scalar_one_or_none()
            if asset is None:
                raise NotFoundError("Asset not found")
            return asset.code or asset.name

        raise UnprocessableError("Version must be linked to a shot or asset")

    async def _resolve_project_id(
        self, shot_id: uuid.UUID | None, asset_id: uuid.UUID | None
    ) -> uuid.UUID:
        from app.models import Asset, Shot

        if shot_id is not None:
            result = await self.db.execute(select(Shot).where(Shot.id == shot_id))
            shot = result.scalar_one_or_none()
            if shot is None:
                raise NotFoundError("Shot not found")
            return shot.project_id

        if asset_id is not None:
            result = await self.db.execute(select(Asset).where(Asset.id == asset_id))
            asset = result.scalar_one_or_none()
            if asset is None:
                raise NotFoundError("Asset not found")
            return asset.project_id

        raise UnprocessableError("Version must be linked to a shot or asset")

    async def _associate_files(self, version_id: uuid.UUID, file_ids: list[uuid.UUID]) -> None:
        from sqlalchemy import update

        from app.models import File

        await self.db.execute(
            update(File).where(File.id.in_(file_ids)).values(version_id=version_id)
        )

    async def _log_transition(
        self,
        version_id: uuid.UUID,
        old_status: VersionStatus,
        new_status: VersionStatus,
        changed_by: uuid.UUID,
        comment: str | None,
    ) -> None:
        log = StatusLog(
            entity_type=StatusLogEntityType.version,
            entity_id=version_id,
            old_status=old_status.value,
            new_status=new_status.value,
            changed_by=changed_by,
            comment=comment,
        )
        self.db.add(log)
        await self.db.flush()

    async def _auto_approve_task(self, version: Version, changed_by: uuid.UUID) -> None:
        if version.pipeline_task_id is None:
            return

        task = await self.task_repo.get_task_by_id(version.pipeline_task_id)
        if task is None or task.status == PipelineTaskStatus.approved:
            return

        old_status = task.status
        task.status = PipelineTaskStatus.approved
        self.db.add(task)
        await self.db.flush()

        # Log task transition
        log = StatusLog(
            entity_type=StatusLogEntityType.pipeline_task,
            entity_id=task.id,
            old_status=old_status.value,
            new_status=PipelineTaskStatus.approved.value,
            changed_by=changed_by,
            comment="Auto-approved: version approved",
        )
        self.db.add(log)
        await self.db.flush()

        # Unlock next blocked task
        next_task = await self.task_repo.get_next_blocked_task(
            shot_id=task.shot_id,
            asset_id=task.asset_id,
            current_order=task.order,
        )
        if next_task is not None:
            next_old = next_task.status
            next_task.status = PipelineTaskStatus.pending
            self.db.add(next_task)
            await self.db.flush()
            unlock_log = StatusLog(
                entity_type=StatusLogEntityType.pipeline_task,
                entity_id=next_task.id,
                old_status=next_old.value,
                new_status=PipelineTaskStatus.pending.value,
                changed_by=changed_by,
                comment="Auto-unlocked: previous task approved via version",
            )
            self.db.add(unlock_log)
            await self.db.flush()

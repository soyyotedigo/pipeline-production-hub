import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, AssetStatus, Shot, ShotStatus, StatusLog, StatusLogEntityType
from app.models.pipeline_task import PipelineTaskStatus


class StatusLogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_shot_transition_log(
        self,
        shot_id: uuid.UUID,
        old_status: ShotStatus,
        new_status: ShotStatus,
        changed_by: uuid.UUID,
        comment: str | None,
    ) -> StatusLog:
        status_log = StatusLog(
            entity_type=StatusLogEntityType.shot,
            entity_id=shot_id,
            old_status=old_status.value,
            new_status=new_status.value,
            changed_by=changed_by,
            comment=comment,
        )
        self.db.add(status_log)
        await self.db.flush()
        await self.db.refresh(status_log)
        return status_log

    async def create_asset_transition_log(
        self,
        asset_id: uuid.UUID,
        old_status: AssetStatus,
        new_status: AssetStatus,
        changed_by: uuid.UUID,
        comment: str | None,
    ) -> StatusLog:
        status_log = StatusLog(
            entity_type=StatusLogEntityType.asset,
            entity_id=asset_id,
            old_status=old_status.value,
            new_status=new_status.value,
            changed_by=changed_by,
            comment=comment,
        )
        self.db.add(status_log)
        await self.db.flush()
        await self.db.refresh(status_log)
        return status_log

    async def list_shot_history(
        self,
        shot_id: uuid.UUID,
        offset: int,
        limit: int,
    ) -> tuple[list[StatusLog], int]:
        statement = (
            select(StatusLog)
            .where(
                and_(
                    StatusLog.entity_type == StatusLogEntityType.shot,
                    StatusLog.entity_id == shot_id,
                )
            )
            .order_by(StatusLog.changed_at.desc())
            .offset(offset)
            .limit(limit)
        )
        count_statement = select(func.count(StatusLog.id)).where(
            and_(
                StatusLog.entity_type == StatusLogEntityType.shot,
                StatusLog.entity_id == shot_id,
            )
        )

        result = await self.db.execute(statement)
        rows = list(result.scalars().all())
        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

    async def create_pipeline_task_transition_log(
        self,
        task_id: uuid.UUID,
        old_status: PipelineTaskStatus,
        new_status: PipelineTaskStatus,
        changed_by: uuid.UUID,
        comment: str | None,
    ) -> StatusLog:
        status_log = StatusLog(
            entity_type=StatusLogEntityType.pipeline_task,
            entity_id=task_id,
            old_status=old_status.value,
            new_status=new_status.value,
            changed_by=changed_by,
            comment=comment,
        )
        self.db.add(status_log)
        await self.db.flush()
        await self.db.refresh(status_log)
        return status_log

    async def list_recent_for_project(
        self,
        project_id: uuid.UUID,
        limit: int,
    ) -> list[StatusLog]:
        statement = (
            select(StatusLog)
            .outerjoin(
                Shot,
                and_(
                    StatusLog.entity_type == StatusLogEntityType.shot,
                    StatusLog.entity_id == Shot.id,
                ),
            )
            .outerjoin(
                Asset,
                and_(
                    StatusLog.entity_type == StatusLogEntityType.asset,
                    StatusLog.entity_id == Asset.id,
                ),
            )
            .where(or_(Shot.project_id == project_id, Asset.project_id == project_id))
            .order_by(StatusLog.changed_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(statement)
        return list(result.scalars().all())

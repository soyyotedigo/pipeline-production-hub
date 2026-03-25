import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.time_log import TimeLog


class TimeLogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        date: date,
        duration_minutes: int,
        pipeline_task_id: uuid.UUID | None = None,
        description: str | None = None,
    ) -> TimeLog:
        log = TimeLog(
            project_id=project_id,
            user_id=user_id,
            date=date,
            duration_minutes=duration_minutes,
            pipeline_task_id=pipeline_task_id,
            description=description,
        )
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return log

    async def get_by_id(self, log_id: uuid.UUID) -> TimeLog | None:
        result = await self.db.execute(select(TimeLog).where(TimeLog.id == log_id))
        return result.scalar_one_or_none()

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
        user_id: uuid.UUID | None = None,
        pipeline_task_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TimeLog], int]:
        stmt = select(TimeLog).where(TimeLog.project_id == project_id)
        count_stmt = select(func.count(TimeLog.id)).where(TimeLog.project_id == project_id)
        if date_from:
            stmt = stmt.where(TimeLog.date >= date_from)
            count_stmt = count_stmt.where(TimeLog.date >= date_from)
        if date_to:
            stmt = stmt.where(TimeLog.date <= date_to)
            count_stmt = count_stmt.where(TimeLog.date <= date_to)
        if user_id:
            stmt = stmt.where(TimeLog.user_id == user_id)
            count_stmt = count_stmt.where(TimeLog.user_id == user_id)
        if pipeline_task_id:
            stmt = stmt.where(TimeLog.pipeline_task_id == pipeline_task_id)
            count_stmt = count_stmt.where(TimeLog.pipeline_task_id == pipeline_task_id)
        stmt = stmt.order_by(TimeLog.date.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        total_result = await self.db.execute(count_stmt)
        total = int(total_result.scalar_one())
        return rows, total

    async def list_by_task(
        self, pipeline_task_id: uuid.UUID, offset: int = 0, limit: int = 50
    ) -> tuple[list[TimeLog], int]:
        stmt = select(TimeLog).where(TimeLog.pipeline_task_id == pipeline_task_id)
        count_stmt = select(func.count(TimeLog.id)).where(
            TimeLog.pipeline_task_id == pipeline_task_id
        )
        stmt = stmt.order_by(TimeLog.date.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        total_result = await self.db.execute(count_stmt)
        total = int(total_result.scalar_one())
        return rows, total

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TimeLog], int]:
        stmt = select(TimeLog).where(TimeLog.user_id == user_id)
        count_stmt = select(func.count(TimeLog.id)).where(TimeLog.user_id == user_id)
        if date_from:
            stmt = stmt.where(TimeLog.date >= date_from)
            count_stmt = count_stmt.where(TimeLog.date >= date_from)
        if date_to:
            stmt = stmt.where(TimeLog.date <= date_to)
            count_stmt = count_stmt.where(TimeLog.date <= date_to)
        stmt = stmt.order_by(TimeLog.date.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        total_result = await self.db.execute(count_stmt)
        total = int(total_result.scalar_one())
        return rows, total

    async def get_project_summary(self, project_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
        """Returns [(user_id, total_minutes), ...] for a project."""
        stmt = (
            select(TimeLog.user_id, func.sum(TimeLog.duration_minutes).label("total"))
            .where(TimeLog.project_id == project_id)
            .group_by(TimeLog.user_id)
        )
        result = await self.db.execute(stmt)
        return [(row.user_id, int(row.total)) for row in result.all()]

    async def update(
        self, log: TimeLog, date: date | None, duration_minutes: int | None, description: str | None
    ) -> TimeLog:
        if date is not None:
            log.date = date
        if duration_minutes is not None:
            log.duration_minutes = duration_minutes
        if description is not None:
            log.description = description
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return log

    async def delete(self, log: TimeLog) -> None:
        await self.db.delete(log)
        await self.db.flush()

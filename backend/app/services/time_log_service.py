import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.time_log import TimeLog
from app.repositories.time_log_repository import TimeLogRepository
from app.schemas.time_log import (
    ProjectTimeLogSummary,
    TimeLogCreate,
    TimeLogUpdate,
    UserTimeSummary,
)


class TimeLogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = TimeLogRepository(db)

    async def create(self, data: TimeLogCreate, user_id: uuid.UUID) -> TimeLog:
        log = await self.repository.create(
            project_id=data.project_id,
            user_id=user_id,
            date=data.date,
            duration_minutes=data.duration_minutes,
            pipeline_task_id=data.pipeline_task_id,
            description=data.description,
        )
        await self.db.commit()
        return log

    async def get(self, log_id: uuid.UUID) -> TimeLog:
        log = await self.repository.get_by_id(log_id)
        if not log:
            raise NotFoundError("TimeLog not found")
        return log

    async def update(
        self, log_id: uuid.UUID, data: TimeLogUpdate, user_id: uuid.UUID, is_admin: bool = False
    ) -> TimeLog:
        log = await self.get(log_id)
        if not is_admin and log.user_id != user_id:
            raise ForbiddenError("You can only edit your own timelogs")
        log = await self.repository.update(
            log,
            date=data.date,
            duration_minutes=data.duration_minutes,
            description=data.description,
        )
        await self.db.commit()
        return log

    async def delete(self, log_id: uuid.UUID, user_id: uuid.UUID, is_admin: bool = False) -> None:
        log = await self.get(log_id)
        if not is_admin and log.user_id != user_id:
            raise ForbiddenError("You can only delete your own timelogs")
        await self.repository.delete(log)
        await self.db.commit()

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
        return await self.repository.list_by_project(
            project_id=project_id,
            date_from=date_from,
            date_to=date_to,
            user_id=user_id,
            pipeline_task_id=pipeline_task_id,
            offset=offset,
            limit=limit,
        )

    async def list_by_task(
        self, pipeline_task_id: uuid.UUID, offset: int = 0, limit: int = 50
    ) -> tuple[list[TimeLog], int]:
        return await self.repository.list_by_task(pipeline_task_id, offset=offset, limit=limit)

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TimeLog], int]:
        return await self.repository.list_by_user(
            user_id, date_from=date_from, date_to=date_to, offset=offset, limit=limit
        )

    async def get_project_summary(self, project_id: uuid.UUID) -> ProjectTimeLogSummary:
        rows = await self.repository.get_project_summary(project_id)
        total_minutes = sum(m for _, m in rows)
        total_days = round(total_minutes / 480, 2)
        by_user = [
            UserTimeSummary(user_id=uid, minutes=m, days=round(m / 480, 2)) for uid, m in rows
        ]
        return ProjectTimeLogSummary(
            total_minutes=total_minutes, total_days=total_days, by_user=by_user
        )

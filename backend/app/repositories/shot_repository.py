import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Difficulty, Priority, Shot, ShotStatus


class ShotRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_project_and_code(
        self,
        project_id: uuid.UUID,
        code: str,
        include_archived: bool = False,
    ) -> Shot | None:
        statement = select(Shot).where(Shot.project_id == project_id, Shot.code == code)
        if not include_archived:
            statement = statement.where(Shot.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id(self, shot_id: uuid.UUID, include_archived: bool = False) -> Shot | None:
        statement = select(Shot).where(Shot.id == shot_id)
        if not include_archived:
            statement = statement.where(Shot.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def set_status(self, shot: Shot, status: ShotStatus) -> Shot:
        shot.status = status
        self.db.add(shot)
        await self.db.flush()
        await self.db.refresh(shot)
        return shot

    async def get_last_sort_order_for_sequence(self, sequence_id: uuid.UUID) -> int:
        """Return the highest sort_order of shots in a sequence, or 0 if none exist."""
        statement = (
            select(Shot.sort_order)
            .where(Shot.sequence_id == sequence_id, Shot.sort_order.is_not(None))
            .order_by(desc(Shot.sort_order))
            .limit(1)
        )
        result = await self.db.execute(statement)
        value = result.scalar_one_or_none()
        return int(value) if value is not None else 0

    async def create_for_project(
        self,
        project_id: uuid.UUID,
        sequence_id: uuid.UUID | None,
        name: str,
        code: str,
        frame_start: int | None,
        frame_end: int | None,
        assigned_to: uuid.UUID | None,
        description: str | None = None,
        thumbnail_url: str | None = None,
        priority: Priority = Priority.normal,
        difficulty: Difficulty | None = None,
        handle_head: int | None = None,
        handle_tail: int | None = None,
        cut_in: int | None = None,
        cut_out: int | None = None,
        bid_days: float | None = None,
        sort_order: int | None = None,
    ) -> Shot:
        shot = Shot(
            project_id=project_id,
            sequence_id=sequence_id,
            name=name,
            code=code,
            status=ShotStatus.pending,
            frame_start=frame_start,
            frame_end=frame_end,
            assigned_to=assigned_to,
            description=description,
            thumbnail_url=thumbnail_url,
            priority=priority,
            difficulty=difficulty,
            handle_head=handle_head,
            handle_tail=handle_tail,
            cut_in=cut_in,
            cut_out=cut_out,
            bid_days=bid_days,
            sort_order=sort_order,
        )
        self.db.add(shot)
        await self.db.flush()
        await self.db.refresh(shot)
        return shot

    async def get_by_project_and_id(
        self,
        project_id: uuid.UUID,
        shot_id: uuid.UUID,
        include_archived: bool = False,
    ) -> Shot | None:
        statement = select(Shot).where(Shot.project_id == project_id, Shot.id == shot_id)
        if not include_archived:
            statement = statement.where(Shot.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        offset: int,
        limit: int,
        status: ShotStatus | None,
        assigned_to: uuid.UUID | None,
        include_archived: bool = False,
    ) -> tuple[list[Shot], int]:
        statement = select(Shot).where(Shot.project_id == project_id)
        count_statement = select(func.count(Shot.id)).where(Shot.project_id == project_id)

        if not include_archived:
            statement = statement.where(Shot.archived_at.is_(None))
            count_statement = count_statement.where(Shot.archived_at.is_(None))

        if status is not None:
            statement = statement.where(Shot.status == status)
            count_statement = count_statement.where(Shot.status == status)
        if assigned_to is not None:
            statement = statement.where(Shot.assigned_to == assigned_to)
            count_statement = count_statement.where(Shot.assigned_to == assigned_to)

        statement = statement.order_by(Shot.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())

        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

    async def list_all_for_project(self, project_id: uuid.UUID) -> list[Shot]:
        statement = (
            select(Shot)
            .where(Shot.project_id == project_id, Shot.archived_at.is_(None))
            .order_by(Shot.created_at.asc())
        )
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def archive(self, shot: Shot) -> Shot:
        shot.archived_at = datetime.now(timezone.utc)
        self.db.add(shot)
        await self.db.flush()
        await self.db.refresh(shot)
        return shot

    async def restore(self, shot: Shot) -> Shot:
        shot.archived_at = None
        self.db.add(shot)
        await self.db.flush()
        await self.db.refresh(shot)
        return shot

    async def hard_delete(self, shot: Shot) -> None:
        await self.db.delete(shot)

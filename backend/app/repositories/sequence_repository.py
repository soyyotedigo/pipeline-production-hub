import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Sequence, SequenceScopeType, SequenceStatus


class SequenceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_for_project(
        self,
        project_id: uuid.UUID,
        episode_id: uuid.UUID | None,
        name: str,
        code: str,
        scope_type: SequenceScopeType,
        status: SequenceStatus = SequenceStatus.active,
        description: str | None = None,
        order: int | None = None,
        production_number: int | None = None,
    ) -> Sequence:
        sequence = Sequence(
            project_id=project_id,
            episode_id=episode_id,
            name=name,
            code=code,
            scope_type=scope_type,
            status=status,
            description=description,
            order=order,
            production_number=production_number,
        )
        self.db.add(sequence)
        await self.db.flush()
        await self.db.refresh(sequence)
        return sequence

    async def get_by_id(
        self, sequence_id: uuid.UUID, include_archived: bool = False
    ) -> Sequence | None:
        statement = select(Sequence).where(Sequence.id == sequence_id)
        if not include_archived:
            statement = statement.where(Sequence.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_project_and_code(
        self,
        project_id: uuid.UUID,
        code: str,
        include_archived: bool = False,
    ) -> Sequence | None:
        statement = select(Sequence).where(Sequence.project_id == project_id, Sequence.code == code)
        if not include_archived:
            statement = statement.where(Sequence.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_project_and_id(
        self,
        project_id: uuid.UUID,
        sequence_id: uuid.UUID,
        include_archived: bool = False,
    ) -> Sequence | None:
        statement = select(Sequence).where(
            Sequence.project_id == project_id, Sequence.id == sequence_id
        )
        if not include_archived:
            statement = statement.where(Sequence.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        offset: int,
        limit: int,
        episode_id: uuid.UUID | None,
        include_archived: bool = False,
    ) -> tuple[list[Sequence], int]:
        statement = select(Sequence).where(Sequence.project_id == project_id)
        count_statement = select(func.count(Sequence.id)).where(Sequence.project_id == project_id)

        if not include_archived:
            statement = statement.where(Sequence.archived_at.is_(None))
            count_statement = count_statement.where(Sequence.archived_at.is_(None))

        if episode_id is not None:
            statement = statement.where(Sequence.episode_id == episode_id)
            count_statement = count_statement.where(Sequence.episode_id == episode_id)

        statement = statement.order_by(Sequence.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())

        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

    async def list_all_for_project(self, project_id: uuid.UUID) -> list[Sequence]:
        statement = (
            select(Sequence)
            .where(Sequence.project_id == project_id, Sequence.archived_at.is_(None))
            .order_by(Sequence.created_at.asc())
        )
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def archive(self, sequence: Sequence) -> Sequence:
        sequence.archived_at = datetime.now(timezone.utc)
        self.db.add(sequence)
        await self.db.flush()
        await self.db.refresh(sequence)
        return sequence

    async def restore(self, sequence: Sequence) -> Sequence:
        sequence.archived_at = None
        self.db.add(sequence)
        await self.db.flush()
        await self.db.refresh(sequence)
        return sequence

    async def hard_delete(self, sequence: Sequence) -> None:
        await self.db.delete(sequence)

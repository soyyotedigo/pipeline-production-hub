import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note, NoteEntityType


class NoteRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, note_id: uuid.UUID, include_archived: bool = False) -> Note | None:
        statement = select(Note).where(Note.id == note_id)
        if not include_archived:
            statement = statement.where(Note.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def create(
        self,
        project_id: uuid.UUID,
        entity_type: NoteEntityType,
        entity_id: uuid.UUID,
        author_id: uuid.UUID,
        body: str,
        subject: str | None = None,
        parent_note_id: uuid.UUID | None = None,
        is_client_visible: bool = False,
    ) -> Note:
        note = Note(
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            author_id=author_id,
            subject=subject,
            body=body,
            parent_note_id=parent_note_id,
            is_client_visible=is_client_visible,
        )
        self.db.add(note)
        await self.db.flush()
        await self.db.refresh(note)
        return note

    async def update(self, note: Note, **kwargs: object) -> Note:
        for key, value in kwargs.items():
            if value is not None:
                setattr(note, key, value)
        self.db.add(note)
        await self.db.flush()
        await self.db.refresh(note)
        return note

    async def archive(self, note: Note) -> Note:
        note.archived_at = datetime.now(timezone.utc)
        self.db.add(note)
        await self.db.flush()
        await self.db.refresh(note)
        return note

    async def get_by_entity(
        self,
        entity_type: NoteEntityType,
        entity_id: uuid.UUID,
        offset: int,
        limit: int,
        client_visible_only: bool = False,
        author_id: uuid.UUID | None = None,
    ) -> tuple[list[Note], int]:
        # Only top-level notes
        statement = select(Note).where(
            Note.entity_type == entity_type,
            Note.entity_id == entity_id,
            Note.parent_note_id.is_(None),
            Note.archived_at.is_(None),
        )
        count_statement = select(func.count(Note.id)).where(
            Note.entity_type == entity_type,
            Note.entity_id == entity_id,
            Note.parent_note_id.is_(None),
            Note.archived_at.is_(None),
        )

        if client_visible_only:
            statement = statement.where(Note.is_client_visible.is_(True))
            count_statement = count_statement.where(Note.is_client_visible.is_(True))

        if author_id is not None:
            statement = statement.where(Note.author_id == author_id)
            count_statement = count_statement.where(Note.author_id == author_id)

        statement = statement.order_by(Note.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())

        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

    async def get_replies(self, parent_note_id: uuid.UUID) -> list[Note]:
        statement = (
            select(Note)
            .where(
                Note.parent_note_id == parent_note_id,
                Note.archived_at.is_(None),
            )
            .order_by(Note.created_at.asc())
        )
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def get_by_project(
        self,
        project_id: uuid.UUID,
        offset: int,
        limit: int,
        client_visible_only: bool = False,
        author_id: uuid.UUID | None = None,
    ) -> tuple[list[Note], int]:
        statement = select(Note).where(
            Note.project_id == project_id,
            Note.parent_note_id.is_(None),
            Note.archived_at.is_(None),
        )
        count_statement = select(func.count(Note.id)).where(
            Note.project_id == project_id,
            Note.parent_note_id.is_(None),
            Note.archived_at.is_(None),
        )

        if client_visible_only:
            statement = statement.where(Note.is_client_visible.is_(True))
            count_statement = count_statement.where(Note.is_client_visible.is_(True))

        if author_id is not None:
            statement = statement.where(Note.author_id == author_id)
            count_statement = count_statement.where(Note.author_id == author_id)

        statement = statement.order_by(Note.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())

        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

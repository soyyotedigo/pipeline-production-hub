import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, UnprocessableError
from app.models import Role, RoleName, User, UserRole
from app.models.note import NoteEntityType
from app.repositories.note_repository import NoteRepository
from app.repositories.user_role_repository import UserRoleRepository
from app.schemas.note import (
    NoteCreate,
    NoteListResponse,
    NoteReplyCreate,
    NoteResponse,
    NoteThreadResponse,
    NoteUpdate,
)


class NoteService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = NoteRepository(db)

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _can_modify_note(
        self, note_author_id: uuid.UUID, project_id: uuid.UUID, current_user: User
    ) -> bool:
        """Returns True if the user is the note author or has admin/supervisor role."""
        if current_user.id == note_author_id:
            return True
        role_repo = UserRoleRepository(self.db)
        return await role_repo.has_any_role(
            user_id=current_user.id,
            role_names={RoleName.admin, RoleName.supervisor},
            project_id=project_id,
        )

    async def _is_client(self, user_id: uuid.UUID, project_id: uuid.UUID) -> bool:
        statement = (
            select(UserRole.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                UserRole.user_id == user_id,
                Role.name == RoleName.client,
                UserRole.project_id.in_([project_id, None]),
            )
            .limit(1)
        )
        result = await self.db.execute(statement)
        return result.scalar_one_or_none() is not None

    async def _validate_entity_exists(
        self, entity_type: NoteEntityType, entity_id: uuid.UUID
    ) -> None:
        """Verify the referenced entity actually exists."""
        from typing import Any

        from app.models import Asset, Episode, Project, Sequence, Shot
        from app.models.pipeline_task import PipelineTask

        model_map: dict[NoteEntityType, type[Any]] = {
            NoteEntityType.project: Project,
            NoteEntityType.episode: Episode,
            NoteEntityType.sequence: Sequence,
            NoteEntityType.shot: Shot,
            NoteEntityType.asset: Asset,
            NoteEntityType.pipeline_task: PipelineTask,
        }
        model = model_map.get(entity_type)
        if model is None:
            # version is future — skip validation
            return

        result = await self.db.execute(select(model).where(model.id == entity_id).limit(1))
        if result.scalar_one_or_none() is None:
            raise NotFoundError(f"{entity_type.value} '{entity_id}' not found")

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def create_note(self, payload: NoteCreate, current_user: User) -> NoteResponse:
        await self._validate_entity_exists(payload.entity_type, payload.entity_id)

        note = await self.repository.create(
            project_id=payload.project_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            author_id=current_user.id,
            subject=payload.subject,
            body=payload.body,
            is_client_visible=payload.is_client_visible,
        )
        await self.db.commit()
        await self.db.refresh(note)
        return NoteResponse.model_validate(note)

    async def get_note(self, note_id: uuid.UUID) -> NoteThreadResponse:
        note = await self.repository.get_by_id(note_id)
        if note is None:
            raise NotFoundError("Note not found")

        replies = await self.repository.get_replies(note.id)
        return NoteThreadResponse(
            **NoteResponse.model_validate(note).model_dump(),
            replies=[NoteResponse.model_validate(r) for r in replies],
        )

    async def update_note(
        self, note_id: uuid.UUID, payload: NoteUpdate, current_user: User
    ) -> NoteResponse:
        note = await self.repository.get_by_id(note_id)
        if note is None:
            raise NotFoundError("Note not found")

        if not await self._can_modify_note(note.author_id, note.project_id, current_user):
            raise ForbiddenError("You can only edit your own notes")

        update_data: dict[str, object] = {}
        if payload.subject is not None:
            update_data["subject"] = payload.subject
        if payload.body is not None:
            update_data["body"] = payload.body
        if payload.is_client_visible is not None:
            update_data["is_client_visible"] = payload.is_client_visible

        if update_data:
            note = await self.repository.update(note, **update_data)

        await self.db.commit()
        await self.db.refresh(note)
        return NoteResponse.model_validate(note)

    async def archive_note(self, note_id: uuid.UUID, current_user: User) -> NoteResponse:
        note = await self.repository.get_by_id(note_id)
        if note is None:
            raise NotFoundError("Note not found")

        if not await self._can_modify_note(note.author_id, note.project_id, current_user):
            raise ForbiddenError("You can only archive your own notes")

        note = await self.repository.archive(note)
        await self.db.commit()
        return NoteResponse.model_validate(note)

    async def create_reply(
        self, parent_note_id: uuid.UUID, payload: NoteReplyCreate, current_user: User
    ) -> NoteResponse:
        parent = await self.repository.get_by_id(parent_note_id)
        if parent is None:
            raise NotFoundError("Note not found")

        if parent.parent_note_id is not None:
            raise UnprocessableError(
                "Cannot reply to a reply — only one level of threading allowed"
            )

        note = await self.repository.create(
            project_id=parent.project_id,
            entity_type=parent.entity_type,
            entity_id=parent.entity_id,
            author_id=current_user.id,
            body=payload.body,
            parent_note_id=parent.id,
            is_client_visible=payload.is_client_visible,
        )
        await self.db.commit()
        await self.db.refresh(note)
        return NoteResponse.model_validate(note)

    # ── List by entity ────────────────────────────────────────────────────────

    async def list_by_entity(
        self,
        entity_type: NoteEntityType,
        entity_id: uuid.UUID,
        project_id: uuid.UUID,
        current_user: User,
        offset: int,
        limit: int,
        include_replies: bool = False,
        client_visible_only: bool = False,
        author_id: uuid.UUID | None = None,
    ) -> NoteListResponse:
        # Auto-apply client filter if the current user is a client
        if not client_visible_only:
            is_client = await self._is_client(current_user.id, project_id)
            if is_client:
                client_visible_only = True

        notes, total = await self.repository.get_by_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            offset=offset,
            limit=limit,
            client_visible_only=client_visible_only,
            author_id=author_id,
        )

        items = []
        for note in notes:
            replies: list[NoteResponse] = []
            if include_replies:
                raw_replies = await self.repository.get_replies(note.id)
                replies = [NoteResponse.model_validate(r) for r in raw_replies]
            items.append(
                NoteThreadResponse(
                    **NoteResponse.model_validate(note).model_dump(),
                    replies=replies,
                )
            )

        return NoteListResponse(items=items, offset=offset, limit=limit, total=total)

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        current_user: User,
        offset: int,
        limit: int,
        include_replies: bool = False,
        client_visible_only: bool = False,
        author_id: uuid.UUID | None = None,
    ) -> NoteListResponse:
        if not client_visible_only:
            is_client = await self._is_client(current_user.id, project_id)
            if is_client:
                client_visible_only = True

        notes, total = await self.repository.get_by_project(
            project_id=project_id,
            offset=offset,
            limit=limit,
            client_visible_only=client_visible_only,
            author_id=author_id,
        )

        items = []
        for note in notes:
            replies: list[NoteResponse] = []
            if include_replies:
                raw_replies = await self.repository.get_replies(note.id)
                replies = [NoteResponse.model_validate(r) for r in raw_replies]
            items.append(
                NoteThreadResponse(
                    **NoteResponse.model_validate(note).model_dump(),
                    replies=replies,
                )
            )

        return NoteListResponse(items=items, offset=offset, limit=limit, total=total)

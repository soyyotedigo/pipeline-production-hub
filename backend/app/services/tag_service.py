import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models import RoleName, User
from app.models.tag import Tag, TagEntityType
from app.repositories.tag_repository import TagRepository
from app.repositories.user_role_repository import UserRoleRepository
from app.schemas.tag import EntityTagResponse, TagCreate, TagUpdate

_TAG_MUTATE_ROLES = {RoleName.admin, RoleName.supervisor, RoleName.lead}


class TagService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = TagRepository(db)
        self.role_repository = UserRoleRepository(db)

    async def _require_mutate_permission(
        self, current_user: User, project_id: uuid.UUID | None = None
    ) -> None:
        """Require lead/supervisor/admin to create, update, or delete tags."""
        if project_id is not None:
            allowed = await self.role_repository.has_any_role(
                current_user.id, _TAG_MUTATE_ROLES, project_id
            )
        else:
            allowed = await self.role_repository.has_any_role_in_any_scope(
                current_user.id, _TAG_MUTATE_ROLES
            )
        if not allowed:
            raise ForbiddenError("Insufficient permissions to manage tags")

    async def create_tag(self, data: TagCreate, current_user: User | None = None) -> Tag:
        if current_user is not None:
            await self._require_mutate_permission(current_user, data.project_id)
        existing = await self.repository.get_by_name_and_project(data.name, data.project_id)
        if existing:
            raise ConflictError(f"Tag '{data.name}' already exists in this scope")
        tag = await self.repository.create(
            name=data.name, project_id=data.project_id, color=data.color
        )
        await self.db.commit()
        return tag

    async def get_tag(self, tag_id: uuid.UUID) -> Tag:
        tag = await self.repository.get_by_id(tag_id)
        if not tag:
            raise NotFoundError("Tag not found")
        return tag

    async def list_tags(self, project_id: uuid.UUID | None = None) -> list[Tag]:
        return await self.repository.list_tags(project_id=project_id)

    async def search_tags(self, q: str, project_id: uuid.UUID | None = None) -> list[Tag]:
        return await self.repository.search(q=q, project_id=project_id)

    async def update_tag(
        self, tag_id: uuid.UUID, data: TagUpdate, current_user: User | None = None
    ) -> Tag:
        tag = await self.get_tag(tag_id)
        if current_user is not None:
            await self._require_mutate_permission(current_user, tag.project_id)
        tag = await self.repository.update(tag, name=data.name, color=data.color)
        await self.db.commit()
        return tag

    async def delete_tag(self, tag_id: uuid.UUID, current_user: User | None = None) -> None:
        tag = await self.get_tag(tag_id)
        if current_user is not None:
            await self._require_mutate_permission(current_user, tag.project_id)
        await self.repository.delete(tag)
        await self.db.commit()

    async def attach_tag(
        self, entity_type: TagEntityType, entity_id: uuid.UUID, tag_id: uuid.UUID
    ) -> EntityTagResponse:
        tag = await self.repository.get_by_id(tag_id)
        if not tag:
            raise NotFoundError("Tag not found")
        existing = await self.repository.get_entity_tag(tag_id, entity_type, entity_id)
        if existing:
            raise ConflictError("Tag already attached to this entity")
        entity_tag = await self.repository.attach(
            tag_id=tag_id, entity_type=entity_type, entity_id=entity_id
        )
        await self.db.commit()
        return EntityTagResponse.model_validate(entity_tag)

    async def detach_tag(
        self, entity_type: TagEntityType, entity_id: uuid.UUID, tag_id: uuid.UUID
    ) -> None:
        entity_tag = await self.repository.get_entity_tag(tag_id, entity_type, entity_id)
        if not entity_tag:
            raise NotFoundError("Tag not attached to this entity")
        await self.repository.detach(entity_tag)
        await self.db.commit()

    async def detach_entity_tag(self, entity_tag_id: uuid.UUID) -> None:
        entity_tag = await self.repository.get_entity_tag_by_id(entity_tag_id)
        if not entity_tag:
            raise NotFoundError("Entity tag not found")
        await self.repository.detach(entity_tag)
        await self.db.commit()

    async def list_entity_tags(self, entity_type: TagEntityType, entity_id: uuid.UUID) -> list[Tag]:
        return await self.repository.list_entity_tags(entity_type, entity_id)

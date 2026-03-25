import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import EntityTag, Tag, TagEntityType


class TagRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, name: str, project_id: uuid.UUID | None, color: str | None) -> Tag:
        tag = Tag(name=name, project_id=project_id, color=color)
        self.db.add(tag)
        await self.db.flush()
        await self.db.refresh(tag)
        return tag

    async def get_by_id(self, tag_id: uuid.UUID) -> Tag | None:
        result = await self.db.execute(select(Tag).where(Tag.id == tag_id))
        return result.scalar_one_or_none()

    async def get_by_name_and_project(self, name: str, project_id: uuid.UUID | None) -> Tag | None:
        stmt = select(Tag).where(Tag.name == name, Tag.project_id == project_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_tags(self, project_id: uuid.UUID | None = None) -> list[Tag]:
        stmt = select(Tag)
        if project_id is not None:
            stmt = stmt.where((Tag.project_id == project_id) | Tag.project_id.is_(None))
        stmt = stmt.order_by(Tag.name)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def search(
        self, q: str, project_id: uuid.UUID | None = None, limit: int = 20
    ) -> list[Tag]:
        stmt = select(Tag).where(Tag.name.ilike(f"{q}%"))
        if project_id is not None:
            stmt = stmt.where((Tag.project_id == project_id) | Tag.project_id.is_(None))
        stmt = stmt.order_by(Tag.name).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(self, tag: Tag, name: str | None, color: str | None) -> Tag:
        if name is not None:
            tag.name = name
        if color is not None:
            tag.color = color
        self.db.add(tag)
        await self.db.flush()
        await self.db.refresh(tag)
        return tag

    async def delete(self, tag: Tag) -> None:
        await self.db.delete(tag)
        await self.db.flush()

    async def attach(
        self, tag_id: uuid.UUID, entity_type: TagEntityType, entity_id: uuid.UUID
    ) -> EntityTag:
        entity_tag = EntityTag(tag_id=tag_id, entity_type=entity_type, entity_id=entity_id)
        self.db.add(entity_tag)
        await self.db.flush()
        await self.db.refresh(entity_tag)
        return entity_tag

    async def get_entity_tag(
        self, tag_id: uuid.UUID, entity_type: TagEntityType, entity_id: uuid.UUID
    ) -> EntityTag | None:
        stmt = select(EntityTag).where(
            EntityTag.tag_id == tag_id,
            EntityTag.entity_type == entity_type,
            EntityTag.entity_id == entity_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_entity_tag_by_id(self, entity_tag_id: uuid.UUID) -> EntityTag | None:
        result = await self.db.execute(select(EntityTag).where(EntityTag.id == entity_tag_id))
        return result.scalar_one_or_none()

    async def detach(self, entity_tag: EntityTag) -> None:
        await self.db.delete(entity_tag)
        await self.db.flush()

    async def list_entity_tags(self, entity_type: TagEntityType, entity_id: uuid.UUID) -> list[Tag]:
        stmt = (
            select(Tag)
            .join(EntityTag, EntityTag.tag_id == Tag.id)
            .where(EntityTag.entity_type == entity_type, EntityTag.entity_id == entity_id)
            .order_by(Tag.name)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

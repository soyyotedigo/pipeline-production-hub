import uuid
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationEntityType, NotificationEventType


class NotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        user_id: uuid.UUID,
        event_type: NotificationEventType,
        entity_type: NotificationEntityType,
        entity_id: uuid.UUID,
        title: str,
        project_id: uuid.UUID | None = None,
        body: str | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            project_id=project_id,
            title=title,
            body=body,
        )
        self.db.add(notification)
        await self.db.flush()
        await self.db.refresh(notification)
        return notification

    async def get_by_id(self, notification_id: uuid.UUID) -> Notification | None:
        result = await self.db.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        offset: int,
        limit: int,
        is_read: bool | None = None,
        event_type: NotificationEventType | None = None,
        project_id: uuid.UUID | None = None,
    ) -> tuple[list[Notification], int]:
        statement = select(Notification).where(Notification.user_id == user_id)
        count_statement = select(func.count(Notification.id)).where(Notification.user_id == user_id)

        if is_read is not None:
            statement = statement.where(Notification.is_read == is_read)
            count_statement = count_statement.where(Notification.is_read == is_read)

        if event_type is not None:
            statement = statement.where(Notification.event_type == event_type)
            count_statement = count_statement.where(Notification.event_type == event_type)

        if project_id is not None:
            statement = statement.where(Notification.project_id == project_id)
            count_statement = count_statement.where(Notification.project_id == project_id)

        statement = statement.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())

        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

    async def get_unread_count(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )
        return int(result.scalar_one())

    async def mark_read(self, notification: Notification) -> Notification:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        self.db.add(notification)
        await self.db.flush()
        await self.db.refresh(notification)
        return notification

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
        update_result = cast("CursorResult[object]", result)
        return int(update_result.rowcount)

    async def delete(self, notification: Notification) -> None:
        await self.db.delete(notification)
        await self.db.flush()

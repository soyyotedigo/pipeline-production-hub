import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.notification import Notification, NotificationEntityType, NotificationEventType
from app.repositories.notification_repository import NotificationRepository
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)


class NotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = NotificationRepository(db)

    async def create(
        self,
        user_id: uuid.UUID,
        event_type: NotificationEventType,
        entity_type: NotificationEntityType,
        entity_id: uuid.UUID,
        title: str,
        project_id: uuid.UUID | None = None,
        body: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> Notification:
        # No self-notification
        if actor_id is not None and actor_id == user_id:
            return None  # type: ignore[return-value]

        return await self.repository.create(
            user_id=user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            title=title,
            project_id=project_id,
            body=body,
        )

    async def get_notifications(
        self,
        user_id: uuid.UUID,
        offset: int,
        limit: int,
        is_read: bool | None = None,
        event_type: NotificationEventType | None = None,
        project_id: uuid.UUID | None = None,
    ) -> NotificationListResponse:
        notifications, total = await self.repository.list_by_user(
            user_id=user_id,
            offset=offset,
            limit=limit,
            is_read=is_read,
            event_type=event_type,
            project_id=project_id,
        )
        return NotificationListResponse(
            items=[NotificationResponse.model_validate(n) for n in notifications],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def get_unread_count(self, user_id: uuid.UUID) -> UnreadCountResponse:
        count = await self.repository.get_unread_count(user_id)
        return UnreadCountResponse(count=count)

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> None:
        notification = await self.repository.get_by_id(notification_id)
        if notification is None or notification.user_id != user_id:
            raise NotFoundError("Notification not found")
        await self.repository.mark_read(notification)
        await self.db.commit()

    async def mark_all_read(self, user_id: uuid.UUID) -> None:
        await self.repository.mark_all_read(user_id)
        await self.db.commit()

    async def delete(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> None:
        notification = await self.repository.get_by_id(notification_id)
        if notification is None or notification.user_id != user_id:
            raise NotFoundError("Notification not found")
        await self.repository.delete(notification)
        await self.db.commit()

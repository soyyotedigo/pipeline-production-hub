import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.notification import NotificationEventType
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.services.notification_service import NotificationService

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List Notifications",
    description="List notifications for the current user with optional filters.",
)
async def list_notifications(
    current_user: CurrentUserDep,
    db: DbDep,
    is_read: bool | None = Query(default=None),
    event_type: NotificationEventType | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> NotificationListResponse:
    service = NotificationService(db)
    return await service.get_notifications(
        user_id=current_user.id,
        offset=offset,
        limit=limit,
        is_read=is_read,
        event_type=event_type,
        project_id=project_id,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Get Unread Count",
    description="Get the number of unread notifications for the current user.",
)
async def get_unread_count(
    current_user: CurrentUserDep,
    db: DbDep,
) -> UnreadCountResponse:
    service = NotificationService(db)
    return await service.get_unread_count(user_id=current_user.id)


@router.patch(
    "/{id}/read",
    response_model=NotificationResponse,
    summary="Mark Notification Read",
    description="Mark a single notification as read.",
)
async def mark_read(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> NotificationResponse:
    service = NotificationService(db)
    await service.mark_read(notification_id=id, user_id=current_user.id)
    # Fetch and return the updated notification
    from app.repositories.notification_repository import NotificationRepository

    repo = NotificationRepository(db)
    notification = await repo.get_by_id(id)
    return NotificationResponse.model_validate(notification)


@router.post(
    "/read-all",
    status_code=204,
    summary="Mark All Notifications Read",
    description="Mark all notifications as read for the current user.",
)
async def mark_all_read(
    current_user: CurrentUserDep,
    db: DbDep,
) -> Response:
    service = NotificationService(db)
    await service.mark_all_read(user_id=current_user.id)
    return Response(status_code=204)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Delete Notification",
    description="Delete a notification.",
)
async def delete_notification(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> Response:
    service = NotificationService(db)
    await service.delete(notification_id=id, user_id=current_user.id)
    return Response(status_code=204)

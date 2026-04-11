import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.webhook import (
    WebhookCreateRequest,
    WebhookCreateResponse,
    WebhookListResponse,
    WebhookProjectCreateRequest,
    WebhookResponse,
    WebhookUpdateRequest,
)
from app.services.webhook_service import WebhookService

router = APIRouter()
projects_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post(
    "",
    response_model=WebhookCreateResponse,
    summary="Create Webhook",
    description="Register a project webhook subscription for selected event types.",
)
async def create_webhook(
    payload: WebhookCreateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> WebhookCreateResponse:
    service = WebhookService(db)
    return await service.create_webhook(payload=payload, current_user=current_user)


@router.get(
    "",
    response_model=WebhookListResponse,
    summary="List Webhooks",
    description="List webhook subscriptions with optional project filter and pagination.",
)
async def list_webhooks(
    current_user: CurrentUserDep,
    db: DbDep,
    project_id: uuid.UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> WebhookListResponse:
    service = WebhookService(db)
    return await service.list_webhooks(
        project_id=project_id,
        offset=offset,
        limit=limit,
        current_user=current_user,
    )


@router.patch(
    "/{id}",
    response_model=WebhookResponse,
    summary="Patch Webhook",
    description="Patch webhook URL or subscribed events.",
)
async def patch_webhook(
    id: uuid.UUID,
    payload: WebhookUpdateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> WebhookResponse:
    service = WebhookService(db)
    return await service.patch_webhook(webhook_id=id, payload=payload, current_user=current_user)


@router.post(
    "/{id}/archive",
    response_model=WebhookResponse,
    summary="Archive Webhook",
    description="Disable an active webhook subscription.",
)
async def archive_webhook(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> WebhookResponse:
    service = WebhookService(db)
    return await service.archive_webhook(webhook_id=id, current_user=current_user)


@router.post(
    "/{id}/restore",
    response_model=WebhookResponse,
    summary="Restore Webhook",
    description="Re-enable an archived webhook subscription.",
)
async def restore_webhook(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> WebhookResponse:
    service = WebhookService(db)
    return await service.restore_webhook(webhook_id=id, current_user=current_user)


@projects_router.get(
    "/{id}/webhooks",
    response_model=WebhookListResponse,
    summary="List Project Webhooks",
    description="List webhook subscriptions for a specific project.",
)
async def list_project_webhooks(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> WebhookListResponse:
    service = WebhookService(db)
    return await service.list_webhooks(
        project_id=id,
        offset=offset,
        limit=limit,
        current_user=current_user,
    )


@projects_router.post(
    "/{id}/webhooks",
    response_model=WebhookCreateResponse,
    status_code=201,
    summary="Create Project Webhook",
    description="Register a webhook subscription for a project without needing project_id in body.",
)
async def create_project_webhook(
    id: uuid.UUID,
    payload: WebhookProjectCreateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> WebhookCreateResponse:
    service = WebhookService(db)
    full_payload = WebhookCreateRequest(project_id=id, url=payload.url, events=payload.events)
    return await service.create_webhook(payload=full_payload, current_user=current_user)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Delete Webhook",
    description="Hard delete a webhook (admin only) with force=true.",
)
async def delete_webhook(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    force: bool = Query(default=False),
) -> None:
    service = WebhookService(db)
    await service.delete_webhook(webhook_id=id, current_user=current_user, force=force)

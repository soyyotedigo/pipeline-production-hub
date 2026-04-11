from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, UnprocessableError
from app.models import RoleName, User
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_role_repository import UserRoleRepository
from app.repositories.webhook_repository import WebhookRepository
from app.schemas.task import TaskType
from app.schemas.webhook import (
    WebhookCreateRequest,
    WebhookCreateResponse,
    WebhookEventType,
    WebhookListResponse,
    WebhookResponse,
    WebhookUpdateRequest,
)
from app.services.task_service import TaskService


class WebhookService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.project_repository = ProjectRepository(db)
        self.user_role_repository = UserRoleRepository(db)
        self.webhook_repository = WebhookRepository(db)
        self.task_service = TaskService()

    async def create_webhook(
        self,
        payload: WebhookCreateRequest,
        current_user: User,
    ) -> WebhookCreateResponse:
        await self._require_global_any_role(current_user.id, {RoleName.admin, RoleName.supervisor})

        project = await self.project_repository.get_by_id(payload.project_id)
        if project is None:
            raise NotFoundError("Project not found")

        signing_secret = secrets.token_hex(32)
        webhook = await self.webhook_repository.create(
            project_id=payload.project_id,
            url=str(payload.url),
            events=[item.value for item in payload.events],
            secret=signing_secret,
            created_by=current_user.id,
        )
        await self.db.commit()

        return WebhookCreateResponse(
            **WebhookResponse.model_validate(webhook).model_dump(),
            signing_secret=signing_secret,
        )

    async def list_webhooks(
        self,
        *,
        project_id: uuid.UUID | None,
        offset: int,
        limit: int,
        current_user: User,
    ) -> WebhookListResponse:
        await self._require_global_any_role(current_user.id, {RoleName.admin, RoleName.supervisor})

        if project_id is not None:
            project = await self.project_repository.get_by_id(project_id)
            if project is None:
                raise NotFoundError("Project not found")

        rows, total = await self.webhook_repository.list_webhooks(
            project_id=project_id,
            offset=offset,
            limit=limit,
        )
        return WebhookListResponse(
            items=[WebhookResponse.model_validate(item) for item in rows],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def patch_webhook(
        self,
        webhook_id: uuid.UUID,
        payload: WebhookUpdateRequest,
        current_user: User,
    ) -> WebhookResponse:
        await self._require_global_any_role(current_user.id, {RoleName.admin, RoleName.supervisor})
        webhook = await self.webhook_repository.get_by_id(webhook_id, include_inactive=True)
        if webhook is None:
            raise NotFoundError("Webhook not found")

        if payload.url is not None:
            webhook.url = str(payload.url)
        if payload.events is not None:
            webhook.events = [event.value for event in payload.events]

        self.db.add(webhook)
        await self.db.commit()
        await self.db.refresh(webhook)
        return WebhookResponse.model_validate(webhook)

    async def archive_webhook(self, webhook_id: uuid.UUID, current_user: User) -> WebhookResponse:
        await self._require_global_any_role(current_user.id, {RoleName.admin, RoleName.supervisor})
        webhook = await self.webhook_repository.get_by_id(webhook_id, include_inactive=True)
        if webhook is None:
            raise NotFoundError("Webhook not found")

        webhook = await self.webhook_repository.archive(webhook)
        await self.db.commit()
        return WebhookResponse.model_validate(webhook)

    async def restore_webhook(self, webhook_id: uuid.UUID, current_user: User) -> WebhookResponse:
        await self._require_global_any_role(current_user.id, {RoleName.admin, RoleName.supervisor})
        webhook = await self.webhook_repository.get_by_id(webhook_id, include_inactive=True)
        if webhook is None:
            raise NotFoundError("Webhook not found")

        webhook = await self.webhook_repository.restore(webhook)
        await self.db.commit()
        return WebhookResponse.model_validate(webhook)

    async def delete_webhook(self, webhook_id: uuid.UUID, current_user: User, force: bool) -> None:
        if not force:
            raise UnprocessableError("Hard delete requires force=true")
        await self._require_global_any_role(current_user.id, {RoleName.admin})
        webhook = await self.webhook_repository.get_by_id(webhook_id, include_inactive=True)
        if webhook is None:
            raise NotFoundError("Webhook not found")

        await self.webhook_repository.hard_delete(webhook)
        await self.db.commit()

    async def enqueue_event(
        self,
        *,
        event_type: WebhookEventType,
        project_id: uuid.UUID,
        entity_data: dict[str, Any],
        triggered_by: uuid.UUID,
    ) -> list[uuid.UUID]:
        webhooks = await self.webhook_repository.list_active_for_project(project_id)
        task_ids: list[uuid.UUID] = []
        now = datetime.now(timezone.utc).isoformat()

        for webhook in webhooks:
            if event_type.value not in webhook.events:
                continue

            body = {
                "event": event_type.value,
                "entity": entity_data,
                "timestamp": now,
            }
            body_json = json.dumps(body, separators=(",", ":"), sort_keys=True)
            signature = self.sign_payload(webhook.secret, body_json)
            task_id = await self.task_service.enqueue_task(
                task_type=TaskType.webhook_dispatch,
                created_by=triggered_by,
                payload={
                    "webhook_id": str(webhook.id),
                    "url": webhook.url,
                    "secret": webhook.secret,
                    "event": event_type.value,
                    "body": body,
                    "signature": signature,
                },
            )
            task_ids.append(task_id)

        return task_ids

    @staticmethod
    def sign_payload(secret: str, body_json: str) -> str:
        return hmac.new(
            secret.encode("utf-8"),
            body_json.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def _require_global_any_role(self, user_id: uuid.UUID, roles: set[RoleName]) -> None:
        has_any = await self.user_role_repository.has_global_any_role(
            user_id=user_id, role_names=roles
        )
        if has_any:
            return
        raise ForbiddenError("Insufficient permissions")

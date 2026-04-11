import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Webhook


class WebhookRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        project_id: uuid.UUID,
        url: str,
        events: list[str],
        secret: str,
        created_by: uuid.UUID,
    ) -> Webhook:
        webhook = Webhook(
            project_id=project_id,
            url=url,
            events=events,
            secret=secret,
            created_by=created_by,
            is_active=True,
        )
        self.db.add(webhook)
        await self.db.flush()
        await self.db.refresh(webhook)
        return webhook

    async def list_webhooks(
        self,
        *,
        project_id: uuid.UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Webhook], int]:
        statement = select(Webhook).where(Webhook.is_active.is_(True))
        count_statement = select(func.count(Webhook.id)).where(Webhook.is_active.is_(True))

        if project_id is not None:
            statement = statement.where(Webhook.project_id == project_id)
            count_statement = count_statement.where(Webhook.project_id == project_id)

        statement = statement.order_by(Webhook.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())

        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

    async def list_active_for_project(self, project_id: uuid.UUID) -> list[Webhook]:
        statement = (
            select(Webhook)
            .where(
                Webhook.project_id == project_id,
                Webhook.is_active.is_(True),
            )
            .order_by(Webhook.created_at.desc())
        )
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def get_by_id(
        self, webhook_id: uuid.UUID, include_inactive: bool = False
    ) -> Webhook | None:
        statement = select(Webhook).where(Webhook.id == webhook_id)
        if not include_inactive:
            statement = statement.where(Webhook.is_active.is_(True))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def archive(self, webhook: Webhook) -> Webhook:
        webhook.is_active = False
        self.db.add(webhook)
        await self.db.flush()
        await self.db.refresh(webhook)
        return webhook

    async def restore(self, webhook: Webhook) -> Webhook:
        webhook.is_active = True
        self.db.add(webhook)
        await self.db.flush()
        await self.db.refresh(webhook)
        return webhook

    async def hard_delete(self, webhook: Webhook) -> None:
        await self.db.delete(webhook)

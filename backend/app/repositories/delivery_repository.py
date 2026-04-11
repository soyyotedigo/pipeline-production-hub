import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery import Delivery, DeliveryItem, DeliveryStatus


class DeliveryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        project_id: uuid.UUID,
        name: str,
        created_by: uuid.UUID,
        delivery_date: date | None = None,
        recipient: str | None = None,
        notes: str | None = None,
    ) -> Delivery:
        delivery = Delivery(
            project_id=project_id,
            name=name,
            created_by=created_by,
            delivery_date=delivery_date,
            recipient=recipient,
            notes=notes,
        )
        self.db.add(delivery)
        await self.db.flush()
        await self.db.refresh(delivery)
        return delivery

    async def get_by_id(self, delivery_id: uuid.UUID) -> Delivery | None:
        result = await self.db.execute(select(Delivery).where(Delivery.id == delivery_id))
        return result.scalar_one_or_none()

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        status: DeliveryStatus | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        recipient: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Delivery], int]:
        stmt = select(Delivery).where(Delivery.project_id == project_id)
        count_stmt = select(func.count(Delivery.id)).where(Delivery.project_id == project_id)
        if status:
            stmt = stmt.where(Delivery.status == status)
            count_stmt = count_stmt.where(Delivery.status == status)
        if date_from:
            stmt = stmt.where(Delivery.delivery_date >= date_from)
            count_stmt = count_stmt.where(Delivery.delivery_date >= date_from)
        if date_to:
            stmt = stmt.where(Delivery.delivery_date <= date_to)
            count_stmt = count_stmt.where(Delivery.delivery_date <= date_to)
        if recipient:
            stmt = stmt.where(Delivery.recipient.ilike(f"%{recipient}%"))
            count_stmt = count_stmt.where(Delivery.recipient.ilike(f"%{recipient}%"))
        stmt = stmt.order_by(Delivery.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        total_result = await self.db.execute(count_stmt)
        total = int(total_result.scalar_one())
        return rows, total

    async def update(
        self,
        delivery: Delivery,
        name: str | None,
        delivery_date: date | None,
        recipient: str | None,
        notes: str | None,
    ) -> Delivery:
        if name is not None:
            delivery.name = name
        if delivery_date is not None:
            delivery.delivery_date = delivery_date
        if recipient is not None:
            delivery.recipient = recipient
        if notes is not None:
            delivery.notes = notes
        self.db.add(delivery)
        await self.db.flush()
        await self.db.refresh(delivery)
        return delivery

    async def update_status(self, delivery: Delivery, status: DeliveryStatus) -> Delivery:
        delivery.status = status
        self.db.add(delivery)
        await self.db.flush()
        await self.db.refresh(delivery)
        return delivery

    async def delete(self, delivery: Delivery) -> None:
        await self.db.delete(delivery)
        await self.db.flush()

    # Items
    async def add_item(
        self,
        delivery_id: uuid.UUID,
        version_id: uuid.UUID,
        shot_id: uuid.UUID | None,
        notes: str | None = None,
    ) -> DeliveryItem:
        item = DeliveryItem(
            delivery_id=delivery_id,
            version_id=version_id,
            shot_id=shot_id,
            notes=notes,
        )
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def get_item(self, item_id: uuid.UUID) -> DeliveryItem | None:
        result = await self.db.execute(select(DeliveryItem).where(DeliveryItem.id == item_id))
        return result.scalar_one_or_none()

    async def get_item_by_version(
        self, delivery_id: uuid.UUID, version_id: uuid.UUID
    ) -> DeliveryItem | None:
        result = await self.db.execute(
            select(DeliveryItem).where(
                DeliveryItem.delivery_id == delivery_id, DeliveryItem.version_id == version_id
            )
        )
        return result.scalar_one_or_none()

    async def list_items(self, delivery_id: uuid.UUID) -> list[DeliveryItem]:
        result = await self.db.execute(
            select(DeliveryItem)
            .where(DeliveryItem.delivery_id == delivery_id)
            .order_by(DeliveryItem.created_at)
        )
        return list(result.scalars().all())

    async def delete_item(self, item: DeliveryItem) -> None:
        await self.db.delete(item)
        await self.db.flush()

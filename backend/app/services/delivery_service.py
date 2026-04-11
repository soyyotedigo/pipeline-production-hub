import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.delivery import Delivery, DeliveryItem, DeliveryStatus
from app.repositories.delivery_repository import DeliveryRepository
from app.schemas.delivery import (
    DeliveryCreate,
    DeliveryItemCreate,
    DeliveryUpdate,
)

# Valid status transitions
VALID_TRANSITIONS = {
    DeliveryStatus.preparing: {DeliveryStatus.sent},
    DeliveryStatus.sent: {DeliveryStatus.acknowledged},
    DeliveryStatus.acknowledged: {DeliveryStatus.accepted, DeliveryStatus.rejected},
    DeliveryStatus.rejected: {DeliveryStatus.preparing},
    DeliveryStatus.accepted: set(),
}

# Statuses that lock items
LOCKED_STATUSES = {DeliveryStatus.sent, DeliveryStatus.acknowledged, DeliveryStatus.accepted}


class DeliveryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = DeliveryRepository(db)

    async def create(
        self, project_id: uuid.UUID, data: DeliveryCreate, created_by: uuid.UUID
    ) -> Delivery:
        delivery = await self.repository.create(
            project_id=project_id,
            name=data.name,
            created_by=created_by,
            delivery_date=data.delivery_date,
            recipient=data.recipient,
            notes=data.notes,
        )
        await self.db.commit()
        return delivery

    async def get(self, delivery_id: uuid.UUID) -> Delivery:
        delivery = await self.repository.get_by_id(delivery_id)
        if not delivery:
            raise NotFoundError("Delivery not found")
        return delivery

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
        return await self.repository.list_by_project(
            project_id=project_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
            recipient=recipient,
            offset=offset,
            limit=limit,
        )

    async def update(self, delivery_id: uuid.UUID, data: DeliveryUpdate) -> Delivery:
        delivery = await self.get(delivery_id)
        delivery = await self.repository.update(
            delivery,
            name=data.name,
            delivery_date=data.delivery_date,
            recipient=data.recipient,
            notes=data.notes,
        )
        await self.db.commit()
        return delivery

    async def update_status(self, delivery_id: uuid.UUID, new_status: DeliveryStatus) -> Delivery:
        delivery = await self.get(delivery_id)
        allowed = VALID_TRANSITIONS.get(delivery.status, set())
        if new_status not in allowed:
            raise ForbiddenError(
                f"Cannot transition from {delivery.status.value} to {new_status.value}"
            )
        delivery = await self.repository.update_status(delivery, new_status)
        await self.db.commit()
        return delivery

    async def delete(self, delivery_id: uuid.UUID) -> None:
        delivery = await self.get(delivery_id)
        if delivery.status != DeliveryStatus.preparing:
            raise ForbiddenError("Can only delete deliveries in 'preparing' status")
        await self.repository.delete(delivery)
        await self.db.commit()

    async def add_item(self, delivery_id: uuid.UUID, data: DeliveryItemCreate) -> DeliveryItem:
        delivery = await self.get(delivery_id)
        if delivery.status in LOCKED_STATUSES:
            raise ForbiddenError("Cannot add items to a locked delivery")

        # Get version to auto-populate shot_id
        from app.repositories.version_repository import VersionRepository

        version_repo = VersionRepository(self.db)
        version = await version_repo.get_by_id(data.version_id)
        if not version:
            raise NotFoundError("Version not found")
        if version.project_id != delivery.project_id:
            raise ForbiddenError("Version does not belong to this project")

        existing = await self.repository.get_item_by_version(delivery_id, data.version_id)
        if existing:
            raise ConflictError("Version already in this delivery")

        item = await self.repository.add_item(
            delivery_id=delivery_id,
            version_id=data.version_id,
            shot_id=version.shot_id,
            notes=data.notes,
        )
        await self.db.commit()
        return item

    async def list_items(self, delivery_id: uuid.UUID) -> list[DeliveryItem]:
        await self.get(delivery_id)  # Ensure delivery exists
        return await self.repository.list_items(delivery_id)

    async def remove_item(self, item_id: uuid.UUID) -> None:
        item = await self.repository.get_item(item_id)
        if not item:
            raise NotFoundError("Delivery item not found")
        delivery = await self.get(item.delivery_id)
        if delivery.status in LOCKED_STATUSES:
            raise ForbiddenError("Cannot remove items from a locked delivery")
        await self.repository.delete_item(item)
        await self.db.commit()

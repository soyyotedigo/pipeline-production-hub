import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.models.delivery import DeliveryStatus
from app.schemas.delivery import (
    DeliveryCreate,
    DeliveryItemCreate,
    DeliveryItemResponse,
    DeliveryResponse,
    DeliveryStatusUpdate,
    DeliveryUpdate,
)
from app.services.delivery_service import DeliveryService

router = APIRouter()
projects_router = APIRouter()
delivery_items_router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@projects_router.post(
    "/{id}/deliveries",
    response_model=DeliveryResponse,
    status_code=201,
    summary="Create Delivery",
    description="Create a new delivery package under the given project.",
)
async def create_delivery(
    id: uuid.UUID, data: DeliveryCreate, current_user: CurrentUserDep, db: DbDep
) -> DeliveryResponse:
    service = DeliveryService(db)
    delivery = await service.create(project_id=id, data=data, created_by=current_user.id)
    return DeliveryResponse.model_validate(delivery)


@projects_router.get(
    "/{id}/deliveries",
    response_model=list[DeliveryResponse],
    summary="List Deliveries",
    description="List deliveries of a project with optional status, date range and recipient filters.",
)
async def list_deliveries(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    status: DeliveryStatus | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    recipient: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[DeliveryResponse]:
    service = DeliveryService(db)
    deliveries, _ = await service.list_by_project(
        id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        recipient=recipient,
        offset=offset,
        limit=limit,
    )
    return [DeliveryResponse.model_validate(d) for d in deliveries]


@router.get(
    "/{id}",
    response_model=DeliveryResponse,
    summary="Get Delivery",
    description="Retrieve a single delivery by its identifier.",
)
async def get_delivery(id: uuid.UUID, current_user: CurrentUserDep, db: DbDep) -> DeliveryResponse:
    service = DeliveryService(db)
    delivery = await service.get(id)
    return DeliveryResponse.model_validate(delivery)


@router.patch(
    "/{id}",
    response_model=DeliveryResponse,
    summary="Update Delivery",
    description="Update mutable fields of a delivery such as recipient, notes or scheduled date.",
)
async def update_delivery(
    id: uuid.UUID, data: DeliveryUpdate, current_user: CurrentUserDep, db: DbDep
) -> DeliveryResponse:
    service = DeliveryService(db)
    delivery = await service.update(id, data)
    return DeliveryResponse.model_validate(delivery)


@router.patch(
    "/{id}/status",
    response_model=DeliveryResponse,
    summary="Update Delivery Status",
    description="Transition a delivery to a new status following the delivery workflow rules.",
)
async def update_delivery_status(
    id: uuid.UUID, data: DeliveryStatusUpdate, current_user: CurrentUserDep, db: DbDep
) -> DeliveryResponse:
    service = DeliveryService(db)
    delivery = await service.update_status(id, data.status)
    return DeliveryResponse.model_validate(delivery)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Delete Delivery",
    description="Delete a delivery and all of its items.",
)
async def delete_delivery(id: uuid.UUID, current_user: CurrentUserDep, db: DbDep) -> Response:
    service = DeliveryService(db)
    await service.delete(id)
    return Response(status_code=204)


@router.post(
    "/{id}/items",
    response_model=DeliveryItemResponse,
    status_code=201,
    summary="Add Delivery Item",
    description="Attach a version (or other deliverable entity) as an item of the delivery.",
)
async def add_delivery_item(
    id: uuid.UUID, data: DeliveryItemCreate, current_user: CurrentUserDep, db: DbDep
) -> DeliveryItemResponse:
    service = DeliveryService(db)
    item = await service.add_item(id, data)
    return DeliveryItemResponse.model_validate(item)


@router.get(
    "/{id}/items",
    response_model=list[DeliveryItemResponse],
    summary="List Delivery Items",
    description="List all items currently included in the delivery.",
)
async def list_delivery_items(
    id: uuid.UUID, current_user: CurrentUserDep, db: DbDep
) -> list[DeliveryItemResponse]:
    service = DeliveryService(db)
    items = await service.list_items(id)
    return [DeliveryItemResponse.model_validate(i) for i in items]


@delivery_items_router.delete(
    "/{item_id}",
    status_code=204,
    summary="Remove Delivery Item",
    description="Detach an item from its delivery without deleting the underlying entity.",
)
async def remove_delivery_item(
    item_id: uuid.UUID, current_user: CurrentUserDep, db: DbDep
) -> Response:
    service = DeliveryService(db)
    await service.remove_item(item_id)
    return Response(status_code=204)

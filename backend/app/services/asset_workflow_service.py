import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models import Asset, AssetStatus, RoleName, User
from app.repositories.asset_repository import AssetRepository
from app.repositories.status_log_repository import StatusLogRepository
from app.repositories.user_role_repository import UserRoleRepository
from app.schemas.asset import AssetStatusUpdateResponse
from app.schemas.webhook import WebhookEventType
from app.services.webhook_service import WebhookService

logger = structlog.get_logger(__name__)


VALID_TRANSITIONS: dict[AssetStatus, set[AssetStatus]] = {
    AssetStatus.pending: {AssetStatus.in_progress, AssetStatus.on_hold, AssetStatus.omitted},
    AssetStatus.in_progress: {AssetStatus.review, AssetStatus.on_hold, AssetStatus.omitted},
    AssetStatus.review: {AssetStatus.revision, AssetStatus.on_hold},
    AssetStatus.revision: {AssetStatus.in_progress, AssetStatus.approved, AssetStatus.on_hold},
    AssetStatus.approved: {AssetStatus.revision, AssetStatus.delivered, AssetStatus.final},
    AssetStatus.delivered: {AssetStatus.final},
    AssetStatus.on_hold: {AssetStatus.pending, AssetStatus.in_progress},
    AssetStatus.omitted: set(),
    AssetStatus.final: set(),
}


class AssetWorkflowService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.asset_repository = AssetRepository(db)
        self.status_log_repository = StatusLogRepository(db)
        self.user_role_repository = UserRoleRepository(db)
        self.webhook_service = WebhookService(db)

    async def update_status(
        self,
        asset_id: uuid.UUID,
        target_status: AssetStatus,
        comment: str | None,
        current_user: User,
        project_id: uuid.UUID | None = None,
    ) -> AssetStatusUpdateResponse:
        asset = await self.asset_repository.get_by_id(asset_id)
        if asset is None:
            raise NotFoundError("Asset not found")
        if project_id is not None and asset.project_id != project_id:
            raise NotFoundError("Asset not found")

        old_status = asset.status
        if target_status not in VALID_TRANSITIONS[old_status]:
            raise ConflictError(
                f"Invalid status transition: {old_status.value} -> {target_status.value}"
            )

        await self._enforce_transition_permissions(
            asset=asset,
            target_status=target_status,
            current_user=current_user,
        )

        await self.asset_repository.set_status(asset, target_status)
        status_log = await self.status_log_repository.create_asset_transition_log(
            asset_id=asset.id,
            old_status=old_status,
            new_status=target_status,
            changed_by=current_user.id,
            comment=comment,
        )

        await self.db.commit()

        await self.webhook_service.enqueue_event(
            event_type=WebhookEventType.status_changed,
            project_id=asset.project_id,
            entity_data={
                "entity_type": "asset",
                "entity_id": str(asset.id),
                "old_status": old_status.value,
                "new_status": target_status.value,
                "comment": comment,
            },
            triggered_by=current_user.id,
        )

        logger.info(
            "asset.status_changed",
            asset_id=str(asset.id),
            project_id=str(asset.project_id),
            old_status=old_status.value,
            new_status=target_status.value,
            changed_by=str(current_user.id),
        )

        return AssetStatusUpdateResponse(
            id=asset.id,
            project_id=asset.project_id,
            old_status=old_status,
            new_status=target_status,
            comment=status_log.comment,
            changed_at=status_log.changed_at,
        )

    async def _enforce_transition_permissions(
        self,
        asset: Asset,
        target_status: AssetStatus,
        current_user: User,
    ) -> None:
        user_id = current_user.id
        project_id = asset.project_id

        is_owner = asset.assigned_to == user_id
        has_artist = await self.user_role_repository.has_any_role(
            user_id=user_id,
            role_names={RoleName.artist},
            project_id=project_id,
        )
        is_artist_owner = is_owner and has_artist

        if target_status == AssetStatus.in_progress:
            if is_artist_owner:
                return
            allowed_roles = {RoleName.lead, RoleName.supervisor, RoleName.admin}
            if await self.user_role_repository.has_any_role(user_id, allowed_roles, project_id):
                return
            raise ForbiddenError("Insufficient permissions for transition to in_progress")

        if target_status == AssetStatus.review:
            if is_artist_owner:
                return
            allowed_roles = {RoleName.lead}
            if await self.user_role_repository.has_any_role(user_id, allowed_roles, project_id):
                return
            raise ForbiddenError("Insufficient permissions for transition to review")

        if target_status == AssetStatus.approved:
            allowed_roles = {RoleName.supervisor, RoleName.admin}
            if await self.user_role_repository.has_any_role(user_id, allowed_roles, project_id):
                return
            raise ForbiddenError("Insufficient permissions for transition to approved")

        if target_status == AssetStatus.delivered:
            allowed_roles = {RoleName.admin}
            if await self.user_role_repository.has_any_role(user_id, allowed_roles, project_id):
                return
            raise ForbiddenError("Insufficient permissions for transition to delivered")

        if target_status == AssetStatus.revision:
            allowed_roles = {RoleName.supervisor, RoleName.admin}
            if await self.user_role_repository.has_any_role(user_id, allowed_roles, project_id):
                return
            raise ForbiddenError("Insufficient permissions for transition to revision")

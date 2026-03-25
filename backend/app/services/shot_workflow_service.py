import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models import RoleName, Shot, ShotStatus, User
from app.repositories.shot_repository import ShotRepository
from app.repositories.status_log_repository import StatusLogRepository
from app.repositories.user_role_repository import UserRoleRepository
from app.schemas.shot import (
    ShotStatusHistoryItem,
    ShotStatusHistoryResponse,
    ShotStatusUpdateResponse,
)
from app.schemas.webhook import WebhookEventType
from app.services.webhook_service import WebhookService

logger = structlog.get_logger(__name__)


VALID_TRANSITIONS: dict[ShotStatus, set[ShotStatus]] = {
    ShotStatus.pending: {ShotStatus.in_progress, ShotStatus.on_hold, ShotStatus.omitted},
    ShotStatus.in_progress: {ShotStatus.review, ShotStatus.on_hold, ShotStatus.omitted},
    ShotStatus.review: {ShotStatus.revision, ShotStatus.on_hold},
    ShotStatus.revision: {ShotStatus.in_progress, ShotStatus.approved, ShotStatus.on_hold},
    ShotStatus.approved: {ShotStatus.revision, ShotStatus.delivered, ShotStatus.final},
    ShotStatus.delivered: {ShotStatus.final},
    ShotStatus.on_hold: {ShotStatus.pending, ShotStatus.in_progress},
    ShotStatus.omitted: set(),
    ShotStatus.final: set(),
}


class ShotWorkflowService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.shot_repository = ShotRepository(db)
        self.status_log_repository = StatusLogRepository(db)
        self.user_role_repository = UserRoleRepository(db)
        self.webhook_service = WebhookService(db)

    async def update_status(
        self,
        shot_id: uuid.UUID,
        target_status: ShotStatus,
        comment: str | None,
        current_user: User,
        project_id: uuid.UUID | None = None,
    ) -> ShotStatusUpdateResponse:
        shot = await self.shot_repository.get_by_id(shot_id)
        if shot is None:
            raise NotFoundError("Shot not found")
        if project_id is not None and shot.project_id != project_id:
            raise NotFoundError("Shot not found")

        old_status = shot.status
        if target_status not in VALID_TRANSITIONS[old_status]:
            raise ConflictError(
                f"Invalid status transition: {old_status.value} -> {target_status.value}"
            )

        await self._enforce_transition_permissions(
            shot=shot,
            target_status=target_status,
            current_user=current_user,
        )

        await self.shot_repository.set_status(shot, target_status)
        status_log = await self.status_log_repository.create_shot_transition_log(
            shot_id=shot.id,
            old_status=old_status,
            new_status=target_status,
            changed_by=current_user.id,
            comment=comment,
        )

        await self.db.commit()

        await self.webhook_service.enqueue_event(
            event_type=WebhookEventType.status_changed,
            project_id=shot.project_id,
            entity_data={
                "entity_type": "shot",
                "entity_id": str(shot.id),
                "old_status": old_status.value,
                "new_status": target_status.value,
                "comment": comment,
            },
            triggered_by=current_user.id,
        )

        logger.info(
            "shot.status_changed",
            shot_id=str(shot.id),
            project_id=str(shot.project_id),
            old_status=old_status.value,
            new_status=target_status.value,
            changed_by=str(current_user.id),
        )

        return ShotStatusUpdateResponse(
            id=shot.id,
            project_id=shot.project_id,
            old_status=old_status,
            new_status=target_status,
            comment=status_log.comment,
            changed_at=status_log.changed_at,
        )

    async def list_status_history(
        self,
        shot_id: uuid.UUID,
        current_user: User,
        offset: int,
        limit: int,
        project_id: uuid.UUID | None = None,
    ) -> ShotStatusHistoryResponse:
        shot = await self.shot_repository.get_by_id(shot_id)
        if shot is None:
            raise NotFoundError("Shot not found")
        if project_id is not None and shot.project_id != project_id:
            raise NotFoundError("Shot not found")

        await self._require_project_access(
            user_id=current_user.id,
            project_id=shot.project_id,
            allowed_roles={
                RoleName.admin,
                RoleName.supervisor,
                RoleName.lead,
                RoleName.artist,
                RoleName.worker,
            },
        )

        logs, total = await self.status_log_repository.list_shot_history(
            shot_id=shot.id,
            offset=offset,
            limit=limit,
        )
        return ShotStatusHistoryResponse(
            shot_id=shot.id,
            items=[
                ShotStatusHistoryItem(
                    changed_at=entry.changed_at,
                    old_status=entry.old_status,
                    new_status=entry.new_status,
                    changed_by=entry.changed_by,
                    comment=entry.comment,
                )
                for entry in logs
            ],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def _enforce_transition_permissions(
        self,
        shot: Shot,
        target_status: ShotStatus,
        current_user: User,
    ) -> None:
        user_id = current_user.id
        project_id = shot.project_id

        is_owner = shot.assigned_to == user_id
        has_artist = await self.user_role_repository.has_any_role(
            user_id=user_id,
            role_names={RoleName.artist},
            project_id=project_id,
        )
        is_artist_owner = is_owner and has_artist

        if target_status == ShotStatus.in_progress:
            if is_artist_owner:
                return
            allowed_roles = {RoleName.lead, RoleName.supervisor, RoleName.admin}
            if await self.user_role_repository.has_any_role(user_id, allowed_roles, project_id):
                return
            raise ForbiddenError("Insufficient permissions for transition to in_progress")

        if target_status == ShotStatus.review:
            if is_artist_owner:
                return
            allowed_roles = {RoleName.lead}
            if await self.user_role_repository.has_any_role(user_id, allowed_roles, project_id):
                return
            raise ForbiddenError("Insufficient permissions for transition to review")

        if target_status == ShotStatus.approved:
            allowed_roles = {RoleName.supervisor, RoleName.admin}
            if await self.user_role_repository.has_any_role(user_id, allowed_roles, project_id):
                return
            raise ForbiddenError("Insufficient permissions for transition to approved")

        if target_status == ShotStatus.delivered:
            allowed_roles = {RoleName.admin}
            if await self.user_role_repository.has_any_role(user_id, allowed_roles, project_id):
                return
            raise ForbiddenError("Insufficient permissions for transition to delivered")

        if target_status == ShotStatus.revision:
            allowed_roles = {RoleName.supervisor, RoleName.admin}
            if await self.user_role_repository.has_any_role(user_id, allowed_roles, project_id):
                return
            raise ForbiddenError("Insufficient permissions for transition to revision")

    async def _require_project_access(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        allowed_roles: set[RoleName],
    ) -> None:
        if await self.user_role_repository.has_any_role(user_id, allowed_roles, project_id):
            return
        raise ForbiddenError("Insufficient permissions")

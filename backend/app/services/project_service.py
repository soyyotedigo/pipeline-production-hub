import csv
import os
import re
import uuid
from datetime import datetime, timezone
from io import StringIO

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.models import (
    Asset,
    AssetStatus,
    AssetType,
    Project,
    ProjectStatus,
    RoleName,
    Shot,
    ShotStatus,
    User,
)
from app.repositories.asset_repository import AssetRepository
from app.repositories.episode_repository import EpisodeRepository
from app.repositories.file_repository import FileRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.sequence_repository import SequenceRepository
from app.repositories.shot_repository import ShotRepository
from app.repositories.status_log_repository import StatusLogRepository
from app.repositories.user_role_repository import UserRoleRepository
from app.schemas.asset import (
    AssetCreateRequest,
    AssetListResponse,
    AssetResponse,
    AssetUpdateRequest,
)
from app.schemas.project import (
    EpisodeCreateRequest,
    EpisodeListResponse,
    EpisodeResponse,
    EpisodeUpdateRequest,
    ProjectCreateRequest,
    ProjectExportAcceptedResponse,
    ProjectListResponse,
    ProjectOverviewResponse,
    ProjectReportActivityItem,
    ProjectReportResponse,
    ProjectResponse,
    ProjectUpdateRequest,
    ScaffoldRequest,
    ScaffoldResponse,
    SequenceCreateRequest,
    SequenceListResponse,
    SequenceResponse,
    SequenceUpdateRequest,
)
from app.schemas.shot import ShotCreateRequest, ShotListResponse, ShotResponse, ShotUpdateRequest
from app.schemas.task import TaskType
from app.schemas.webhook import WebhookEventType
from app.services.code_generator import (
    generate_episode_code,
    generate_sequence_code,
    generate_shot_code,
)
from app.services.task_service import TaskService
from app.services.webhook_service import WebhookService


class ProjectService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.project_repository = ProjectRepository(db)
        self.shot_repository = ShotRepository(db)
        self.asset_repository = AssetRepository(db)
        self.file_repository = FileRepository(db)
        self.status_log_repository = StatusLogRepository(db)
        self.episode_repository = EpisodeRepository(db)
        self.sequence_repository = SequenceRepository(db)
        self.user_role_repository = UserRoleRepository(db)
        self.task_service = TaskService()
        self.webhook_service = WebhookService(db)

    async def create_project(
        self, payload: ProjectCreateRequest, current_user: User
    ) -> ProjectResponse:
        await self._require_global_any_role(current_user.id, {RoleName.admin, RoleName.supervisor})

        requested_code = payload.code.upper() if payload.code is not None else None
        if requested_code is not None:
            existing = await self.project_repository.get_by_code(requested_code)
            if existing is not None:
                raise ConflictError("Project code already exists")
            project_code = requested_code
        else:
            project_code = await self._generate_unique_project_code(payload.name)

        project = await self.project_repository.create(
            name=payload.name,
            code=project_code,
            client=payload.client,
            project_type=payload.project_type,
            description=payload.description,
            created_by=current_user.id,
            naming_rules=payload.naming_rules,
            path_templates=payload.path_templates,
        )
        await self.db.commit()
        return ProjectResponse.model_validate(project)

    async def list_projects(
        self,
        current_user: User,
        offset: int,
        limit: int,
        status: ProjectStatus | None,
        include_archived: bool = False,
    ) -> ProjectListResponse:
        allowed_roles = {
            RoleName.admin,
            RoleName.supervisor,
            RoleName.lead,
            RoleName.artist,
            RoleName.worker,
        }
        if not await self.user_role_repository.has_any_role_in_any_scope(
            current_user.id, allowed_roles
        ):
            raise ForbiddenError("Insufficient permissions")
        projects, total = await self.project_repository.list_visible_to_user(
            user_id=current_user.id,
            role_names=allowed_roles,
            offset=offset,
            limit=limit,
            status=status,
            include_archived=include_archived,
        )
        return ProjectListResponse(
            items=[ProjectResponse.model_validate(project) for project in projects],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def get_project(self, project_id: uuid.UUID, current_user: User) -> ProjectResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist, RoleName.worker},
        )
        return ProjectResponse.model_validate(project)

    async def patch_project(
        self,
        project_id: uuid.UUID,
        payload: ProjectUpdateRequest,
        current_user: User,
    ) -> ProjectResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_management_role(current_user.id, project.id)

        if payload.name is not None:
            project.name = payload.name
        if payload.client is not None:
            project.client = payload.client
        if payload.project_type is not None:
            project.project_type = payload.project_type
        if payload.description is not None:
            project.description = payload.description
        if payload.status is not None:
            project.status = payload.status
        if payload.start_date is not None:
            project.start_date = payload.start_date  # type: ignore
        if payload.end_date is not None:
            project.end_date = payload.end_date  # type: ignore
        if payload.fps is not None:
            project.fps = payload.fps
        if payload.resolution_width is not None:
            project.resolution_width = payload.resolution_width
        if payload.resolution_height is not None:
            project.resolution_height = payload.resolution_height
        if payload.thumbnail_url is not None:
            project.thumbnail_url = payload.thumbnail_url
        if payload.color_space is not None:
            project.color_space = payload.color_space
        if payload.naming_rules is not None:
            project.naming_rules = payload.naming_rules
        if payload.path_templates is not None:
            project.path_templates = payload.path_templates

        self.db.add(project)
        await self.db.commit()
        await self.db.refresh(project)
        return ProjectResponse.model_validate(project)

    async def archive_project(self, project_id: uuid.UUID, current_user: User) -> ProjectResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_management_role(current_user.id, project.id)
        project = await self.project_repository.archive(project)
        await self.db.commit()
        return ProjectResponse.model_validate(project)

    async def restore_project(self, project_id: uuid.UUID, current_user: User) -> ProjectResponse:
        project = await self._get_project_or_404(project_id, include_archived=True)
        await self._require_project_management_role(current_user.id, project.id)
        project = await self.project_repository.restore(project)
        await self.db.commit()
        return ProjectResponse.model_validate(project)

    async def delete_project(self, project_id: uuid.UUID, current_user: User, force: bool) -> None:
        if not force:
            raise UnprocessableError("Hard delete requires force=true")
        await self._require_global_any_role(current_user.id, {RoleName.admin})
        project = await self._get_project_or_404(project_id, include_archived=True)
        await self.project_repository.hard_delete(project)
        await self.db.commit()

    async def create_project_shot(
        self,
        project_id: uuid.UUID,
        payload: ShotCreateRequest,
        current_user: User,
    ) -> ShotResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )

        sequence_id: uuid.UUID | None = None
        sequence_obj = None
        if payload.sequence_id is not None:
            sequence_obj = await self.sequence_repository.get_by_id(payload.sequence_id)
            if sequence_obj is None or sequence_obj.project_id != project.id:
                raise NotFoundError("Sequence not found")
            sequence_id = sequence_obj.id

        if payload.code is not None:
            shot_code = payload.code
            shot_sort_order = None
        elif sequence_obj is not None:
            last_order = await self.shot_repository.get_last_sort_order_for_sequence(
                sequence_obj.id
            )
            shot_code, shot_sort_order = generate_shot_code(
                sequence_obj.code, last_order, project.naming_rules
            )
        else:
            raise ConflictError(
                "Either code or sequence_id is required to auto-generate a shot code"
            )

        existing_shot = await self.shot_repository.get_by_project_and_code(
            project_id=project.id,
            code=shot_code,
            include_archived=True,
        )
        if existing_shot is not None:
            raise ConflictError("Shot code already exists")

        shot = await self.shot_repository.create_for_project(
            project_id=project.id,
            sequence_id=sequence_id,
            name=payload.name,
            code=shot_code,
            frame_start=payload.frame_start,
            frame_end=payload.frame_end,
            assigned_to=payload.assigned_to,
            description=payload.description,
            thumbnail_url=payload.thumbnail_url,
            priority=payload.priority,
            difficulty=payload.difficulty,
            handle_head=payload.handle_head,
            handle_tail=payload.handle_tail,
            cut_in=payload.cut_in,
            cut_out=payload.cut_out,
            bid_days=payload.bid_days,
            sort_order=shot_sort_order,
        )

        # Auto-generate pipeline tasks from template
        from app.services.pipeline_task_service import PipelineTaskService

        pipeline_service = PipelineTaskService(self.db)
        await pipeline_service.generate_tasks_for_shot(shot)

        await self.db.commit()
        return ShotResponse.model_validate(shot)

    async def list_project_shots(
        self,
        project_id: uuid.UUID,
        current_user: User,
        offset: int,
        limit: int,
        status: ShotStatus | None,
        assigned_to: uuid.UUID | None,
    ) -> ShotListResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist, RoleName.worker},
        )

        shots, total = await self.shot_repository.list_for_project(
            project_id=project.id,
            offset=offset,
            limit=limit,
            status=status,
            assigned_to=assigned_to,
        )
        return ShotListResponse(
            items=[ShotResponse.model_validate(shot) for shot in shots],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def archive_shot(self, shot_id: uuid.UUID, current_user: User) -> ShotResponse:
        shot = await self.shot_repository.get_by_id(shot_id)
        if shot is None:
            raise NotFoundError("Shot not found")

        await self._require_project_any_role(
            current_user.id,
            shot.project_id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )
        shot = await self.shot_repository.archive(shot)
        await self.db.commit()
        return ShotResponse.model_validate(shot)

    async def restore_shot(self, shot_id: uuid.UUID, current_user: User) -> ShotResponse:
        shot = await self.shot_repository.get_by_id(shot_id, include_archived=True)
        if shot is None:
            raise NotFoundError("Shot not found")

        await self._require_project_any_role(
            current_user.id,
            shot.project_id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )
        shot = await self.shot_repository.restore(shot)
        await self.db.commit()
        return ShotResponse.model_validate(shot)

    async def delete_shot(self, shot_id: uuid.UUID, current_user: User, force: bool) -> None:
        if not force:
            raise UnprocessableError("Hard delete requires force=true")
        await self._require_global_any_role(current_user.id, {RoleName.admin})
        shot = await self.shot_repository.get_by_id(shot_id, include_archived=True)
        if shot is None:
            raise NotFoundError("Shot not found")
        await self.shot_repository.hard_delete(shot)
        await self.db.commit()

    async def get_shot(self, shot_id: uuid.UUID, current_user: User) -> ShotResponse:
        shot = await self.shot_repository.get_by_id(shot_id)
        if shot is None:
            raise NotFoundError("Shot not found")

        await self._require_project_any_role(
            current_user.id,
            shot.project_id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist, RoleName.worker},
        )

        return ShotResponse.model_validate(shot)

    async def patch_shot(
        self,
        shot_id: uuid.UUID,
        payload: ShotUpdateRequest,
        current_user: User,
    ) -> ShotResponse:
        shot = await self.shot_repository.get_by_id(shot_id)
        if shot is None:
            raise NotFoundError("Shot not found")

        await self._apply_shot_patch(
            shot=shot,
            project_id=shot.project_id,
            payload=payload,
            current_user=current_user,
        )

        return ShotResponse.model_validate(shot)

    async def _apply_shot_patch(
        self,
        shot: Shot,
        project_id: uuid.UUID,
        payload: ShotUpdateRequest,
        current_user: User,
    ) -> None:
        previous_assigned_to = shot.assigned_to

        can_patch = await self._has_global_any_role(
            current_user.id, {RoleName.admin, RoleName.supervisor}
        )
        if not can_patch:
            can_patch = await self.user_role_repository.has_any_role(
                current_user.id,
                {RoleName.lead},
                project_id,
            )
        if not can_patch:
            raise ForbiddenError("Insufficient permissions to patch shot")

        if payload.name is not None:
            shot.name = payload.name
        if payload.sequence_id is not None:
            sequence = await self.sequence_repository.get_by_id(payload.sequence_id)
            if sequence is None or sequence.project_id != project_id:
                raise NotFoundError("Sequence not found")
            shot.sequence_id = sequence.id
        if payload.frame_start is not None:
            shot.frame_start = payload.frame_start
        if payload.frame_end is not None:
            shot.frame_end = payload.frame_end
        if payload.assigned_to is not None:
            shot.assigned_to = payload.assigned_to
        if payload.description is not None:
            shot.description = payload.description
        if payload.thumbnail_url is not None:
            shot.thumbnail_url = payload.thumbnail_url
        if payload.priority is not None:
            shot.priority = payload.priority
        if payload.difficulty is not None:
            shot.difficulty = payload.difficulty
        if payload.handle_head is not None:
            shot.handle_head = payload.handle_head
        if payload.handle_tail is not None:
            shot.handle_tail = payload.handle_tail
        if payload.cut_in is not None:
            shot.cut_in = payload.cut_in
        if payload.cut_out is not None:
            shot.cut_out = payload.cut_out
        if payload.bid_days is not None:
            shot.bid_days = payload.bid_days
        if payload.sort_order is not None:
            shot.sort_order = payload.sort_order

        self.db.add(shot)
        await self.db.commit()
        await self.db.refresh(shot)

        if previous_assigned_to != shot.assigned_to:
            await self.webhook_service.enqueue_event(
                event_type=WebhookEventType.assignment_changed,
                project_id=project_id,
                entity_data={
                    "entity_type": "shot",
                    "entity_id": str(shot.id),
                    "old_assigned_to": str(previous_assigned_to)
                    if previous_assigned_to is not None
                    else None,
                    "new_assigned_to": str(shot.assigned_to)
                    if shot.assigned_to is not None
                    else None,
                },
                triggered_by=current_user.id,
            )

    async def create_project_asset(
        self,
        project_id: uuid.UUID,
        payload: AssetCreateRequest,
        current_user: User,
    ) -> AssetResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )

        requested_code = payload.code.strip() if payload.code is not None else None
        if requested_code:
            existing_asset = await self.asset_repository.get_by_project_and_code(
                project.id,
                requested_code,
                include_archived=True,
            )
            if existing_asset is not None:
                raise ConflictError("Asset code already exists")
            asset_code = requested_code
        else:
            asset_code = await self._generate_unique_asset_code(project.id, payload.name)

        asset = await self.asset_repository.create_for_project(
            project_id=project.id,
            name=payload.name,
            code=asset_code,
            asset_type=payload.asset_type,
            assigned_to=payload.assigned_to,
            description=payload.description,
            thumbnail_url=payload.thumbnail_url,
            priority=payload.priority,
        )

        # Auto-generate pipeline tasks from template
        from app.services.pipeline_task_service import PipelineTaskService

        pipeline_service = PipelineTaskService(self.db)
        await pipeline_service.generate_tasks_for_asset(asset)

        await self.db.commit()
        return AssetResponse.model_validate(asset)

    async def create_project_episode(
        self,
        project_id: uuid.UUID,
        payload: EpisodeCreateRequest,
        current_user: User,
    ) -> EpisodeResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )

        if payload.production_number is not None:
            episode_code = generate_episode_code(payload.production_number, project.naming_rules)
        elif payload.code is not None:
            episode_code = payload.code
        else:
            raise ConflictError("Either production_number or code is required")

        existing = await self.episode_repository.get_by_project_and_code(project.id, episode_code)
        if existing is not None:
            raise ConflictError("Episode code already exists in project")

        episode = await self.episode_repository.create_for_project(
            project_id=project.id,
            name=payload.name,
            code=episode_code,
            status=payload.status,
            description=payload.description,
            order=payload.order,
            production_number=payload.production_number,
        )
        await self.db.commit()
        return EpisodeResponse.model_validate(episode)

    async def list_project_episodes(
        self,
        project_id: uuid.UUID,
        current_user: User,
        offset: int,
        limit: int,
    ) -> EpisodeListResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist, RoleName.worker},
        )

        rows, total = await self.episode_repository.list_for_project(
            project_id=project.id,
            offset=offset,
            limit=limit,
        )
        return EpisodeListResponse(
            items=[EpisodeResponse.model_validate(item) for item in rows],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def get_episode(self, episode_id: uuid.UUID, current_user: User) -> EpisodeResponse:
        episode = await self.episode_repository.get_by_id(episode_id)
        if episode is None:
            raise NotFoundError("Episode not found")

        await self._require_project_any_role(
            current_user.id,
            episode.project_id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist, RoleName.worker},
        )
        return EpisodeResponse.model_validate(episode)

    async def patch_episode(
        self,
        episode_id: uuid.UUID,
        payload: EpisodeUpdateRequest,
        current_user: User,
    ) -> EpisodeResponse:
        episode = await self.episode_repository.get_by_id(episode_id)
        if episode is None:
            raise NotFoundError("Episode not found")

        await self._require_project_any_role(
            current_user.id,
            episode.project_id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )

        if payload.name is not None:
            episode.name = payload.name
        if payload.status is not None:
            episode.status = payload.status
        if payload.description is not None:
            episode.description = payload.description
        if payload.order is not None:
            episode.order = payload.order

        self.db.add(episode)
        await self.db.commit()
        await self.db.refresh(episode)
        return EpisodeResponse.model_validate(episode)

    async def archive_episode(self, episode_id: uuid.UUID, current_user: User) -> EpisodeResponse:
        episode = await self.episode_repository.get_by_id(episode_id)
        if episode is None:
            raise NotFoundError("Episode not found")

        await self._require_project_any_role(
            current_user.id,
            episode.project_id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )
        episode = await self.episode_repository.archive(episode)
        await self.db.commit()
        return EpisodeResponse.model_validate(episode)

    async def restore_episode(self, episode_id: uuid.UUID, current_user: User) -> EpisodeResponse:
        episode = await self.episode_repository.get_by_id(episode_id, include_archived=True)
        if episode is None:
            raise NotFoundError("Episode not found")

        await self._require_project_any_role(
            current_user.id,
            episode.project_id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )
        episode = await self.episode_repository.restore(episode)
        await self.db.commit()
        return EpisodeResponse.model_validate(episode)

    async def delete_episode(self, episode_id: uuid.UUID, current_user: User, force: bool) -> None:
        if not force:
            raise UnprocessableError("Hard delete requires force=true")
        await self._require_global_any_role(current_user.id, {RoleName.admin})

        episode = await self.episode_repository.get_by_id(episode_id, include_archived=True)
        if episode is None:
            raise NotFoundError("Episode not found")

        await self.episode_repository.hard_delete(episode)
        await self.db.commit()

    async def archive_project_episode(
        self,
        project_id: uuid.UUID,
        episode_id: uuid.UUID,
        current_user: User,
    ) -> EpisodeResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )
        episode = await self.episode_repository.get_by_project_and_id(project.id, episode_id)
        if episode is None:
            raise NotFoundError("Episode not found")

        episode = await self.episode_repository.archive(episode)
        await self.db.commit()
        return EpisodeResponse.model_validate(episode)

    async def restore_project_episode(
        self,
        project_id: uuid.UUID,
        episode_id: uuid.UUID,
        current_user: User,
    ) -> EpisodeResponse:
        project = await self._get_project_or_404(project_id, include_archived=True)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )
        episode = await self.episode_repository.get_by_project_and_id(
            project.id,
            episode_id,
            include_archived=True,
        )
        if episode is None:
            raise NotFoundError("Episode not found")

        episode = await self.episode_repository.restore(episode)
        await self.db.commit()
        return EpisodeResponse.model_validate(episode)

    async def delete_project_episode(
        self,
        project_id: uuid.UUID,
        episode_id: uuid.UUID,
        current_user: User,
        force: bool,
    ) -> None:
        if not force:
            raise UnprocessableError("Hard delete requires force=true")
        await self._require_global_any_role(current_user.id, {RoleName.admin})
        episode = await self.episode_repository.get_by_project_and_id(
            project_id,
            episode_id,
            include_archived=True,
        )
        if episode is None:
            raise NotFoundError("Episode not found")

        await self.episode_repository.hard_delete(episode)
        await self.db.commit()

    async def create_project_sequence(
        self,
        project_id: uuid.UUID,
        payload: SequenceCreateRequest,
        current_user: User,
    ) -> SequenceResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )

        if payload.episode_id is not None:
            episode = await self.episode_repository.get_by_id(payload.episode_id)
            if episode is None or episode.project_id != project.id:
                raise NotFoundError("Episode not found")

        if payload.production_number is not None:
            sequence_code = generate_sequence_code(payload.production_number, project.naming_rules)
        elif payload.code is not None:
            sequence_code = payload.code
        else:
            raise ConflictError("Either production_number or code is required")

        existing = await self.sequence_repository.get_by_project_and_code(project.id, sequence_code)
        if existing is not None:
            raise ConflictError("Sequence code already exists in project")

        sequence = await self.sequence_repository.create_for_project(
            project_id=project.id,
            episode_id=payload.episode_id,
            name=payload.name,
            code=sequence_code,
            scope_type=payload.scope_type,
            status=payload.status,
            description=payload.description,
            order=payload.order,
            production_number=payload.production_number,
        )
        await self.db.commit()
        return SequenceResponse.model_validate(sequence)

    async def list_project_sequences(
        self,
        project_id: uuid.UUID,
        current_user: User,
        offset: int,
        limit: int,
        episode_id: uuid.UUID | None,
    ) -> SequenceListResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist, RoleName.worker},
        )

        if episode_id is not None:
            episode = await self.episode_repository.get_by_id(episode_id)
            if episode is None or episode.project_id != project.id:
                raise NotFoundError("Episode not found")

        rows, total = await self.sequence_repository.list_for_project(
            project_id=project.id,
            offset=offset,
            limit=limit,
            episode_id=episode_id,
        )
        return SequenceListResponse(
            items=[SequenceResponse.model_validate(item) for item in rows],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def get_sequence(self, sequence_id: uuid.UUID, current_user: User) -> SequenceResponse:
        sequence = await self.sequence_repository.get_by_id(sequence_id)
        if sequence is None:
            raise NotFoundError("Sequence not found")

        await self._require_project_any_role(
            current_user.id,
            sequence.project_id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist, RoleName.worker},
        )
        return SequenceResponse.model_validate(sequence)

    async def patch_sequence(
        self,
        sequence_id: uuid.UUID,
        payload: SequenceUpdateRequest,
        current_user: User,
    ) -> SequenceResponse:
        sequence = await self.sequence_repository.get_by_id(sequence_id)
        if sequence is None:
            raise NotFoundError("Sequence not found")

        await self._require_project_any_role(
            current_user.id,
            sequence.project_id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )

        if payload.episode_id is not None:
            episode = await self.episode_repository.get_by_id(payload.episode_id)
            if episode is None or episode.project_id != sequence.project_id:
                raise NotFoundError("Episode not found")
            sequence.episode_id = payload.episode_id

        if payload.name is not None:
            sequence.name = payload.name
        if payload.scope_type is not None:
            sequence.scope_type = payload.scope_type
        if payload.status is not None:
            sequence.status = payload.status
        if payload.description is not None:
            sequence.description = payload.description
        if payload.order is not None:
            sequence.order = payload.order

        self.db.add(sequence)
        await self.db.commit()
        await self.db.refresh(sequence)
        return SequenceResponse.model_validate(sequence)

    async def archive_sequence(
        self, sequence_id: uuid.UUID, current_user: User
    ) -> SequenceResponse:
        sequence = await self.sequence_repository.get_by_id(sequence_id)
        if sequence is None:
            raise NotFoundError("Sequence not found")

        await self._require_project_any_role(
            current_user.id,
            sequence.project_id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )
        sequence = await self.sequence_repository.archive(sequence)
        await self.db.commit()
        return SequenceResponse.model_validate(sequence)

    async def restore_sequence(
        self, sequence_id: uuid.UUID, current_user: User
    ) -> SequenceResponse:
        sequence = await self.sequence_repository.get_by_id(sequence_id, include_archived=True)
        if sequence is None:
            raise NotFoundError("Sequence not found")

        await self._require_project_any_role(
            current_user.id,
            sequence.project_id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )
        sequence = await self.sequence_repository.restore(sequence)
        await self.db.commit()
        return SequenceResponse.model_validate(sequence)

    async def delete_sequence(
        self, sequence_id: uuid.UUID, current_user: User, force: bool
    ) -> None:
        if not force:
            raise UnprocessableError("Hard delete requires force=true")
        await self._require_global_any_role(current_user.id, {RoleName.admin})

        sequence = await self.sequence_repository.get_by_id(sequence_id, include_archived=True)
        if sequence is None:
            raise NotFoundError("Sequence not found")

        await self.sequence_repository.hard_delete(sequence)
        await self.db.commit()

    async def archive_project_sequence(
        self,
        project_id: uuid.UUID,
        sequence_id: uuid.UUID,
        current_user: User,
    ) -> SequenceResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )
        sequence = await self.sequence_repository.get_by_project_and_id(project.id, sequence_id)
        if sequence is None:
            raise NotFoundError("Sequence not found")

        sequence = await self.sequence_repository.archive(sequence)
        await self.db.commit()
        return SequenceResponse.model_validate(sequence)

    async def restore_project_sequence(
        self,
        project_id: uuid.UUID,
        sequence_id: uuid.UUID,
        current_user: User,
    ) -> SequenceResponse:
        project = await self._get_project_or_404(project_id, include_archived=True)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )
        sequence = await self.sequence_repository.get_by_project_and_id(
            project.id,
            sequence_id,
            include_archived=True,
        )
        if sequence is None:
            raise NotFoundError("Sequence not found")

        sequence = await self.sequence_repository.restore(sequence)
        await self.db.commit()
        return SequenceResponse.model_validate(sequence)

    async def delete_project_sequence(
        self,
        project_id: uuid.UUID,
        sequence_id: uuid.UUID,
        current_user: User,
        force: bool,
    ) -> None:
        if not force:
            raise UnprocessableError("Hard delete requires force=true")
        await self._require_global_any_role(current_user.id, {RoleName.admin})
        sequence = await self.sequence_repository.get_by_project_and_id(
            project_id,
            sequence_id,
            include_archived=True,
        )
        if sequence is None:
            raise NotFoundError("Sequence not found")

        await self.sequence_repository.hard_delete(sequence)
        await self.db.commit()

    async def list_project_assets(
        self,
        project_id: uuid.UUID,
        current_user: User,
        offset: int,
        limit: int,
        status: AssetStatus | None,
        assigned_to: uuid.UUID | None,
        asset_type: AssetType | None,
    ) -> AssetListResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist, RoleName.worker},
        )

        assets, total = await self.asset_repository.list_for_project(
            project_id=project.id,
            offset=offset,
            limit=limit,
            status=status,
            assigned_to=assigned_to,
            asset_type=asset_type,
        )
        return AssetListResponse(
            items=[AssetResponse.model_validate(asset) for asset in assets],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def archive_asset(self, asset_id: uuid.UUID, current_user: User) -> AssetResponse:
        asset = await self.asset_repository.get_by_id(asset_id)
        if asset is None:
            raise NotFoundError("Asset not found")

        await self._require_project_any_role(
            current_user.id,
            asset.project_id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )
        asset = await self.asset_repository.archive(asset)
        await self.db.commit()
        return AssetResponse.model_validate(asset)

    async def restore_asset(self, asset_id: uuid.UUID, current_user: User) -> AssetResponse:
        asset = await self.asset_repository.get_by_id(asset_id, include_archived=True)
        if asset is None:
            raise NotFoundError("Asset not found")

        await self._require_project_any_role(
            current_user.id,
            asset.project_id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead},
        )
        asset = await self.asset_repository.restore(asset)
        await self.db.commit()
        return AssetResponse.model_validate(asset)

    async def delete_asset(self, asset_id: uuid.UUID, current_user: User, force: bool) -> None:
        if not force:
            raise UnprocessableError("Hard delete requires force=true")
        await self._require_global_any_role(current_user.id, {RoleName.admin})
        asset = await self.asset_repository.get_by_id(asset_id, include_archived=True)
        if asset is None:
            raise NotFoundError("Asset not found")
        await self.asset_repository.hard_delete(asset)
        await self.db.commit()

    async def patch_asset(
        self,
        asset_id: uuid.UUID,
        payload: AssetUpdateRequest,
        current_user: User,
    ) -> AssetResponse:
        asset = await self.asset_repository.get_by_id(asset_id)
        if asset is None:
            raise NotFoundError("Asset not found")

        previous_assigned_to = asset.assigned_to

        can_patch = await self._has_global_any_role(
            current_user.id, {RoleName.admin, RoleName.supervisor}
        )
        if not can_patch:
            can_patch = await self.user_role_repository.has_any_role(
                current_user.id,
                {RoleName.lead},
                asset.project_id,
            )
        if not can_patch:
            raise ForbiddenError("Insufficient permissions to patch asset")

        if payload.name is not None:
            asset.name = payload.name
        if payload.code is not None:
            requested_code = payload.code.strip()
            if requested_code and requested_code != asset.code:
                existing = await self.asset_repository.get_by_project_and_code(
                    asset.project_id,
                    requested_code,
                    include_archived=True,
                )
                if existing is not None and existing.id != asset.id:
                    raise ConflictError("Asset code already exists")
                asset.code = requested_code
        if payload.asset_type is not None:
            asset.asset_type = payload.asset_type
        if payload.assigned_to is not None:
            asset.assigned_to = payload.assigned_to
        if payload.description is not None:
            asset.description = payload.description
        if payload.thumbnail_url is not None:
            asset.thumbnail_url = payload.thumbnail_url
        if payload.priority is not None:
            asset.priority = payload.priority

        self.db.add(asset)
        await self.db.commit()
        await self.db.refresh(asset)

        if previous_assigned_to != asset.assigned_to:
            await self.webhook_service.enqueue_event(
                event_type=WebhookEventType.assignment_changed,
                project_id=asset.project_id,
                entity_data={
                    "entity_type": "asset",
                    "entity_id": str(asset.id),
                    "old_assigned_to": str(previous_assigned_to)
                    if previous_assigned_to is not None
                    else None,
                    "new_assigned_to": str(asset.assigned_to)
                    if asset.assigned_to is not None
                    else None,
                },
                triggered_by=current_user.id,
            )

        return AssetResponse.model_validate(asset)

    async def get_project_overview(
        self,
        project_id: uuid.UUID,
        current_user: User,
    ) -> ProjectOverviewResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist, RoleName.worker},
        )

        total_shots = await self.project_repository.count_shots(project.id)
        total_assets = await self.project_repository.count_assets(project.id)
        shot_status_counts = await self.project_repository.shot_status_counts(project.id)
        asset_status_counts = await self.project_repository.asset_status_counts(project.id)

        total_entities = total_shots + total_assets
        completed = (
            shot_status_counts.get(ShotStatus.approved.value, 0)
            + shot_status_counts.get(ShotStatus.delivered.value, 0)
            + shot_status_counts.get(ShotStatus.final.value, 0)
            + asset_status_counts.get("approved", 0)
            + asset_status_counts.get("delivered", 0)
            + asset_status_counts.get("final", 0)
        )
        completion_percent = (completed / total_entities * 100.0) if total_entities > 0 else 0.0

        return ProjectOverviewResponse(
            project_id=project.id,
            total_shots=total_shots,
            total_assets=total_assets,
            shot_status_counts=shot_status_counts,
            asset_status_counts=asset_status_counts,
            completion_percent=round(completion_percent, 2),
        )

    async def get_project_report(
        self,
        project_id: uuid.UUID,
        current_user: User,
    ) -> ProjectReportResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist, RoleName.worker},
        )

        total_shots = await self.project_repository.count_shots(project.id)
        total_assets = await self.project_repository.count_assets(project.id)
        shot_status_counts = await self.project_repository.shot_status_counts(project.id)
        asset_status_counts = await self.project_repository.asset_status_counts(project.id)

        total_entities = total_shots + total_assets
        completed = (
            shot_status_counts.get(ShotStatus.approved.value, 0)
            + shot_status_counts.get(ShotStatus.delivered.value, 0)
            + shot_status_counts.get(ShotStatus.final.value, 0)
            + asset_status_counts.get(AssetStatus.approved.value, 0)
            + asset_status_counts.get(AssetStatus.delivered.value, 0)
            + asset_status_counts.get(AssetStatus.final.value, 0)
        )
        completion_percent = (completed / total_entities * 100.0) if total_entities > 0 else 0.0

        uploaded_files_total = await self.file_repository.count_active_for_project(project.id)
        storage_used_bytes = await self.file_repository.storage_used_bytes_for_project(project.id)
        recent_logs = await self.status_log_repository.list_recent_for_project(project.id, limit=20)

        return ProjectReportResponse(
            project_id=project.id,
            total_shots=total_shots,
            total_assets=total_assets,
            shot_status_counts=shot_status_counts,
            asset_status_counts=asset_status_counts,
            completion_percent=round(completion_percent, 2),
            uploaded_files_total=uploaded_files_total,
            storage_used_bytes=storage_used_bytes,
            recent_activity=[
                ProjectReportActivityItem(
                    id=item.id,
                    entity_type=item.entity_type.value,
                    entity_id=item.entity_id,
                    old_status=item.old_status,
                    new_status=item.new_status,
                    changed_by=item.changed_by,
                    changed_at=item.changed_at,
                    comment=item.comment,
                )
                for item in recent_logs
            ],
        )

    async def export_project_csv(
        self,
        project_id: uuid.UUID,
        current_user: User,
    ) -> tuple[str, bytes] | ProjectExportAcceptedResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist, RoleName.worker},
        )

        total_shots = await self.project_repository.count_shots(project.id)
        total_assets = await self.project_repository.count_assets(project.id)
        total_entities = total_shots + total_assets

        if total_entities >= settings.project_export_async_threshold_entities:
            task_id = await self.task_service.enqueue_task(
                task_type=TaskType.project_export_csv,
                created_by=current_user.id,
                payload={
                    "project_id": str(project.id),
                },
            )
            return ProjectExportAcceptedResponse(task_id=task_id, status="pending")

        shots = await self.shot_repository.list_all_for_project(project.id)
        assets = await self.asset_repository.list_all_for_project(project.id)
        csv_bytes = self._build_project_csv_bytes(project.id, shots, assets)
        file_name = f"{project.code.lower()}_export.csv"
        return file_name, csv_bytes

    async def scaffold_project_filesystem(
        self,
        project_id: uuid.UUID,
        payload: ScaffoldRequest,
        current_user: User,
    ) -> ScaffoldResponse:
        project = await self._get_project_or_404(project_id)
        await self._require_project_any_role(
            current_user.id,
            project.id,
            {RoleName.admin, RoleName.supervisor, RoleName.lead, RoleName.artist, RoleName.worker},
        )

        root = (payload.root or settings.local_storage_root).rstrip("/").rstrip("\\")

        episodes = await self.episode_repository.list_all_for_project(project.id)
        sequences = await self.sequence_repository.list_all_for_project(project.id)
        shots = await self.shot_repository.list_all_for_project(project.id)
        assets = await self.asset_repository.list_all_for_project(project.id)

        # Index sequences by id for quick lookup
        seq_by_id = {seq.id: seq for seq in sequences}
        # Index episodes by id
        ep_by_id = {ep.id: ep for ep in episodes}

        dirs: list[str] = []

        def _add(path: str) -> None:
            dirs.append(path)

        project_root = os.path.join(root, project.code)
        _add(project_root)
        _add(os.path.join(project_root, "assets"))
        _add(os.path.join(project_root, "shots"))
        _add(os.path.join(project_root, "references"))
        _add(os.path.join(project_root, "deliveries"))

        # Episodes
        for ep in episodes:
            ep_root = os.path.join(project_root, "episodes", ep.code)
            _add(ep_root)
            _add(os.path.join(ep_root, "assets"))
            _add(os.path.join(ep_root, "shots"))

        # Sequences
        for seq in sequences:
            if seq.episode_id and seq.episode_id in ep_by_id:
                ep = ep_by_id[seq.episode_id]
                seq_root = os.path.join(project_root, "episodes", ep.code, "shots", seq.code)
            else:
                seq_root = os.path.join(project_root, "shots", seq.code)
            _add(seq_root)

        # Shots
        departments = ["anim", "comp", "fx", "light", "model", "rig", "layout"]
        for shot in shots:
            if shot.sequence_id and shot.sequence_id in seq_by_id:
                seq = seq_by_id[shot.sequence_id]
                if seq.episode_id and seq.episode_id in ep_by_id:
                    ep = ep_by_id[seq.episode_id]
                    shot_root = os.path.join(
                        project_root, "episodes", ep.code, "shots", seq.code, shot.code
                    )
                else:
                    shot_root = os.path.join(project_root, "shots", seq.code, shot.code)
            else:
                shot_root = os.path.join(project_root, "shots", shot.code)
            _add(shot_root)
            for dept in departments:
                _add(os.path.join(shot_root, "work", dept))
                _add(os.path.join(shot_root, "publish", dept))

        # Assets
        for asset in assets:
            asset_code = asset.code or re.sub(r"[^A-Z0-9_]", "_", asset.name.upper())
            asset_root = os.path.join(project_root, "assets", asset.asset_type.value, asset_code)
            _add(asset_root)
            _add(os.path.join(asset_root, "work"))
            _add(os.path.join(asset_root, "publish"))

        return ScaffoldResponse(
            root=root,
            project_code=project.code,
            created_dirs=dirs,
            total=len(dirs),
        )

    def _build_project_csv_bytes(
        self,
        project_id: uuid.UUID,
        shots: list[Shot],
        assets: list[Asset],
    ) -> bytes:
        buffer = StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "entity_type",
                "entity_id",
                "project_id",
                "code",
                "name",
                "status",
                "assigned_to",
                "frame_start",
                "frame_end",
                "asset_type",
                "created_at",
            ]
        )

        for shot in shots:
            writer.writerow(
                [
                    "shot",
                    str(shot.id),
                    str(project_id),
                    shot.code,
                    shot.name,
                    shot.status.value,
                    str(shot.assigned_to) if shot.assigned_to is not None else "",
                    shot.frame_start if shot.frame_start is not None else "",
                    shot.frame_end if shot.frame_end is not None else "",
                    "",
                    self._format_datetime(shot.created_at),
                ]
            )

        for asset in assets:
            writer.writerow(
                [
                    "asset",
                    str(asset.id),
                    str(project_id),
                    asset.code or "",
                    asset.name,
                    asset.status.value,
                    str(asset.assigned_to) if asset.assigned_to is not None else "",
                    "",
                    "",
                    asset.asset_type.value,
                    self._format_datetime(asset.created_at),
                ]
            )

        return buffer.getvalue().encode("utf-8")

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return ""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()

    async def _get_project_or_404(
        self, project_id: uuid.UUID, include_archived: bool = False
    ) -> Project:
        project = await self.project_repository.get_by_id(
            project_id, include_archived=include_archived
        )
        if project is None:
            raise NotFoundError("Project not found")
        return project

    async def _require_project_management_role(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> None:
        can_manage = await self._has_global_any_role(user_id, {RoleName.admin, RoleName.supervisor})
        if not can_manage:
            can_manage = await self.user_role_repository.has_any_role(
                user_id, {RoleName.lead}, project_id
            )
        if not can_manage:
            raise ForbiddenError("Insufficient permissions to manage project")

    async def _require_global_any_role(self, user_id: uuid.UUID, roles: set[RoleName]) -> None:
        if await self._has_global_any_role(user_id, roles):
            return
        raise ForbiddenError("Insufficient permissions")

    async def _has_global_any_role(self, user_id: uuid.UUID, roles: set[RoleName]) -> bool:
        return await self.user_role_repository.has_global_any_role(
            user_id=user_id, role_names=roles
        )

    async def _generate_unique_project_code(self, name: str) -> str:
        base_code = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
        if not base_code:
            base_code = "PRJ"

        base_code = base_code[:64]
        candidate = base_code
        counter = 2

        while await self.project_repository.get_by_code(candidate) is not None:
            suffix = f"_{counter}"
            candidate = f"{base_code[: 64 - len(suffix)]}{suffix}"
            counter += 1

        return candidate

    async def _generate_unique_asset_code(self, project_id: uuid.UUID, name: str) -> str:
        base_code = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
        if not base_code:
            base_code = "ASSET"

        base_code = base_code[:50]
        candidate = base_code
        counter = 2

        while (
            await self.asset_repository.get_by_project_and_code(
                project_id,
                candidate,
                include_archived=True,
            )
            is not None
        ):
            suffix = f"_{counter}"
            candidate = f"{base_code[: 50 - len(suffix)]}{suffix}"
            counter += 1

        return candidate

    async def _require_project_any_role(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        roles: set[RoleName],
    ) -> None:
        if await self.user_role_repository.has_any_role(user_id, roles, project_id):
            return
        raise ForbiddenError("Insufficient permissions")

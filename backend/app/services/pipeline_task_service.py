import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, UnprocessableError
from app.models.pipeline_task import (
    PipelineTask,
    PipelineTaskStatus,
)
from app.models.status_log import StatusLog, StatusLogEntityType
from app.repositories.pipeline_task_repository import PipelineTaskRepository
from app.schemas.pipeline_task import (
    ApplyTemplateResponse,
    PipelineTaskCreateRequest,
    PipelineTaskListResponse,
    PipelineTaskResponse,
    PipelineTaskStatusUpdateRequest,
    PipelineTaskStatusUpdateResponse,
    PipelineTaskUpdateRequest,
    PipelineTemplateCreateRequest,
    PipelineTemplateListResponse,
    PipelineTemplateResponse,
    PipelineTemplateStepResponse,
    PipelineTemplateUpdateRequest,
)

# Valid status transitions
VALID_TRANSITIONS: dict[PipelineTaskStatus, set[PipelineTaskStatus]] = {
    PipelineTaskStatus.pending: {PipelineTaskStatus.in_progress},
    PipelineTaskStatus.in_progress: {PipelineTaskStatus.review},
    PipelineTaskStatus.review: {PipelineTaskStatus.revision, PipelineTaskStatus.approved},
    PipelineTaskStatus.revision: {PipelineTaskStatus.in_progress},
}


class PipelineTaskService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = PipelineTaskRepository(db)

    # ── Template CRUD ────────────────────────────────────────────────────────

    async def create_template(
        self,
        payload: PipelineTemplateCreateRequest,
    ) -> PipelineTemplateResponse:
        template = await self.repository.create_template(
            project_type=payload.project_type,
            name=payload.name,
            description=payload.description,
        )

        steps = []
        for step_data in payload.steps:
            step = await self.repository.create_template_step(
                template_id=template.id,
                step_name=step_data.step_name,
                step_type=step_data.step_type,  # type: ignore
                order=step_data.order,
                applies_to=step_data.applies_to,  # type: ignore
            )
            steps.append(step)

        await self.db.commit()
        await self.db.refresh(template)

        return PipelineTemplateResponse(
            id=template.id,
            project_type=template.project_type,
            name=template.name,
            description=template.description,
            created_at=template.created_at,
            archived_at=template.archived_at,
            steps=[PipelineTemplateStepResponse.model_validate(s) for s in steps],
        )

    async def list_templates(
        self,
        offset: int,
        limit: int,
        project_type: str | None = None,
    ) -> PipelineTemplateListResponse:
        templates, total = await self.repository.list_templates(
            offset=offset,
            limit=limit,
            project_type=project_type,
        )

        items = []
        for tmpl in templates:
            steps = await self.repository.list_template_steps(tmpl.id)
            items.append(
                PipelineTemplateResponse(
                    id=tmpl.id,
                    project_type=tmpl.project_type,
                    name=tmpl.name,
                    description=tmpl.description,
                    created_at=tmpl.created_at,
                    archived_at=tmpl.archived_at,
                    steps=[PipelineTemplateStepResponse.model_validate(s) for s in steps],
                )
            )

        return PipelineTemplateListResponse(
            items=items,
            offset=offset,
            limit=limit,
            total=total,
        )

    async def get_template(self, template_id: uuid.UUID) -> PipelineTemplateResponse:
        template = await self.repository.get_template_by_id(template_id)
        if template is None:
            raise NotFoundError("Pipeline template not found")
        steps = await self.repository.list_template_steps(template.id)
        return PipelineTemplateResponse(
            id=template.id,
            project_type=template.project_type,
            name=template.name,
            description=template.description,
            created_at=template.created_at,
            archived_at=template.archived_at,
            steps=[PipelineTemplateStepResponse.model_validate(s) for s in steps],
        )

    async def update_template(
        self,
        template_id: uuid.UUID,
        payload: PipelineTemplateUpdateRequest,
    ) -> PipelineTemplateResponse:
        template = await self.repository.get_template_by_id(template_id)
        if template is None:
            raise NotFoundError("Pipeline template not found")

        if payload.name is not None:
            template.name = payload.name
        if payload.description is not None:
            template.description = payload.description

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        steps = await self.repository.list_template_steps(template.id)
        return PipelineTemplateResponse(
            id=template.id,
            project_type=template.project_type,
            name=template.name,
            description=template.description,
            created_at=template.created_at,
            archived_at=template.archived_at,
            steps=[PipelineTemplateStepResponse.model_validate(s) for s in steps],
        )

    async def archive_template(self, template_id: uuid.UUID) -> PipelineTemplateResponse:
        template = await self.repository.get_template_by_id(template_id)
        if template is None:
            raise NotFoundError("Pipeline template not found")
        template = await self.repository.archive_template(template)
        await self.db.commit()
        steps = await self.repository.list_template_steps(template.id)
        return PipelineTemplateResponse(
            id=template.id,
            project_type=template.project_type,
            name=template.name,
            description=template.description,
            created_at=template.created_at,
            archived_at=template.archived_at,
            steps=[PipelineTemplateStepResponse.model_validate(s) for s in steps],
        )

    async def delete_template(self, template_id: uuid.UUID) -> None:
        template = await self.repository.get_template_by_id(template_id, include_archived=True)
        if template is None:
            raise NotFoundError("Pipeline template not found")
        await self.repository.hard_delete_template(template)
        await self.db.commit()

    # ── Auto-generation ──────────────────────────────────────────────────────

    async def generate_tasks_for_shot(self, shot: object) -> list[PipelineTask]:
        return await self._generate_tasks(
            entity_type="shot",
            shot_id=shot.id,  # type: ignore[attr-defined]
            asset_id=None,
            project_type=None,
            project=None,
            shot_obj=shot,
        )

    async def generate_tasks_for_asset(self, asset: object) -> list[PipelineTask]:
        return await self._generate_tasks(
            entity_type="asset",
            shot_id=None,
            asset_id=asset.id,  # type: ignore[attr-defined]
            project_type=None,
            project=None,
            asset_obj=asset,
        )

    async def _generate_tasks(
        self,
        entity_type: str,
        shot_id: uuid.UUID | None,
        asset_id: uuid.UUID | None,
        project_type: str | None,
        project: object | None,
        shot_obj: object | None = None,
        asset_obj: object | None = None,
    ) -> list[PipelineTask]:
        # Resolve project_type from the entity's project
        if project_type is None:
            from sqlalchemy import select

            from app.models import Project

            if shot_obj is not None:
                project_id = shot_obj.project_id  # type: ignore[attr-defined]
            elif asset_obj is not None:
                project_id = asset_obj.project_id  # type: ignore[attr-defined]
            else:
                return []

            result = await self.db.execute(select(Project).where(Project.id == project_id))
            proj = result.scalar_one_or_none()
            if proj is None or proj.project_type is None:
                return []
            project_type = proj.project_type.value

        template = await self.repository.get_active_template_for_project_type(project_type)
        if template is None:
            return []

        steps = await self.repository.get_steps_for_entity_type(template.id, entity_type)
        if not steps:
            return []

        tasks = []
        for i, step in enumerate(steps):
            status = PipelineTaskStatus.pending if i == 0 else PipelineTaskStatus.blocked
            task = PipelineTask(
                shot_id=shot_id,
                asset_id=asset_id,
                step_name=step.step_name,
                step_type=step.step_type,
                order=step.order,
                status=status,
            )
            tasks.append(task)

        return await self.repository.bulk_create_tasks(tasks)

    # ── Task queries ─────────────────────────────────────────────────────────

    async def list_tasks_for_shot(
        self,
        shot_id: uuid.UUID,
        offset: int,
        limit: int,
        status: PipelineTaskStatus | None = None,
    ) -> PipelineTaskListResponse:
        tasks, total = await self.repository.list_tasks_for_shot(
            shot_id=shot_id,
            offset=offset,
            limit=limit,
            status=status,
        )
        return PipelineTaskListResponse(
            items=[PipelineTaskResponse.model_validate(t) for t in tasks],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def list_tasks_for_asset(
        self,
        asset_id: uuid.UUID,
        offset: int,
        limit: int,
        status: PipelineTaskStatus | None = None,
    ) -> PipelineTaskListResponse:
        tasks, total = await self.repository.list_tasks_for_asset(
            asset_id=asset_id,
            offset=offset,
            limit=limit,
            status=status,
        )
        return PipelineTaskListResponse(
            items=[PipelineTaskResponse.model_validate(t) for t in tasks],
            offset=offset,
            limit=limit,
            total=total,
        )

    async def get_task(self, task_id: uuid.UUID) -> PipelineTaskResponse:
        task = await self.repository.get_task_by_id(task_id)
        if task is None:
            raise NotFoundError("Pipeline task not found")
        return PipelineTaskResponse.model_validate(task)

    async def update_task(
        self,
        task_id: uuid.UUID,
        payload: PipelineTaskUpdateRequest,
        actor_id: uuid.UUID | None = None,
    ) -> PipelineTaskResponse:
        task = await self.repository.get_task_by_id(task_id)
        if task is None:
            raise NotFoundError("Pipeline task not found")

        old_assigned = task.assigned_to

        if payload.assigned_to is not None:
            task.assigned_to = payload.assigned_to
        if payload.due_date is not None:
            task.due_date = payload.due_date
        if payload.notes is not None:
            task.notes = payload.notes

        self.db.add(task)
        await self.db.flush()

        if payload.assigned_to is not None and payload.assigned_to != old_assigned:
            from app.models.notification import NotificationEntityType, NotificationEventType
            from app.services.notification_service import NotificationService

            notification_service = NotificationService(self.db)
            await notification_service.create(
                user_id=payload.assigned_to,
                event_type=NotificationEventType.task_assigned,
                entity_type=NotificationEntityType.pipeline_task,
                entity_id=task.id,
                project_id=None,
                title=f"You were assigned to {task.step_name}",
                actor_id=actor_id,
            )

        await self.db.commit()
        await self.db.refresh(task)
        return PipelineTaskResponse.model_validate(task)

    async def archive_task(self, task_id: uuid.UUID) -> PipelineTaskResponse:
        task = await self.repository.get_task_by_id(task_id)
        if task is None:
            raise NotFoundError("Pipeline task not found")
        task = await self.repository.archive_task(task)
        await self.db.commit()
        return PipelineTaskResponse.model_validate(task)

    async def create_task(
        self,
        shot_id: uuid.UUID | None,
        asset_id: uuid.UUID | None,
        payload: PipelineTaskCreateRequest,
    ) -> PipelineTaskResponse:
        task = await self.repository.create_task(
            shot_id=shot_id,
            asset_id=asset_id,
            step_name=payload.step_name,
            step_type=payload.step_type.value,
            order=payload.order,
            status=payload.status,
        )
        if payload.assigned_to is not None:
            task.assigned_to = payload.assigned_to
        if payload.due_date is not None:
            task.due_date = payload.due_date
        if payload.notes is not None:
            task.notes = payload.notes
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return PipelineTaskResponse.model_validate(task)

    async def delete_task(self, task_id: uuid.UUID) -> None:
        task = await self.repository.get_task_by_id(task_id, include_archived=True)
        if task is None:
            raise NotFoundError("Pipeline task not found")
        await self.repository.hard_delete_task(task)
        await self.db.commit()

    async def apply_template(
        self,
        template_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> ApplyTemplateResponse:
        if entity_type not in ("shot", "asset"):
            raise UnprocessableError("entity_type must be 'shot' or 'asset'")

        template = await self.repository.get_template_by_id(template_id)
        if template is None:
            raise NotFoundError("Pipeline template not found")

        steps = await self.repository.get_steps_for_entity_type(template_id, entity_type)
        if not steps:
            return ApplyTemplateResponse(
                template_id=template_id,
                entity_type=entity_type,
                entity_id=entity_id,
                tasks_created=0,
                tasks=[],
            )

        shot_id = entity_id if entity_type == "shot" else None
        asset_id = entity_id if entity_type == "asset" else None

        tasks = []
        for i, step in enumerate(steps):
            status = PipelineTaskStatus.pending if i == 0 else PipelineTaskStatus.blocked
            task = PipelineTask(
                shot_id=shot_id,
                asset_id=asset_id,
                step_name=step.step_name,
                step_type=step.step_type,
                order=step.order,
                status=status,
            )
            tasks.append(task)

        created = await self.repository.bulk_create_tasks(tasks)
        await self.db.commit()

        return ApplyTemplateResponse(
            template_id=template_id,
            entity_type=entity_type,
            entity_id=entity_id,
            tasks_created=len(created),
            tasks=[PipelineTaskResponse.model_validate(t) for t in created],
        )

    # ── Status transitions ───────────────────────────────────────────────────

    async def update_task_status(
        self,
        task_id: uuid.UUID,
        payload: PipelineTaskStatusUpdateRequest,
        changed_by: uuid.UUID,
    ) -> PipelineTaskStatusUpdateResponse:
        task = await self.repository.get_task_by_id(task_id)
        if task is None:
            raise NotFoundError("Pipeline task not found")

        old_status = task.status
        new_status = payload.status

        # Validate transition
        allowed = VALID_TRANSITIONS.get(old_status, set())
        if new_status not in allowed:
            raise UnprocessableError(
                f"Invalid status transition: {old_status.value} -> {new_status.value}"
            )

        task.status = new_status
        self.db.add(task)
        await self.db.flush()

        # Log the transition
        await self._log_transition(task.id, old_status, new_status, changed_by, payload.comment)

        # If approved, unlock the next task
        if new_status == PipelineTaskStatus.approved:
            next_task = await self.repository.get_next_blocked_task(
                shot_id=task.shot_id,
                asset_id=task.asset_id,
                current_order=task.order,
            )
            if next_task is not None:
                next_old = next_task.status
                next_task.status = PipelineTaskStatus.pending
                self.db.add(next_task)
                await self.db.flush()
                await self._log_transition(
                    next_task.id,
                    next_old,
                    PipelineTaskStatus.pending,
                    changed_by,
                    "Auto-unlocked: previous task approved",
                )

        if task.assigned_to is not None and task.assigned_to != changed_by:
            from app.models.notification import NotificationEntityType, NotificationEventType
            from app.services.notification_service import NotificationService

            notification_service = NotificationService(self.db)
            await notification_service.create(
                user_id=task.assigned_to,
                event_type=NotificationEventType.task_status_changed,
                entity_type=NotificationEntityType.pipeline_task,
                entity_id=task.id,
                project_id=None,
                title=f"{task.step_name} → {new_status.value}",
                actor_id=changed_by,
            )

        await self.db.commit()
        await self.db.refresh(task)

        return PipelineTaskStatusUpdateResponse(
            id=task.id,
            old_status=old_status,
            new_status=new_status,
            comment=payload.comment,
            changed_at=datetime.now(timezone.utc),
        )

    async def _log_transition(
        self,
        task_id: uuid.UUID,
        old_status: PipelineTaskStatus,
        new_status: PipelineTaskStatus,
        changed_by: uuid.UUID,
        comment: str | None,
    ) -> StatusLog:
        log = StatusLog(
            entity_type=StatusLogEntityType.pipeline_task,
            entity_id=task_id,
            old_status=old_status.value,
            new_status=new_status.value,
            changed_by=changed_by,
            comment=comment,
        )
        self.db.add(log)
        await self.db.flush()
        return log

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline_task import (
    PipelineStepAppliesTo,
    PipelineTask,
    PipelineTaskStatus,
    PipelineTemplate,
    PipelineTemplateStep,
)


class PipelineTaskRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Templates ────────────────────────────────────────────────────────────

    async def create_template(
        self,
        project_type: str,
        name: str,
        description: str | None,
    ) -> PipelineTemplate:
        template = PipelineTemplate(
            project_type=project_type,
            name=name,
            description=description,
        )
        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def create_template_step(
        self,
        template_id: uuid.UUID,
        step_name: str,
        step_type: str,
        order: int,
        applies_to: str,
    ) -> PipelineTemplateStep:
        step = PipelineTemplateStep(
            template_id=template_id,
            step_name=step_name,
            step_type=step_type,
            order=order,
            applies_to=applies_to,
        )
        self.db.add(step)
        await self.db.flush()
        await self.db.refresh(step)
        return step

    async def get_template_by_id(
        self,
        template_id: uuid.UUID,
        include_archived: bool = False,
    ) -> PipelineTemplate | None:
        statement = select(PipelineTemplate).where(PipelineTemplate.id == template_id)
        if not include_archived:
            statement = statement.where(PipelineTemplate.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def list_template_steps(self, template_id: uuid.UUID) -> list[PipelineTemplateStep]:
        statement = (
            select(PipelineTemplateStep)
            .where(PipelineTemplateStep.template_id == template_id)
            .order_by(PipelineTemplateStep.order.asc())
        )
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def list_templates(
        self,
        offset: int,
        limit: int,
        project_type: str | None = None,
        include_archived: bool = False,
    ) -> tuple[list[PipelineTemplate], int]:
        statement = select(PipelineTemplate)
        count_statement = select(func.count(PipelineTemplate.id))

        if not include_archived:
            statement = statement.where(PipelineTemplate.archived_at.is_(None))
            count_statement = count_statement.where(PipelineTemplate.archived_at.is_(None))

        if project_type is not None:
            statement = statement.where(PipelineTemplate.project_type == project_type)
            count_statement = count_statement.where(PipelineTemplate.project_type == project_type)

        statement = (
            statement.order_by(PipelineTemplate.created_at.desc()).offset(offset).limit(limit)
        )
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())

        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

    async def archive_template(self, template: PipelineTemplate) -> PipelineTemplate:
        template.archived_at = datetime.now(timezone.utc)
        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def hard_delete_template(self, template: PipelineTemplate) -> None:
        await self.db.delete(template)

    async def get_active_template_for_project_type(
        self, project_type: str
    ) -> PipelineTemplate | None:
        statement = (
            select(PipelineTemplate)
            .where(
                PipelineTemplate.project_type == project_type,
                PipelineTemplate.archived_at.is_(None),
            )
            .order_by(PipelineTemplate.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def get_steps_for_entity_type(
        self,
        template_id: uuid.UUID,
        entity_type: str,
    ) -> list[PipelineTemplateStep]:
        applies_values = [PipelineStepAppliesTo.both]
        if entity_type == "shot":
            applies_values.append(PipelineStepAppliesTo.shot)
        else:
            applies_values.append(PipelineStepAppliesTo.asset)

        statement = (
            select(PipelineTemplateStep)
            .where(
                PipelineTemplateStep.template_id == template_id,
                PipelineTemplateStep.applies_to.in_(applies_values),
            )
            .order_by(PipelineTemplateStep.order.asc())
        )
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    # ── Tasks ────────────────────────────────────────────────────────────────

    async def create_task(
        self,
        shot_id: uuid.UUID | None,
        asset_id: uuid.UUID | None,
        step_name: str,
        step_type: str,
        order: int,
        status: PipelineTaskStatus,
    ) -> PipelineTask:
        task = PipelineTask(
            shot_id=shot_id,
            asset_id=asset_id,
            step_name=step_name,
            step_type=step_type,
            order=order,
            status=status,
        )
        self.db.add(task)
        await self.db.flush()
        return task

    async def bulk_create_tasks(self, tasks: list[PipelineTask]) -> list[PipelineTask]:
        self.db.add_all(tasks)
        await self.db.flush()
        for task in tasks:
            await self.db.refresh(task)
        return tasks

    async def get_task_by_id(
        self,
        task_id: uuid.UUID,
        include_archived: bool = False,
    ) -> PipelineTask | None:
        statement = select(PipelineTask).where(PipelineTask.id == task_id)
        if not include_archived:
            statement = statement.where(PipelineTask.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def list_tasks_for_shot(
        self,
        shot_id: uuid.UUID,
        offset: int,
        limit: int,
        status: PipelineTaskStatus | None = None,
        include_archived: bool = False,
    ) -> tuple[list[PipelineTask], int]:
        return await self._list_tasks(
            shot_id=shot_id,
            asset_id=None,
            offset=offset,
            limit=limit,
            status=status,
            include_archived=include_archived,
        )

    async def list_tasks_for_asset(
        self,
        asset_id: uuid.UUID,
        offset: int,
        limit: int,
        status: PipelineTaskStatus | None = None,
        include_archived: bool = False,
    ) -> tuple[list[PipelineTask], int]:
        return await self._list_tasks(
            shot_id=None,
            asset_id=asset_id,
            offset=offset,
            limit=limit,
            status=status,
            include_archived=include_archived,
        )

    async def _list_tasks(
        self,
        shot_id: uuid.UUID | None,
        asset_id: uuid.UUID | None,
        offset: int,
        limit: int,
        status: PipelineTaskStatus | None,
        include_archived: bool,
    ) -> tuple[list[PipelineTask], int]:
        statement = select(PipelineTask)
        count_statement = select(func.count(PipelineTask.id))

        if shot_id is not None:
            statement = statement.where(PipelineTask.shot_id == shot_id)
            count_statement = count_statement.where(PipelineTask.shot_id == shot_id)
        if asset_id is not None:
            statement = statement.where(PipelineTask.asset_id == asset_id)
            count_statement = count_statement.where(PipelineTask.asset_id == asset_id)

        if not include_archived:
            statement = statement.where(PipelineTask.archived_at.is_(None))
            count_statement = count_statement.where(PipelineTask.archived_at.is_(None))

        if status is not None:
            statement = statement.where(PipelineTask.status == status)
            count_statement = count_statement.where(PipelineTask.status == status)

        statement = statement.order_by(PipelineTask.order.asc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())

        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

    async def get_next_blocked_task(
        self,
        shot_id: uuid.UUID | None,
        asset_id: uuid.UUID | None,
        current_order: int,
    ) -> PipelineTask | None:
        statement = select(PipelineTask).where(
            PipelineTask.status == PipelineTaskStatus.blocked,
            PipelineTask.archived_at.is_(None),
        )
        if shot_id is not None:
            statement = statement.where(PipelineTask.shot_id == shot_id)
        if asset_id is not None:
            statement = statement.where(PipelineTask.asset_id == asset_id)

        statement = statement.where(PipelineTask.order == current_order + 1).limit(1)
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def archive_task(self, task: PipelineTask) -> PipelineTask:
        task.archived_at = datetime.now(timezone.utc)
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def hard_delete_task(self, task: PipelineTask) -> None:
        await self.db.delete(task)

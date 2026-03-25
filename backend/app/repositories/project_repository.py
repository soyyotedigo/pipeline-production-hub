from __future__ import annotations

import builtins
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, Project, ProjectStatus, ProjectType, Role, RoleName, Shot, UserRole


class ProjectRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        name: str,
        code: str,
        client: str | None,
        project_type: ProjectType | None,
        description: str | None,
        created_by: uuid.UUID | None,
        naming_rules: dict[str, object] | None = None,
        path_templates: dict[str, object] | None = None,
    ) -> Project:
        project = Project(
            name=name,
            code=code,
            client=client,
            project_type=project_type,
            description=description,
            created_by=created_by,
            status=ProjectStatus.pending,
            naming_rules=naming_rules,
            path_templates=path_templates,
        )
        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def get_by_id(
        self, project_id: uuid.UUID, include_archived: bool = False
    ) -> Project | None:
        statement = select(Project).where(Project.id == project_id)
        if not include_archived:
            statement = statement.where(Project.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str, include_archived: bool = False) -> Project | None:
        statement = select(Project).where(Project.code == code)
        if not include_archived:
            statement = statement.where(Project.archived_at.is_(None))
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def list(
        self,
        offset: int,
        limit: int,
        status: ProjectStatus | None,
        include_archived: bool = False,
    ) -> tuple[builtins.list[Project], int]:
        statement = select(Project)
        count_statement = select(func.count(Project.id))

        if not include_archived:
            statement = statement.where(Project.archived_at.is_(None))
            count_statement = count_statement.where(Project.archived_at.is_(None))

        if status is not None:
            statement = statement.where(Project.status == status)
            count_statement = count_statement.where(Project.status == status)

        statement = statement.order_by(Project.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())

        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

    async def list_visible_to_user(
        self,
        user_id: uuid.UUID,
        role_names: set[RoleName],
        offset: int,
        limit: int,
        status: ProjectStatus | None,
        include_archived: bool = False,
    ) -> tuple[builtins.list[Project], int]:
        # Use a subquery for distinct project IDs to avoid DISTINCT on non-comparable JSON columns.
        visibility_condition = (UserRole.project_id == Project.id) | (UserRole.project_id.is_(None))
        id_subquery = (
            select(Project.id)
            .join(UserRole, visibility_condition)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                UserRole.user_id == user_id,
                Role.name.in_(role_names),
            )
            .distinct()
        ).subquery()

        statement = select(Project).where(Project.id.in_(select(id_subquery.c.id)))
        count_statement = (
            select(func.count())
            .select_from(Project)
            .where(Project.id.in_(select(id_subquery.c.id)))
        )

        if not include_archived:
            statement = statement.where(Project.archived_at.is_(None))
            count_statement = count_statement.where(Project.archived_at.is_(None))

        if status is not None:
            statement = statement.where(Project.status == status)
            count_statement = count_statement.where(Project.status == status)

        statement = statement.order_by(Project.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(statement)
        rows = list(result.scalars().all())

        total_result = await self.db.execute(count_statement)
        total = int(total_result.scalar_one())
        return rows, total

    async def hard_delete(self, project: Project) -> None:
        await self.db.delete(project)

    async def archive(self, project: Project) -> Project:
        project.archived_at = datetime.now(timezone.utc)
        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def restore(self, project: Project) -> Project:
        project.archived_at = None
        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def count_shots(self, project_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(Shot.id)).where(
                Shot.project_id == project_id, Shot.archived_at.is_(None)
            )
        )
        return int(result.scalar_one())

    async def count_assets(self, project_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(Asset.id)).where(
                Asset.project_id == project_id, Asset.archived_at.is_(None)
            )
        )
        return int(result.scalar_one())

    async def shot_status_counts(self, project_id: uuid.UUID) -> dict[str, int]:
        statement = (
            select(Shot.status, func.count(Shot.id))
            .where(Shot.project_id == project_id, Shot.archived_at.is_(None))
            .group_by(Shot.status)
        )
        result = await self.db.execute(statement)
        return {status.value: int(count) for status, count in result.all()}

    async def asset_status_counts(self, project_id: uuid.UUID) -> dict[str, int]:
        statement = (
            select(Asset.status, func.count(Asset.id))
            .where(Asset.project_id == project_id, Asset.archived_at.is_(None))
            .group_by(Asset.status)
        )
        result = await self.db.execute(statement)
        return {status.value: int(count) for status, count in result.all()}

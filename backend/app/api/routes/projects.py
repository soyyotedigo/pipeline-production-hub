import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import ProjectStatus, User
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectExportAcceptedResponse,
    ProjectListResponse,
    ProjectOverviewResponse,
    ProjectReportResponse,
    ProjectResponse,
    ProjectUpdateRequest,
    ScaffoldRequest,
    ScaffoldResponse,
)
from app.services.project_service import ProjectService

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.post(
    "",
    response_model=ProjectResponse,
    summary="Create Project",
    description="Create a new project with optional client and type metadata.",
)
async def create_project(
    payload: ProjectCreateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ProjectResponse:
    service = ProjectService(db)
    return await service.create_project(payload, current_user)


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="List Projects",
    description="List accessible projects with pagination and optional status filter.",
)
async def list_projects(
    current_user: CurrentUserDep,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: ProjectStatus | None = Query(default=None),
    include_archived: bool = Query(default=False),
) -> ProjectListResponse:
    service = ProjectService(db)
    return await service.list_projects(
        current_user=current_user,
        offset=offset,
        limit=limit,
        status=status,
        include_archived=include_archived,
    )


@router.patch(
    "/{id}",
    response_model=ProjectResponse,
    summary="Update Project",
    description="Patch mutable project fields such as name, status, client, or description.",
)
async def patch_project(
    id: uuid.UUID,
    payload: ProjectUpdateRequest,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ProjectResponse:
    service = ProjectService(db)
    return await service.patch_project(
        project_id=id,
        payload=payload,
        current_user=current_user,
    )


@router.get(
    "/{id}",
    response_model=ProjectResponse,
    summary="Get Project",
    description="Get a single project by id.",
)
async def get_project(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ProjectResponse:
    service = ProjectService(db)
    return await service.get_project(project_id=id, current_user=current_user)


@router.post(
    "/{id}/archive",
    response_model=ProjectResponse,
    summary="Archive Project",
    description="Archive a project (soft delete).",
)
async def archive_project(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ProjectResponse:
    service = ProjectService(db)
    return await service.archive_project(project_id=id, current_user=current_user)


@router.post(
    "/{id}/restore",
    response_model=ProjectResponse,
    summary="Restore Project",
    description="Restore a previously archived project.",
)
async def restore_project(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ProjectResponse:
    service = ProjectService(db)
    return await service.restore_project(project_id=id, current_user=current_user)


@router.delete(
    "/{id}",
    status_code=204,
    summary="Delete Project",
    description="Hard delete a project (admin only) with force=true.",
)
async def delete_project(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    force: bool = Query(default=False),
) -> None:
    service = ProjectService(db)
    await service.delete_project(project_id=id, current_user=current_user, force=force)


@router.get(
    "/{id}/overview",
    response_model=ProjectOverviewResponse,
    summary="Get Project Overview",
    description="Return aggregate shot/asset counts by status plus completion percentage.",
)
async def get_project_overview(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ProjectOverviewResponse:
    service = ProjectService(db)
    return await service.get_project_overview(
        project_id=id,
        current_user=current_user,
    )


@router.get(
    "/{id}/report",
    response_model=ProjectReportResponse,
    summary="Get Project Report",
    description="Return detailed project KPIs including storage usage and recent activity.",
)
async def get_project_report(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ProjectReportResponse:
    service = ProjectService(db)
    return await service.get_project_report(
        project_id=id,
        current_user=current_user,
    )


@router.post(
    "/{id}/scaffold",
    response_model=ScaffoldResponse,
    summary="Scaffold Project Filesystem",
    description=(
        "Generate (and optionally create) the full directory tree for the project. "
        "Pass 'root' to override the default storage root (e.g. 'E:/projects'). "
        "Set 'create': true to materialize the folders on disk (local storage only)."
    ),
)
async def scaffold_project(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    payload: ScaffoldRequest = ScaffoldRequest(),
) -> ScaffoldResponse:
    service = ProjectService(db)
    return await service.scaffold_project_filesystem(
        project_id=id,
        payload=payload,
        current_user=current_user,
    )


@router.get(
    "/{id}/export",
    response_model=ProjectExportAcceptedResponse,
    summary="Export Project Data",
    description=(
        "Export project shots/assets as CSV. For small projects the CSV is streamed immediately; "
        "for large projects it returns 202 with a task id."
    ),
    responses={202: {"description": "Export accepted and running asynchronously"}},
)
async def export_project(
    id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
    format: Literal["csv"] = Query(default="csv"),
) -> Response:
    del format
    service = ProjectService(db)
    result = await service.export_project_csv(
        project_id=id,
        current_user=current_user,
    )

    if isinstance(result, ProjectExportAcceptedResponse):
        return JSONResponse(status_code=202, content=result.model_dump(mode="json"))

    file_name, csv_bytes = result

    async def stream_csv(content: bytes) -> AsyncIterator[bytes]:
        yield content

    return StreamingResponse(
        stream_csv(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )

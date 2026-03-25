from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import RequestLoggingMiddleware
from app.api.routes import (
    assets,
    auth,
    deliveries,
    departments,
    episodes,
    files,
    health,
    metrics,
    notes,
    notifications,
    pipeline_tasks,
    playlists,
    projects,
    sequences,
    shot_asset_links,
    shots,
    tags,
    tasks,
    time_logs,
    users,
    versions,
    webhooks,
)
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.metrics import configure_metrics
from app.db.session import engine

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup / shutdown resources."""
    # Startup: nothing heavy yet — DB connections are lazily created per request
    yield
    # Shutdown: dispose the async engine connection pool cleanly
    await engine.dispose()


app = FastAPI(
    title="Pipeline Production Hub",
    version="0.1.0",
    description="Production pipeline management system for VFX studios",
    lifespan=lifespan,
)

configure_metrics(app)

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)


# ── Exception handlers ────────────────────────────────────────────────────────
register_exception_handlers(app)

# ── Routers — mount here as features are implemented ─────────────────────────
app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(projects.router, prefix="/projects", tags=["project"])
app.include_router(shots.project_router, prefix="/projects", tags=["project"])
app.include_router(assets.project_router, prefix="/projects", tags=["project"])
app.include_router(files.project_router, prefix="/projects", tags=["project"])
app.include_router(files.shots_router, prefix="/shots", tags=["shots"])
app.include_router(files.assets_router, prefix="/assets", tags=["assets"])
app.include_router(episodes.project_router, prefix="/projects", tags=["project"])
app.include_router(sequences.project_router, prefix="/projects", tags=["project"])
app.include_router(episodes.router, prefix="/episodes", tags=["episodes"])
app.include_router(sequences.router, prefix="/sequences", tags=["sequences"])
app.include_router(shots.router, prefix="/shots", tags=["shots"])
app.include_router(assets.router, prefix="/assets", tags=["assets"])
app.include_router(files.router, prefix="/files", tags=["files"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
app.include_router(webhooks.projects_router, prefix="/projects", tags=["project"])
app.include_router(
    pipeline_tasks.template_router, prefix="/pipeline-templates", tags=["pipeline-templates"]
)
app.include_router(pipeline_tasks.shot_tasks_router, prefix="/shots", tags=["shots"])
app.include_router(pipeline_tasks.asset_tasks_router, prefix="/assets", tags=["assets"])
app.include_router(
    pipeline_tasks.task_ops_router, prefix="/pipeline-tasks", tags=["pipeline-tasks"]
)
app.include_router(notes.router, prefix="/notes", tags=["notes"])
app.include_router(notes.shots_router, prefix="/shots", tags=["shots"])
app.include_router(notes.assets_router, prefix="/assets", tags=["assets"])
app.include_router(notes.pipeline_tasks_router, prefix="/pipeline-tasks", tags=["pipeline-tasks"])
app.include_router(notes.projects_router, prefix="/projects", tags=["project"])
app.include_router(versions.router, prefix="/versions", tags=["versions"])
app.include_router(versions.project_router, prefix="/projects", tags=["project"])
app.include_router(versions.shots_router, prefix="/shots", tags=["shots"])
app.include_router(versions.assets_router, prefix="/assets", tags=["assets"])
app.include_router(
    versions.pipeline_tasks_router, prefix="/pipeline-tasks", tags=["pipeline-tasks"]
)
app.include_router(shot_asset_links.shots_router, prefix="/shots", tags=["shots"])
app.include_router(shot_asset_links.assets_router, prefix="/assets", tags=["assets"])
app.include_router(
    shot_asset_links.shot_asset_links_router, prefix="/shot-asset-links", tags=["shots"]
)
app.include_router(playlists.router, prefix="/playlists", tags=["playlists"])
app.include_router(playlists.projects_router, prefix="/projects", tags=["project"])
app.include_router(playlists.playlist_items_router, prefix="/playlist-items", tags=["playlists"])
app.include_router(departments.router, prefix="/departments", tags=["departments"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(departments.users_router, prefix="/users", tags=["users"])
app.include_router(
    departments.department_members_router, prefix="/department-members", tags=["departments"]
)
app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
app.include_router(tags.router, prefix="/tags", tags=["tags"])
app.include_router(tags.projects_router, prefix="/projects", tags=["project"])
app.include_router(tags.shots_router, prefix="/shots", tags=["shots"])
app.include_router(tags.assets_router, prefix="/assets", tags=["assets"])
app.include_router(tags.sequences_router, prefix="/sequences", tags=["sequences"])
app.include_router(tags.entity_tags_router, prefix="/entity-tags", tags=["tags"])
app.include_router(time_logs.router, prefix="/timelogs", tags=["timelogs"])
app.include_router(time_logs.projects_router, prefix="/projects", tags=["project"])
app.include_router(time_logs.tasks_router, prefix="/pipeline-tasks", tags=["pipeline-tasks"])
app.include_router(time_logs.users_router, prefix="/users", tags=["users"])
app.include_router(deliveries.router, prefix="/deliveries", tags=["deliveries"])
app.include_router(deliveries.projects_router, prefix="/projects", tags=["project"])
app.include_router(deliveries.delivery_items_router, prefix="/delivery-items", tags=["deliveries"])

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _api import PipelineApiClient, PublishContext

StatusReporter = Callable[[str], None]


@dataclass(frozen=True)
class EntityLocator:
    project_id: str | None = None
    project_code: str | None = None
    shot_id: str | None = None
    shot_code: str | None = None
    asset_id: str | None = None
    asset_code: str | None = None


@dataclass(frozen=True)
class PublishRequest:
    task_id: str
    primary_file: Path
    preview_file: Path | None = None
    description: str | None = None
    set_task_status: str | None = None
    status_comment: str | None = None
    source_label: str = "CLI"


@dataclass(frozen=True)
class PublishResult:
    user: dict[str, Any]
    context: PublishContext
    uploaded_files: list[dict[str, Any]]
    version: dict[str, Any]
    status_update: dict[str, Any] | None


def ensure_task(
    client: PipelineApiClient,
    *,
    task_id: str | None,
    locator: EntityLocator,
    step_type: str | None,
    step_name: str | None,
    order: int,
    initial_status: str,
    notify: StatusReporter,
) -> str:
    if task_id is not None:
        return task_id

    if step_type is None:
        raise ValueError("step_type is required when task_id is not provided")

    resolved_step_name = step_name or step_type.replace("_", " ").title()
    entity = resolve_entity_locator(client, locator)
    notify(
        f"Creating a new {entity['entity_type']} pipeline task "
        f"for {entity['entity_code']} ({resolved_step_name})."
    )

    if entity["entity_type"] == "shot":
        task = client.create_shot_task(
            shot_id=entity["entity_id"],
            step_name=resolved_step_name,
            step_type=step_type,
            order=order,
            status=initial_status,
        )
    else:
        task = client.create_asset_task(
            asset_id=entity["entity_id"],
            step_name=resolved_step_name,
            step_type=step_type,
            order=order,
            status=initial_status,
        )

    return str(task["id"])


def resolve_entity_locator(client: PipelineApiClient, locator: EntityLocator) -> dict[str, str]:
    _validate_locator(locator)

    if locator.shot_id is not None:
        shot = client.get_shot(locator.shot_id)
        return {
            "entity_type": "shot",
            "entity_id": str(shot["id"]),
            "entity_code": str(shot["code"]),
            "project_id": str(shot["project_id"]),
        }

    if locator.asset_id is not None:
        asset = client.get_asset(locator.asset_id)
        return {
            "entity_type": "asset",
            "entity_id": str(asset["id"]),
            "entity_code": str(asset.get("code") or asset["name"]),
            "project_id": str(asset["project_id"]),
        }

    project_id = locator.project_id or _resolve_project_id_by_code(client, locator.project_code)

    if locator.shot_code is not None:
        for shot in client.list_project_shots(project_id):
            if str(shot["code"]) == locator.shot_code:
                return {
                    "entity_type": "shot",
                    "entity_id": str(shot["id"]),
                    "entity_code": str(shot["code"]),
                    "project_id": project_id,
                }
        raise RuntimeError(f"Shot code '{locator.shot_code}' not found in project {project_id}")

    if locator.asset_code is not None:
        for asset in client.list_project_assets(project_id):
            if str(asset.get("code") or asset["name"]) == locator.asset_code:
                return {
                    "entity_type": "asset",
                    "entity_id": str(asset["id"]),
                    "entity_code": str(asset.get("code") or asset["name"]),
                    "project_id": project_id,
                }
        raise RuntimeError(f"Asset code '{locator.asset_code}' not found in project {project_id}")

    raise RuntimeError("Unable to resolve a shot or asset from the provided locator")


def run_publish(
    client: PipelineApiClient,
    request: PublishRequest,
    *,
    notify: StatusReporter,
) -> PublishResult:
    _ensure_local_file(request.primary_file)
    if request.preview_file is not None:
        _ensure_local_file(request.preview_file)

    user = client.get_me()
    context = client.resolve_publish_context(request.task_id)

    notify(
        f"Authenticated as {user['email']}. "
        f"Resolved {context.entity_type} {context.entity_code} / {context.task_step_type}."
    )

    uploaded_files: list[dict[str, Any]] = []
    uploaded_files.append(
        _upload_file_for_context(
            client, context=context, file_path=request.primary_file, notify=notify
        )
    )

    if request.preview_file is not None:
        uploaded_files.append(
            _upload_file_for_context(
                client, context=context, file_path=request.preview_file, notify=notify
            )
        )

    # The current API links files to a Version at creation time via file_ids, so the
    # example uploads first and creates the version second instead of inventing a fake route.
    file_ids = [str(item["id"]) for item in uploaded_files]
    description = request.description or _default_description(context, request)
    notify("Creating a reviewable Version and associating uploaded file ids.")
    version = client.create_version(
        task_id=request.task_id, description=description, file_ids=file_ids
    )

    status_update: dict[str, Any] | None = None
    if request.set_task_status is not None:
        comment = request.status_comment or f"Publish submitted from {request.source_label}"
        notify(f"Updating pipeline task status to {request.set_task_status}.")
        status_update = client.update_pipeline_task_status(
            task_id=request.task_id,
            status=request.set_task_status,
            comment=comment,
        )

    return PublishResult(
        user=user,
        context=context,
        uploaded_files=uploaded_files,
        version=version,
        status_update=status_update,
    )


def render_summary(result: PublishResult) -> str:
    lines = [
        "Publish succeeded.",
        f"User: {result.user['email']}",
        f"Entity: {result.context.entity_type} {result.context.entity_code}",
        f"Task: {result.context.task_id} ({result.context.task_step_type})",
        f"Version: {result.version['code']}",
        f"Version ID: {result.version['id']}",
        "Uploaded files:",
    ]

    for item in result.uploaded_files:
        lines.append(f"- {item['original_name']} -> {item['storage_path']}")

    final_status = result.context.task_status
    if result.status_update is not None:
        final_status = str(result.status_update["new_status"])
    lines.append(f"Task status: {final_status}")
    return "\n".join(lines)


def _upload_file_for_context(
    client: PipelineApiClient,
    *,
    context: PublishContext,
    file_path: Path,
    notify: StatusReporter,
) -> dict[str, Any]:
    notify(f"Uploading {file_path.name} to {context.entity_type} {context.entity_code}.")
    shot_id = context.entity_id if context.entity_type == "shot" else None
    asset_id = context.entity_id if context.entity_type == "asset" else None
    return client.upload_project_file(
        project_id=context.project_id,
        file_path=file_path,
        shot_id=shot_id,
        asset_id=asset_id,
    )


def _resolve_project_id_by_code(client: PipelineApiClient, project_code: str | None) -> str:
    if project_code is None:
        raise ValueError("project_code is required when project_id is not provided")

    for project in client.list_projects():
        if str(project["code"]) == project_code:
            return str(project["id"])

    raise RuntimeError(f"Project code '{project_code}' not found among accessible projects")


def _validate_locator(locator: EntityLocator) -> None:
    shot_flags = [locator.shot_id is not None, locator.shot_code is not None]
    asset_flags = [locator.asset_id is not None, locator.asset_code is not None]

    if any(shot_flags) and any(asset_flags):
        raise ValueError("Provide shot locator or asset locator, not both")

    if not any(shot_flags) and not any(asset_flags):
        raise ValueError("Provide either a shot locator or an asset locator")

    if (
        locator.shot_id is None
        and locator.asset_id is None
        and locator.project_id is None
        and locator.project_code is None
    ):
        raise ValueError(
            "project_id or project_code is required when using shot_code or asset_code"
        )


def _ensure_local_file(file_path: Path) -> None:
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if not file_path.is_file():
        raise FileNotFoundError(f"Path is not a file: {file_path}")


def _default_description(context: PublishContext, request: PublishRequest) -> str:
    return (
        f"{request.source_label} publish for {context.entity_code} "
        f"({context.task_step_type}) using {request.primary_file.name}"
    )

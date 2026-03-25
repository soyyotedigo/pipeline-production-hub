from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from io import BytesIO, StringIO
from typing import Any
from urllib import error, request

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.repositories.asset_repository import AssetRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.shot_repository import ShotRepository
from app.repositories.task_queue_repository import TaskQueueRepository
from app.schemas.task import TaskType
from app.services.storage import get_storage_backend


async def _run_thumbnail_stub(payload: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(0.05)
    return {
        "job": "thumbnail",
        "status": "generated",
        "entity_type": payload.get("entity_type"),
        "entity_id": payload.get("entity_id"),
        "file_id": payload.get("file_id"),
    }


async def _run_checksum_stub(payload: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(0.05)
    return {
        "job": "checksum_large_file",
        "status": "verified",
        "file_id": payload.get("file_id"),
        "checksum": payload.get("checksum_sha256"),
        "size_bytes": payload.get("size_bytes"),
    }


def _post_webhook(url: str, headers: dict[str, str], body_bytes: bytes, timeout: int) -> int:
    req = request.Request(url=url, data=body_bytes, headers=headers, method="POST")
    with request.urlopen(req, timeout=timeout) as response:
        return int(response.status)


async def _run_webhook_dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    url = str(payload["url"])
    event = str(payload["event"])
    secret = str(payload["secret"])

    body = payload.get("body", {})
    if not isinstance(body, dict):
        body = {}
    body_json = json.dumps(body, separators=(",", ":"), sort_keys=True)
    body_bytes = body_json.encode("utf-8")

    signature = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": event,
        "X-Webhook-Signature": signature,
    }

    retry_delays = [1, 5, 25]
    last_error: str | None = None

    for attempt, delay_seconds in enumerate(retry_delays, start=1):
        try:
            status_code = await asyncio.to_thread(_post_webhook, url, headers, body_bytes, 10)
            if 200 <= status_code < 300:
                return {
                    "job": "webhook_dispatch",
                    "status": "delivered",
                    "attempts": attempt,
                    "status_code": status_code,
                }
            last_error = f"HTTP {status_code}"
        except error.URLError as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)

        if attempt < len(retry_delays):
            await asyncio.sleep(delay_seconds)

    raise RuntimeError(last_error or "Webhook dispatch failed")


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.isoformat()


def _build_project_csv_bytes(project_id: uuid.UUID, shots: list[Any], assets: list[Any]) -> bytes:
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
                _format_datetime(shot.created_at),
            ]
        )

    for asset in assets:
        writer.writerow(
            [
                "asset",
                str(asset.id),
                str(project_id),
                "",
                asset.name,
                asset.status.value,
                str(asset.assigned_to) if asset.assigned_to is not None else "",
                "",
                "",
                asset.asset_type.value,
                _format_datetime(asset.created_at),
            ]
        )

    return buffer.getvalue().encode("utf-8")


async def _run_project_export_csv(payload: dict[str, Any]) -> dict[str, Any]:
    project_id_raw = payload.get("project_id")
    if project_id_raw is None:
        raise RuntimeError("Missing project_id")

    project_id = uuid.UUID(str(project_id_raw))

    async with AsyncSessionLocal() as db:
        project_repository = ProjectRepository(db)
        shot_repository = ShotRepository(db)
        asset_repository = AssetRepository(db)

        project = await project_repository.get_by_id(project_id)
        if project is None:
            raise RuntimeError("Project not found")

        shots = await shot_repository.list_all_for_project(project_id)
        assets = await asset_repository.list_all_for_project(project_id)

    csv_bytes = _build_project_csv_bytes(project_id, shots, assets)
    file_name = (
        f"{project.code.lower()}_export_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.csv"
    )
    storage_path = f"exports/projects/{project.code.lower()}/{file_name}"

    storage = get_storage_backend()
    await storage.upload(storage_path, BytesIO(csv_bytes))
    download_url = await storage.get_url(storage_path, expires=settings.storage_url_expires_default)

    return {
        "job": "project_export_csv",
        "project_id": str(project_id),
        "entity_count": len(shots) + len(assets),
        "file_name": file_name,
        "storage_path": storage_path,
        "download_url": download_url,
    }


async def _process_task(queue: TaskQueueRepository, task_data: dict[str, Any]) -> None:
    task_id = uuid.UUID(str(task_data["id"]))
    task_type = TaskType(str(task_data["task_type"]))
    payload = task_data.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    # Skip tasks that were cancelled before the worker picked them up
    current_status = await queue.get_task_status(task_id)
    if current_status and current_status.get("status") == "cancelled":
        return

    await queue.mark_running(task_id)

    try:
        if task_type is TaskType.thumbnail:
            result = await _run_thumbnail_stub(payload)
        elif task_type is TaskType.checksum_large_file:
            result = await _run_checksum_stub(payload)
        elif task_type is TaskType.webhook_dispatch:
            result = await _run_webhook_dispatch(payload)
        elif task_type is TaskType.project_export_csv:
            result = await _run_project_export_csv(payload)
        else:
            raise ValueError(f"Unsupported task type: {task_type.value}")
        await queue.mark_completed(task_id, result)
    except Exception as exc:
        await queue.mark_failed(task_id, str(exc))


async def main() -> None:
    queue = TaskQueueRepository()
    while True:
        task_data = await queue.dequeue_task(timeout_seconds=5)
        if task_data is None:
            await asyncio.sleep(0.1)
            continue
        await _process_task(queue, task_data)


if __name__ == "__main__":
    asyncio.run(main())

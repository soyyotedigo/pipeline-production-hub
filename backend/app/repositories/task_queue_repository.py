from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, cast

from redis.asyncio import Redis

from app.core.config import settings
from app.schemas.task import TaskStatus, TaskType


class TaskQueueRepository:
    def __init__(self) -> None:
        self.queue_key = settings.task_queue_name
        self.status_ttl_seconds = settings.task_status_ttl_seconds

    @staticmethod
    def _status_key(task_id: str) -> str:
        return f"tasks:status:{task_id}"

    @staticmethod
    def _user_index_key(user_id: str) -> str:
        return f"tasks:user:{user_id}"

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _redis_client() -> Redis[str]:
        return Redis.from_url(settings.redis_url, decode_responses=True)

    async def enqueue_task(
        self,
        *,
        task_id: uuid.UUID,
        task_type: TaskType,
        created_by: uuid.UUID,
        payload: dict[str, Any],
    ) -> None:
        task_id_str = str(task_id)
        now = self._utc_now_iso()
        status_key = self._status_key(task_id_str)
        user_index_key = self._user_index_key(str(created_by))
        queue_item = {
            "id": task_id_str,
            "task_type": task_type.value,
            "created_by": str(created_by),
            "payload": payload,
        }

        redis_client = self._redis_client()
        try:
            pipe = redis_client.pipeline()
            pipe.hset(
                status_key,
                mapping={
                    "id": task_id_str,
                    "task_type": task_type.value,
                    "status": TaskStatus.pending.value,
                    "created_by": str(created_by),
                    "created_at": now,
                    "updated_at": now,
                    "result_json": "",
                    "error": "",
                },
            )
            pipe.expire(status_key, self.status_ttl_seconds)
            # Track by user with timestamp as score for ordered listing
            pipe.zadd(user_index_key, {task_id_str: datetime.now(timezone.utc).timestamp()})
            pipe.expire(user_index_key, self.status_ttl_seconds)
            pipe.lpush(self.queue_key, json.dumps(queue_item))
            await pipe.execute()
        finally:
            await redis_client.close()

    async def dequeue_task(self, timeout_seconds: int = 5) -> dict[str, Any] | None:
        redis_client = self._redis_client()
        try:
            popped = await redis_client.brpop(self.queue_key, timeout=timeout_seconds)
            if popped is None:
                return None
            _, raw_payload = popped
            return dict(json.loads(raw_payload))
        finally:
            await redis_client.close()

    async def get_task_status(self, task_id: uuid.UUID) -> dict[str, str] | None:
        redis_client = self._redis_client()
        try:
            data = await redis_client.hgetall(self._status_key(str(task_id)))
            return data or None
        finally:
            await redis_client.close()

    async def list_user_tasks(
        self,
        user_id: uuid.UUID,
        offset: int,
        limit: int,
        status_filter: str | None,
    ) -> tuple[list[dict[str, str]], int]:
        """Return paginated task records for a user, newest first."""
        redis_client = self._redis_client()
        try:
            # Get all task IDs for this user (sorted by score desc = newest first)
            user_index_key = self._user_index_key(str(user_id))
            all_ids: list[str] = await redis_client.zrevrange(user_index_key, 0, -1)

            # Hydrate and optionally filter by status
            records: list[dict[str, str]] = []
            for task_id_str in all_ids:
                data = await redis_client.hgetall(self._status_key(task_id_str))
                if not data:
                    continue
                if status_filter is not None and data.get("status") != status_filter:
                    continue
                records.append(data)

            total = len(records)
            page = records[offset : offset + limit]
            return page, total
        finally:
            await redis_client.close()

    async def mark_cancelled(self, task_id: uuid.UUID) -> None:
        await self._update_status(
            task_id=task_id,
            status=TaskStatus.cancelled,
            error="Cancelled by user",
        )

    async def mark_running(self, task_id: uuid.UUID) -> None:
        await self._update_status(task_id=task_id, status=TaskStatus.running)

    async def mark_completed(self, task_id: uuid.UUID, result: dict[str, Any]) -> None:
        await self._update_status(
            task_id=task_id, status=TaskStatus.completed, result=result, error=""
        )

    async def mark_failed(self, task_id: uuid.UUID, error: str) -> None:
        await self._update_status(
            task_id=task_id, status=TaskStatus.failed, result=None, error=error
        )

    async def _update_status(
        self,
        *,
        task_id: uuid.UUID,
        status: TaskStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        now = self._utc_now_iso()
        mapping: dict[str, str] = {
            "status": status.value,
            "updated_at": now,
        }

        if result is not None:
            mapping["result_json"] = json.dumps(result)
        if error is not None:
            mapping["error"] = error

        redis_client = self._redis_client()
        try:
            status_key = self._status_key(str(task_id))
            await redis_client.hset(status_key, mapping=cast("dict[Any, Any]", mapping))
            await redis_client.expire(status_key, self.status_ttl_seconds)
        finally:
            await redis_client.close()

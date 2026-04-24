from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None


class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, status_code: int, body: str) -> None:
        super().__init__(f"{method} {path} failed with {status_code}: {body}")
        self.method = method
        self.path = path
        self.status_code = status_code
        self.body = body


@dataclass(frozen=True)
class PublishContext:
    task_id: str
    project_id: str
    entity_type: str
    entity_id: str
    entity_code: str
    task_step_name: str
    task_step_type: str
    task_status: str


class PipelineApiClient:
    def __init__(self, base_url: str, timeout_seconds: float = 30.0) -> None:
        if httpx is None:
            raise RuntimeError(
                "This example requires 'httpx'. Install the local dev environment with "
                '`pip install -e ".[dev,test]"` or use the repository .venv.'
            )

        self.base_url = base_url.rstrip("/")
        self._access_token: str | None = None
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PipelineApiClient:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def login(self, email: str, password: str) -> dict[str, Any]:
        payload = {"email": email, "password": password}
        response = self._request("POST", "/api/v1/auth/login", json=payload, expected={200})
        self._access_token = str(response["access_token"])
        return response

    def get_me(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/auth/me", expected={200})

    def list_projects(self, limit: int = 100) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            "/api/v1/projects",
            params={"offset": 0, "limit": limit},
            expected={200},
        )
        return list(response["items"])

    def get_project(self, project_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/projects/{project_id}", expected={200})

    def list_project_shots(self, project_id: str, limit: int = 100) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            f"/api/v1/projects/{project_id}/shots",
            params={"offset": 0, "limit": limit},
            expected={200},
        )
        return list(response["items"])

    def list_project_assets(self, project_id: str, limit: int = 100) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            f"/api/v1/projects/{project_id}/assets",
            params={"offset": 0, "limit": limit},
            expected={200},
        )
        return list(response["items"])

    def get_shot(self, shot_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/shots/{shot_id}", expected={200})

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/assets/{asset_id}", expected={200})

    def list_shot_tasks(self, shot_id: str, limit: int = 50) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            f"/api/v1/shots/{shot_id}/tasks",
            params={"offset": 0, "limit": limit},
            expected={200},
        )
        return list(response["items"])

    def list_asset_tasks(self, asset_id: str, limit: int = 50) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            f"/api/v1/assets/{asset_id}/tasks",
            params={"offset": 0, "limit": limit},
            expected={200},
        )
        return list(response["items"])

    def get_pipeline_task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/pipeline-tasks/{task_id}", expected={200})

    def create_shot_task(
        self,
        *,
        shot_id: str,
        step_name: str,
        step_type: str,
        order: int,
        status: str = "pending",
    ) -> dict[str, Any]:
        payload = {
            "step_name": step_name,
            "step_type": step_type,
            "order": order,
            "status": status,
        }
        return self._request(
            "POST",
            f"/api/v1/shots/{shot_id}/tasks",
            json=payload,
            expected={201},
        )

    def create_asset_task(
        self,
        *,
        asset_id: str,
        step_name: str,
        step_type: str,
        order: int,
        status: str = "pending",
    ) -> dict[str, Any]:
        payload = {
            "step_name": step_name,
            "step_type": step_type,
            "order": order,
            "status": status,
        }
        return self._request(
            "POST",
            f"/api/v1/assets/{asset_id}/tasks",
            json=payload,
            expected={201},
        )

    def create_version(
        self,
        *,
        task_id: str,
        description: str | None,
        file_ids: list[str],
    ) -> dict[str, Any]:
        payload = {
            "description": description,
            "thumbnail_url": None,
            "media_url": None,
            "file_ids": file_ids,
        }
        return self._request(
            "POST",
            f"/api/v1/pipeline-tasks/{task_id}/versions",
            json=payload,
            expected={201},
        )

    def upload_project_file(
        self,
        *,
        project_id: str,
        file_path: Path,
        shot_id: str | None,
        asset_id: str | None,
    ) -> dict[str, Any]:
        if shot_id is None and asset_id is None:
            raise ValueError("File upload requires either shot_id or asset_id")

        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        data: dict[str, str] = {}
        if shot_id is not None:
            data["shot_id"] = shot_id
        if asset_id is not None:
            data["asset_id"] = asset_id

        with file_path.open("rb") as stream:
            files = {"upload": (file_path.name, stream, mime_type)}
            return self._request(
                "POST",
                f"/api/v1/projects/{project_id}/files/upload",
                data=data,
                files=files,
                expected={200},
            )

    def update_pipeline_task_status(
        self, *, task_id: str, status: str, comment: str | None
    ) -> dict[str, Any]:
        payload = {"status": status, "comment": comment}
        return self._request(
            "PATCH",
            f"/api/v1/pipeline-tasks/{task_id}/status",
            json=payload,
            expected={200},
        )

    def resolve_publish_context(self, task_id: str) -> PublishContext:
        task = self.get_pipeline_task(task_id)

        shot_id = task.get("shot_id")
        asset_id = task.get("asset_id")
        if shot_id:
            shot = self.get_shot(str(shot_id))
            return PublishContext(
                task_id=str(task["id"]),
                project_id=str(shot["project_id"]),
                entity_type="shot",
                entity_id=str(shot["id"]),
                entity_code=str(shot["code"]),
                task_step_name=str(task["step_name"]),
                task_step_type=str(task["step_type"]),
                task_status=str(task["status"]),
            )

        if asset_id:
            asset = self.get_asset(str(asset_id))
            return PublishContext(
                task_id=str(task["id"]),
                project_id=str(asset["project_id"]),
                entity_type="asset",
                entity_id=str(asset["id"]),
                entity_code=str(asset.get("code") or asset["name"]),
                task_step_name=str(task["step_name"]),
                task_step_type=str(task["step_type"]),
                task_status=str(task["status"]),
            )

        raise RuntimeError("Pipeline task is not linked to a shot or asset")

    def _request(
        self,
        method: str,
        path: str,
        *,
        expected: set[int],
        **kwargs: Any,
    ) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}))
        if self._access_token is not None:
            headers["Authorization"] = f"Bearer {self._access_token}"

        response = self._client.request(method, path, headers=headers, **kwargs)
        if response.status_code not in expected:
            raise ApiError(method, path, response.status_code, self._format_body(response))

        if response.status_code == 204:
            return {}

        return dict(response.json())

    @staticmethod
    def _format_body(response: Any) -> str:
        try:
            payload = response.json()
        except ValueError:
            text = response.text.strip()
            return text[:500] if text else "<empty response body>"

        return json.dumps(payload, ensure_ascii=True)[:500]

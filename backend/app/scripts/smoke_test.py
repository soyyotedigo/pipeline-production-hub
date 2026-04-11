from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SmokeConfig:
    base_url: str
    email: str
    password: str
    timeout: float


class SmokeTestError(RuntimeError):
    pass


def _get_default_config() -> SmokeConfig:
    return SmokeConfig(
        base_url=os.getenv("SMOKE_BASE_URL", "http://localhost:8000").rstrip("/"),
        email=os.getenv("SMOKE_EMAIL", os.getenv("SEED_ADMIN_EMAIL", "admin@vfxhub.dev")),
        password=os.getenv("SMOKE_PASSWORD", os.getenv("SEED_ADMIN_PASSWORD", "admin123")),
        timeout=float(os.getenv("SMOKE_TIMEOUT_SECONDS", "10")),
    )


def _build_parser(defaults: SmokeConfig) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Run a basic end-to-end smoke test against the Pipeline Production Hub API.")
    )
    parser.add_argument("--base-url", default=defaults.base_url, help="API base URL.")
    parser.add_argument("--email", default=defaults.email, help="Login email.")
    parser.add_argument("--password", default=defaults.password, help="Login password.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=defaults.timeout,
        help="Per-request timeout in seconds.",
    )
    return parser


def _request(
    *,
    method: str,
    url: str,
    timeout: float,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    data: bytes | None = None
    headers = {"Accept": "application/json"}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        url=url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.getcode()
            raw_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw_body = exc.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise SmokeTestError(f"{method} {url} failed: {exc.reason}") from exc

    if not raw_body:
        return status, None

    try:
        return status, json.loads(raw_body)
    except json.JSONDecodeError:
        return status, raw_body


def _assert_status(
    *,
    step: str,
    actual_status: int,
    expected_status: int,
    response_body: Any,
) -> None:
    if actual_status != expected_status:
        raise SmokeTestError(
            f"{step} failed: expected {expected_status}, got {actual_status}. "
            f"Response: {response_body}"
        )


def _require_key(step: str, payload: Any, key: str) -> Any:
    if not isinstance(payload, dict) or key not in payload:
        raise SmokeTestError(f"{step} failed: response is missing '{key}'. Response: {payload}")
    return payload[key]


def run_smoke_test(config: SmokeConfig) -> None:
    unique_suffix = str(int(time.time()))
    project_code = f"SMK{unique_suffix[-6:]}"
    project_name = f"Smoke Test {unique_suffix}"
    shot_name = f"Smoke Shot {unique_suffix}"

    api = f"{config.base_url}/api/v1"

    print(f"[1/6] GET {config.base_url}/health")
    status, payload = _request(
        method="GET",
        url=f"{config.base_url}/health",
        timeout=config.timeout,
    )
    _assert_status(
        step="Health check",
        actual_status=status,
        expected_status=200,
        response_body=payload,
    )

    print(f"[2/6] POST {api}/auth/login")
    status, payload = _request(
        method="POST",
        url=f"{api}/auth/login",
        timeout=config.timeout,
        payload={"email": config.email, "password": config.password},
    )
    _assert_status(
        step="Login",
        actual_status=status,
        expected_status=200,
        response_body=payload,
    )
    access_token = _require_key("Login", payload, "access_token")

    print(f"[3/6] GET {api}/auth/me")
    status, payload = _request(
        method="GET",
        url=f"{api}/auth/me",
        timeout=config.timeout,
        token=access_token,
    )
    _assert_status(
        step="Get current user",
        actual_status=status,
        expected_status=200,
        response_body=payload,
    )
    user_email = _require_key("Get current user", payload, "email")

    print(f"[4/6] POST {api}/projects")
    status, payload = _request(
        method="POST",
        url=f"{api}/projects",
        timeout=config.timeout,
        token=access_token,
        payload={
            "name": project_name,
            "code": project_code,
            "client": "Smoke Test",
            "project_type": "series",
            "description": "Temporary project created by smoke_test.py",
        },
    )
    _assert_status(
        step="Create project",
        actual_status=status,
        expected_status=200,
        response_body=payload,
    )
    project_id = _require_key("Create project", payload, "id")

    print(f"[5/6] POST {api}/projects/{project_id}/shots")
    status, payload = _request(
        method="POST",
        url=f"{api}/projects/{project_id}/shots",
        timeout=config.timeout,
        token=access_token,
        payload={
            "name": shot_name,
            "code": f"SH{unique_suffix[-4:]}",
            "frame_start": 1001,
            "frame_end": 1040,
            "priority": "normal",
        },
    )
    _assert_status(
        step="Create shot",
        actual_status=status,
        expected_status=200,
        response_body=payload,
    )
    shot_id = _require_key("Create shot", payload, "id")

    print(f"[6/6] PATCH {api}/shots/{shot_id}/status")
    status, payload = _request(
        method="PATCH",
        url=f"{api}/shots/{shot_id}/status",
        timeout=config.timeout,
        token=access_token,
        payload={"status": "in_progress", "comment": "Smoke test transition"},
    )
    _assert_status(
        step="Update shot status",
        actual_status=status,
        expected_status=200,
        response_body=payload,
    )
    new_status = _require_key("Update shot status", payload, "new_status")

    print("")
    print("Smoke test passed")
    print(f"Authenticated as: {user_email}")
    print(f"Project created: {project_id} ({project_code})")
    print(f"Shot created: {shot_id}")
    print(f"Final shot status: {new_status}")
    print("Note: this script does not delete the created entities.")


def main() -> int:
    defaults = _get_default_config()
    parser = _build_parser(defaults)
    args = parser.parse_args()

    config = SmokeConfig(
        base_url=args.base_url.rstrip("/"),
        email=args.email,
        password=args.password,
        timeout=args.timeout,
    )

    try:
        run_smoke_test(config)
    except SmokeTestError as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

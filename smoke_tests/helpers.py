"""Shared helpers, config, and result types for all smoke test modules."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

# ── Config & result types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class SmokeConfig:
    base_url: str  # API base, e.g. http://localhost:8000/api/v1
    root_url: str  # Server root for infra endpoints (/health, /metrics)
    email: str
    password: str
    timeout: float


@dataclass
class SmokeResults:
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


class SmokeTestError(RuntimeError):
    pass


def _get_default_config() -> SmokeConfig:
    root = os.getenv("SMOKE_BASE_URL", "http://localhost:8000").rstrip("/")
    return SmokeConfig(
        base_url=f"{root}/api/v1",
        root_url=root,
        email=os.getenv("SMOKE_EMAIL", os.getenv("SEED_ADMIN_EMAIL", "admin@vfxhub.dev")),
        password=os.getenv("SMOKE_PASSWORD", os.getenv("SEED_ADMIN_PASSWORD", "admin123")),
        timeout=float(os.getenv("SMOKE_TIMEOUT_SECONDS", "10")),
    )


def _normalize_base_urls(raw_base_url: str) -> tuple[str, str]:
    normalized = raw_base_url.rstrip("/")
    if normalized.endswith("/api/v1"):
        return normalized, normalized[: -len("/api/v1")]
    return f"{normalized}/api/v1", normalized


def _build_parser(defaults: SmokeConfig) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default=defaults.base_url)
    p.add_argument("--email", default=defaults.email)
    p.add_argument("--password", default=defaults.password)
    p.add_argument("--timeout", type=float, default=defaults.timeout)
    return p


def _make_config(args: argparse.Namespace) -> SmokeConfig:
    base_url, root = _normalize_base_urls(args.base_url)
    return SmokeConfig(
        base_url=base_url,
        root_url=root,
        email=args.email,
        password=args.password,
        timeout=args.timeout,
    )


# ── HTTP helpers ───────────────────────────────────────────────────────────────


def _request(
    *,
    method: str,
    url: str,
    timeout: float,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    data: bytes | None = None
    headers: dict[str, str] = {"Accept": "application/json"}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url=url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise SmokeTestError(f"{method} {url} → connection error: {exc.reason}") from exc

    if not raw:
        return status, None
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def _assert_status(*, step: str, actual: int, expected: int, body: Any) -> None:
    if actual != expected:
        raise SmokeTestError(f"expected HTTP {expected}, got {actual}. Body: {body}")


def _key(step: str, body: Any, key: str) -> Any:
    if not isinstance(body, dict) or key not in body:
        raise SmokeTestError(f"missing '{key}' in response: {body}")
    return body[key]


def _upload_multipart(
    *,
    url: str,
    timeout: float,
    token: str,
    file_content: bytes,
    filename: str,
    fields: dict[str, str | None] | None = None,
) -> tuple[int, Any]:
    """POST a multipart/form-data request with a single file field named 'upload'."""
    import uuid as _uuid

    boundary = _uuid.uuid4().hex
    CRLF = b"\r\n"
    parts: list[bytes] = []
    for name, value in (fields or {}).items():
        if value is None:
            continue
        parts += [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode(),
            CRLF,
        ]
    parts += [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="upload"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        file_content,
        CRLF,
        f"--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise SmokeTestError(f"POST {url} → connection error: {exc.reason}") from exc
    if not raw:
        return status, None
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def _check(results: SmokeResults, label: str, fn: Any) -> Any:
    """Run *fn*, record pass/fail, return result (or None on failure)."""
    try:
        result = fn()
        print(f"  [PASS] {label}")
        results.passed.append(label)
        return result
    except SmokeTestError as exc:
        print(f"  [FAIL] {label}: {exc}")
        results.failed.append(label)
        return None


# ── Summary printer ────────────────────────────────────────────────────────────


def print_summary(results: SmokeResults, title: str = "RESULTS") -> None:
    total = len(results.passed) + len(results.failed)
    print(f"\n{'═' * 70}")
    print(f"{title}  {len(results.passed)}/{total} passed")
    if results.failed:
        print(f"\nFailed steps ({len(results.failed)}):")
        for step in results.failed:
            print(f"  ✗ {step}")
    else:
        print("All steps passed.")
    print(f"{'═' * 70}")
    print("Note: created entities are NOT deleted. Run against a dev/test stack.")

"""Section 8 — Shots: CRUD + status, history, versions, files"""

from __future__ import annotations

from typing import Any

from smoke_tests.context import SmokeContext
from smoke_tests.helpers import (
    SmokeResults,
    SmokeTestError,
    _assert_status,
    _build_parser,
    _check,
    _get_default_config,
    _key,
    _make_config,
    _request,
    print_summary,
)

SECTION = "8 — Shots"


def run(ctx: SmokeContext) -> None:
    B, T, R, S = ctx.config.base_url, ctx.config.timeout, ctx.results, ctx.suffix
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="POST",
            url=f"{B}/projects/{ctx.project_id}/shots",
            timeout=T,
            token=ctx.token,
            payload={
                "name": f"Smoke Shot {S[-4:]}",
                "code": f"SH{S[-4:]}",
                "frame_start": 1001,
                "frame_end": 1040,
                "priority": "normal",
            },
        )
        _assert_status(step="POST /projects/{id}/shots", actual=s, expected=200, body=b)
        ctx.shot_id = _key("create_shot", b, "id")
        return b

    _check(R, "POST /projects/{id}/shots", _create)

    def _list() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET", url=f"{B}/projects/{ctx.project_id}/shots", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /projects/{id}/shots", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/shots", _list)

    def _get() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(method="GET", url=f"{B}/shots/{ctx.shot_id}", timeout=T, token=ctx.token)
        _assert_status(step="GET /shots/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /shots/{id}", _get)

    def _patch() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(
            method="PATCH",
            url=f"{B}/shots/{ctx.shot_id}",
            timeout=T,
            token=ctx.token,
            payload={"priority": "high"},
        )
        _assert_status(step="PATCH /shots/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "PATCH /shots/{id}", _patch)

    def _status() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(
            method="PATCH",
            url=f"{B}/shots/{ctx.shot_id}/status",
            timeout=T,
            token=ctx.token,
            payload={"status": "in_progress", "comment": "Smoke test transition"},
        )
        _assert_status(step="PATCH /shots/{id}/status", actual=s, expected=200, body=b)
        return b

    _check(R, "PATCH /shots/{id}/status", _status)

    def _history() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(
            method="GET", url=f"{B}/shots/{ctx.shot_id}/history", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /shots/{id}/history", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /shots/{id}/history", _history)

    def _versions() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(
            method="GET", url=f"{B}/shots/{ctx.shot_id}/versions", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /shots/{id}/versions", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /shots/{id}/versions", _versions)

    def _files() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(
            method="GET", url=f"{B}/shots/{ctx.shot_id}/files", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /shots/{id}/files", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /shots/{id}/files", _files)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth
    from smoke_tests.test_05_projects import run as run_projects

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run_projects(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 8 — Shots")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

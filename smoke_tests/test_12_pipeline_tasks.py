"""Section 12 — Pipeline Tasks: create on shot, list, get, status, notes, timelogs"""

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

SECTION = "12 — Pipeline Tasks"


def run(ctx: SmokeContext) -> None:
    B, T, R, S = ctx.config.base_url, ctx.config.timeout, ctx.results, ctx.suffix
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(
            method="POST",
            url=f"{B}/shots/{ctx.shot_id}/tasks",
            timeout=T,
            token=ctx.token,
            payload={"step_name": f"Smoke Task {S}", "step_type": "layout", "order": 1},
        )
        _assert_status(step="POST /shots/{id}/tasks", actual=s, expected=201, body=b)
        ctx.pipeline_task_id = _key("create_task", b, "id")
        return b

    _check(R, "POST /shots/{id}/tasks", _create)

    def _list() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(
            method="GET", url=f"{B}/shots/{ctx.shot_id}/tasks", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /shots/{id}/tasks", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /shots/{id}/tasks", _list)

    def _get() -> Any:
        if not ctx.pipeline_task_id:
            raise SmokeTestError("no pipeline_task_id")
        s, b = _request(
            method="GET",
            url=f"{B}/pipeline-tasks/{ctx.pipeline_task_id}",
            timeout=T,
            token=ctx.token,
        )
        _assert_status(step="GET /pipeline-tasks/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /pipeline-tasks/{id}", _get)

    def _status() -> Any:
        if not ctx.pipeline_task_id:
            raise SmokeTestError("no pipeline_task_id")
        s, b = _request(
            method="PATCH",
            url=f"{B}/pipeline-tasks/{ctx.pipeline_task_id}/status",
            timeout=T,
            token=ctx.token,
            payload={"status": "in_progress", "comment": "Smoke test"},
        )
        _assert_status(step="PATCH /pipeline-tasks/{id}/status", actual=s, expected=200, body=b)
        return b

    _check(R, "PATCH /pipeline-tasks/{id}/status", _status)

    def _notes() -> Any:
        if not ctx.pipeline_task_id:
            raise SmokeTestError("no pipeline_task_id")
        s, b = _request(
            method="GET",
            url=f"{B}/pipeline-tasks/{ctx.pipeline_task_id}/notes",
            timeout=T,
            token=ctx.token,
        )
        _assert_status(step="GET /pipeline-tasks/{id}/notes", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /pipeline-tasks/{id}/notes", _notes)

    def _timelogs() -> Any:
        if not ctx.pipeline_task_id:
            raise SmokeTestError("no pipeline_task_id")
        s, b = _request(
            method="GET",
            url=f"{B}/pipeline-tasks/{ctx.pipeline_task_id}/timelogs",
            timeout=T,
            token=ctx.token,
        )
        _assert_status(step="GET /pipeline-tasks/{id}/timelogs", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /pipeline-tasks/{id}/timelogs", _timelogs)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth
    from smoke_tests.test_05_projects import run as run_projects
    from smoke_tests.test_08_shots import run as run_shots

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run_projects(ctx)
    run_shots(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 12 — Pipeline Tasks")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

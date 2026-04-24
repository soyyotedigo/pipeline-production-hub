"""Section 16 — Time Logs: create, get, list by project/task/user, summary"""

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

SECTION = "16 — Time Logs"


def run(ctx: SmokeContext) -> None:
    B, T, R = ctx.config.base_url, ctx.config.timeout, ctx.results
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create() -> Any:
        if not ctx.pipeline_task_id or not ctx.project_id:
            raise SmokeTestError("no pipeline_task_id or project_id")
        s, b = _request(
            method="POST",
            url=f"{B}/timelogs",
            timeout=T,
            token=ctx.token,
            payload={
                "pipeline_task_id": ctx.pipeline_task_id,
                "project_id": ctx.project_id,
                "duration_minutes": 150,
                "date": "2026-03-22",
                "description": "Smoke test time log",
            },
        )
        _assert_status(step="POST /timelogs", actual=s, expected=201, body=b)
        ctx.timelog_id = _key("create_timelog", b, "id")
        return b

    _check(R, "POST /timelogs", _create)

    def _get() -> Any:
        if not ctx.timelog_id:
            raise SmokeTestError("no timelog_id")
        s, b = _request(
            method="GET", url=f"{B}/timelogs/{ctx.timelog_id}", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /timelogs/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /timelogs/{id}", _get)

    def _list_project() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET", url=f"{B}/projects/{ctx.project_id}/timelogs", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /projects/{id}/timelogs", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/timelogs", _list_project)

    def _summary() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET",
            url=f"{B}/projects/{ctx.project_id}/timelogs/summary",
            timeout=T,
            token=ctx.token,
        )
        _assert_status(step="GET /projects/{id}/timelogs/summary", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/timelogs/summary", _summary)

    def _list_user() -> Any:
        if not ctx.my_user_id:
            raise SmokeTestError("no my_user_id")
        s, b = _request(
            method="GET", url=f"{B}/users/{ctx.my_user_id}/timelogs", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /users/{id}/timelogs", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /users/{id}/timelogs", _list_user)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth
    from smoke_tests.test_05_projects import run as run_projects
    from smoke_tests.test_08_shots import run as run_shots
    from smoke_tests.test_12_pipeline_tasks import run as run_tasks

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run_projects(ctx)
    run_shots(ctx)
    run_tasks(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 16 — Time Logs")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

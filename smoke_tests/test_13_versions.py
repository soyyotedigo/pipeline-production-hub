"""Section 13 — Versions: create for task, list by task/shot/project, get"""

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

SECTION = "13 — Versions"


def run(ctx: SmokeContext) -> None:
    B, T, R, S = ctx.config.base_url, ctx.config.timeout, ctx.results, ctx.suffix
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create() -> Any:
        if not ctx.pipeline_task_id:
            raise SmokeTestError("no pipeline_task_id")
        s, b = _request(
            method="POST",
            url=f"{B}/pipeline-tasks/{ctx.pipeline_task_id}/versions",
            timeout=T,
            token=ctx.token,
            payload={"description": f"Smoke version {S}"},
        )
        _assert_status(step="POST /pipeline-tasks/{id}/versions", actual=s, expected=201, body=b)
        ctx.version_id = _key("create_version", b, "id")
        return b

    _check(R, "POST /pipeline-tasks/{id}/versions", _create)

    def _list_task() -> Any:
        if not ctx.pipeline_task_id:
            raise SmokeTestError("no pipeline_task_id")
        s, b = _request(
            method="GET",
            url=f"{B}/pipeline-tasks/{ctx.pipeline_task_id}/versions",
            timeout=T,
            token=ctx.token,
        )
        _assert_status(step="GET /pipeline-tasks/{id}/versions", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /pipeline-tasks/{id}/versions", _list_task)

    def _list_shot() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(
            method="GET", url=f"{B}/shots/{ctx.shot_id}/versions", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /shots/{id}/versions", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /shots/{id}/versions", _list_shot)

    def _get() -> Any:
        if not ctx.version_id:
            raise SmokeTestError("no version_id")
        s, b = _request(
            method="GET", url=f"{B}/versions/{ctx.version_id}", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /versions/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /versions/{id}", _get)

    def _list_project() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET", url=f"{B}/projects/{ctx.project_id}/versions", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /projects/{id}/versions", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/versions", _list_project)


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
    print_summary(ctx.results, "Section 13 — Versions")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

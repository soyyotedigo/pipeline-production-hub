"""Section 22 — Files: GET /files, GET /projects/{id}/files"""

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
    _make_config,
    _request,
    print_summary,
)

SECTION = "22 — Files"


def run(ctx: SmokeContext) -> None:
    B, T, R = ctx.config.base_url, ctx.config.timeout, ctx.results
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _list() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(
            method="GET", url=f"{B}/files?shot_id={ctx.shot_id}", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /files", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /files", _list)

    def _list_project() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET", url=f"{B}/projects/{ctx.project_id}/files", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /projects/{id}/files", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/files", _list_project)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth
    from smoke_tests.test_05_projects import run as run_projects

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run_projects(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 22 — Files")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

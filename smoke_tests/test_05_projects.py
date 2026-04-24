"""Section 5 — Projects: CRUD + overview, report, export"""

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

SECTION = "5 — Projects"


def run(ctx: SmokeContext) -> None:
    B, T, R, S = ctx.config.base_url, ctx.config.timeout, ctx.results, ctx.suffix
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create_project() -> Any:
        s, b = _request(
            method="POST",
            url=f"{B}/projects",
            timeout=T,
            token=ctx.token,
            payload={
                "name": f"Smoke Project {S}",
                "code": f"SP{S[-6:]}",
                "client": "Smoke Client",
                "project_type": "series",
                "description": "Created by smoke_tests",
            },
        )
        _assert_status(step="POST /projects", actual=s, expected=200, body=b)
        ctx.project_id = _key("create_project", b, "id")
        return b

    _check(R, "POST /projects", _create_project)

    def _list_projects() -> Any:
        s, b = _request(method="GET", url=f"{B}/projects", timeout=T, token=ctx.token)
        _assert_status(step="GET /projects", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects", _list_projects)

    def _get_project() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET", url=f"{B}/projects/{ctx.project_id}", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /projects/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}", _get_project)

    def _patch_project() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="PATCH",
            url=f"{B}/projects/{ctx.project_id}",
            timeout=T,
            token=ctx.token,
            payload={"description": "Updated by smoke_tests"},
        )
        _assert_status(step="PATCH /projects/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "PATCH /projects/{id}", _patch_project)

    def _overview() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET", url=f"{B}/projects/{ctx.project_id}/overview", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /projects/{id}/overview", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/overview", _overview)

    def _report() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET", url=f"{B}/projects/{ctx.project_id}/report", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /projects/{id}/report", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/report", _report)

    def _export() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET",
            url=f"{B}/projects/{ctx.project_id}/export?format=csv",
            timeout=T,
            token=ctx.token,
        )
        if s not in (200, 202):
            raise SmokeTestError(f"expected 200 or 202, got {s}. Body: {b}")
        return b

    _check(R, "GET /projects/{id}/export", _export)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 5 — Projects")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

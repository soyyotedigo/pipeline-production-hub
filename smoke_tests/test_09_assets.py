"""Section 9 — Assets: POST/GET /projects/{id}/assets, GET /assets/{id}/files|versions"""

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

SECTION = "9 — Assets"


def run(ctx: SmokeContext) -> None:
    B, T, R, S = ctx.config.base_url, ctx.config.timeout, ctx.results, ctx.suffix
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="POST",
            url=f"{B}/projects/{ctx.project_id}/assets",
            timeout=T,
            token=ctx.token,
            payload={
                "name": f"Smoke Asset {S}",
                "code": f"AST{S[-4:]}",
                "asset_type": "prop",
            },
        )
        _assert_status(step="POST /projects/{id}/assets", actual=s, expected=200, body=b)
        ctx.asset_id = _key("create_asset", b, "id")
        return b

    _check(R, "POST /projects/{id}/assets", _create)

    def _list() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET", url=f"{B}/projects/{ctx.project_id}/assets", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /projects/{id}/assets", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/assets", _list)

    def _files() -> Any:
        if not ctx.asset_id:
            raise SmokeTestError("no asset_id")
        s, b = _request(
            method="GET", url=f"{B}/assets/{ctx.asset_id}/files", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /assets/{id}/files", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /assets/{id}/files", _files)

    def _versions() -> Any:
        if not ctx.asset_id:
            raise SmokeTestError("no asset_id")
        s, b = _request(
            method="GET", url=f"{B}/assets/{ctx.asset_id}/versions", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /assets/{id}/versions", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /assets/{id}/versions", _versions)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth
    from smoke_tests.test_05_projects import run as run_projects

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run_projects(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 9 — Assets")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

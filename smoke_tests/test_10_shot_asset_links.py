"""Section 10 — Shot-Asset Links: link, list shot assets, list asset shots"""

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

SECTION = "10 — Shot-Asset Links"


def run(ctx: SmokeContext) -> None:
    B, T, R = ctx.config.base_url, ctx.config.timeout, ctx.results
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _link() -> Any:
        if not ctx.shot_id or not ctx.asset_id:
            raise SmokeTestError("no shot_id or asset_id")
        s, b = _request(
            method="POST",
            url=f"{B}/shots/{ctx.shot_id}/assets",
            timeout=T,
            token=ctx.token,
            payload={"asset_id": ctx.asset_id, "link_type": "references"},
        )
        _assert_status(step="POST /shots/{id}/assets", actual=s, expected=201, body=b)
        ctx.link_id = _key("link_asset", b, "id")
        return b

    _check(R, "POST /shots/{id}/assets (link)", _link)

    def _shot_assets() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(
            method="GET", url=f"{B}/shots/{ctx.shot_id}/assets", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /shots/{id}/assets", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /shots/{id}/assets", _shot_assets)

    def _asset_shots() -> Any:
        if not ctx.asset_id:
            raise SmokeTestError("no asset_id")
        s, b = _request(
            method="GET", url=f"{B}/assets/{ctx.asset_id}/shots", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /assets/{id}/shots", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /assets/{id}/shots", _asset_shots)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth
    from smoke_tests.test_05_projects import run as run_projects
    from smoke_tests.test_08_shots import run as run_shots
    from smoke_tests.test_09_assets import run as run_assets

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run_projects(ctx)
    run_shots(ctx)
    run_assets(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 10 — Shot-Asset Links")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

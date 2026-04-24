"""Section 6 — Episodes: POST/GET /projects/{id}/episodes, GET/PATCH /episodes/{id}"""

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

SECTION = "6 — Episodes"


def run(ctx: SmokeContext) -> None:
    B, T, R, S = ctx.config.base_url, ctx.config.timeout, ctx.results, ctx.suffix
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="POST",
            url=f"{B}/projects/{ctx.project_id}/episodes",
            timeout=T,
            token=ctx.token,
            payload={"code": f"EP{S[-4:]}", "name": f"Smoke Episode {S}"},
        )
        _assert_status(step="POST /projects/{id}/episodes", actual=s, expected=200, body=b)
        ctx.episode_id = _key("create_episode", b, "id")
        return b

    _check(R, "POST /projects/{id}/episodes", _create)

    def _list() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET", url=f"{B}/projects/{ctx.project_id}/episodes", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /projects/{id}/episodes", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/episodes", _list)

    def _get() -> Any:
        if not ctx.episode_id:
            raise SmokeTestError("no episode_id")
        s, b = _request(
            method="GET", url=f"{B}/episodes/{ctx.episode_id}", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /episodes/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /episodes/{id}", _get)

    def _patch() -> Any:
        if not ctx.episode_id:
            raise SmokeTestError("no episode_id")
        s, b = _request(
            method="PATCH",
            url=f"{B}/episodes/{ctx.episode_id}",
            timeout=T,
            token=ctx.token,
            payload={"name": f"Smoke Episode {S} updated"},
        )
        _assert_status(step="PATCH /episodes/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "PATCH /episodes/{id}", _patch)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth
    from smoke_tests.test_05_projects import run as run_projects

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run_projects(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 6 — Episodes")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

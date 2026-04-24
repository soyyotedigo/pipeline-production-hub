"""Section 21 — Background Tasks: GET /tasks"""

from __future__ import annotations

from typing import Any

from smoke_tests.context import SmokeContext
from smoke_tests.helpers import (
    SmokeResults,
    _assert_status,
    _build_parser,
    _check,
    _get_default_config,
    _make_config,
    _request,
    print_summary,
)

SECTION = "21 — Background Tasks"


def run(ctx: SmokeContext) -> None:
    B, T, R = ctx.config.base_url, ctx.config.timeout, ctx.results
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _list() -> Any:
        s, b = _request(method="GET", url=f"{B}/tasks", timeout=T, token=ctx.token)
        _assert_status(step="GET /tasks", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /tasks", _list)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 21 — Background Tasks")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

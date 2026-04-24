"""Section 1 — Health: GET /health"""

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

SECTION = "1 — Health"


def run(ctx: SmokeContext) -> None:
    B, T, R = ctx.config.root_url, ctx.config.timeout, ctx.results
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _health() -> Any:
        s, b = _request(method="GET", url=f"{B}/health", timeout=T)
        _assert_status(step="GET /health", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /health", _health)


def main() -> int:
    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run(ctx)
    print_summary(ctx.results, "Section 1 — Health")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Section 20 — Notifications: list, unread-count, mark-all-read"""

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

SECTION = "20 — Notifications"


def run(ctx: SmokeContext) -> None:
    B, T, R = ctx.config.base_url, ctx.config.timeout, ctx.results
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _list() -> Any:
        s, b = _request(method="GET", url=f"{B}/notifications", timeout=T, token=ctx.token)
        _assert_status(step="GET /notifications", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /notifications", _list)

    def _unread_count() -> Any:
        s, b = _request(
            method="GET", url=f"{B}/notifications/unread-count", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /notifications/unread-count", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /notifications/unread-count", _unread_count)

    def _mark_all_read() -> Any:
        s, b = _request(
            method="POST", url=f"{B}/notifications/read-all", timeout=T, token=ctx.token
        )
        if s != 204:
            raise SmokeTestError(f"expected 204, got {s}. Body: {b}")
        return b

    _check(R, "POST /notifications/read-all", _mark_all_read)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 20 — Notifications")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

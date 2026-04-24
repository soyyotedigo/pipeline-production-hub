"""Section 2 — Auth: POST /auth/login, GET /auth/me, POST /auth/refresh"""

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

SECTION = "2 — Auth"


def run(ctx: SmokeContext) -> None:
    B, T, R = ctx.config.base_url, ctx.config.timeout, ctx.results
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _login() -> Any:
        s, b = _request(
            method="POST",
            url=f"{B}/auth/login",
            timeout=T,
            payload={"email": ctx.config.email, "password": ctx.config.password},
        )
        _assert_status(step="POST /auth/login", actual=s, expected=200, body=b)
        ctx.token = _key("login", b, "access_token")
        ctx.refresh_token = _key("login", b, "refresh_token")
        return b

    _check(R, "POST /auth/login", _login)

    def _me() -> Any:
        if not ctx.token:
            raise SmokeTestError("no token — login step failed")
        s, b = _request(method="GET", url=f"{B}/auth/me", timeout=T, token=ctx.token)
        _assert_status(step="GET /auth/me", actual=s, expected=200, body=b)
        ctx.my_user_id = _key("me", b, "id")
        return b

    _check(R, "GET /auth/me", _me)

    def _refresh() -> Any:
        if not ctx.refresh_token:
            raise SmokeTestError("no refresh_token — login step failed")
        s, b = _request(
            method="POST",
            url=f"{B}/auth/refresh",
            timeout=T,
            payload={"refresh_token": ctx.refresh_token},
        )
        _assert_status(step="POST /auth/refresh", actual=s, expected=200, body=b)
        ctx.token = _key("refresh", b, "access_token")
        return b

    _check(R, "POST /auth/refresh", _refresh)


def main() -> int:
    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run(ctx)
    print_summary(ctx.results, "Section 2 — Auth")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

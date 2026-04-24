"""Section 3 — Users: GET /users, POST /users, GET /users/{id}, GET /users/{id}/roles"""

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

SECTION = "3 — Users"


def run(ctx: SmokeContext) -> None:
    B, T, R, S = ctx.config.base_url, ctx.config.timeout, ctx.results, ctx.suffix
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _list_users() -> Any:
        s, b = _request(method="GET", url=f"{B}/users", timeout=T, token=ctx.token)
        if s not in (200, 403):
            raise SmokeTestError(f"expected HTTP 200 or 403, got {s}. Body: {b}")
        return b

    _check(R, "GET /users", _list_users)

    def _create_user() -> Any:
        s, b = _request(
            method="POST",
            url=f"{B}/users",
            timeout=T,
            token=ctx.token,
            payload={
                "email": f"smokeuser{S}@vfxhub.dev",
                "full_name": f"Smoke User {S}",
                "password": "SmokePass123!",
            },
        )
        _assert_status(step="POST /users", actual=s, expected=201, body=b)
        ctx.new_user_id = _key("create_user", b, "id")
        return b

    _check(R, "POST /users", _create_user)

    def _get_user() -> Any:
        if not ctx.my_user_id:
            raise SmokeTestError("no my_user_id")
        s, b = _request(method="GET", url=f"{B}/users/{ctx.my_user_id}", timeout=T, token=ctx.token)
        _assert_status(step="GET /users/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /users/{id}", _get_user)

    def _list_user_roles() -> Any:
        if not ctx.my_user_id:
            raise SmokeTestError("no my_user_id")
        s, b = _request(
            method="GET", url=f"{B}/users/{ctx.my_user_id}/roles", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /users/{id}/roles", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /users/{id}/roles", _list_user_roles)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 3 — Users")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

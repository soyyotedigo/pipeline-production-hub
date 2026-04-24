"""Section 4 — Departments: CRUD + members + user→departments"""

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

SECTION = "4 — Departments"


def run(ctx: SmokeContext) -> None:
    B, T, R, S = ctx.config.base_url, ctx.config.timeout, ctx.results, ctx.suffix
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create_dept() -> Any:
        s, b = _request(
            method="POST",
            url=f"{B}/departments",
            timeout=T,
            token=ctx.token,
            payload={"name": f"Smoke Dept {S}", "code": f"SMD{S[-4:]}"},
        )
        _assert_status(step="POST /departments", actual=s, expected=201, body=b)
        ctx.dept_id = _key("create_dept", b, "id")
        return b

    _check(R, "POST /departments", _create_dept)

    def _list_depts() -> Any:
        s, b = _request(method="GET", url=f"{B}/departments", timeout=T, token=ctx.token)
        _assert_status(step="GET /departments", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /departments", _list_depts)

    def _get_dept() -> Any:
        if not ctx.dept_id:
            raise SmokeTestError("no dept_id")
        s, b = _request(
            method="GET", url=f"{B}/departments/{ctx.dept_id}", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /departments/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /departments/{id}", _get_dept)

    def _add_member() -> Any:
        if not ctx.dept_id or not ctx.new_user_id:
            raise SmokeTestError("no dept_id or new_user_id")
        s, b = _request(
            method="POST",
            url=f"{B}/departments/{ctx.dept_id}/members",
            timeout=T,
            token=ctx.token,
            payload={"user_id": ctx.new_user_id},
        )
        _assert_status(step="POST /departments/{id}/members", actual=s, expected=201, body=b)
        ctx.dept_member_id = _key("add_member", b, "id")
        return b

    _check(R, "POST /departments/{id}/members", _add_member)

    def _list_members() -> Any:
        if not ctx.dept_id:
            raise SmokeTestError("no dept_id")
        s, b = _request(
            method="GET", url=f"{B}/departments/{ctx.dept_id}/members", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /departments/{id}/members", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /departments/{id}/members", _list_members)

    def _user_depts() -> Any:
        if not ctx.new_user_id:
            raise SmokeTestError("no new_user_id")
        s, b = _request(
            method="GET", url=f"{B}/users/{ctx.new_user_id}/departments", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /users/{id}/departments", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /users/{id}/departments", _user_depts)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth
    from smoke_tests.test_03_users import run as run_users

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run_users(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 4 — Departments")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

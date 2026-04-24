"""Section 19 — Webhooks: create, list, list project webhooks"""

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

SECTION = "19 — Webhooks"


def run(ctx: SmokeContext) -> None:
    B, T, R = ctx.config.base_url, ctx.config.timeout, ctx.results
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="POST",
            url=f"{B}/webhooks",
            timeout=T,
            token=ctx.token,
            payload={
                "project_id": ctx.project_id,
                "url": "http://localhost:9999/webhook-smoke",
                "events": ["status.changed"],
            },
        )
        _assert_status(step="POST /webhooks", actual=s, expected=200, body=b)
        ctx.webhook_id = _key("create_webhook", b, "id")
        return b

    _check(R, "POST /webhooks", _create)

    def _list() -> Any:
        s, b = _request(method="GET", url=f"{B}/webhooks", timeout=T, token=ctx.token)
        _assert_status(step="GET /webhooks", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /webhooks", _list)

    def _list_project() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET", url=f"{B}/projects/{ctx.project_id}/webhooks", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /projects/{id}/webhooks", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/webhooks", _list_project)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth
    from smoke_tests.test_05_projects import run as run_projects

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run_projects(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 19 — Webhooks")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

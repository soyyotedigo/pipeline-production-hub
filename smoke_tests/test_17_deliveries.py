"""Section 17 — Deliveries: create, list, get, add item, list items"""

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

SECTION = "17 — Deliveries"


def run(ctx: SmokeContext) -> None:
    B, T, R, S = ctx.config.base_url, ctx.config.timeout, ctx.results, ctx.suffix
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="POST",
            url=f"{B}/projects/{ctx.project_id}/deliveries",
            timeout=T,
            token=ctx.token,
            payload={
                "name": f"Smoke Delivery {S}",
                "recipient": "client@example.com",
                "due_date": "2026-03-31",
            },
        )
        _assert_status(step="POST /projects/{id}/deliveries", actual=s, expected=201, body=b)
        ctx.delivery_id = _key("create_delivery", b, "id")
        return b

    _check(R, "POST /projects/{id}/deliveries", _create)

    def _list() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET",
            url=f"{B}/projects/{ctx.project_id}/deliveries",
            timeout=T,
            token=ctx.token,
        )
        _assert_status(step="GET /projects/{id}/deliveries", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/deliveries", _list)

    def _get() -> Any:
        if not ctx.delivery_id:
            raise SmokeTestError("no delivery_id")
        s, b = _request(
            method="GET", url=f"{B}/deliveries/{ctx.delivery_id}", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /deliveries/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /deliveries/{id}", _get)

    def _add_item() -> Any:
        if not ctx.delivery_id or not ctx.version_id:
            raise SmokeTestError("no delivery_id or version_id")
        s, b = _request(
            method="POST",
            url=f"{B}/deliveries/{ctx.delivery_id}/items",
            timeout=T,
            token=ctx.token,
            payload={"version_id": ctx.version_id, "note": "Smoke delivery item"},
        )
        _assert_status(step="POST /deliveries/{id}/items", actual=s, expected=201, body=b)
        return b

    _check(R, "POST /deliveries/{id}/items", _add_item)

    def _list_items() -> Any:
        if not ctx.delivery_id:
            raise SmokeTestError("no delivery_id")
        s, b = _request(
            method="GET", url=f"{B}/deliveries/{ctx.delivery_id}/items", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /deliveries/{id}/items", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /deliveries/{id}/items", _list_items)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth
    from smoke_tests.test_05_projects import run as run_projects
    from smoke_tests.test_08_shots import run as run_shots
    from smoke_tests.test_12_pipeline_tasks import run as run_tasks
    from smoke_tests.test_13_versions import run as run_versions

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run_projects(ctx)
    run_shots(ctx)
    run_tasks(ctx)
    run_versions(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 17 — Deliveries")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

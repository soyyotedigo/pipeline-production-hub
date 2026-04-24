"""Section 11 — Pipeline Templates: POST/GET /pipeline-templates, GET /pipeline-templates/{id}"""

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

SECTION = "11 — Pipeline Templates"


def run(ctx: SmokeContext) -> None:
    B, T, R, S = ctx.config.base_url, ctx.config.timeout, ctx.results, ctx.suffix
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create() -> Any:
        s, b = _request(
            method="POST",
            url=f"{B}/pipeline-templates",
            timeout=T,
            token=ctx.token,
            payload={
                "name": f"Smoke Template {S}",
                "project_type": "series",
                "steps": [
                    {
                        "step_name": "Layout",
                        "step_type": "layout",
                        "order": 1,
                        "applies_to": "shot",
                    },
                    {
                        "step_name": "Animation",
                        "step_type": "animation",
                        "order": 2,
                        "applies_to": "shot",
                    },
                ],
            },
        )
        _assert_status(step="POST /pipeline-templates", actual=s, expected=200, body=b)
        ctx.template_id = _key("create_template", b, "id")
        return b

    _check(R, "POST /pipeline-templates", _create)

    def _list() -> Any:
        s, b = _request(method="GET", url=f"{B}/pipeline-templates", timeout=T, token=ctx.token)
        _assert_status(step="GET /pipeline-templates", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /pipeline-templates", _list)

    def _get() -> Any:
        if not ctx.template_id:
            raise SmokeTestError("no template_id")
        s, b = _request(
            method="GET",
            url=f"{B}/pipeline-templates/{ctx.template_id}",
            timeout=T,
            token=ctx.token,
        )
        _assert_status(step="GET /pipeline-templates/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /pipeline-templates/{id}", _get)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 11 — Pipeline Templates")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

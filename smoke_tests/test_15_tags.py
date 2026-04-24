"""Section 15 — Tags: create, list, search, attach to shot/sequence, list project tags"""

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

SECTION = "15 — Tags"


def run(ctx: SmokeContext) -> None:
    B, T, R, S = ctx.config.base_url, ctx.config.timeout, ctx.results, ctx.suffix
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="POST",
            url=f"{B}/tags",
            timeout=T,
            token=ctx.token,
            payload={"name": f"smoke-tag-{S}", "color": "#FF6B6B", "project_id": ctx.project_id},
        )
        _assert_status(step="POST /tags", actual=s, expected=201, body=b)
        ctx.tag_id = _key("create_tag", b, "id")
        return b

    _check(R, "POST /tags", _create)

    def _list() -> Any:
        s, b = _request(method="GET", url=f"{B}/tags", timeout=T, token=ctx.token)
        _assert_status(step="GET /tags", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /tags", _list)

    def _search() -> Any:
        s, b = _request(method="GET", url=f"{B}/tags/search?q=smoke", timeout=T, token=ctx.token)
        _assert_status(step="GET /tags/search", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /tags/search", _search)

    def _attach_shot() -> Any:
        if not ctx.shot_id or not ctx.tag_id:
            raise SmokeTestError("no shot_id or tag_id")
        s, b = _request(
            method="POST",
            url=f"{B}/shots/{ctx.shot_id}/tags",
            timeout=T,
            token=ctx.token,
            payload={"tag_id": ctx.tag_id},
        )
        _assert_status(step="POST /shots/{id}/tags", actual=s, expected=201, body=b)
        ctx.entity_tag_id = _key("attach_tag", b, "id")
        return b

    _check(R, "POST /shots/{id}/tags", _attach_shot)

    def _list_shot_tags() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(
            method="GET", url=f"{B}/shots/{ctx.shot_id}/tags", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /shots/{id}/tags", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /shots/{id}/tags", _list_shot_tags)

    def _list_project_tags() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET", url=f"{B}/projects/{ctx.project_id}/tags", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /projects/{id}/tags", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/tags", _list_project_tags)

    def _attach_sequence() -> Any:
        if not ctx.seq_id or not ctx.tag_id:
            raise SmokeTestError("no seq_id or tag_id")
        s, b = _request(
            method="POST",
            url=f"{B}/sequences/{ctx.seq_id}/tags",
            timeout=T,
            token=ctx.token,
            payload={"tag_id": ctx.tag_id},
        )
        _assert_status(step="POST /sequences/{id}/tags", actual=s, expected=201, body=b)
        return b

    _check(R, "POST /sequences/{id}/tags", _attach_sequence)

    def _list_seq_tags() -> Any:
        if not ctx.seq_id:
            raise SmokeTestError("no seq_id")
        s, b = _request(
            method="GET", url=f"{B}/sequences/{ctx.seq_id}/tags", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /sequences/{id}/tags", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /sequences/{id}/tags", _list_seq_tags)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth
    from smoke_tests.test_05_projects import run as run_projects
    from smoke_tests.test_07_sequences import run as run_sequences
    from smoke_tests.test_08_shots import run as run_shots

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run_projects(ctx)
    run_sequences(ctx)
    run_shots(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 15 — Tags")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

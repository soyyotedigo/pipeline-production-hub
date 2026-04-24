"""Section 18 — Playlists: create, get, list project playlists, add item"""

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

SECTION = "18 — Playlists"


def run(ctx: SmokeContext) -> None:
    B, T, R, S = ctx.config.base_url, ctx.config.timeout, ctx.results, ctx.suffix
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="POST",
            url=f"{B}/playlists",
            timeout=T,
            token=ctx.token,
            payload={
                "project_id": ctx.project_id,
                "name": f"Smoke Playlist {S}",
                "date": "2026-03-22",
            },
        )
        _assert_status(step="POST /playlists", actual=s, expected=201, body=b)
        ctx.playlist_id = _key("create_playlist", b, "id")
        return b

    _check(R, "POST /playlists", _create)

    def _get() -> Any:
        if not ctx.playlist_id:
            raise SmokeTestError("no playlist_id")
        s, b = _request(
            method="GET", url=f"{B}/playlists/{ctx.playlist_id}", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /playlists/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /playlists/{id}", _get)

    def _list_project() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET", url=f"{B}/projects/{ctx.project_id}/playlists", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /projects/{id}/playlists", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/playlists", _list_project)

    def _add_item() -> Any:
        if not ctx.playlist_id or not ctx.version_id:
            raise SmokeTestError("no playlist_id or version_id")
        s, b = _request(
            method="POST",
            url=f"{B}/playlists/{ctx.playlist_id}/items",
            timeout=T,
            token=ctx.token,
            payload={"version_id": ctx.version_id},
        )
        _assert_status(step="POST /playlists/{id}/items", actual=s, expected=201, body=b)
        return b

    _check(R, "POST /playlists/{id}/items", _add_item)


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
    print_summary(ctx.results, "Section 18 — Playlists")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Section 14 — Notes: create/list on shot, get, reply, create/list on project"""

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

SECTION = "14 — Notes"


def run(ctx: SmokeContext) -> None:
    B, T, R = ctx.config.base_url, ctx.config.timeout, ctx.results
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    def _create_shot_note() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(
            method="POST",
            url=f"{B}/shots/{ctx.shot_id}/notes",
            timeout=T,
            token=ctx.token,
            payload={
                "project_id": ctx.project_id,
                "body": "Smoke test note on shot",
                "subject": "Smoke Note",
            },
        )
        _assert_status(step="POST /shots/{id}/notes", actual=s, expected=201, body=b)
        ctx.note_id = _key("create_shot_note", b, "id")
        return b

    _check(R, "POST /shots/{id}/notes", _create_shot_note)

    def _list_shot_notes() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        s, b = _request(
            method="GET", url=f"{B}/shots/{ctx.shot_id}/notes", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /shots/{id}/notes", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /shots/{id}/notes", _list_shot_notes)

    def _get_note() -> Any:
        if not ctx.note_id:
            raise SmokeTestError("no note_id")
        s, b = _request(method="GET", url=f"{B}/notes/{ctx.note_id}", timeout=T, token=ctx.token)
        _assert_status(step="GET /notes/{id}", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /notes/{id}", _get_note)

    def _reply() -> Any:
        if not ctx.note_id:
            raise SmokeTestError("no note_id")
        s, b = _request(
            method="POST",
            url=f"{B}/notes/{ctx.note_id}/reply",
            timeout=T,
            token=ctx.token,
            payload={"body": "Smoke test reply"},
        )
        _assert_status(step="POST /notes/{id}/reply", actual=s, expected=201, body=b)
        return b

    _check(R, "POST /notes/{id}/reply", _reply)

    def _create_project_note() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="POST",
            url=f"{B}/projects/{ctx.project_id}/notes",
            timeout=T,
            token=ctx.token,
            payload={"body": "Smoke test project note", "subject": "Project Note"},
        )
        _assert_status(step="POST /projects/{id}/notes", actual=s, expected=201, body=b)
        return b

    _check(R, "POST /projects/{id}/notes", _create_project_note)

    def _list_project_notes() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET", url=f"{B}/projects/{ctx.project_id}/notes", timeout=T, token=ctx.token
        )
        _assert_status(step="GET /projects/{id}/notes", actual=s, expected=200, body=b)
        return b

    _check(R, "GET /projects/{id}/notes", _list_project_notes)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth
    from smoke_tests.test_05_projects import run as run_projects
    from smoke_tests.test_08_shots import run as run_shots

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run_projects(ctx)
    run_shots(ctx)
    run(ctx)
    print_summary(ctx.results, "Section 14 — Notes")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

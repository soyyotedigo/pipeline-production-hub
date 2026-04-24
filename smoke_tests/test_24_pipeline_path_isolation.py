"""Section 24 — Pipeline/Path Isolation

Certifies that applying a pipeline template to a shot does NOT alter the
project's path template or the file naming structure.

Happy-path flow:
  1. Read project → confirm path_templates is null (built-in template active)
  2. Upload a dummy file linked to the shot → record storage_path and name (v1)
  3. Create a pipeline template and apply it to the same shot
  4. Upload a second file to the same shot → record storage_path and name (v2)
  5. Assert: directory structure of v1 and v2 are identical (only version segment differs)
  6. Assert: filename version advanced by exactly 1 (e.g. _v001. → _v002.)
  7. Read project again → confirm path_templates is still null (not mutated)
"""

from __future__ import annotations

import re
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
    _upload_multipart,
    print_summary,
)

SECTION = "24 — Pipeline/Path Isolation"

# Minimal dummy payload — not a real EXR, just enough bytes to satisfy the upload
_DUMMY_EXR = b"SMOKE_TEST_FAKE_EXR_PAYLOAD_DO_NOT_USE"
_ORIGINAL_FILENAME = "isolation_plate.exr"


def run(ctx: SmokeContext) -> None:
    B, T, R, S = ctx.config.base_url, ctx.config.timeout, ctx.results, ctx.suffix
    print(f"\n── SECTION {SECTION} ────────────────────────────────────────────────")

    state: dict[str, Any] = {}

    # ── 1. Read project — confirm path_templates is null ──────────────────────
    def _read_project_initial() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET",
            url=f"{B}/projects/{ctx.project_id}",
            timeout=T,
            token=ctx.token,
        )
        _assert_status(step="GET /projects/{id} initial", actual=s, expected=200, body=b)
        state["initial_path_templates"] = b.get("path_templates")
        return b

    _check(R, "GET /projects/{id} — initial path_templates", _read_project_initial)

    # ── 2. Upload v1 (before any pipeline template) ───────────────────────────
    def _upload_v1() -> Any:
        if not ctx.project_id or not ctx.shot_id:
            raise SmokeTestError("no project_id or shot_id")
        s, b = _upload_multipart(
            url=f"{B}/projects/{ctx.project_id}/files/upload",
            timeout=T,
            token=ctx.token,
            file_content=_DUMMY_EXR,
            filename=_ORIGINAL_FILENAME,
            fields={"shot_id": ctx.shot_id},
        )
        _assert_status(step="upload v1", actual=s, expected=200, body=b)
        state["path_v1"] = _key("upload_v1_path", b, "storage_path")
        state["name_v1"] = _key("upload_v1_name", b, "name")
        state["version_v1"] = _key("upload_v1_version", b, "version")
        return b

    _check(R, "POST /projects/{id}/files/upload — v1 before template", _upload_v1)

    # ── 3. Create a pipeline template ─────────────────────────────────────────
    def _create_isolation_template() -> Any:
        s, b = _request(
            method="POST",
            url=f"{B}/pipeline-templates",
            timeout=T,
            token=ctx.token,
            payload={
                "name": f"Isolation Template {S}",
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
                    {
                        "step_name": "Compositing",
                        "step_type": "compositing",
                        "order": 3,
                        "applies_to": "shot",
                    },
                ],
            },
        )
        _assert_status(step="POST /pipeline-templates isolation", actual=s, expected=200, body=b)
        state["isolation_template_id"] = _key("create_isolation_template", b, "id")
        return b

    _check(R, "POST /pipeline-templates — isolation template", _create_isolation_template)

    # ── 4. Apply template to the shot ─────────────────────────────────────────
    def _apply_template() -> Any:
        if not ctx.shot_id:
            raise SmokeTestError("no shot_id")
        tid = state.get("isolation_template_id")
        if not tid:
            raise SmokeTestError("no isolation_template_id — template creation failed")
        s, b = _request(
            method="POST",
            url=f"{B}/pipeline-templates/{tid}/apply",
            timeout=T,
            token=ctx.token,
            payload={"entity_type": "shot", "entity_id": ctx.shot_id},
        )
        _assert_status(step="POST /pipeline-templates/{id}/apply", actual=s, expected=201, body=b)
        created = b.get("tasks_created", 0) if isinstance(b, dict) else 0
        if created < 1:
            raise SmokeTestError(f"expected tasks_created >= 1, got {created}")
        return b

    _check(R, "POST /pipeline-templates/{id}/apply — to shot", _apply_template)

    # ── 5. Upload v2 (after applying template) ────────────────────────────────
    def _upload_v2() -> Any:
        if not ctx.project_id or not ctx.shot_id:
            raise SmokeTestError("no project_id or shot_id")
        s, b = _upload_multipart(
            url=f"{B}/projects/{ctx.project_id}/files/upload",
            timeout=T,
            token=ctx.token,
            file_content=_DUMMY_EXR,
            filename=_ORIGINAL_FILENAME,
            fields={"shot_id": ctx.shot_id},
        )
        _assert_status(step="upload v2", actual=s, expected=200, body=b)
        state["path_v2"] = _key("upload_v2_path", b, "storage_path")
        state["name_v2"] = _key("upload_v2_name", b, "name")
        state["version_v2"] = _key("upload_v2_version", b, "version")
        return b

    _check(R, "POST /projects/{id}/files/upload — v2 after template", _upload_v2)

    # ── 6. Assert: directory structure unchanged ──────────────────────────────
    def _assert_path_isolation() -> Any:
        p1 = state.get("path_v1")
        p2 = state.get("path_v2")
        if not p1 or not p2:
            raise SmokeTestError("missing path_v1 or path_v2 from earlier steps")
        # Normalize the version directory segment (e.g. /v001/ → /vNNN/)
        norm_v1 = re.sub(r"/v\d{3}(/|$)", "/vNNN\\1", p1)
        norm_v2 = re.sub(r"/v\d{3}(/|$)", "/vNNN\\1", p2)
        if norm_v1 != norm_v2:
            raise SmokeTestError(
                f"Path structure changed after applying pipeline template!\n"
                f"  before: {p1}\n"
                f"  after:  {p2}"
            )
        return {"path_v1": p1, "path_v2": p2, "normalized": norm_v1}

    _check(R, "path structure unchanged after pipeline template apply", _assert_path_isolation)

    # ── 7. Assert: filename version advanced by 1 ─────────────────────────────
    def _assert_filename_versioning() -> Any:
        ver1 = state.get("version_v1")
        ver2 = state.get("version_v2")
        if ver1 is None or ver2 is None:
            raise SmokeTestError("missing version_v1 or version_v2 from earlier steps")
        if ver2 != ver1 + 1:
            raise SmokeTestError(
                f"expected version to advance by 1 but got v{ver1:03d} → v{ver2:03d}"
            )
        return {
            "name_v1": state.get("name_v1"),
            "name_v2": state.get("name_v2"),
            "ver1": ver1,
            "ver2": ver2,
        }

    _check(R, "filename versioning advances normally (vN → vN+1)", _assert_filename_versioning)

    # ── 8. Confirm project.path_templates not mutated ─────────────────────────
    def _read_project_final() -> Any:
        if not ctx.project_id:
            raise SmokeTestError("no project_id")
        s, b = _request(
            method="GET",
            url=f"{B}/projects/{ctx.project_id}",
            timeout=T,
            token=ctx.token,
        )
        _assert_status(step="GET /projects/{id} final", actual=s, expected=200, body=b)
        initial = state.get("initial_path_templates")
        current = b.get("path_templates")
        if current != initial:
            raise SmokeTestError(
                f"project.path_templates was mutated by pipeline template apply!\n"
                f"  before: {initial}\n"
                f"  after:  {current}"
            )
        return b

    _check(R, "GET /projects/{id} — path_templates unchanged after apply", _read_project_final)


def main() -> int:
    from smoke_tests.test_02_auth import run as run_auth
    from smoke_tests.test_05_projects import run as run_projects

    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    ctx = SmokeContext(config=_make_config(args), results=SmokeResults())
    run_auth(ctx)
    run_projects(ctx)
    # Create a shot with an explicit code (avoids sequence dependency)
    if ctx.project_id and ctx.token:
        s, b = _request(
            method="POST",
            url=f"{ctx.config.base_url}/projects/{ctx.project_id}/shots",
            timeout=ctx.config.timeout,
            token=ctx.token,
            payload={
                "name": f"IsolShot{ctx.suffix[-4:]}",
                "code": f"IS{ctx.suffix[-4:]}",
                "frame_start": 1001,
                "frame_end": 1040,
            },
        )
        if s == 200 and isinstance(b, dict) and "id" in b:
            ctx.shot_id = b["id"]
    run(ctx)
    print_summary(ctx.results, f"Section {SECTION}")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

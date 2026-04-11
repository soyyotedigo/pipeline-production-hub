"""
Pipeline Production Hub - End-to-End Integration Test
Exercises the full production pipeline flow against the running Docker API.
Base URL: http://localhost:8000
API prefix: /api/v1
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from io import BytesIO
from typing import Any

import requests

BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/v1"

ADMIN_EMAIL = "admin@vfxhub.dev"
ADMIN_PASSWORD = "admin123"

TIMESTAMP = int(time.time())
TEST_PROJECT_NAME = f"test_pipeline_{TIMESTAMP}"


# ── Helpers ───────────────────────────────────────────────────────────────────


class PhaseResult:
    def __init__(self, phase: str) -> None:
        self.phase = phase
        self.passed = False
        self.detail = ""
        self.skipped = False
        self.skip_reason = ""

    def ok(self, detail: str) -> PhaseResult:
        self.passed = True
        self.detail = detail
        return self

    def fail(self, detail: str) -> PhaseResult:
        self.passed = False
        self.detail = detail
        return self

    def skip(self, reason: str) -> PhaseResult:
        self.skipped = True
        self.skip_reason = reason
        return self

    def status_icon(self) -> str:
        if self.skipped:
            return "SKIP"
        return "PASS" if self.passed else "FAIL"


def assert_status(resp: requests.Response, expected: int, context: str) -> None:
    if resp.status_code != expected:
        raise AssertionError(
            f"{context}: expected HTTP {expected}, got {resp.status_code}. Body: {resp.text[:500]}"
        )


def assert_field(data: dict[str, Any], key: str, context: str) -> None:
    if key not in data or data[key] is None:
        raise AssertionError(f"{context}: missing required field '{key}'. Got: {list(data.keys())}")


# ── Phase runners ─────────────────────────────────────────────────────────────


def phase_1_auth() -> tuple[PhaseResult, dict[str, str]]:
    result = PhaseResult("1. Auth")
    headers: dict[str, str] = {}
    try:
        # Valid login
        resp = requests.post(
            f"{API}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10,
        )
        assert_status(resp, 200, "POST /auth/login")
        data = resp.json()
        assert_field(data, "access_token", "login response")
        assert_field(data, "refresh_token", "login response")
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Validate token via /auth/me
        me_resp = requests.get(f"{API}/auth/me", headers=headers, timeout=10)
        assert_status(me_resp, 200, "GET /auth/me")
        me_data = me_resp.json()
        assert_field(me_data, "id", "me response")

        # Invalid credentials - expect 401
        bad_resp = requests.post(
            f"{API}/auth/login",
            json={"email": ADMIN_EMAIL, "password": "wrongpassword"},
            timeout=10,
        )
        if bad_resp.status_code != 401:
            return result.fail(
                f"Bad credentials returned {bad_resp.status_code}, expected 401"
            ), headers

        result.ok(
            f"Authenticated as {me_data.get('email', 'unknown')} | token valid | 401 on bad creds"
        )
    except Exception as exc:
        result.fail(str(exc))
    return result, headers


def phase_2_project(headers: dict[str, str]) -> tuple[PhaseResult, str | None]:
    result = PhaseResult("2. Project")
    project_id: str | None = None
    try:
        # Create test project
        resp = requests.post(
            f"{API}/projects",
            json={"name": TEST_PROJECT_NAME, "client": "IntegrationTestClient"},
            headers=headers,
            timeout=10,
        )
        assert_status(resp, 200, "POST /projects")
        data = resp.json()
        assert_field(data, "id", "project response")
        assert_field(data, "name", "project response")
        assert_field(data, "code", "project response")
        assert_field(data, "status", "project response")
        assert_field(data, "created_at", "project response")
        assert_field(data, "updated_at", "project response")

        if data["name"] != TEST_PROJECT_NAME:
            return result.fail(f"name mismatch: got '{data['name']}'"), None

        project_id = data["id"]

        # Verify via GET
        get_resp = requests.get(f"{API}/projects/{project_id}", headers=headers, timeout=10)
        assert_status(get_resp, 200, f"GET /projects/{project_id}")
        get_data = get_resp.json()
        if get_data["id"] != project_id:
            return result.fail("GET project returned different id"), None

        # Invalid request - missing name
        bad_resp = requests.post(
            f"{API}/projects",
            json={"client": "no name"},
            headers=headers,
            timeout=10,
        )
        if bad_resp.status_code not in (400, 422):
            return result.fail(
                f"Missing name returned {bad_resp.status_code}, expected 422"
            ), project_id

        result.ok(
            f"id={project_id} | code={data['code']} | status={data['status']} | 422 on bad payload"
        )
    except Exception as exc:
        result.fail(str(exc))
    return result, project_id


def phase_3_episodes_sequences(
    headers: dict[str, str], project_id: str
) -> tuple[PhaseResult, str | None, str | None]:
    result = PhaseResult("3. Episodes/Sequences")
    sequence_id: str | None = None
    try:
        # Create episode
        ep_resp = requests.post(
            f"{API}/projects/{project_id}/episodes",
            json={"name": "Episode 101", "code": "EP101"},
            headers=headers,
            timeout=10,
        )
        assert_status(ep_resp, 200, "POST /projects/{id}/episodes")
        ep_data = ep_resp.json()
        assert_field(ep_data, "id", "episode response")
        assert_field(ep_data, "name", "episode response")
        if ep_data.get("project_id") != project_id:
            return (
                result.fail(
                    f"episode project_id mismatch: {ep_data.get('project_id')} vs {project_id}"
                ),
                None,
                None,
            )
        episode_id = ep_data["id"]

        # Verify GET episode
        get_ep = requests.get(f"{API}/episodes/{episode_id}", headers=headers, timeout=10)
        assert_status(get_ep, 200, f"GET /episodes/{episode_id}")

        # Create sequence under episode
        seq_resp = requests.post(
            f"{API}/projects/{project_id}/sequences",
            json={"name": "Sequence 010", "code": "SQ010", "episode_id": episode_id},
            headers=headers,
            timeout=10,
        )
        assert_status(seq_resp, 200, "POST /projects/{id}/sequences")
        seq_data = seq_resp.json()
        assert_field(seq_data, "id", "sequence response")
        if seq_data.get("project_id") != project_id:
            return (
                result.fail(
                    f"sequence project_id mismatch: {seq_data.get('project_id')} vs {project_id}"
                ),
                episode_id,
                None,
            )
        if seq_data.get("episode_id") != episode_id:
            return (
                result.fail(
                    f"sequence episode_id mismatch: {seq_data.get('episode_id')} vs {episode_id}"
                ),
                episode_id,
                None,
            )
        sequence_id = seq_data["id"]

        # Verify GET sequence
        get_seq = requests.get(f"{API}/sequences/{sequence_id}", headers=headers, timeout=10)
        assert_status(get_seq, 200, f"GET /sequences/{sequence_id}")

        result.ok(f"episode={episode_id} | sequence={sequence_id} | parent linkage correct")
    except Exception as exc:
        result.fail(str(exc))
    return result, episode_id, sequence_id


def phase_4_shots(
    headers: dict[str, str], project_id: str, sequence_id: str | None
) -> tuple[PhaseResult, list[str]]:
    result = PhaseResult("4. Shots")
    shot_ids: list[str] = []
    try:
        shot_payloads = [
            {
                "name": "Shot 010",
                "code": "SH010",
                "sequence_id": sequence_id,
                "frame_start": 1001,
                "frame_end": 1120,
            },
            {
                "name": "Shot 020",
                "code": "SH020",
                "sequence_id": sequence_id,
                "frame_start": 1121,
                "frame_end": 1240,
            },
        ]

        for payload in shot_payloads:
            resp = requests.post(
                f"{API}/projects/{project_id}/shots",
                json=payload,
                headers=headers,
                timeout=10,
            )
            assert_status(resp, 200, f"POST /projects/{project_id}/shots")
            shot_data = resp.json()
            assert_field(shot_data, "id", "shot response")
            assert_field(shot_data, "name", "shot response")
            assert_field(shot_data, "project_id", "shot response")
            assert_field(shot_data, "status", "shot response")
            assert_field(shot_data, "created_at", "shot response")
            if shot_data["project_id"] != project_id:
                return result.fail(f"shot project_id mismatch for {payload['name']}"), shot_ids
            shot_ids.append(shot_data["id"])

        # Verify shots appear in listing
        list_resp = requests.get(
            f"{API}/projects/{project_id}/shots",
            headers=headers,
            timeout=10,
        )
        assert_status(list_resp, 200, f"GET /projects/{project_id}/shots")
        list_data = list_resp.json()
        assert_field(list_data, "items", "shot list response")
        listed_ids = [s["id"] for s in list_data["items"]]
        for sid in shot_ids:
            if sid not in listed_ids:
                return result.fail(f"Shot {sid} missing from project shots listing"), shot_ids

        # Test pagination
        page_resp = requests.get(
            f"{API}/projects/{project_id}/shots?limit=1&offset=0",
            headers=headers,
            timeout=10,
        )
        assert_status(page_resp, 200, "GET shots with pagination")
        page_data = page_resp.json()
        if len(page_data["items"]) > 1:
            return result.fail("Pagination limit=1 returned more than 1 item"), shot_ids

        # Invalid shot - missing name
        bad_resp = requests.post(
            f"{API}/projects/{project_id}/shots",
            json={"frame_start": 1001},
            headers=headers,
            timeout=10,
        )
        if bad_resp.status_code not in (400, 422):
            return result.fail(
                f"Missing name returned {bad_resp.status_code}, expected 422"
            ), shot_ids

        result.ok(f"shots={shot_ids} | listing verified | pagination ok | 422 on bad payload")
    except Exception as exc:
        result.fail(str(exc))
    return result, shot_ids


def phase_5_assets_links(
    headers: dict[str, str], project_id: str, shot_ids: list[str]
) -> tuple[PhaseResult, str | None, str | None]:
    result = PhaseResult("5. Assets & Links")
    asset_id: str | None = None
    link_id: str | None = None
    try:
        # Create asset
        resp = requests.post(
            f"{API}/projects/{project_id}/assets",
            json={
                "name": "Test Hero Prop",
                "asset_type": "prop",
                "description": "Integration test hero prop asset",
            },
            headers=headers,
            timeout=10,
        )
        assert_status(resp, 200, f"POST /projects/{project_id}/assets")
        asset_data = resp.json()
        assert_field(asset_data, "id", "asset response")
        assert_field(asset_data, "name", "asset response")
        assert_field(asset_data, "asset_type", "asset response")
        assert_field(asset_data, "status", "asset response")
        if asset_data["project_id"] != project_id:
            return result.fail("asset project_id mismatch"), None, None
        asset_id = asset_data["id"]

        # Link asset to shot
        shot_id = shot_ids[0]
        link_resp = requests.post(
            f"{API}/shots/{shot_id}/assets",
            json={"asset_id": asset_id, "link_type": "uses"},
            headers=headers,
            timeout=10,
        )
        assert_status(link_resp, 201, f"POST /shots/{shot_id}/assets")
        link_data = link_resp.json()
        assert_field(link_data, "id", "link response")
        if link_data["shot_id"] != shot_id:
            return result.fail("link shot_id mismatch"), asset_id, None
        if link_data["asset_id"] != asset_id:
            return result.fail("link asset_id mismatch"), asset_id, None
        link_id = link_data["id"]

        # Verify bidirectional: shot shows asset
        shot_assets_resp = requests.get(
            f"{API}/shots/{shot_id}/assets",
            headers=headers,
            timeout=10,
        )
        assert_status(shot_assets_resp, 200, f"GET /shots/{shot_id}/assets")
        shot_assets_data = shot_assets_resp.json()
        linked_asset_ids = [item["asset_id"] for item in shot_assets_data["items"]]
        if asset_id not in linked_asset_ids:
            return result.fail("asset not found in shot's assets list"), asset_id, link_id

        # Verify bidirectional: asset shows shot
        asset_shots_resp = requests.get(
            f"{API}/assets/{asset_id}/shots",
            headers=headers,
            timeout=10,
        )
        assert_status(asset_shots_resp, 200, f"GET /assets/{asset_id}/shots")
        asset_shots_data = asset_shots_resp.json()
        linked_shot_ids = [item["shot_id"] for item in asset_shots_data["items"]]
        if shot_id not in linked_shot_ids:
            return result.fail("shot not found in asset's shots list"), asset_id, link_id

        result.ok(f"asset={asset_id} | link={link_id} | bidirectional relationship confirmed")
    except Exception as exc:
        result.fail(str(exc))
    return result, asset_id, link_id


def phase_6_pipeline_tasks_versions(
    headers: dict[str, str],
    project_id: str,
    shot_ids: list[str],
) -> tuple[PhaseResult, str | None, str | None]:
    result = PhaseResult("6. Pipeline Tasks & Versions")
    task_id: str | None = None
    version_id: str | None = None
    try:
        shot_id = shot_ids[0]

        # Create pipeline task on shot (order is required, no default)
        task_resp = requests.post(
            f"{API}/shots/{shot_id}/tasks",
            json={"step_name": "Lighting", "step_type": "lighting", "order": 1},
            headers=headers,
            timeout=10,
        )
        assert_status(task_resp, 201, f"POST /shots/{shot_id}/tasks")
        task_data = task_resp.json()
        assert_field(task_data, "id", "pipeline task response")
        assert_field(task_data, "step_name", "pipeline task response")
        assert_field(task_data, "status", "pipeline task response")
        if task_data.get("shot_id") != shot_id:
            return (
                result.fail(f"task shot_id mismatch: {task_data.get('shot_id')} vs {shot_id}"),
                None,
                None,
            )
        task_id = task_data["id"]

        # Create version for the pipeline task
        version_resp = requests.post(
            f"{API}/pipeline-tasks/{task_id}/versions",
            json={"description": "First lighting pass", "media_url": None},
            headers=headers,
            timeout=10,
        )
        assert_status(version_resp, 201, f"POST /pipeline-tasks/{task_id}/versions")
        version_data = version_resp.json()
        assert_field(version_data, "id", "version response")
        assert_field(version_data, "version_number", "version response")
        assert_field(version_data, "code", "version response")
        assert_field(version_data, "status", "version response")
        if version_data.get("pipeline_task_id") != task_id:
            return result.fail("version pipeline_task_id mismatch"), task_id, None
        if version_data["version_number"] != 1:
            return (
                result.fail(f"expected version_number=1, got {version_data['version_number']}"),
                task_id,
                None,
            )
        version_id = version_data["id"]

        # Create second version - verify auto-increment
        v2_resp = requests.post(
            f"{API}/pipeline-tasks/{task_id}/versions",
            json={"description": "Second lighting pass"},
            headers=headers,
            timeout=10,
        )
        assert_status(v2_resp, 201, f"POST /pipeline-tasks/{task_id}/versions (v2)")
        v2_data = v2_resp.json()
        if v2_data["version_number"] != 2:
            return (
                result.fail(f"expected version_number=2, got {v2_data['version_number']}"),
                task_id,
                version_id,
            )

        result.ok(
            f"task={task_id} | version={version_id} | v1+v2 auto-numbered | code={version_data['code']}"
        )
    except Exception as exc:
        result.fail(str(exc))
    return result, task_id, version_id


def phase_7_file_upload(
    headers: dict[str, str], project_id: str, shot_ids: list[str]
) -> tuple[PhaseResult, str | None]:
    result = PhaseResult("7. File Upload")
    file_id: str | None = None
    try:
        shot_id = shot_ids[0] if shot_ids else None
        dummy_content = b"PIPELINE_INTEGRATION_TEST_FILE\nTimestamp: " + str(TIMESTAMP).encode()
        files = {
            "upload": ("integration_test.txt", BytesIO(dummy_content), "text/plain"),
        }
        data: dict[str, str] = {}
        if shot_id:
            data["shot_id"] = shot_id

        resp = requests.post(
            f"{API}/projects/{project_id}/files/upload",
            files=files,
            data=data,
            headers=headers,
            timeout=30,
        )
        assert_status(resp, 200, f"POST /projects/{project_id}/files/upload")
        file_data = resp.json()
        assert_field(file_data, "id", "file response")
        assert_field(file_data, "original_name", "file response")
        assert_field(file_data, "mime_type", "file response")
        assert_field(file_data, "size_bytes", "file response")  # field is size_bytes not size
        assert_field(file_data, "created_at", "file response")
        assert_field(file_data, "checksum_sha256", "file response")

        if file_data["original_name"] != "integration_test.txt":
            return result.fail(f"filename mismatch: {file_data['original_name']}"), None
        if file_data["size_bytes"] != len(dummy_content):
            return result.fail(
                f"size mismatch: expected {len(dummy_content)}, got {file_data['size_bytes']}"
            ), None
        file_id = file_data["id"]

        # Verify file metadata via GET
        get_resp = requests.get(f"{API}/files/{file_id}", headers=headers, timeout=10)
        assert_status(get_resp, 200, f"GET /files/{file_id}")
        get_data = get_resp.json()
        if get_data["id"] != file_id:
            return result.fail("GET file returned different id"), file_id

        # Verify file appears in project listing
        list_resp = requests.get(
            f"{API}/projects/{project_id}/files",
            headers=headers,
            timeout=10,
        )
        assert_status(list_resp, 200, f"GET /projects/{project_id}/files")
        list_data = list_resp.json()
        assert_field(list_data, "items", "file list response")
        listed_ids = [f["id"] for f in list_data["items"]]
        if file_id not in listed_ids:
            return result.fail("uploaded file missing from project files listing"), file_id

        # Verify file is linked to shot if shot_id was provided
        shot_link_ok = ""
        if shot_id:
            shot_files_resp = requests.get(
                f"{API}/shots/{shot_id}/files",
                headers=headers,
                timeout=10,
            )
            assert_status(shot_files_resp, 200, f"GET /shots/{shot_id}/files")
            shot_files_data = shot_files_resp.json()
            shot_file_ids = [f["id"] for f in shot_files_data["items"]]
            if file_id in shot_file_ids:
                shot_link_ok = " | shot-file link verified"
            else:
                shot_link_ok = " | WARNING: file not in shot files list"

        result.ok(
            f"file={file_id} | name=integration_test.txt | size_bytes={len(dummy_content)}"
            f" | checksum present | project listing verified{shot_link_ok}"
        )
    except Exception as exc:
        result.fail(str(exc))
    return result, file_id


def phase_8_notes_tags(
    headers: dict[str, str], project_id: str, shot_ids: list[str]
) -> PhaseResult:
    result = PhaseResult("8. Notes & Tags")
    try:
        shot_id = shot_ids[0]

        # Create note on shot via convenience endpoint
        note_resp = requests.post(
            f"{API}/shots/{shot_id}/notes",
            json={
                "project_id": project_id,
                "subject": "Integration Test Note",
                "body": "This note was created by the pipeline integration test.",
                "is_client_visible": False,
            },
            headers=headers,
            timeout=10,
        )
        assert_status(note_resp, 201, f"POST /shots/{shot_id}/notes")
        note_data = note_resp.json()
        assert_field(note_data, "id", "note response")
        assert_field(note_data, "body", "note response")
        assert_field(note_data, "entity_type", "note response")
        assert_field(note_data, "created_at", "note response")
        if note_data["entity_type"] != "shot":
            return result.fail(f"entity_type mismatch: {note_data['entity_type']}")
        if note_data["entity_id"] != shot_id:
            return result.fail("entity_id mismatch")
        note_id = note_data["id"]

        # Verify note via GET
        get_note_resp = requests.get(f"{API}/notes/{note_id}", headers=headers, timeout=10)
        assert_status(get_note_resp, 200, f"GET /notes/{note_id}")
        get_note_data = get_note_resp.json()
        if get_note_data["id"] != note_id:
            return result.fail("GET note returned different id")

        # Verify note in shot notes list
        shot_notes_resp = requests.get(
            f"{API}/shots/{shot_id}/notes",
            headers=headers,
            timeout=10,
        )
        assert_status(shot_notes_resp, 200, f"GET /shots/{shot_id}/notes")
        shot_notes_data = shot_notes_resp.json()
        assert_field(shot_notes_data, "items", "note list response")
        note_ids_in_list = [n["id"] for n in shot_notes_data["items"]]
        if note_id not in note_ids_in_list:
            return result.fail("created note not found in shot notes list")

        # Create project-scoped tag
        tag_resp = requests.post(
            f"{API}/projects/{project_id}/tags",
            json={"name": "integration-test-tag", "color": "#FF5733"},
            headers=headers,
            timeout=10,
        )
        assert_status(tag_resp, 201, f"POST /projects/{project_id}/tags")
        tag_data = tag_resp.json()
        assert_field(tag_data, "id", "tag response")
        assert_field(tag_data, "name", "tag response")
        tag_id = tag_data["id"]

        # Attach tag to shot
        attach_resp = requests.post(
            f"{API}/shots/{shot_id}/tags",
            json={"tag_id": tag_id},
            headers=headers,
            timeout=10,
        )
        assert_status(attach_resp, 201, f"POST /shots/{shot_id}/tags")
        attach_data = attach_resp.json()
        assert_field(attach_data, "id", "entity tag response")

        # Verify tag is in shot's tags list
        shot_tags_resp = requests.get(
            f"{API}/shots/{shot_id}/tags",
            headers=headers,
            timeout=10,
        )
        assert_status(shot_tags_resp, 200, f"GET /shots/{shot_id}/tags")
        shot_tags_data = shot_tags_resp.json()
        shot_tag_ids = [t["id"] for t in shot_tags_data]
        if tag_id not in shot_tag_ids:
            return result.fail("created tag not found in shot tags list")

        result.ok(
            f"note={note_id} (on shot, entity_type=shot) | "
            f"tag={tag_id} ('{tag_data['name']}') | "
            f"tag attached and listed on shot"
        )
    except Exception as exc:
        result.fail(str(exc))
    return result


def phase_9_cleanup(
    headers: dict[str, str],
    project_id: str | None,
) -> PhaseResult:
    result = PhaseResult("9. Cleanup")
    if not project_id:
        return result.skip("No project_id available to clean up")
    try:
        # Archive the test project (soft delete)
        archive_resp = requests.post(
            f"{API}/projects/{project_id}/archive",
            headers=headers,
            timeout=10,
        )
        assert_status(archive_resp, 200, f"POST /projects/{project_id}/archive")
        archive_data = archive_resp.json()
        # Archive sets archived_at (soft delete) - status remains unchanged
        if archive_data.get("archived_at") is None:
            return result.fail(
                f"archived_at is null after archive call; project status={archive_data.get('status')}"
            )

        # Hard delete the test project with force=true
        delete_resp = requests.delete(
            f"{API}/projects/{project_id}?force=true",
            headers=headers,
            timeout=10,
        )
        assert_status(delete_resp, 204, f"DELETE /projects/{project_id}?force=true")

        # Confirm it's gone
        check_resp = requests.get(f"{API}/projects/{project_id}", headers=headers, timeout=10)
        if check_resp.status_code == 200:
            return result.fail("project still accessible after hard delete")

        result.ok(
            f"project {project_id} archived (archived_at set) then hard-deleted | confirmed gone"
        )
    except Exception as exc:
        result.fail(str(exc))
    return result


# ── Main test runner ──────────────────────────────────────────────────────────


def run_integration_tests() -> None:
    print(f"\nStarting Pipeline Integration Tests at {datetime.utcnow().isoformat()}Z")
    print(f"Target: {BASE_URL}\n")

    # Check health first
    health_resp = requests.get(f"{BASE_URL}/health", timeout=10)
    if health_resp.status_code != 200:
        print(f"FATAL: Health check failed ({health_resp.status_code}). Aborting.")
        sys.exit(1)
    print(f"Health check: OK ({health_resp.status_code})")

    # Collected entity IDs
    project_id: str | None = None
    sequence_id: str | None = None
    shot_ids: list[str] = []
    asset_id: str | None = None
    link_id: str | None = None
    task_id: str | None = None
    version_id: str | None = None
    file_id: str | None = None

    phases: list[PhaseResult] = []

    # Phase 1: Auth
    p1, headers = phase_1_auth()
    phases.append(p1)
    if not p1.passed:
        print(f"FATAL: Auth failed: {p1.detail}")
        _print_report(phases, project_id, shot_ids, file_id, asset_id, link_id, task_id, version_id)
        sys.exit(1)

    # Phase 2: Project
    p2, project_id = phase_2_project(headers)
    phases.append(p2)

    # Phase 3: Episodes/Sequences
    if project_id:
        p3, _episode_id, sequence_id = phase_3_episodes_sequences(headers, project_id)
    else:
        p3 = PhaseResult("3. Episodes/Sequences").skip("Depends on Phase 2 (no project_id)")
    phases.append(p3)

    # Phase 4: Shots
    if project_id:
        p4, shot_ids = phase_4_shots(headers, project_id, sequence_id)
    else:
        p4 = PhaseResult("4. Shots").skip("Depends on Phase 2 (no project_id)")
    phases.append(p4)

    # Phase 5: Assets & Links
    if project_id and shot_ids:
        p5, asset_id, link_id = phase_5_assets_links(headers, project_id, shot_ids)
    else:
        p5 = PhaseResult("5. Assets & Links").skip("Depends on Phases 2+4")
    phases.append(p5)

    # Phase 6: Pipeline Tasks & Versions
    if project_id and shot_ids:
        p6, task_id, version_id = phase_6_pipeline_tasks_versions(headers, project_id, shot_ids)
    else:
        p6 = PhaseResult("6. Pipeline Tasks & Versions").skip("Depends on Phases 2+4")
    phases.append(p6)

    # Phase 7: File Upload
    if project_id:
        p7, file_id = phase_7_file_upload(headers, project_id, shot_ids)
    else:
        p7 = PhaseResult("7. File Upload").skip("Depends on Phase 2 (no project_id)")
    phases.append(p7)

    # Phase 8: Notes & Tags
    if project_id and shot_ids:
        p8 = phase_8_notes_tags(headers, project_id, shot_ids)
    else:
        p8 = PhaseResult("8. Notes & Tags").skip("Depends on Phases 2+4")
    phases.append(p8)

    # Phase 9: Cleanup
    p9 = phase_9_cleanup(headers, project_id)
    phases.append(p9)

    _print_report(phases, project_id, shot_ids, file_id, asset_id, link_id, task_id, version_id)


def _print_report(
    phases: list[PhaseResult],
    project_id: str | None,
    shot_ids: list[str],
    file_id: str | None,
    asset_id: str | None,
    link_id: str | None,
    task_id: str | None,
    version_id: str | None,
) -> None:
    passed = sum(1 for p in phases if p.passed and not p.skipped)
    total_runnable = sum(1 for p in phases if not p.skipped)
    failed = [p for p in phases if not p.passed and not p.skipped]

    print("\n" + "=" * 70)
    print("## Pipeline Integration Test Report")
    print(f"\n**Date:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("**Environment:** Docker Compose")
    print(f"**Base URL:** {BASE_URL}")
    print("\n### Results Summary\n")
    print(f"{'Phase':<35} {'Status':<8} {'Details'}")
    print("-" * 70)

    for p in phases:
        icon = p.status_icon()
        detail = p.skip_reason if p.skipped else p.detail
        if not detail:
            detail = "(no detail)"
        # Truncate detail for table readability
        detail_short = detail[:80] + "..." if len(detail) > 80 else detail
        print(f"{p.phase:<35} [{icon}]   {detail_short}")

    overall = "PASS" if not failed else "FAIL"
    print(f"\n### Overall: {overall} ({passed}/{total_runnable} phases passed)")

    if failed:
        print("\n### Issues Found")
        for p in failed:
            print(f"  - {p.phase}: {p.detail}")

    print("\n### Entity IDs Created")
    print(f"  Project:       {project_id or 'N/A'}")
    print(f"  Shots:         {shot_ids or 'N/A'}")
    print(f"  Asset:         {asset_id or 'N/A'}")
    print(f"  Shot-Asset Link: {link_id or 'N/A'}")
    print(f"  Pipeline Task: {task_id or 'N/A'}")
    print(f"  Version:       {version_id or 'N/A'}")
    print(f"  File:          {file_id or 'N/A'}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_integration_tests()

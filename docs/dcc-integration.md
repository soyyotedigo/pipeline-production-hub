# DCC Integration — Pipeline Production Hub

**Location:** `examples/dcc/`
**Purpose:** Demonstrate how an artist publishes from Maya, Houdini, or Nuke by connecting directly to the hub API, replicating the pattern of ShotGrid Create and ftrack Connect.

---

## Layered architecture

```
task_launcher_gui.py          ← Desktop GUI (PySide6)
maya_publish.py               ← Maya adapter (maya.cmds)
houdini_publish.py            ← Houdini adapter (hou)
nuke_publish.py               ← Nuke adapter (nuke)
artist_publish.py             ← Generic CLI (no DCC required)
        ↓ all use
_workflow.py                  ← Reusable publish logic
        ↓ which uses
_api.py                       ← Hub HTTP client (httpx)
        ↓ which talks to
Pipeline Production Hub API   ← FastAPI at localhost:8000
```

The DCC adapters are only responsible for **extracting context** from the host software (scene path, frame range). The real work — authenticate, upload, create version, update task status — is handled by `_workflow.py` in all cases.

---

## Tool reference

| File | Type | What it does | DCC API used | Mock mode |
|------|------|-------------|--------------|-----------|
| `_api.py` | HTTP client | httpx wrapper with JWT, typed methods for each hub endpoint | — | — |
| `_workflow.py` | Core logic | `run_publish()`: uploads file, creates version, updates task status | — | — |
| `artist_publish.py` | Generic CLI | Publish from terminal without a DCC open — useful for render farm scripts | — | `--file` any path |
| `maya_publish.py` | Maya adapter | Reads active scene and frame range from `maya.cmds`, publishes to hub | `maya.cmds` | `--mode mock` or `--scene-path` |
| `houdini_publish.py` | Houdini adapter | Reads active `.hip` and frame range from `hou.playbar`, publishes to hub | `hou` | `--mode mock` or `--hip-path` |
| `nuke_publish.py` | Nuke adapter | Reads active script and frame range from `nuke.root()`, publishes to hub | `nuke` | `--mode mock` or `--script-path` |
| `task_launcher_gui.py` | PySide6 GUI | Desktop window: login, browse projects/shots/tasks, publish with file picker | — | Runs without DCC |

---

## Per-tool detail

### `_api.py` — `PipelineApiClient`

Synchronous HTTP client over `httpx`. Encapsulates JWT authentication and all relevant hub endpoints as typed methods.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `login()` | `POST /api/v1/auth/login` | Obtains JWT, stores it in memory |
| `get_me()` | `GET /api/v1/auth/me` | Verifies authenticated user |
| `list_projects()` | `GET /api/v1/projects` | Lists projects accessible to the user |
| `list_project_shots()` | `GET /api/v1/projects/{id}/shots` | Lists shots for a project |
| `list_shot_tasks()` | `GET /api/v1/shots/{id}/tasks` | Lists pipeline tasks for a shot |
| `create_shot_task()` | `POST /api/v1/shots/{id}/tasks` | Creates task if it does not exist |
| `create_asset_task()` | `POST /api/v1/assets/{id}/tasks` | Creates asset task if it does not exist |
| `upload_project_file()` | `POST /api/v1/projects/{id}/files/upload` | Uploads file to the hub (and to S3) |
| `create_version()` | `POST /api/v1/pipeline-tasks/{id}/versions` | Creates a reviewable version with file_ids |
| `update_pipeline_task_status()` | `PATCH /api/v1/pipeline-tasks/{id}/status` | Moves task to `review`, `approved`, etc. |
| `resolve_publish_context()` | Composite | Resolves task → shot/asset → project in a single call |

The publish context is modeled as a frozen `PublishContext` dataclass:
```
task_id, project_id, entity_type, entity_id, entity_code,
task_step_name, task_step_type, task_status
```

---

### `_workflow.py` — `run_publish()`

Shared publish logic used by all adapters. Receives a `PublishRequest` and executes this flow:

```
1. Verify the file exists on disk
2. get_me()  →  confirm authenticated user
3. resolve_publish_context(task_id)  →  get project, entity, step
4. upload_project_file()  →  upload primary_file (and preview if provided)
5. create_version()  →  associate file_ids with the reviewable version
6. [optional] update_pipeline_task_status()  →  move task to review/approved
7. Return PublishResult with full context for the summary
```

`PublishRequest` — input parameters:

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Pipeline task ID |
| `primary_file` | `Path` | Main file to upload |
| `preview_file` | `Path \| None` | Optional preview (thumbnail, etc.) |
| `description` | `str \| None` | Version description |
| `set_task_status` | `str \| None` | If provided, moves the task to this status |
| `status_comment` | `str \| None` | Comment for the status change |
| `source_label` | `str` | Who is publishing ("Maya", "Nuke", "CLI") |

---

### `artist_publish.py` — Generic CLI

Publish from terminal without an open DCC. Useful for:
- Render farm scripts that upload outputs automatically
- Pipeline TDs testing the publish flow without opening Maya
- CI/CD pipelines verifying end-to-end publish behavior

```bash
python examples/dcc/artist_publish.py \
  --email artist@studio.com \
  --password secret \
  --project-code DEMO \
  --shot-code SH010 \
  --step-type animation \
  --file /renders/SH010_anim_v001.abc \
  --set-task-status review
```

Entity resolution by ID or by code:

| Available flags | When to use |
|-----------------|-------------|
| `--task-id` | You know the exact task UUID |
| `--shot-id` / `--asset-id` | You know the shot/asset UUID |
| `--project-code` + `--shot-code` | You only know the human-readable codes |

If the task does not exist, `--step-type` + `--step-name` will create it automatically.

---

### `maya_publish.py` — Maya Adapter

Automatically detects whether it is running inside Maya or outside with `--mode auto`:

| Mode | Behavior |
|------|----------|
| `--mode auto` | Attempts `maya.cmds`, falls back to mock on failure |
| `--mode maya` | Forces `maya.cmds`, fails if not available |
| `--mode mock` | Uses local fixture or `--scene-path` |

When running **inside Maya** (`maya.cmds` available):
```python
scene_path = Path(cmds.file(q=True, sceneName=True))
frame_start = int(cmds.playbackOptions(q=True, minTime=True))
frame_end   = int(cmds.playbackOptions(q=True, maxTime=True))
```

Maya-specific parameters:

| Flag | Default | Description |
|------|---------|-------------|
| `--scene-path` | active scene | Path to the `.ma` / `.mb` file to upload |
| `--frame-start` | playback `minTime` | Start frame of the range |
| `--frame-end` | playback `maxTime` | End frame of the range |
| `--step-type` | `animation` | Pipeline step type |
| `--step-name` | `"Animation"` | Human-readable step name |

---

### `houdini_publish.py` — Houdini Adapter

Same pattern as Maya, using the Houdini Python API (`hou`):

| Mode | Behavior |
|------|----------|
| `--mode auto` | Attempts `hou`, falls back to mock on failure |
| `--mode houdini` | Forces `hou`, fails if not available |
| `--mode mock` | Uses local fixture or `--hip-path` |

When running **inside Houdini** (`hou` available):
```python
hip_path    = Path(hou.hipFile.path())
frame_start = int(hou.playbar.frameRange()[0])
frame_end   = int(hou.playbar.frameRange()[1])
```

Houdini-specific parameters:

| Flag | Default | Description |
|------|---------|-------------|
| `--hip-path` | active `.hip` | Path to the hip file to upload |
| `--frame-start` | `playbar.frameRange()[0]` | Start frame |
| `--frame-end` | `playbar.frameRange()[1]` | End frame |
| `--step-type` | `fx` | Default for FX work |
| `--step-name` | `"FX"` | Human-readable step name |

---

### `nuke_publish.py` — Nuke Adapter

Uses the Nuke Python API (`nuke`):

| Mode | Behavior |
|------|----------|
| `--mode auto` | Attempts `nuke`, falls back to mock on failure |
| `--mode nuke` | Forces `nuke`, fails if not available |
| `--mode mock` | Uses local fixture or `--script-path` |

When running **inside Nuke** (`nuke` available):
```python
script_path = Path(nuke.root().name())
frame_start = int(nuke.root()["first_frame"].value())
frame_end   = int(nuke.root()["last_frame"].value())
```

Nuke-specific parameters:

| Flag | Default | Description |
|------|---------|-------------|
| `--script-path` | active script | Path to the `.nk` file to upload |
| `--frame-start` | root `first_frame` | Start frame |
| `--frame-end` | root `last_frame` | End frame |
| `--step-type` | `compositing` | Default for compositing work |
| `--step-name` | `"Compositing"` | Human-readable step name |

---

### `task_launcher_gui.py` — PySide6 GUI

Desktop window inspired by ShotGrid Create / ftrack Connect.
Does not require an open DCC — runs as a standalone application.

**Requirements:**
```bash
pip install -e ".[dcc-gui]"   # installs PySide6
python examples/dcc/task_launcher_gui.py
```

**GUI flow:**

```
1. Login  →  base URL + email + password
2. Project combo  →  loads automatically on login
3. Shot combo  →  loads on project selection
4. Task list  →  loads on shot selection (step_name, step_type, status)
5. File picker  →  Browse... opens QFileDialog
6. Publish  →  enabled only when a task and file are selected
7. Activity log  →  shows each workflow step in real time
8. Status bar  →  published version ID on completion
```

**Window components:**

| Widget | Qt type | Function |
|--------|---------|---------|
| Base URL, Email, Password | `QLineEdit` | Connection credentials |
| Log in | `QPushButton` | Triggers authentication + project load |
| Project | `QComboBox` | Project selector, populated by `list_projects()` |
| Shot | `QComboBox` | Shot selector, populated by `list_project_shots()` |
| Pipeline tasks | `QListWidget` | Task list for the selected shot |
| File path | `QLineEdit` | Path of the file to publish |
| Browse | `QPushButton` | Opens `QFileDialog.getOpenFileName()` |
| Publish | `QPushButton` | Disabled until a task and file are selected |
| Activity log | `QPlainTextEdit` | Real-time log of each step |
| Status bar | `QStatusBar` | Connection state and last published version |

---

## Full publish flow (all adapters)

```
DCC (Maya / Houdini / Nuke / CLI / GUI)
  │
  ├─ 1. Read scene context (path, frames, step)
  │
  ├─ 2. PipelineApiClient.login()
  │       POST /api/v1/auth/login  →  JWT
  │
  ├─ 3. ensure_task()
  │       If task_id is known → use it directly
  │       Otherwise → resolve entity by ID or code → POST /api/v1/shots/{id}/tasks
  │
  ├─ 4. run_publish()
  │       ├─ resolve_publish_context()  →  task + shot/asset + project
  │       ├─ upload_project_file()  →  POST /api/v1/projects/{id}/files/upload
  │       │       file goes to S3 (pipeline-production-hub bucket)
  │       ├─ create_version()  →  POST /api/v1/pipeline-tasks/{id}/versions
  │       └─ [optional] update_pipeline_task_status()  →  PATCH .../status
  │
  └─ 5. render_summary()  →  prints result to console / Activity log
```

---

## Scope and limitations

- The adapters do not trigger renders or export from the DCC — they upload a file that already exists on disk.
- The GUI is synchronous (no `QThread`) — not suitable for production use with large files.
- Automatic thumbnail generation from DCCs is not handled here — that is the background worker's responsibility.

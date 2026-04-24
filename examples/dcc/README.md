# DCC Integration Examples

These examples are thin DCC-side publish clients that exercise the real Pipeline Production Hub API for:

- authentication
- pipeline task resolution or creation
- file upload
- version creation
- optional task status transitions

They are intended for portfolio demos and local learning. The backend workflow is real. Only the host-specific DCC context may be mocked.

## Files

- `artist_publish.py` — generic CLI publish flow
- `nuke_publish.py` — Nuke-oriented publish flow with live or mock mode
- `maya_publish.py` — Maya-oriented publish flow with live or mock mode
- `houdini_publish.py` — Houdini-oriented publish flow with live or mock mode
- `task_launcher_gui.py` — PySide6 desktop launcher (login → pick task → publish)
- `fixtures/comp_v001.nk` — tiny mock Nuke script for portable demos
- `fixtures/anim_v001.ma` — tiny Maya ASCII fixture for portable demos
- `fixtures/fx_v001.hiplc` — Houdini placeholder for portable demos

## Prerequisites

1. Start the Docker stack:

```bash
docker compose up --build
```

2. Seed demo data:

```bash
docker compose exec api python -m app.scripts.seed
```

3. Run the examples from a local Python environment that has `httpx` available:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev,test]"
```

The API still runs in Docker. The client scripts run locally and talk to `http://localhost:8000`.

## Default demo credentials

- admin: `admin@vfxhub.dev` / `admin123`
- artist: `artist@vfxhub.dev` / `demo123`

## Fastest seed-backed workflow

The seed does not create pipeline tasks. The examples support creating a task on demand from a seeded shot or asset.

### Generic artist publish against seeded shot `SH010`

```bash
python examples/dcc/artist_publish.py \
  --base-url http://localhost:8000 \
  --email admin@vfxhub.dev \
  --password admin123 \
  --project-code DEMO \
  --shot-code SH010 \
  --step-type compositing \
  --step-name "Comp" \
  --file examples/dcc/fixtures/comp_v001.nk
```

### Nuke-oriented publish in mock mode

```bash
python examples/dcc/nuke_publish.py \
  --base-url http://localhost:8000 \
  --email admin@vfxhub.dev \
  --password admin123 \
  --mode mock \
  --project-code DEMO \
  --shot-code SH010 \
  --frame-start 1001 \
  --frame-end 1048
```

Use `--preview-file <path>` in either example to upload an additional review file such as a `.mov` or `.jpg`.

### Maya publish in mock mode

```bash
python examples/dcc/maya_publish.py \
  --base-url http://localhost:8000 \
  --email admin@vfxhub.dev \
  --password admin123 \
  --mode mock \
  --project-code DEMO \
  --shot-code SH010 \
  --step-type animation \
  --frame-start 1001 \
  --frame-end 1100
```

Run with `--mode maya` from a `mayapy` interpreter to read the live scene path
and playback range via `cmds.file` and `cmds.playbackOptions`.

### Houdini publish in mock mode

```bash
python examples/dcc/houdini_publish.py \
  --base-url http://localhost:8000 \
  --email admin@vfxhub.dev \
  --password admin123 \
  --mode mock \
  --project-code DEMO \
  --shot-code SH010 \
  --step-type fx \
  --frame-start 1001 \
  --frame-end 1100
```

Run with `--mode houdini` from `hython` to read the live `hou.hipFile.path()`
and `hou.playbar.frameRange()`.

### Desktop task launcher (PySide6 GUI)

A small ShotGrid Create-style window that logs in, browses projects and shots,
lists pipeline tasks, and publishes a selected file using the same workflow as
the CLI examples.

Install the optional GUI dependency once:

```bash
pip install -e ".[dcc-gui]"
```

Then launch:

```bash
python examples/dcc/task_launcher_gui.py
```

## Real Nuke workflow

If you can run the script from a Nuke Python environment, the example can read the live script path and frame range:

```bash
python examples/dcc/nuke_publish.py \
  --base-url http://localhost:8000 \
  --email admin@vfxhub.dev \
  --password admin123 \
  --mode nuke \
  --project-code DEMO \
  --shot-code SH010
```

If Nuke is not available, `--mode auto` falls back to the bundled mock script.

## Optional task status changes

Task transitions depend on the current state. To avoid fake success paths, the scripts only change task status when you explicitly ask for it:

```bash
python examples/dcc/artist_publish.py \
  --base-url http://localhost:8000 \
  --email admin@vfxhub.dev \
  --password admin123 \
  --project-code DEMO \
  --shot-code SH010 \
  --step-type compositing \
  --file examples/dcc/fixtures/comp_v001.nk \
  --set-task-status in_progress
```

## Important API note

The current backend associates files to a `Version` at version creation time through `file_ids`. Because of that, these examples intentionally:

1. upload file(s) first
2. create the `Version` second using the uploaded file ids

This is a real contract workaround, not a fake simplification.

## Portfolio guidance

For stronger portfolio presentation:

- customize seeded project and client names before recording demos
- replace the fixture script with a real `.nk` file from your local exercises
- pass a real preview output with `--preview-file`
- capture one successful terminal run and one API-side confirmation in Swagger or the DB

## Troubleshooting

- `401 Unauthorized`: check credentials and login rate limiting
- `404` on project or shot code: verify the seed ran and the code exists
- `File not found`: use an absolute or repository-relative path that exists
- `Invalid status transition`: retry without `--set-task-status` or choose a valid next state

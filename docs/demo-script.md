# Interview Demo Script

Use this script for a 2 to 5 minute walkthrough of Pipeline Production Hub.

## Goal

Show that the system is not just a CRUD API, but a compact production-management backend with authentication, RBAC, production entities, review flows, file support, and operational visibility.

## Demo setup

Start the stack and seed demo data:

```bash
docker compose up --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.scripts.seed
```

Default seeded demo values used below:

- Admin login: `admin@vfxhub.dev` / `admin123`
- Demo project: `DEMO` (`Demo Project`)
- Demo users: `supervisor@vfxhub.dev`, `lead@vfxhub.dev`, `artist@vfxhub.dev`, `worker@vfxhub.dev`, `client@vfxhub.dev`
- Demo episodes: `E01`, `E02`
- Demo sequences: `SQ010`, `SQ020`, `SQ030`
- Demo shots: `SH010 Opening Wide`, `SH020 Hero Reveal`, `SH030 FX Impact`
- Demo assets: `AST-CHR-001 Hero Character`, `AST-ENV-001 Main Environment`, `AST-FX-001 Explosion FX`

Open:

- Swagger UI: `http://localhost:8000/docs`
- Health endpoint: `http://localhost:8000/health`
- Metrics endpoint: `http://localhost:8000/metrics`

## Fixed script

### 1. Start with the value proposition

Say:

"This is a FastAPI backend for production pipeline management. It models projects, shots, assets, versions, tasks, notes, deliveries, and related workflow concerns such as auth, RBAC, metrics, and background jobs."

### 2. Show login

- Open the auth endpoints in Swagger.
- Run login with the seeded admin user `admin@vfxhub.dev` / `admin123`.
- Point out access and refresh tokens.

Key point:

"The API supports short-lived access tokens, refresh tokens, and logout backed by Redis token invalidation."

### 3. Show a real production entity flow

- List projects and open the seeded `DEMO` project.
- Open the nested shot route and list shots inside `DEMO`.
- Call out `SH010 Opening Wide` in `SQ010` and the hierarchy `project -> episode -> sequence -> shot`.
- Highlight that project structure is not flat CRUD; shots and assets live inside a production hierarchy.

Key point:

"The API is organized around production relationships, not only around isolated tables."

### 4. Show workflow progression

- Update one seeded shot status, for example move `SH030 FX Impact` from `pending` to `in_progress`.
- Then open project versions or shot versions and show that seeded review data already exists.
- If you want one extra click, mention playlists or deliveries as downstream review surfaces.

Key point:

"This backend is meant to support production state changes, review loops, and artist-supervisor collaboration."

### 5. Show file/version flow

- Open `GET /projects/{id}/versions` for the seeded `DEMO` project and show that the project already contains seeded versions.
- Open `GET /shots/{id}/versions` for `SH010` or `SH020` to show version history tied to production work.
- If you want a stronger storage example, open `GET /shots/{id}/files` or `GET /projects/{id}/files` and point out file metadata plus version lineage endpoints under `/files/{id}/versions`.
- Mention that file uploads enqueue thumbnail and checksum background tasks after metadata is created.

Key point:

"The project includes reviewable version history and file lineage, not just entity CRUD. Uploads also trigger background work through the task queue."

### 6. Show operational credibility

- Open `/health`.
- Open `/metrics`.
- Mention Docker Compose, Alembic migrations, tests, and CI.

Key point:

"I wanted the project to show production-minded engineering, not just endpoint count."

## Optional extension

If there is time, show one of these:

- background task flow
- Bruno collection or smoke test coverage
- DCC example under `examples/dcc/`

## What to avoid

- Do not improvise new flows during the demo.
- Do not claim features you have not validated recently.
- Do not go endpoint by endpoint.
- Do not spend the whole demo on setup commands.

## Interview framing

Good closing line:

"The project is intentionally shaped as a portfolio backend that shows how I think about API design, production workflows, system boundaries, and shipping something credible end to end."

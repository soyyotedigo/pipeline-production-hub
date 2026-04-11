# Pipeline Production Hub

> Production pipeline management system for VFX studios

[![CI](https://github.com/soyyotedigo/pipeline-production-hub-dev/actions/workflows/ci.yml/badge.svg)](https://github.com/soyyotedigo/pipeline-production-hub-dev/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Coverage](https://img.shields.io/badge/Coverage-92%25-brightgreen)
![Tests](https://img.shields.io/badge/Tests-566%20passed-brightgreen)
![MyPy](https://img.shields.io/badge/MyPy-0%20errors-blue)

---

## What this is

Pipeline Production Hub is a backend REST API that manages the full production lifecycle of creative projects: shots, assets, departments, pipeline tasks, client deliveries, hour tracking, and internal reviews.

It was built as a portfolio project demonstrating production-grade patterns in FastAPI — async-first architecture, layered service design, RBAC, structured logging, Prometheus metrics, and pluggable cloud storage. The system is flexible enough to support VFX studios, game development pipelines, animation houses, and other media production workflows.

---

## Tech Stack

| Layer            | Technology                                           |
| ---------------- | ---------------------------------------------------- |
| Framework        | FastAPI + Uvicorn                                    |
| Database         | PostgreSQL 16 (async via `asyncpg`)                  |
| ORM / Migrations | SQLAlchemy 2.0 + Alembic                             |
| Cache / Queue    | Redis 7 (task queue, token blacklist, rate limiting) |
| Auth             | JWT (access + refresh tokens) + bcrypt               |
| Config           | Pydantic Settings v2                                 |
| Logging          | structlog (structured JSON logs)                     |
| Metrics          | Prometheus + prometheus-fastapi-instrumentator       |
| Containerization | Docker / Docker Compose                              |
| Testing          | Pytest + httpx async client                          |
| Code quality     | Ruff, MyPy, Hatch                                    |

---

## Architecture

```
Client
  │
  ▼
FastAPI Router          ← schema validation, dependency injection
  │
  ▼
Service Layer           ← business logic, RBAC enforcement
  │
  ▼
Repository Layer        ← async SQLAlchemy queries, no business logic
  │
  ├──▶ PostgreSQL       ← persistent state
  └──▶ Redis            ← task queue, token blacklist, rate limit, metrics

Background Worker       ← separate process, consumes Redis queue
  └──▶ Storage          ← local filesystem or S3-compatible
```

All I/O is async. Background jobs (e.g. project exports) are enqueued to Redis and consumed by a dedicated worker process.

---

## Design Highlights

- **Layered architecture** — strict separation: routers handle HTTP, services own business rules, repositories own persistence. No business logic leaks into routes.
- **Async-first** — all I/O is async (`asyncpg`, `httpx`, Redis). No sync blocking anywhere in the request path.
- **RBAC at service layer** — six roles (`admin`, `supervisor`, `lead`, `artist`, `worker`, `client`) enforced in service methods, not middleware, so authorization logic lives next to the domain it protects.
- **Pluggable storage** — `local` and S3-compatible backends behind a common interface; swap with a single `STORAGE_BACKEND` env var.
- **Background jobs via Redis queue** — heavy operations (project exports) are enqueued to Redis and consumed by a dedicated worker, decoupling API response time from job duration.
- **Structured logging + Prometheus** — structlog emits JSON logs; `/metrics` exposes Prometheus histograms and gauges for active users and request latency.
- **DCC integration examples** — publish scripts for Maya, Houdini, Nuke, and a standalone PySide6 GUI, demonstrating the artist-facing side of the pipeline.

---

## Features

| Domain | Description |
|---|---|
| **Auth / RBAC** | JWT access + refresh tokens, Redis blacklist on logout, IP-based login rate limiting, six scoped roles (`admin`, `supervisor`, `lead`, `artist`, `worker`, `client`) at global and project scope |
| **Projects** | Full CRUD with status tracking, per-project role assignments, and async export |
| **Episodes / Sequences** | Editorial hierarchy for series and episodic productions |
| **Shots** | Status lifecycle, frame ranges, assignment, status history |
| **Assets** | Characters, props, environments with asset-type classification |
| **Files** | Upload, download, checksum, deduplication, size limits, local + S3 storage |
| **Pipeline Tasks** | Department-level tasks per shot/asset, template instantiation |
| **Notes** | Polymorphic threaded feedback on any entity (shot, asset, task, project) |
| **Versions** | Artist version submissions with review status transitions (`pending_review` → `approved` / `revision_requested`) |
| **Shot–Asset Links** | Many-to-many relationship between shots and assets with link type |
| **Playlists** | Dailies review sessions — ordered version lists with per-item review status |
| **Departments** | Dynamic department management and user membership |
| **Tags** | Flexible polymorphic categorization on shots, assets, sequences, projects |
| **Time Logs** | Hour tracking per task and artist, bid vs actual comparison |
| **Deliveries** | Client delivery packages with versioned items and acceptance status |
| **Notifications** | Internal notifications auto-generated from system events |
| **Webhooks** | Signed outgoing HTTP events to external systems |
| **Background Tasks** | Redis queue + dedicated worker process for heavy async jobs |
| **Metrics** | Prometheus endpoint with active-user gauge and request latency histograms |
| **Health** | `/health` liveness probe |

---

## API Example

Create a shot inside a project:

```bash
curl -X POST http://localhost:8000/projects/{project_id}/shots \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Shot 010",
    "code": "SH010",
    "frame_start": 1001,
    "frame_end": 1040,
    "assigned_to": "<user_id>"
  }'
```

Response `200 OK`:

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "project_id": "...",
  "name": "Shot 010",
  "code": "SH010",
  "status": "pending",
  "frame_start": 1001,
  "frame_end": 1040,
  "assigned_to": "...",
  "created_at": "2026-03-01T12:00:00Z",
  "archived_at": null
}
```

Transition shot status:

```bash
curl -X PATCH http://localhost:8000/shots/{shot_id}/status \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress", "comment": "Starting layout pass"}'
```

Full interactive docs at `http://localhost:8000/docs`.

---

## Quick Start

### Start all services

```bash
docker compose up --build
```

Services will be available at:

- **API**: `http://localhost:8000`
- **Interactive docs**: `http://localhost:8000/docs`
- **Metrics**: `http://localhost:8000/metrics`

### Apply database migrations

Run this once after the first `docker compose up` (and after any future schema change):

```bash
docker compose exec api alembic upgrade head
```

### Initialize demo data

Seed the database with a complete demo dataset (roles, admin user, demo users, demo project, episodes, sequences, shots, assets, and project role assignments):

```bash
docker compose exec api python -m app.scripts.seed
```

Customize seed values via `.env`:

```
SEED_ADMIN_EMAIL=admin@studio.com
SEED_ADMIN_PASSWORD=changeme
SEED_DEMO_USER_PASSWORD=demo123
SEED_DEMO_PROJECT_NAME=Demo Project
SEED_DEMO_PROJECT_CODE=DEMO
```

### Run tests

Run all tests:

```bash
docker compose exec api python -m pytest -v
```

Run tests by marker:

```bash
docker compose exec api python -m pytest -m projects -v
```

Run specific test file:

```bash
docker compose exec api python -m pytest test/test_projects_endpoints.py -v
```

Run a specific test:

```bash
docker compose exec api python -m pytest test/test_projects_endpoints.py::test_projects_crud_and_delete_admin_only -v
```

Run with coverage report:

```bash
docker compose exec api python -m pytest --cov=backend --cov-report=term-missing
```

### Smoke tests

Fast end-to-end API sanity check against a running stack. Covers all 24 domains.

Run the full suite:

```bash
docker compose exec api python -m smoke_tests.runner
```

Run a single domain (standalone — creates its own prerequisites):

```bash
docker compose exec api python -m smoke_tests.test_08_shots
docker compose exec api python -m smoke_tests.test_12_pipeline_tasks
docker compose exec api python -m smoke_tests.test_24_pipeline_path_isolation
```

Override defaults:

```bash
docker compose exec api python -m smoke_tests.runner \
  --base-url http://localhost:8000 \
  --email admin@vfxhub.dev \
  --password admin123
```

Environment overrides: `SMOKE_BASE_URL`, `SMOKE_EMAIL`, `SMOKE_PASSWORD`, `SMOKE_TIMEOUT_SECONDS`.

---

### DCC integration examples

Thin DCC-side publish examples live under `examples/dcc/`.

- generic artist CLI publish flow
- Nuke-oriented publish flow with live or mock DCC context

Start here: [`examples/dcc/README.md`](./examples/dcc/README.md)

---

### Code quality (lint, format, type check)

Run linter:

```bash
docker compose exec api ruff check .
```

Format code:

```bash
docker compose exec api ruff format .
```

Type checking:

```bash
docker compose exec api mypy backend
```

Run all checks:

```bash
docker compose exec api bash -c "ruff check . && ruff format . && mypy backend && python -m pytest -v"
```

---

## Environment

Copy `.env.example` to `.env` and fill in the values. Key variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | Async PostgreSQL URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis connection string |
| `JWT_SECRET` | Secret key for signing JWTs |
| `STORAGE_BACKEND` | `local` (default) or `s3` |
| `LOCAL_STORAGE_ROOT` | Base path for local file storage |
| `S3_BUCKET` | S3 / MinIO bucket name |
| `S3_ENDPOINT_URL` | Custom endpoint for MinIO / LocalStack |

---

## Project Structure

```
pipeline-production-hub-dev/
├── backend/app/
│   ├── api/routes/         # 21 FastAPI routers, one per domain
│   ├── services/           # Business logic and RBAC orchestration
│   ├── repositories/       # Async SQLAlchemy persistence layer
│   ├── models/             # SQLAlchemy ORM models
│   ├── schemas/            # Pydantic request/response contracts
│   ├── core/               # Config, security, logging, metrics, exceptions
│   └── scripts/            # Seed script, background task worker
├── backend/alembic/        # Database migration versions
├── test/                   # Pytest test suite
├── examples/
│   └── dcc/                # Portfolio-oriented DCC / artist publish examples
├── docs/
│   ├── architecture/       # Technical reference docs
│   └── plans/              # Implementation plans
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

---

## Documentation

- [Architecture reference](./docs/architecture/README.md)
- [Implementation plans](./docs/plans/README.md)
- [Testing workflow](./docs/testing-workflow.md)

---

## License

MIT

## Inspect database (Docker)

Open an interactive PostgreSQL shell:

```bash
# Linux / macOS / Git Bash
docker compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

### Optional: local editor environment for VS Code

If your editor shows unresolved imports or missing dependencies, you can create a local virtual environment only for IntelliSense and static analysis.

This environment is **not** used to run the API, tests, migrations, or worker. Runtime commands still run inside Docker.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev,test]"
```

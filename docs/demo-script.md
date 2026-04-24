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
- Run login with a seeded admin user.
- Point out access and refresh tokens.

Key point:

"The API supports short-lived access tokens, refresh tokens, and logout backed by Redis token invalidation."

### 3. Show a real production entity flow

- List projects or create a new project.
- Open the nested shot route and create or list a shot inside that project.
- Highlight that project structure is not flat CRUD; shots and assets live inside a production hierarchy.

Key point:

"The API is organized around production relationships, not only around isolated tables."

### 4. Show workflow progression

- Update a shot or task status.
- If useful, show versions, notes, or playlists to demonstrate review-oriented workflow.

Key point:

"This backend is meant to support production state changes, review loops, and artist-supervisor collaboration."

### 5. Show operational credibility

- Open `/health`.
- Open `/metrics`.
- Mention Docker Compose, Alembic migrations, tests, and CI.

Key point:

"I wanted the project to show production-minded engineering, not just endpoint count."

## Optional extension

If there is time, show one of these:

- file upload or storage configuration
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

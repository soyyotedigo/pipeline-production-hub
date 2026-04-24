# Interview Prep

Use this document as a compact interview reference for Pipeline Production Hub.

## Why a layered architecture

- Routers keep HTTP concerns at the boundary: validation, status codes, and dependency injection.
- Services own business rules and authorization decisions, which keeps workflow logic near the domain it affects.
- Repositories isolate persistence details so database queries do not leak across the application.
- This split makes the code easier to test, change, and explain under interview pressure.

## Auth and RBAC

- Authentication is JWT-based with short-lived access tokens and refresh tokens.
- Logout invalidates refresh tokens through Redis-backed revocation.
- RBAC is enforced at the service layer instead of middleware so authorization rules stay close to business operations.
- The system supports global and project-scoped roles: `admin`, `supervisor`, `lead`, `artist`, `worker`, and `client`.

## Why Redis is in the system

- Refresh-token revocation on logout
- Login rate limiting
- Background job coordination
- Lightweight operational state such as active-user and metrics support

## Sync vs async

- Request I/O paths are async: FastAPI handlers, database access, HTTP clients, and Redis operations.
- Longer-running work is pushed out of the request-response path into a background worker.
- Some CPU-bound work such as password hashing is still synchronous by nature.

## Local storage vs S3

- Local storage is the simplest development path and works well for demos, tests, and local validation.
- S3-compatible storage is the production-oriented path for externalized file storage and signed access URLs.
- The application hides both behind a storage abstraction so the API contract stays stable while the backend changes.

## How to test this in a studio-like setup

- Start with seeded demo data for manual API exploration.
- Use Swagger or Bruno for fast smoke checks.
- Capture critical flows as reproducible requests.
- Back those flows with pytest coverage for regression confidence.
- Validate auth, RBAC, file handling, and one representative production workflow before calling a feature done.

## What is really ready now

- Dockerized local stack
- Alembic migrations
- Seeded demo environment
- Auth, refresh, logout, and representative RBAC checks
- Core CRUD for projects, shots, and assets
- File upload and file version lineage validation
- Health, metrics, and local pytest coverage

## What still needs to be closed

- Public repository sync so recruiter-facing GitHub state matches the current local repo
- Final cleanup of root-level presentation signals before public review
- Optional polish such as release tagging, changelog, and short video demo

## What I would use in production and what I would change

- I would keep the layered API design, async I/O, migrations, Docker-based workflow, and storage abstraction.
- I would harden deployment concerns around secrets, environments, monitoring, backups, and external infrastructure.
- I would likely add stronger audit/reporting workflows, operational dashboards, and more explicit production deployment docs.

## What is intentionally outside v1

- Full studio-specific pipeline customization for every workflow edge case
- Packaged production plugins for each DCC instead of integration-oriented examples
- A polished frontend product layer on top of the backend
- Release-management and portfolio-publication polish that depends on syncing the public repository

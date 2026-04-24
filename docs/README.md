# Documentation Overview

This directory contains the public-facing reference material for Pipeline Production Hub.

## Start here

| Area | Why it matters | Start Here |
|------|----------------|------------|
| Architecture | Technical overview of the backend, data model, and infrastructure | [architecture/README.md](./architecture/README.md) |
| Guided walkthrough | Short recruiter-friendly demo flow using the seeded environment | [demo-script.md](./demo-script.md) |
| DCC integration | Artist-facing publish examples for Maya, Houdini, Nuke, and CLI tooling | [dcc-integration.md](./dcc-integration.md) |
| Testing and quality | How the project is validated locally and in CI | [testing-workflow.md](./testing-workflow.md) |
| Data model reference | Visual schema snapshot for the core production entities | [vfx_hub_schema.md](./vfx_hub_schema.md) |

## System Overview

```mermaid
flowchart TD
    Client[Client / Swagger / DCC tooling]
    API[FastAPI API]
    Services[Services]
    Repos[Repositories]
    PG[(PostgreSQL)]
    Redis[(Redis)]
    Worker[Background worker]
    Storage[(Local storage / S3)]

    Client --> API
    API --> Services
    Services --> Repos
    Repos --> PG
    Services --> Redis
    Redis --> Worker
    Worker --> Redis
    Worker --> PG
    Worker --> Storage
```

## Notes

- `docs/architecture/` is the canonical technical reference.
- The other documents in this folder are portfolio-facing guides that explain demo flow, validation, and integration examples.

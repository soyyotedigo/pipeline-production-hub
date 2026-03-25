# Alembic Migrations

## What Alembic does in this repo

Alembic is the database schema migration system. Every change to SQLAlchemy models that needs to be reflected in PostgreSQL is written as a migration file.

Migrations live in `backend/alembic/versions/` and are applied in order through a chain of revisions.

---

## File structure

```
alembic.ini                        ← main configuration
backend/alembic/
  env.py                           ← async execution environment
  script.py.mako                   ← template for new migrations
  versions/                        ← one migration per file
    93fcc9a81cf5_create_users_table.py
    89f144418787_create_users_roles_user_roles.py
    ...
```

---

## How env.py works

`env.py` is the heart of the migration system. It does three key things:

1. **Injects the database URL** from `settings.database_url` (not from `alembic.ini`), normalizing it to `postgresql+asyncpg://`.
2. **Registers all models** by importing `app.models`, which loads their definitions into `Base.metadata`.
3. **Runs migrations asynchronously** using `async_engine_from_config` + `asyncio.run`.

```mermaid
flowchart TD
    CLI[alembic upgrade heads]
    ENV[env.py]
    CFG[app.core.config settings]
    MODELS[app.models → Base.metadata]
    ENGINE[async_engine_from_config]
    PG[(PostgreSQL)]

    CLI --> ENV
    ENV --> CFG
    ENV --> MODELS
    ENV --> ENGINE
    ENGINE --> PG
```

---

## Anatomy of a migration file

Each migration file has this structure:

```python
"""short description"""

revision: str = "a1b2c3d4e5f6"       # unique ID of this migration
down_revision: str | None = "prev123" # ID of previous migration (None = first ever)
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Changes to apply (create table, add column, create enum...)
    op.create_table("my_table", ...)

def downgrade() -> None:
    # Reverse the upgrade() changes
    op.drop_table("my_table")
```

The chain `down_revision → revision → next revision` forms the migration graph.

---

## Current migration chain

```mermaid
flowchart TD
    R1["93fcc9a81cf5\ncreate_users_table\n(ROOT)"]
    R2["89f144418787\ncreate_users_roles_user_roles"]
    R3["c1e7a5f9b312\ncreate_projects_shots_assets"]
    R4["e4a8f8d2c6b1\nexpand_area2_models"]
    R5["f3b19d4a6c2e\ncreate_files_table"]
    R6["2ac41a0f7e9b\nadd_deleted_at_to_files"]
    R7["7b6c2d1e4f90\nadd_project_client_and_type"]
    R8["868c807dfacb\nupdate_code_create_more"]
    R9["c8d9f1a2b3e4\nadd_episodes_sequences"]
    R10["d4f0a6c1b7a2\ncreate_webhooks_table"]
    R11["a1b2c3d4e5f6\nadd_archived_at_core_entities"]
    R12["a1b2c3d4e5f7\nadd_tags"]
    R13["b2c3d4e5f6a7\nadd_pipeline_tasks"]

    R14["c3d4e5f6a7b8\nadd_entity_field_gaps"]
    R15["d5e6f7a8b9c0\nadd_notes"]
    R16["e6f7a8b9c0d1\nadd_versions"]
    R17["f7a8b9c0d1e2\nadd_shot_asset_links"]
    R18["a2b3c4d5e6f7\nadd_notifications"]
    R19["a8b9c0d1e2f3\nadd_playlists"]
    R20["b9c0d1e2f3a4\nadd_departments"]

    R21["b2c3d4e5f6a1\nadd_time_logs"]
    R22["c3d4e5f6a1b2\nadd_deliveries"]

    R1 --> R2 --> R3 --> R4 --> R5 --> R6 --> R7 --> R8 --> R9
    R9 --> R10 --> R11 --> R12 --> R13

    R13 --> R14
    R14 --> R15 --> R16 --> R17
    R17 --> R18
    R17 --> R19 --> R20

    R13 --> R21 --> R22
```

> **Note:** There are two branches leaving `b2c3d4e5f6a7` (add_pipeline_tasks) and two leaving `f7a8b9c0d1e2` (add_shot_asset_links). Alembic calls these **branches**. To apply all branches use `alembic upgrade heads` (plural).

---

## Essential commands

```bash
# Apply all pending migrations
alembic upgrade head         # if there is a single head
alembic upgrade heads        # if there are multiple branches (this repo)

# Roll back the last migration
alembic downgrade -1

# Show current applied revision(s)
alembic current

# Show full history
alembic history --verbose

# Show active heads (if branches exist)
alembic heads

# Create a new manual migration
alembic revision -m "add_new_table"

# Create a migration auto-detecting model changes
alembic revision --autogenerate -m "add_new_table"
```

### Inside Docker

```bash
docker compose exec api alembic upgrade heads
docker compose exec api alembic current
docker compose exec api alembic history --verbose
```

---

## How the alembic_version table works

Alembic maintains a table called `alembic_version` in PostgreSQL that records which revisions are currently applied:

```sql
SELECT * FROM alembic_version;
-- version_num
-- f7a8b9c0d1e2
-- b9c0d1e2f3a4
-- c3d4e5f6a1b2
```

When there are multiple branches, there can be multiple rows at the same time — one per active head.

```mermaid
flowchart LR
    PG[(PostgreSQL)]
    AV[alembic_version table]
    CHAIN[Migration chain]

    PG --> AV
    AV -->|version_num = HEAD| CHAIN
    CHAIN -->|upgrade / downgrade| AV
```

---

## How to create a new migration in this repo

### 1. Create or modify the SQLAlchemy model

```python
# backend/app/models/my_entity.py
class MyEntity(Base):
    __tablename__ = "my_entity"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
```

### 2. Register the model in base.py and models/__init__.py

```python
# backend/app/db/base.py
from app.models.my_entity import MyEntity  # noqa: F401

# backend/app/models/__init__.py
from app.models.my_entity import MyEntity
__all__ = [..., "MyEntity"]
```

### 3. Create the migration file

**Option A — manual** (recommended for full control):

```bash
alembic revision -m "add_my_entity"
```

Edit the generated file and write `upgrade()` and `downgrade()` by hand.

**Option B — autogenerate** (useful as a starting point):

```bash
alembic revision --autogenerate -m "add_my_entity"
```

Always review the generated file. Autogenerate does not detect everything — PostgreSQL enums in particular must be created manually.

### 4. Verify the revision chain

The `down_revision` in the new file must point to the current head:

```python
revision: str = "new_id_here"
down_revision: str | None = "c3d4e5f6a1b2"  # the current head
```

### 5. Apply

```bash
alembic upgrade heads
```

---

## PostgreSQL enums in migrations

PostgreSQL enums require explicit creation and deletion. The pattern used in this repo:

```python
def upgrade() -> None:
    # Create the enum first
    my_enum = postgresql.ENUM("val1", "val2", name="myenum")
    my_enum.create(op.get_bind(), checkfirst=True)

    # Then create the table that uses it
    op.create_table("my_table",
        sa.Column("status", sa.Enum(name="myenum", create_type=False), ...),
    )

def downgrade() -> None:
    op.drop_table("my_table")
    op.execute("DROP TYPE IF EXISTS myenum")
```

---

## Repo conventions

| Convention | Detail |
|-----------|--------|
| File naming | `{revision_id}_{description}.py` |
| Revision IDs | 12 hex characters |
| `down_revision = None` | Only in the root migration (`create_users_table`) |
| Enums | Always `checkfirst=True` on `create`, `IF EXISTS` on `DROP` |
| UUID columns | `postgresql.UUID()` in migrations, `Uuid` in models |
| Indexes | Create explicitly in `upgrade()`, drop in `downgrade()` |

---

## Full schema change flow

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant Model as SQLAlchemy Model
    participant Alembic as Alembic CLI
    participant PG as PostgreSQL

    Dev->>Model: create or modify model
    Dev->>Model: register in base.py and __init__.py
    Dev->>Alembic: alembic revision -m "description"
    Alembic-->>Dev: generates file in versions/
    Dev->>Alembic: write upgrade() and downgrade()
    Dev->>Alembic: alembic upgrade heads
    Alembic->>PG: execute upgrade() via asyncpg
    PG-->>Alembic: OK
    Alembic->>PG: UPDATE alembic_version
    PG-->>Dev: schema updated
```

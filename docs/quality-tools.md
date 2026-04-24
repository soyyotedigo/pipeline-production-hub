# Quality Tools — Pipeline Production Hub

**Stack:** Python 3.10+, FastAPI, configured in `pyproject.toml`

---

## Summary

| Tool | Role | Command | Current result |
|------|------|---------|----------------|
| **Ruff** (linter) | Detects bugs and code smells | `ruff check .` | 0 errors |
| **Ruff** (formatter) | Consistent code formatting | `ruff format --check .` | 235 files OK |
| **Mypy** | Static type checking | `mypy backend` | 0 errors, 162 sources |
| **Pytest** | Automated test suite | `pytest -v --tb=short` | 566 passed |
| **Coverage** | Test coverage percentage | `pytest --cov=backend` | 92.57% (gate: 80%) |
| **Hatch** | Environment and command orchestrator | `hatch run check` | Runs lint + types + test |

---

## 1. Ruff — Linter

**Version:** 0.15.10 | **Written in:** Rust (10–100x faster than flake8)

### What it does

Analyzes source code without executing it, detecting logic errors, unused imports, dangerous patterns, and style violations.

### Active rules in this project

| Code | Plugin | What it detects | Example |
|------|--------|----------------|---------|
| `E` / `W` | pycodestyle | PEP 8 style errors and warnings | indentation, whitespace |
| `F` | Pyflakes | Real bugs | unused variables, unused imports |
| `I` | isort | Import ordering | stdlib before third-party |
| `UP` | pyupgrade | Outdated Python syntax | `Optional[X]` → `X \| None` |
| `B` | flake8-bugbear | Dangerous patterns | mutable default args |
| `C4` | flake8-comprehensions | Unnecessary list/dict comprehensions | `list(x for x in y)` |
| `SIM` | flake8-simplify | Simplifiable code | `if x == True:` → `if x:` |
| `RUF` | Ruff-specific | Ruff's own rules | various |

### How to run

```bash
# Check only (no modifications)
docker compose exec api ruff check .

# Show source context for each error
docker compose exec api ruff check . --show-source

# Auto-fix what can be fixed automatically
docker compose exec api ruff check . --fix
```

---

## 2. Ruff — Formatter

**Role:** Replaces Black. Guarantees identical formatting across the team.

### Configuration in this project

```toml
[tool.ruff.format]
quote-style = "double"        # double quotes
indent-style = "space"        # spaces, not tabs
docstring-code-format = true  # formats code blocks in docstrings
```

### How to run

```bash
# Check without modifying (CI mode)
docker compose exec api ruff format --check .

# Apply formatting (dev mode)
docker compose exec api ruff format .
```

---

## 3. Mypy — Static Type Checker

**Version:** 1.20.0 (compiled) | **Mode:** `strict = true`

### What it does

Verifies that types in the code are consistent **without executing it**. With `strict = true`, this is the highest enforcement level: requires annotations on all functions, disallows implicit `Any`, and validates generics.

### Configuration in this project

```toml
[tool.mypy]
python_version = "3.10"
strict = true                  # full strict mode
ignore_missing_imports = true  # does not fail on libs without stubs
plugins = ["pydantic.mypy"]    # integrates with Pydantic models
mypy_path = ["backend"]
```

### What `strict = true` implies

| Implicit flag | What it enforces |
|---------------|-----------------|
| `--disallow-untyped-defs` | All functions must have type annotations |
| `--disallow-any-generics` | No bare `List` — must be `List[str]` |
| `--warn-return-any` | Cannot return `Any` without explicit annotation |
| `--no-implicit-optional` | `x: str = None` is invalid — must be `x: str \| None` |
| `--warn-unused-ignores` | `# type: ignore` comments with no effect are reported as errors |

### How to run

```bash
docker compose exec api mypy backend
```

---

## 4. Pytest — Test Suite

**Version:** 9.0.3 | **Current tests:** 566 | **Async mode:** auto

### Project structure

```
test/
├── conftest.py                     # shared fixtures (db, client, users)
├── test_assets_endpoints.py
├── test_auth_endpoints.py
├── test_deliveries_endpoints.py
├── test_departments_endpoints.py
├── test_episodes_endpoints.py
├── test_files_endpoints.py
├── test_notes_endpoints.py
├── test_notifications_endpoints.py
├── test_pipeline_tasks_endpoints.py
├── test_playlists_endpoints.py
├── test_projects_endpoints.py
├── test_sequences_endpoints.py
├── test_shot_asset_links_endpoints.py
├── test_shots_endpoints.py
├── test_storage_backends.py        # storage unit tests (mocks)
├── test_s3_live.py                 # integration tests against real AWS S3
├── test_tags_endpoints.py
├── test_tasks_endpoints.py
├── test_time_logs_endpoints.py
├── test_users_endpoints.py
├── test_versions_endpoints.py
└── test_webhooks_endpoints.py
```

### Relevant configuration

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"           # all async tests run without an extra decorator
testpaths   = ["test"]
addopts     = "-v --tb=short"
```

`asyncio_mode = "auto"` means any `async def test_*` is automatically run in an event loop — no `@pytest.mark.asyncio` needed.

### Test types in this project

| Type | Files | What they verify |
|------|-------|----------------|
| **Endpoint tests** | `test_*_endpoints.py` | HTTP request → response, status codes, RBAC |
| **Storage unit** | `test_storage_backends.py` | LocalStorage and S3Storage with mocks |
| **Storage live** | `test_s3_live.py` | Real operations against AWS S3 |

### How to run

```bash
# Full suite
docker compose exec api python -m pytest -v --tb=short

# A specific domain
docker compose exec api python -m pytest test/test_shots_endpoints.py -v

# By marker
docker compose exec api python -m pytest -m shots -v

# Live tests only (requires AWS credentials in .env)
python -m pytest test/test_s3_live.py -v -s
```

---

## 5. Coverage

**Version:** 7.13.5 | **Current coverage:** 92.57% | **Minimum gate:** 80%

### What it measures

For every line of code in `backend/`, it records whether that line was executed during the tests. The overall percentage is a weighted average across modules.

### Configuration in this project

```toml
[tool.coverage.run]
source      = ["backend"]
omit        = ["*/alembic/*", "*/scripts/*"]  # migrations and seed scripts excluded

[tool.coverage.report]
show_missing = true    # shows line numbers not covered
fail_under   = 80      # build fails if coverage < 80%
```

### Coverage gate

`fail_under = 80` means `pytest --cov` returns exit code 1 if coverage drops below 80%. This blocks CI automatically.

### How to run

```bash
# With terminal report (shows missing lines)
docker compose exec api python -m pytest --cov=backend --cov-report=term-missing

# With navigable HTML report
docker compose exec api python -m pytest --cov=backend --cov-report=html
# Result at htmlcov/index.html
```

### Coverage by layer

| Layer | Typical coverage | Notes |
|-------|-----------------|-------|
| `api/routes/` | ~95% | Well covered by endpoint tests |
| `services/` | ~90% | Good coverage of main paths |
| `repositories/` | ~88% | Some error branches less covered |
| `schemas/` | ~98% | Pydantic tested indirectly |
| `core/` | ~85% | Config and security well covered |
| `task_queue_repository` | ~57% | Known gap — async enqueue/dequeue |

---

## 6. Hatch — Environment Orchestrator

**Role:** Manages virtual environments and defines command shortcuts.

### Defined scripts

```toml
[tool.hatch.envs.default.scripts]
serve  = "uvicorn app.main:app --reload --app-dir backend"
lint   = "ruff check ."
fmt    = "ruff format ."
types  = "mypy backend"
test   = "pytest -v --cov=backend --cov-report=term-missing"
check  = ["lint", "types", "test"]   # runs all three in sequence
```

### How to use

```bash
hatch run lint      # linter only
hatch run types     # mypy only
hatch run test      # pytest with coverage
hatch run check     # lint + types + test (full pipeline)
```

`hatch run check` is the local equivalent of the CI pipeline — a single command that replicates what runs in GitHub Actions.

---

## Full pipeline (CI equivalent)

```bash
docker compose exec api bash -c "
  ruff check . &&
  ruff format --check . &&
  mypy backend &&
  python -m pytest -v --tb=short --cov=backend --cov-report=term-missing
"
```

**Current state:** all checks green, 566 tests, 92.57% coverage.

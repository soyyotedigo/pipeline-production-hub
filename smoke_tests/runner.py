"""
Full-coverage smoke test runner for Pipeline Production Hub API.

Runs all 23 domain modules in order, threading shared state through a single
SmokeContext. Each step is independent — failures are recorded and execution
continues so you get a complete picture of what works and what doesn't.

Usage:
    docker compose exec api python -m smoke_tests.runner
    docker compose exec api python -m smoke_tests.runner \
        --base-url http://localhost:8000 \
        --email admin@vfxhub.dev \
        --password admin123

Environment overrides:
    SMOKE_BASE_URL, SMOKE_EMAIL, SMOKE_PASSWORD, SMOKE_TIMEOUT_SECONDS
"""

from __future__ import annotations

import importlib

from smoke_tests.context import SmokeContext
from smoke_tests.helpers import (
    SmokeResults,
    _build_parser,
    _get_default_config,
    _make_config,
    print_summary,
)

MODULES = [
    "smoke_tests.test_01_health",
    "smoke_tests.test_02_auth",
    "smoke_tests.test_03_users",
    "smoke_tests.test_04_departments",
    "smoke_tests.test_05_projects",
    "smoke_tests.test_06_episodes",
    "smoke_tests.test_07_sequences",
    "smoke_tests.test_08_shots",
    "smoke_tests.test_09_assets",
    "smoke_tests.test_10_shot_asset_links",
    "smoke_tests.test_11_pipeline_templates",
    "smoke_tests.test_12_pipeline_tasks",
    "smoke_tests.test_13_versions",
    "smoke_tests.test_14_notes",
    "smoke_tests.test_15_tags",
    "smoke_tests.test_16_time_logs",
    "smoke_tests.test_17_deliveries",
    "smoke_tests.test_18_playlists",
    "smoke_tests.test_19_webhooks",
    "smoke_tests.test_20_notifications",
    "smoke_tests.test_21_background_tasks",
    "smoke_tests.test_22_files",
    "smoke_tests.test_23_auth_logout",
    "smoke_tests.test_24_pipeline_path_isolation",
]


def main() -> int:
    defaults = _get_default_config()
    args = _build_parser(defaults).parse_args()
    config = _make_config(args)

    print(f"Full smoke test → {config.base_url}  (user: {config.email})")
    print(f"Running {len(MODULES)} sections\n")

    ctx = SmokeContext(config=config, results=SmokeResults())

    for mod_name in MODULES:
        mod = importlib.import_module(mod_name)
        mod.run(ctx)

    print_summary(ctx.results, "FULL SUITE RESULTS")
    return 0 if not ctx.results.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Shared mutable context threaded through all smoke test modules."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from smoke_tests.helpers import SmokeConfig, SmokeResults


@dataclass
class SmokeContext:
    config: SmokeConfig
    results: SmokeResults

    # Auth state
    token: str | None = None
    refresh_token: str | None = None

    # User IDs
    my_user_id: str | None = None
    new_user_id: str | None = None

    # Org IDs
    dept_id: str | None = None
    dept_member_id: str | None = None

    # Project hierarchy IDs
    project_id: str | None = None
    episode_id: str | None = None
    seq_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    link_id: str | None = None

    # Pipeline IDs
    template_id: str | None = None
    pipeline_task_id: str | None = None
    version_id: str | None = None

    # Content IDs
    note_id: str | None = None
    tag_id: str | None = None
    entity_tag_id: str | None = None
    timelog_id: str | None = None
    delivery_id: str | None = None
    playlist_id: str | None = None
    webhook_id: str | None = None

    # Unique suffix for entity names/codes to avoid collisions across runs
    suffix: str = field(default_factory=lambda: str(int(time.time()))[-8:])

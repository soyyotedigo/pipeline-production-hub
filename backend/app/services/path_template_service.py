from __future__ import annotations

import os
import re
from dataclasses import dataclass

from app.models import ProjectType


@dataclass(frozen=True)
class PathTemplateDefinition:
    id: str
    name: str
    version: int
    definition_json: dict[str, object]


_BASIC_VFX_TEMPLATE = PathTemplateDefinition(
    id="tplvfx-001",
    name="basic_vfx",
    version=1,
    definition_json={
        "name": "basic_vfx",
        "version": 1,
        "entities": {
            "project_root": "/projects/{project_code}",
            "shot_root": "{project_root}/shots/{sequence_code}/{shot_code}",
            "asset_root": "{project_root}/assets/{asset_type}/{asset_code}",
        },
        "paths": {
            "project_assets": "{project_root}/assets",
            "project_shots": "{project_root}/shots",
            "shot_work": "{shot_root}/work/{department}",
            "shot_publish": "{shot_root}/publish/{department}/v{version:03d}",
            "asset_work": "{asset_root}/work/{department}",
        },
        "filenames": {
            "scene_file": "{project_code}_{sequence_code}_{shot_code}_{department}_v{version:03d}.{ext}",
        },
    },
)

_FILM_TEMPLATE = PathTemplateDefinition(
    id="tplvfx-film-001",
    name="film_vfx",
    version=1,
    definition_json={
        "name": "film_vfx",
        "version": 1,
        "entities": {
            "project_root": "/projects/{project_code}",
            "sequence_root": "{project_root}/shots/{sequence_code}",
            "shot_root": "{sequence_root}/{shot_code}",
            "asset_root": "{project_root}/assets/{asset_type}/{asset_code}",
        },
        "paths": {
            "project_assets": "{project_root}/assets",
            "project_shots": "{project_root}/shots",
            "shot_work": "{shot_root}/work/{department}",
            "shot_publish": "{shot_root}/publish/{department}/v{version:03d}",
            "asset_work": "{asset_root}/work/{department}",
        },
        "filenames": {
            "scene_file": "{project_code}_{sequence_code}_{shot_code}_{department}_v{version:03d}.{ext}",
        },
    },
)

_SERIES_TEMPLATE = PathTemplateDefinition(
    id="tplvfx-series-001",
    name="series_vfx",
    version=1,
    definition_json={
        "name": "series_vfx",
        "version": 1,
        "entities": {
            "project_root": "/projects/{project_code}",
            "episode_root": "{project_root}/episodes/{episode_code}",
            "sequence_root": "{episode_root}/shots/{sequence_code}",
            "shot_root": "{sequence_root}/{shot_code}",
            "asset_root": "{episode_root}/assets/{asset_type}/{asset_code}",
        },
        "paths": {
            "project_episodes": "{project_root}/episodes",
            "episode_assets": "{episode_root}/assets",
            "episode_shots": "{episode_root}/shots",
            "shot_work": "{shot_root}/work/{department}",
            "shot_publish": "{shot_root}/publish/{department}/v{version:03d}",
            "asset_work": "{asset_root}/work/{department}",
        },
        "filenames": {
            "scene_file": "{project_code}_{episode_code}_{sequence_code}_{shot_code}_{department}_v{version:03d}.{ext}",
        },
    },
)

_COMMERCIAL_TEMPLATE = PathTemplateDefinition(
    id="tplvfx-commercial-001",
    name="commercial_vfx",
    version=1,
    definition_json={
        "name": "commercial_vfx",
        "version": 1,
        "entities": {
            "project_root": "/projects/{project_code}",
            "spot_root": "{project_root}/spots/{spot_code}",
            "shot_root": "{spot_root}/shots/{shot_code}",
            "asset_root": "{project_root}/assets/{asset_type}/{asset_code}",
        },
        "paths": {
            "project_assets": "{project_root}/assets",
            "project_spots": "{project_root}/spots",
            "shot_work": "{shot_root}/work/{department}",
            "shot_publish": "{shot_root}/publish/{department}/v{version:03d}",
            "asset_work": "{asset_root}/work/{department}",
        },
        "filenames": {
            "scene_file": "{project_code}_{spot_code}_{shot_code}_{department}_v{version:03d}.{ext}",
        },
    },
)

_GAME_TEMPLATE = PathTemplateDefinition(
    id="tplvfx-game-001",
    name="game_vfx",
    version=1,
    definition_json={
        "name": "game_vfx",
        "version": 1,
        "entities": {
            "project_root": "/projects/{project_code}",
            "level_root": "{project_root}/levels/{level_code}",
            "shot_root": "{level_root}/shots/{shot_code}",
            "asset_root": "{project_root}/assets/{asset_type}/{asset_code}",
        },
        "paths": {
            "project_assets": "{project_root}/assets",
            "project_levels": "{project_root}/levels",
            "shot_work": "{shot_root}/work/{department}",
            "shot_publish": "{shot_root}/publish/{department}/v{version:03d}",
            "asset_work": "{asset_root}/work/{department}",
        },
        "filenames": {
            "scene_file": "{project_code}_{level_code}_{shot_code}_{department}_v{version:03d}.{ext}",
        },
    },
)

_OTHER_TEMPLATE = PathTemplateDefinition(
    id="tplvfx-other-001",
    name="other_vfx",
    version=1,
    definition_json={
        "name": "other_vfx",
        "version": 1,
        "entities": {
            "project_root": "/projects/{project_code}",
            "shot_root": "{project_root}/shots/{sequence_code}/{shot_code}",
            "asset_root": "{project_root}/assets/{asset_type}/{asset_code}",
        },
        "paths": {
            "project_assets": "{project_root}/assets",
            "project_shots": "{project_root}/shots",
            "shot_work": "{shot_root}/work/{department}",
            "shot_publish": "{shot_root}/publish/{department}/v{version:03d}",
            "asset_work": "{asset_root}/work/{department}",
        },
        "filenames": {
            "scene_file": "{project_code}_{sequence_code}_{shot_code}_{department}_v{version:03d}.{ext}",
        },
    },
)

_TEMPLATE_BY_PROJECT_TYPE: dict[ProjectType, PathTemplateDefinition] = {
    ProjectType.film: _FILM_TEMPLATE,
    ProjectType.series: _SERIES_TEMPLATE,
    ProjectType.commercial: _COMMERCIAL_TEMPLATE,
    ProjectType.game: _GAME_TEMPLATE,
    ProjectType.other: _OTHER_TEMPLATE,
}


class PathTemplateService:
    def resolve_upload_path(
        self,
        *,
        project_code: str,
        project_type: ProjectType | None,
        entity_type: str,
        version: int,
        original_name: str,
        shot_code: str | None = None,
        sequence_code: str | None = None,
        episode_code: str | None = None,
        asset_code: str | None = None,
        asset_type: str | None = None,
        spot_code: str | None = None,
        level_code: str | None = None,
        department: str = "general",
        project_path_templates: dict[str, object] | None = None,
    ) -> tuple[str, str, PathTemplateDefinition]:
        if project_path_templates:
            # Use per-project templates stored in the database.
            template = PathTemplateDefinition(
                id="project-custom",
                name="project_custom",
                version=1,
                definition_json=project_path_templates,
            )
        else:
            template = (
                _TEMPLATE_BY_PROJECT_TYPE[project_type]
                if project_type is not None
                else _BASIC_VFX_TEMPLATE
            )
        definition = template.definition_json

        ext = os.path.splitext(original_name)[1].lstrip(".") or "bin"
        normalized_shot_code = self._normalize_token(shot_code or "SHOT")
        normalized_asset_code = self._normalize_token(asset_code or "ASSET")
        normalized_asset_type = self._normalize_token(asset_type or "generic")
        normalized_department = self._normalize_token(department or "general")

        values: dict[str, object] = {
            "project_code": self._normalize_token(project_code),
            "episode_code": self._normalize_token(episode_code or "EP001"),
            "sequence_code": self._normalize_token(
                sequence_code or self._derive_sequence_code(normalized_shot_code)
            ),
            "shot_code": normalized_shot_code,
            "asset_code": normalized_asset_code,
            "asset_type": normalized_asset_type.lower(),
            "spot_code": self._normalize_token(spot_code or "SPOT001"),
            "level_code": self._normalize_token(level_code or "LVL001"),
            "department": normalized_department.lower(),
            "version": version,
            "ext": ext,
        }

        entities = self._render_group(definition.get("entities", {}), values)
        values.update(entities)
        paths = self._render_group(definition.get("paths", {}), values)
        values.update(paths)
        filenames = self._render_group(definition.get("filenames", {}), values)

        if entity_type == "shot":
            target_dir = paths.get("shot_publish", "")
        else:
            target_dir = paths.get("asset_work", "")

        rendered_name = filenames.get("scene_file")
        if not target_dir or not rendered_name:
            raise ValueError("Template did not produce upload path and filename")

        storage_path = f"{target_dir.strip('/')}/{rendered_name}"
        return storage_path, rendered_name, template

    @staticmethod
    def _render_group(group: object, values: dict[str, object]) -> dict[str, str]:
        if not isinstance(group, dict):
            return {}

        rendered: dict[str, str] = {}
        for key, raw_value in group.items():
            if not isinstance(raw_value, str):
                continue
            rendered[key] = raw_value.format(**values, **rendered)
        return rendered

    @staticmethod
    def _normalize_token(value: str) -> str:
        clean = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
        clean = clean.strip("_")
        return clean or "item"

    @staticmethod
    def _derive_sequence_code(shot_code: str) -> str:
        match = re.match(r"([A-Za-z]+)", shot_code)
        if match is not None:
            return match.group(1).upper()
        return "MAIN"

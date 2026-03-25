from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

JsonObject = dict[str, object]

_DEFAULT_NAMING_RULES: dict[str, str] = {
    "episode": "EP{production_number:03d}",
    "sequence": "SQ{production_number:04d}",
    "shot": "{sequence_code}_SH{order:04d}0",
    "asset": "{SANITIZED_NAME}",
}


def get_naming_rules(project_naming_rules: JsonObject | None) -> dict[str, str]:
    """Return project naming rules merged with defaults."""
    rules = dict(_DEFAULT_NAMING_RULES)
    if project_naming_rules:
        string_rules: Mapping[str, str] = {
            key: value for key, value in project_naming_rules.items() if isinstance(value, str)
        }
        rules.update(string_rules)
    return rules


def sanitize_name_to_code(name: str) -> str:
    """Convert a human-readable name to a valid uppercase code.

    Examples:
        'Hero Robot'      → 'HERO_ROBOT'
        'Láser Gun v2'    → 'LASER_GUN_V2'
        'Cocoa Melon 3'   → 'COCOA_MELON_3'
    """
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    sanitized = re.sub(r"[^A-Z0-9]", "_", ascii_only.upper())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "ITEM"


def generate_episode_code(production_number: int, naming_rules: JsonObject | None = None) -> str:
    """Generate an episode code from its production number.

    Example: production_number=5 → 'EP005'
    """
    rules = get_naming_rules(naming_rules)
    template = rules["episode"]
    return template.format(production_number=production_number)


def generate_sequence_code(production_number: int, naming_rules: JsonObject | None = None) -> str:
    """Generate a sequence code from its production number.

    Example: production_number=8 → 'SQ0008'
    """
    rules = get_naming_rules(naming_rules)
    template = rules["sequence"]
    return template.format(production_number=production_number)


def generate_shot_code(
    sequence_code: str,
    last_order: int,
    naming_rules: JsonObject | None = None,
) -> tuple[str, int]:
    """Generate the next shot code within a sequence, auto-incrementing by 10.

    Returns the generated code and the order number used.

    Example: sequence_code='SQ0080', last_order=20 → ('SQ0080_SH0030', 30)
    """
    next_order = last_order + 10
    rules = get_naming_rules(naming_rules)
    template = rules["shot"]
    code = template.format(sequence_code=sequence_code, order=next_order)
    return code, next_order

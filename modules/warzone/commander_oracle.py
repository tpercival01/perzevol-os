"""Commander to Oracle bridge.

Commander owns mission selection. Oracle owns weapon preparation and tactical
advice. This module translates the active Commander stop into a MissionProfile
without introducing Streamlit or changing Commander scoring.
"""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Mapping

from modules.warzone.oracle_models import MissionProfile


MODE_TO_PROFILE = {
    "multiplayer": "multiplayer",
    "warzone": "warzone",
    "zombies": "zombies",
    "co-op / endgame": "co_op_endgame",
    "co_op_endgame": "co_op_endgame",
}

ORACLE_WEAPON_TASK_TYPES = {
    "camo",
    "mastery_badge_weapon",
    "weapon_prestige",
}

LEGACY_PLAN_LOADOUT_KEYS = {
    "loadout",
    "loadouts",
    "loadout_templates",
    "loadout_template",
    "loadout_template_id",
    "template_loadouts",
}

LEGACY_STOP_LOADOUT_KEYS = {
    "loadout",
    "loadout_template",
    "loadout_template_id",
    "template",
    "template_id",
    "template_name",
    "primary",
    "primary_weapon",
    "primary_attachments",
    "primary_attachment_source",
    "primary_reason",
    "secondary",
    "secondary_attachments",
    "wildcard",
    "perks",
    "tactical",
    "lethal",
    "field_upgrade",
    "scorestreaks",
    "skill_tracks",
    "natural_goal",
    "natural_goal_source",
    "ttk_oracle",
    "ttk_oracle_note",
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def _int_from_values(default: int, *values: Any) -> int:
    for value in values:
        try:
            number = int(float(clean(value)))
        except (TypeError, ValueError):
            continue

        if number > 0:
            return number

    return int(default)


def _challenge_text(stop: Mapping[str, Any]) -> str:
    return clean(
        stop.get("challenge_text")
        or stop.get("raw_requirement")
        or stop.get("challenge")
        or stop.get("camo")
    )


def stats_profile_for_mode(mode: str) -> str:
    return MODE_TO_PROFILE.get(clean(mode).lower(), clean(mode).lower().replace(" ", "_"))


def stop_is_oracle_eligible(stop: Mapping[str, Any]) -> bool:
    weapon = clean(stop.get("weapon"))
    task_type = clean(stop.get("task_type")).lower()
    mode = clean(stop.get("mode")).lower()

    if not weapon or task_type not in ORACLE_WEAPON_TASK_TYPES:
        return False

    return mode in MODE_TO_PROFILE


def strip_legacy_stop_loadout(stop: Mapping[str, Any]) -> dict:
    """Remove old template loadout payload from a Commander stop."""
    cleaned = dict(stop)

    for key in LEGACY_STOP_LOADOUT_KEYS:
        cleaned.pop(key, None)

    return cleaned


def stop_to_mission_profile(
    stop: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> MissionProfile:
    mode = clean(stop.get("mode") or plan.get("mode") or "Multiplayer")
    stats_profile = stats_profile_for_mode(mode)
    challenge_text = _challenge_text(stop)

    constraints = {
        "enemy_health": _int_from_values(
            300 if stats_profile == "warzone" else 100,
            stop.get("enemy_health"),
            plan.get("enemy_health"),
        ),
        "attachment_count": _int_from_values(
            5,
            stop.get("attachment_count"),
            plan.get("attachment_count"),
        ),
    }

    explicit_requirement = clean(
        stop.get("challenge_requirement")
        or stop.get("attachment_requirement")
        or plan.get("challenge_requirement")
    )
    if explicit_requirement:
        constraints["challenge_requirement"] = explicit_requirement

    custom_attachment_text = clean(
        stop.get("attachment_name_contains")
        or stop.get("required_attachment")
        or plan.get("attachment_name_contains")
    )
    if custom_attachment_text:
        constraints["attachment_name_contains"] = custom_attachment_text

    role_scope = clean(
        stop.get("challenge_role_scope")
        or plan.get("challenge_role_scope")
    )
    if role_scope:
        constraints["challenge_role_scope"] = role_scope

    preferences = {}
    companion_text = " ".join(
        clean(item)
        for item in (stop.get("companion_objectives", []) or [])
    ).lower()
    if any(term in companion_text for term in ["scorestreak", "vehicle", "equipment", "destroy"]):
        preferences["secondary"] = "launcher"

    return MissionProfile(
        mode=mode,
        stats_profile=stats_profile,
        weapon_id=clean(stop.get("weapon")),
        target=clean(stop.get("camo") or stop.get("chain") or "Current challenge"),
        challenge_type=clean(stop.get("task_type")),
        challenge_name=challenge_text,
        remaining=None,
        session_id=clean(plan.get("mission_id") or plan.get("session_id")),
        constraints=constraints,
        preferences=preferences,
        metadata={
            "source": "completion_commander",
            "task_id": clean(stop.get("task_id")),
            "stop_number": stop.get("stop_number"),
            "chain": clean(stop.get("chain")),
            "weapon_class": clean(stop.get("weapon_class")),
            "recommended_mode": clean(stop.get("recommended_mode")),
            "estimated_minutes": stop.get("estimated_minutes"),
            "challenge_description": challenge_text,
            "task_name": clean(stop.get("task_name") or stop.get("camo")),
            "companion_objectives": list(stop.get("companion_objectives", []) or []),
        },
    )


def oracle_cache_key(stop: Mapping[str, Any], plan: Mapping[str, Any]) -> str:
    """Return a deterministic key for the Oracle-relevant mission inputs."""
    mode = clean(stop.get("mode") or plan.get("mode"))
    stats_profile = stats_profile_for_mode(mode)

    payload = {
        "task_id": clean(stop.get("task_id")),
        "weapon": clean(stop.get("weapon")),
        "mode": mode,
        "stats_profile": stats_profile,
        "challenge": _challenge_text(stop),
        "enemy_health": _int_from_values(
            300 if stats_profile == "warzone" else 100,
            stop.get("enemy_health"),
            plan.get("enemy_health"),
        ),
        "attachment_count": _int_from_values(
            5,
            stop.get("attachment_count"),
            plan.get("attachment_count"),
        ),
        "challenge_requirement": clean(
            stop.get("challenge_requirement")
            or stop.get("attachment_requirement")
            or plan.get("challenge_requirement")
        ),
        "attachment_name_contains": clean(
            stop.get("attachment_name_contains")
            or stop.get("required_attachment")
            or plan.get("attachment_name_contains")
        ),
        "challenge_role_scope": clean(
            stop.get("challenge_role_scope")
            or plan.get("challenge_role_scope")
        ),
    }

    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def strip_legacy_loadouts(plan: Mapping[str, Any]) -> dict:
    """Remove template-generated loadouts before Oracle becomes source of truth."""
    updated = deepcopy(dict(plan))

    for key in LEGACY_PLAN_LOADOUT_KEYS:
        updated.pop(key, None)

    cleaned_stops = []
    for stop in updated.get("stops", []) or []:
        cleaned_stops.append(strip_legacy_stop_loadout(stop))

    updated["stops"] = cleaned_stops
    updated["loadout_source"] = "oracle_session_brief"
    return updated


__all__ = [
    "oracle_cache_key",
    "stats_profile_for_mode",
    "stop_is_oracle_eligible",
    "stop_to_mission_profile",
    "strip_legacy_loadouts",
    "strip_legacy_stop_loadout",
]

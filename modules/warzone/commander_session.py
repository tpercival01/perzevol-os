"""Persistent Commander session snapshot.

Mission Control writes the active Oracle SessionBrief here. OBS Record View
reads the same JSON, so recording never depends on the originating Streamlit
session still being alive.
"""

from __future__ import annotations

from copy import deepcopy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


STATE_DIR = Path("data/bo7_state")
CURRENT_COMMANDER_SESSION_PATH = STATE_DIR / "current_commander_session.json"


LEGACY_PLAN_LOADOUT_KEYS = {
    "loadout",
    "loadouts",
    "loadout_templates",
    "loadout_template",
    "loadout_template_id",
    "template",
    "templates",
    "template_loadouts",
}

LEGACY_STOP_LOADOUT_KEYS = {
    "loadout",
    "loadout_template",
    "loadout_template_id",
    "template",
    "template_id",
    "template_name",
    "template_score",
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


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _json_safe(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())

    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def _strip_legacy_stop_payload(stop: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = {
        key: value
        for key, value in dict(stop).items()
        if key not in LEGACY_STOP_LOADOUT_KEYS
    }
    return _json_safe(cleaned)


def _strip_legacy_plan_payload(plan: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(dict(plan))

    for key in LEGACY_PLAN_LOADOUT_KEYS:
        cleaned.pop(key, None)

    cleaned_stops = []
    for stop in cleaned.get("stops", []) or []:
        if isinstance(stop, Mapping):
            cleaned_stops.append(_strip_legacy_stop_payload(stop))

    cleaned["stops"] = cleaned_stops
    cleaned["loadout_source"] = "oracle_session_brief"

    return _json_safe(cleaned)


def _snapshot_metadata(plan: Mapping[str, Any], stop: Mapping[str, Any], status: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "status": _clean(status) or "active",
        "source": "commander_oracle_session",
        "mission_id": _clean(plan.get("mission_id") or plan.get("session_id")),
        "task_id": _clean(stop.get("task_id")),
        "weapon": _clean(stop.get("weapon")),
        "challenge": _clean(
            stop.get("challenge_text")
            or stop.get("raw_requirement")
            or stop.get("camo")
        ),
        "mode": _clean(stop.get("mode") or plan.get("mode")),
        "stop_number": stop.get("stop_number"),
    }


def save_current_commander_session(
    *,
    plan: Mapping[str, Any],
    stop: Mapping[str, Any],
    session_brief: Any,
    status: str = "active",
) -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    cleaned_plan = _strip_legacy_plan_payload(plan)
    cleaned_stop = _strip_legacy_stop_payload(stop)

    payload = {
        **_snapshot_metadata(plan, stop, status),
        "active_plan": cleaned_plan,
        "active_stop": cleaned_stop,
        "session_brief": _json_safe(session_brief),
    }

    CURRENT_COMMANDER_SESSION_PATH.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return payload


def load_current_commander_session() -> dict[str, Any] | None:
    if not CURRENT_COMMANDER_SESSION_PATH.exists():
        return None

    try:
        payload = json.loads(
            CURRENT_COMMANDER_SESSION_PATH.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(payload, dict):
        return None

    if not isinstance(payload.get("session_brief"), dict):
        return None

    return payload


def clear_current_commander_session() -> None:
    if CURRENT_COMMANDER_SESSION_PATH.exists():
        CURRENT_COMMANDER_SESSION_PATH.unlink()


__all__ = [
    "CURRENT_COMMANDER_SESSION_PATH",
    "clear_current_commander_session",
    "load_current_commander_session",
    "save_current_commander_session",
]

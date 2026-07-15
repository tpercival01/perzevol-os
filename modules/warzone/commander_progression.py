"""Automatic Commander mission progression.

After a completed weapon challenge is written to the tracker, Commander reloads
the tracker and asks this module for the next active task for the same weapon.
The next challenge is moved to the front of the unresolved route so Oracle can
prepare the replacement loadout immediately.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping


WEAPON_PROGRESSION_TASK_TYPES = {
    "camo",
    "mastery_badge_weapon",
    "weapon_prestige",
}

LEGACY_STOP_LOADOUT_KEYS = {
    "loadout",
    "template",
    "template_id",
    "template_name",
    "loadout_source",
    "primary",
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
    "reason",
    "score",
}

LEGACY_PLAN_LOADOUT_KEYS = {
    "loadout",
    "loadouts",
    "loadout_templates",
    "template_loadouts",
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def _normalised(value: Any) -> str:
    return clean(value).casefold()


def strip_legacy_stop_payload(stop: Mapping[str, Any]) -> dict:
    """Remove template/class payload so Oracle SessionBrief remains source of truth."""
    cleaned = deepcopy(dict(stop))

    for key in LEGACY_STOP_LOADOUT_KEYS:
        cleaned.pop(key, None)

    return cleaned


def strip_legacy_plan_payload(plan: Mapping[str, Any]) -> dict:
    """Remove plan-level legacy loadout collections and clean each stop."""
    updated = deepcopy(dict(plan))

    for key in LEGACY_PLAN_LOADOUT_KEYS:
        updated.pop(key, None)

    updated["stops"] = [
        strip_legacy_stop_payload(stop)
        for stop in updated.get("stops", []) or []
    ]
    updated["loadout_source"] = "oracle_session_brief"

    return updated


def _candidate_score(task: Mapping[str, Any], completed_stop: Mapping[str, Any]) -> tuple:
    same_chain = _normalised(task.get("chain")) == _normalised(completed_stop.get("chain"))
    same_task_type = _normalised(task.get("task_type")) == _normalised(completed_stop.get("task_type"))

    task_type_priority = {
        "camo": 0,
        "mastery_badge_weapon": 1,
        "weapon_prestige": 2,
    }.get(_normalised(task.get("task_type")), 9)

    progress = task.get("weapon_progress", 0)
    try:
        progress_value = float(progress or 0)
    except (TypeError, ValueError):
        progress_value = 0.0

    return (
        0 if same_chain else 1,
        0 if same_task_type else 1,
        task_type_priority,
        -progress_value,
        clean(task.get("task_id")),
    )


def next_task_for_same_weapon(
    *,
    completed_stop: Mapping[str, Any],
    tasks: Iterable[Mapping[str, Any]],
    completed_task_ids: Iterable[str] = (),
) -> dict | None:
    weapon = _normalised(completed_stop.get("weapon"))
    mode = _normalised(completed_stop.get("mode"))
    completed_ids = {clean(value) for value in completed_task_ids if clean(value)}
    current_task_id = clean(completed_stop.get("task_id"))

    if not weapon:
        return None

    candidates = []

    for raw_task in tasks:
        task = dict(raw_task)
        task_id = clean(task.get("task_id"))

        if not task_id or task_id == current_task_id or task_id in completed_ids:
            continue

        if _normalised(task.get("weapon")) != weapon:
            continue

        if mode and _normalised(task.get("mode")) != mode:
            continue

        if _normalised(task.get("task_type")) not in WEAPON_PROGRESSION_TASK_TYPES:
            continue

        if bool(task.get("locked")):
            continue

        candidates.append(task)

    if not candidates:
        return None

    return sorted(
        candidates,
        key=lambda task: _candidate_score(task, completed_stop),
    )[0]


def advance_plan_after_completed_stop(
    *,
    plan: Mapping[str, Any],
    completed_stop: Mapping[str, Any],
    tasks: Iterable[Mapping[str, Any]],
    completed_task_ids: Iterable[str] = (),
) -> tuple[dict, dict | None]:
    """Move the same weapon's newly active challenge to the next route position."""
    updated = strip_legacy_plan_payload(plan)
    completed_ids = {clean(value) for value in completed_task_ids if clean(value)}

    next_task = next_task_for_same_weapon(
        completed_stop=completed_stop,
        tasks=tasks,
        completed_task_ids=completed_ids,
    )

    if next_task is None:
        updated["progression_status"] = "no_same_weapon_follow_up"
        return updated, None

    existing_stops = [strip_legacy_stop_payload(stop) for stop in updated.get("stops", []) or []]
    next_task_id = clean(next_task.get("task_id"))

    resolved = [
        stop
        for stop in existing_stops
        if clean(stop.get("task_id")) in completed_ids
    ]

    unresolved = [
        stop
        for stop in existing_stops
        if clean(stop.get("task_id")) not in completed_ids
        and clean(stop.get("task_id")) != next_task_id
    ]

    prepared_next = strip_legacy_stop_payload(next_task)
    prepared_next["progression_source"] = "same_weapon_next_challenge"
    prepared_next["previous_task_id"] = clean(completed_stop.get("task_id"))

    reordered = resolved + [prepared_next] + unresolved

    for index, stop in enumerate(reordered, start=1):
        stop["stop_number"] = index

    updated["stops"] = reordered
    updated["progression_status"] = "same_weapon_advanced"
    updated["progression_weapon"] = clean(next_task.get("weapon"))
    updated["progression_task_id"] = next_task_id
    updated["progression_challenge"] = clean(
        next_task.get("challenge_text")
        or next_task.get("camo")
    )

    return updated, prepared_next


__all__ = [
    "advance_plan_after_completed_stop",
    "next_task_for_same_weapon",
    "strip_legacy_plan_payload",
    "strip_legacy_stop_payload",
]

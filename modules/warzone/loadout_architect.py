from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from modules.warzone.killchain_engine import (
    ANCHOR_COLLECTIONS,
    build_session_plan,
    safe_int,
)

from modules.warzone.series_director import series_recording_lines_for_plan

try:
    from modules.warzone.ttk_oracle_engine import (
        describe_weapon_build_data as ttk_describe_weapon_build_data,
        load_ttk_data as ttk_load_ttk_data,
        optimise_single_weapon_build as ttk_optimise_single_weapon_build,
    )
    TTK_ORACLE_AVAILABLE = True
except Exception:  # pragma: no cover - optional when TTK data is absent
    ttk_describe_weapon_build_data = None
    ttk_load_ttk_data = None
    ttk_optimise_single_weapon_build = None
    TTK_ORACLE_AVAILABLE = False

CLEAN_DATA_DIR = Path("data/bo7_clean")
LOADOUT_TEMPLATE_FILE = CLEAN_DATA_DIR / "loadout_templates.csv"

PLAYABLE_WEAPON_CLASSES = {
    "Assault Rifles",
    "Submachine Guns",
    "Shotguns",
    "LMGs",
    "Marksman Rifles",
    "Sniper Rifles",
    "Pistols",
    "Launchers",
    "Specials",
    "Melee",
    "Wonder Weapons",
}

WEAPON_GOAL_TASK_TYPES = {
    "camo",
    "mastery_badge_weapon",
    "weapon_prestige",
}

GENERIC_PRIMARY_PLACEHOLDERS = {
    "",
    "best unfinished singularity weapon",
    "best unfinished multiplayer weapon",
    "use the assigned objective weapon",
    "assigned objective weapon",
    "closest natural weapon goal",
    "use the closest natural weapon goal",
}


GENERIC_ATTACHMENT_PLACEHOLDERS = {
    "",
    "use best available build for the assigned weapon",
    "use the best available close-range build for the selected unfinished weapon",
    "use the best available close-range build for the selected weapon",
    "best attachments for gun",
    "best available build",
    "use the in-game gunsmith",
}

ENERGY_OPTIONS = [
    {
        "key": "any",
        "label": "Any Energy",
        "short": "ANY",
        "motivation": "Decent",
        "session_goal": "Balanced progress",
        "commander_mode": "Optimise my grind",
        "available_minutes": 60,
        "minimum_closeness": 75,
        "focus_targets": [],
        "description": "Let the Commander pick the most sensible route without an energy bias.",
    },
    {
        "key": "low",
        "label": "Low Energy",
        "short": "LOW",
        "motivation": "Barely functioning",
        "session_goal": "Fast dopamine / recordable progress",
        "commander_mode": "Closest finishes",
        "available_minutes": 45,
        "minimum_closeness": 80,
        "focus_targets": [
            "Camos",
            "Calling Cards",
            "Reticles",
            "Weapon Prestige",
            "Weapon Mastery Badges",
            "Equipment Mastery Badges",
        ],
        "description": "Shortest realistic route. Prefer visible progress and nearby completions.",
    },
    {
        "key": "medium",
        "label": "Medium Energy",
        "short": "MED",
        "motivation": "Decent",
        "session_goal": "Balanced progress",
        "commander_mode": "Completion stack",
        "available_minutes": 60,
        "minimum_closeness": 75,
        "focus_targets": [
            "Non-camo completion",
            "Calling Cards",
            "Reticles",
            "Camos",
            "Weapon Mastery Badges",
            "Equipment Mastery Badges",
            "Weapon Prestige",
        ],
        "description": "Balanced route. Stack camos, cards, badges, reticles, and levels together.",
    },
    {
        "key": "high",
        "label": "High Energy",
        "short": "HIGH",
        "motivation": "Locked in",
        "session_goal": "Attack biggest bottleneck",
        "commander_mode": "Optimise my grind",
        "available_minutes": 90,
        "minimum_closeness": 70,
        "focus_targets": [
            "Camos",
            "Weapon Mastery Badges",
            "Equipment Mastery Badges",
            "Weapon Prestige",
            "Reticles",
            "Calling Cards",
        ],
        "description": "Push harder bottlenecks. Less comfort, more tracker movement.",
    },
]

MODE_OPTIONS = [
    {
        "key": "any",
        "label": "Any Mode",
        "short": "ANY MODE",
        "preferred_mode": "Commander chooses",
        "avoided_mode": "Global Cleanup",
        "description": "No mode chosen. Commander compares active modes and picks the best route.",
    },
    {
        "key": "warzone",
        "label": "Warzone",
        "short": "WZ",
        "preferred_mode": "Warzone",
        "avoided_mode": "Zombies",
        "description": "Warzone-only route.",
    },
    {
        "key": "multiplayer",
        "label": "Multiplayer",
        "short": "MP",
        "preferred_mode": "Multiplayer",
        "avoided_mode": "Zombies",
        "description": "Multiplayer-only route.",
    },
    {
        "key": "zombies",
        "label": "Zombies",
        "short": "ZM",
        "preferred_mode": "Zombies",
        "avoided_mode": "Warzone",
        "description": "Zombies-only route.",
    },
    {
        "key": "coop",
        "label": "Co-Op",
        "short": "CO-OP",
        "preferred_mode": "Co-Op / Endgame",
        "avoided_mode": "Warzone",
        "description": "Co-Op and Endgame route.",
    },
    {
        "key": "cleanup",
        "label": "Tracker Cleanup",
        "short": "CLEANUP",
        "preferred_mode": "Global Cleanup",
        "avoided_mode": "",
        "force_commander_mode": "Closest finishes",
        "force_session_goal": "Fast dopamine / recordable progress",
        "description": "Search across tracker cleanup style items and closest finishes.",
    },
]

NON_PRIMARY_TASK_TYPES = {
    "mastery_badge_equipment",
    "scorestreak",
    "equipment",
}

NON_PRIMARY_WEAPON_CLASSES = {
    "Scorestreaks",
    "Scorestreak",
    "Field Upgrades",
    "Equipment",
    "Tactical",
    "Lethal",
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def anchor_collection_default() -> str:
    if "Any stackable progress" in ANCHOR_COLLECTIONS:
        return "Any stackable progress"

    return ANCHOR_COLLECTIONS[0] if ANCHOR_COLLECTIONS else ""


def find_option_by_key(options: list[dict], key: str) -> dict:
    for option in options:
        if option.get("key") == key:
            return option

    return options[0] if options else {}


def build_generation_profile(energy: dict, mode: dict) -> dict:
    commander_mode = mode.get("force_commander_mode") or energy["commander_mode"]
    session_goal = mode.get("force_session_goal") or energy["session_goal"]

    return {
        "energy_label": energy["label"],
        "mode_label": mode["label"],
        "button_label": f"{energy['short']} + {mode['short']}",
        "motivation": energy["motivation"],
        "session_goal": session_goal,
        "commander_mode": commander_mode,
        "preferred_mode": mode["preferred_mode"],
        "avoided_mode": mode["avoided_mode"],
        "available_minutes": int(energy["available_minutes"]),
        "minimum_closeness": int(energy["minimum_closeness"]),
        "focus_targets": list(energy.get("focus_targets", [])),
        "description": f"{energy['description']} {mode['description']}",
    }


def generate_quick_plan(
    *,
    energy: dict,
    mode: dict,
    tasks: list[dict],
    attach_loadouts: bool = True,
) -> dict:
    profile = build_generation_profile(energy, mode)

    plan = build_session_plan(
        tasks=tasks,
        preferred_mode=profile["preferred_mode"],
        session_goal=profile["session_goal"],
        motivation=profile["motivation"],
        available_minutes=profile["available_minutes"],
        commander_mode=profile["commander_mode"],
        focus_targets=profile["focus_targets"],
        anchor_weapon="",
        anchor_class="",
        anchor_collection=anchor_collection_default(),
        minimum_closeness=profile["minimum_closeness"],
        avoided_mode=profile["avoided_mode"],
    )

    plan["quick_energy_key"] = energy["key"]
    plan["quick_mode_key"] = mode["key"]
    plan["quick_energy_label"] = energy["label"]
    plan["quick_mode_label"] = mode["label"]
    plan["quick_button_label"] = profile["button_label"]
    plan["quick_description"] = profile["description"]
    plan["quick_profile"] = profile

    if attach_loadouts:
        plan = attach_loadouts_to_plan(plan, tasks)

    return plan


def load_loadout_templates(path: Path = LOADOUT_TEMPLATE_FILE) -> list[dict]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8", newline="") as file:
        return [
            row for row in csv.DictReader(file)
            if clean(row.get("template_id"))
        ]



def strip_goal_suffix(weapon_text: str) -> str:
    """
    Convert UI labels such as "Strider 300 (Specials: 2 remaining)" back to
    the actual gun name before asking the TTK Oracle for a build.
    """
    text = clean(weapon_text)
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
    text = re.sub(r"\s+if safe, otherwise.*$", "", text, flags=re.IGNORECASE).strip()
    return text


def attachment_text_is_generic(value: str) -> bool:
    text = clean(value).lower()
    if text in GENERIC_ATTACHMENT_PLACEHOLDERS:
        return True

    generic_fragments = [
        "best available build",
        "best available close-range build",
        "best attachments",
    ]
    return any(fragment in text for fragment in generic_fragments)


def unverified_class_text(slot_name: str) -> str:
    return f"Not controlled by Commander. Use your verified in-game {slot_name} choice."


def objective_item_is_non_primary(stop: dict) -> bool:
    task_type = clean(stop.get("task_type"))
    weapon_class = clean(stop.get("weapon_class"))
    category = clean(stop.get("category"))

    return (
        task_type in NON_PRIMARY_TASK_TYPES
        or weapon_class in NON_PRIMARY_WEAPON_CLASSES
        or category in NON_PRIMARY_WEAPON_CLASSES
    )


def objective_item_for_slot(stop: dict, slot_names: set[str]) -> str:
    weapon = clean(stop.get("weapon"))
    if not weapon:
        return ""

    task_type = clean(stop.get("task_type"))
    weapon_class = clean(stop.get("weapon_class"))
    category = clean(stop.get("category"))

    values = {
        task_type.lower(),
        weapon_class.lower(),
        category.lower(),
    }

    wanted = {slot.lower() for slot in slot_names}
    if values & wanted:
        return weapon

    return ""


def verified_perks_for_stop(stop: dict, plan: dict, template_perks: list[str]) -> str:
    """
    The template CSV has contained perk names that are not reliable for BO7.
    Perks are therefore deliberately suppressed until a verified BO7 perk dataset exists.
    """
    return "Not controlled by Commander. Use your verified in-game perk package."


def verified_wildcard_for_stop(stop: dict, plan: dict, template: dict) -> str:
    """
    Suppress unverified wildcard recommendations instead of showing believable
    but potentially fake class items on camera.
    """
    return "Not controlled by Commander."


def tactical_for_stop(stop: dict, template: dict) -> str:
    required = objective_item_for_slot(stop, {"Tactical", "Tacticals"})
    if required:
        return f"Required objective: {required}"

    return unverified_class_text("tactical")


def lethal_for_stop(stop: dict, template: dict) -> str:
    required = objective_item_for_slot(stop, {"Lethal", "Lethals"})
    if required:
        return f"Required objective: {required}"

    return unverified_class_text("lethal")


def field_upgrade_for_stop(stop: dict, template: dict) -> str:
    required = objective_item_for_slot(stop, {"Field Upgrade", "Field Upgrades"})
    if required:
        return f"Required objective: {required}"

    return unverified_class_text("field upgrade")


def scorestreaks_for_stop(stop: dict, template_scorestreaks: list[str]) -> str:
    weapon = clean(stop.get("weapon"))
    task_type = clean(stop.get("task_type"))
    weapon_class = clean(stop.get("weapon_class"))
    category = clean(stop.get("category"))

    is_scorestreak_objective = (
        weapon_class in {"Scorestreaks", "Scorestreak"}
        or category in {"Scorestreaks", "Scorestreak"}
        or task_type in {"scorestreak", "mastery_badge_equipment"}
    )

    if weapon and is_scorestreak_objective:
        return f"Required objective: {weapon}. Remaining streak slots are your comfort choice."

    return "Not controlled by Commander. Use comfort streaks only if they do not block the objective."



def oracle_profile_for_plan(plan: dict) -> dict:
    mode = clean(plan.get("mode"))

    if mode == "Warzone":
        return {
            "map_type": "Large map / Battle Royale",
            "fight_type": "Mid range",
            "build_goal": "Balanced meta build",
            "enemy_health": 300,
        }

    if mode == "Multiplayer":
        return {
            "map_type": "Small map / Resurgence",
            "fight_type": "Close range",
            "build_goal": "Aggressive mobility",
            "enemy_health": 300,
        }

    return {
        "map_type": "Small map / Resurgence",
        "fight_type": "Close range",
        "build_goal": "Balanced meta build",
        "enemy_health": 300,
    }


def ttk_oracle_build_for_primary(primary: str, plan: dict) -> dict:
    """
    Returns a trusted TTK Oracle attachment build for a real primary weapon.

    This deliberately avoids the old placeholder text. If the Oracle cannot
    build from trusted/modelled attachment rows, the caller gets a plain note
    instead of fake "best attachments".
    """
    primary = clean(primary)
    weapon_name = strip_goal_suffix(primary)

    if not weapon_name or primary_is_generic_placeholder(weapon_name):
        return {}

    if (
        not TTK_ORACLE_AVAILABLE
        or ttk_load_ttk_data is None
        or ttk_describe_weapon_build_data is None
        or ttk_optimise_single_weapon_build is None
    ):
        return {
            "available": False,
            "attachments": "",
            "note": "TTK Oracle is not available in this environment.",
        }

    try:
        guns, attachments = ttk_load_ttk_data()
    except Exception as error:
        return {
            "available": False,
            "attachments": "",
            "note": f"TTK Oracle data failed to load: {error}",
        }

    profile = oracle_profile_for_plan(plan)

    # Prefer a five-attachment build, but do not force fake filler parts.
    # If only four or three trusted/modelled slots exist, return the best honest
    # partial build and label it as such.
    for attachment_count in (5, 4, 3):
        status = ttk_describe_weapon_build_data(
            guns=guns,
            attachments=attachments,
            weapon_name=weapon_name,
            attachment_count=attachment_count,
        )

        if not status.get("buildable"):
            continue

        results = ttk_optimise_single_weapon_build(
            guns=guns,
            attachments=attachments,
            weapon_name=weapon_name,
            map_type=profile["map_type"],
            fight_type=profile["fight_type"],
            build_goal=profile["build_goal"],
            enemy_health=profile["enemy_health"],
            attachment_count=attachment_count,
            top_n=1,
        )

        if results.empty:
            continue

        best = results.iloc[0]
        attachments_text = clean(best.get("attachments"))

        if not attachments_text:
            continue

        prefix = "TTK Oracle trusted build"
        if attachment_count < 5:
            prefix = f"TTK Oracle trusted partial build ({attachment_count} attachments)"

        return {
            "available": True,
            "attachments": attachments_text,
            "note": (
                f"{prefix}: {profile['fight_type']} / {profile['build_goal']}. "
                f"{clean(best.get('attachment_trust_note'))}"
            ).strip(),
            "attachment_count": attachment_count,
            "raw_ttk_ms": best.get("raw_ttk_ms", ""),
            "practical_ttk_ms": best.get("practical_ttk_ms", ""),
            "oracle_score": best.get("oracle_score", ""),
        }

    final_status = ttk_describe_weapon_build_data(
        guns=guns,
        attachments=attachments,
        weapon_name=weapon_name,
        attachment_count=5,
    )

    return {
        "available": False,
        "attachments": "",
        "note": final_status.get(
            "message",
            f"No trusted TTK Oracle build is available for {weapon_name}.",
        ),
    }


def primary_attachments_for_loadout(template: dict, primary: str, plan: dict) -> tuple[str, str]:
    weapon_name = strip_goal_suffix(primary) or clean(primary)
    oracle = ttk_oracle_build_for_primary(weapon_name, plan)

    if oracle.get("available") and clean(oracle.get("attachments")):
        attachment_count = clean(oracle.get("attachment_count"))
        label = "TTK Oracle trusted build"
        if attachment_count and attachment_count != "5":
            label = f"TTK Oracle trusted partial build ({attachment_count} attachments)"

        return (
            f"{label}: {clean(oracle.get('attachments'))}",
            clean(oracle.get("note")) or "Only trusted/modelled Oracle attachment rows were allowed.",
        )

    template_attachments = clean(template.get("primary_attachments"))

    if template_attachments and not attachment_text_is_generic(template_attachments):
        note = clean(oracle.get("note")) if oracle else ""
        if note:
            return template_attachments, f"Template attachments used. Oracle note: {note}"

        return template_attachments, "Template attachments used because no Oracle override was needed."

    note = clean(oracle.get("note")) if oracle else ""
    if note:
        return f"No trusted TTK Oracle build for {weapon_name}.", note

    return (
        f"No trusted TTK Oracle build for {weapon_name}.",
        "Add this weapon and its modelled attachment rows to data/bo7_ttk before recording a claimed best build.",
    )



def task_is_available_for_natural_goal(task: dict) -> bool:
    if task.get("locked", False):
        return False

    if task.get("completed_on_session", False):
        return False

    if clean(task.get("last_result")) == "Camo completed":
        return False

    return True


def task_is_weapon_goal(task: dict) -> bool:
    task_type = clean(task.get("task_type"))
    weapon_class = clean(task.get("weapon_class"))
    category = clean(task.get("category"))
    weapon = clean(task.get("weapon"))

    if not weapon:
        return False

    if task_type not in WEAPON_GOAL_TASK_TYPES:
        return False

    if weapon_class in NON_PRIMARY_WEAPON_CLASSES:
        return False

    if category in NON_PRIMARY_WEAPON_CLASSES:
        return False

    if weapon_class and weapon_class not in PLAYABLE_WEAPON_CLASSES:
        return False

    return True


def stop_is_weapon_objective(stop: dict) -> bool:
    task_type = clean(stop.get("task_type"))
    weapon_class = clean(stop.get("weapon_class"))
    weapon = clean(stop.get("weapon"))

    if not weapon:
        return False

    if weapon_class in PLAYABLE_WEAPON_CLASSES:
        return True

    return task_type in WEAPON_GOAL_TASK_TYPES


def assigned_objective_weapon(stop: dict) -> str:
    weapon = clean(stop.get("weapon"))
    task_type = clean(stop.get("task_type"))
    weapon_class = clean(stop.get("weapon_class"))
    category = clean(stop.get("category"))

    if not weapon:
        return ""

    if task_type not in WEAPON_GOAL_TASK_TYPES:
        return ""

    if weapon_class in NON_PRIMARY_WEAPON_CLASSES:
        return ""

    if category in NON_PRIMARY_WEAPON_CLASSES:
        return ""

    if weapon_class and weapon_class not in PLAYABLE_WEAPON_CLASSES:
        return ""

    return weapon


def mode_for_goal_matching(stop: dict, plan: dict) -> str:
    return clean(stop.get("mode") or plan.get("mode"))


def natural_goal_score(task: dict, stop: dict, plan: dict) -> float:
    score = float(task.get("weapon_progress", 0.0) or 0.0)

    task_mode = clean(task.get("mode"))
    target_mode = mode_for_goal_matching(stop, plan)
    task_type = clean(task.get("task_type"))
    camo = clean(task.get("camo")).lower()
    challenge = clean(task.get("challenge_text")).lower()

    if target_mode and target_mode not in {"Any Mode", "Commander chooses", "Global Cleanup"}:
        if task_mode == target_mode:
            score += 120
        else:
            score -= 80

    if task_type == "camo":
        score += 45
    elif task_type == "mastery_badge_weapon":
        score += 35
    elif task_type == "weapon_prestige":
        score += 25

    if "special" in camo:
        score += 35

    if "final military" in camo:
        score += 30

    if "final special" in camo:
        score += 40

    if any(token in camo for token in ["golden", "damascus", "doomsteel", "starglass", "singularity", "apocalypse", "infestation", "genesis"]):
        score += 25

    if "remaining" in camo or "remaining" in challenge:
        score += 15

    stop_weapon_class = clean(stop.get("weapon_class"))
    task_weapon_class = clean(task.get("weapon_class"))

    if stop_weapon_class and task_weapon_class and stop_weapon_class == task_weapon_class:
        score += 20

    return score


def goal_from_stop(stop: dict) -> dict:
    if not stop_is_weapon_objective(stop):
        return {}

    return {
        "task_id": stop.get("task_id", ""),
        "task_type": stop.get("task_type", ""),
        "mode": stop.get("mode", ""),
        "weapon_class": stop.get("weapon_class", ""),
        "weapon": stop.get("weapon", ""),
        "camo": stop.get("camo", ""),
        "challenge_text": stop.get("challenge_text", ""),
        "weapon_progress": stop.get("weapon_progress", 0.0),
    }


def closest_natural_weapon_goal(stop: dict, plan: dict, tasks: list[dict]) -> dict:
    current_goal = goal_from_stop(stop)
    if current_goal:
        return current_goal

    target_mode = mode_for_goal_matching(stop, plan)

    candidates = [
        task for task in tasks
        if task_is_available_for_natural_goal(task)
        and task_is_weapon_goal(task)
    ]

    if target_mode and target_mode not in {"Any Mode", "Commander chooses", "Global Cleanup"}:
        same_mode_candidates = [
            task for task in candidates
            if clean(task.get("mode")) == target_mode
        ]

        if not same_mode_candidates:
            return {}

        candidates = same_mode_candidates

    if not candidates:
        return {}

    ranked = sorted(
        candidates,
        key=lambda task: natural_goal_score(task, stop, plan),
        reverse=True,
    )

    return ranked[0] if ranked else {}


def natural_goal_source_label(goal: dict, stop: dict, plan: dict) -> str:
    if not goal:
        return "No weapon goal found"

    goal_task_id = clean(goal.get("task_id"))
    stop_task_id = clean(stop.get("task_id"))

    if goal_task_id and goal_task_id == stop_task_id:
        return "Objective weapon goal"

    target_mode = mode_for_goal_matching(stop, plan)
    goal_mode = clean(goal.get("mode"))

    if target_mode and target_mode not in {"Any Mode", "Commander chooses", "Global Cleanup"}:
        if goal_mode == target_mode:
            return "Same-mode weapon progress"

        return "Mode mismatch blocked"

    if target_mode == "Global Cleanup":
        return "Cleanup search"

    if target_mode in {"Any Mode", "Commander chooses"}:
        return "Commander-selected mode search"

    return "Natural weapon progress"


def format_natural_goal_weapon(goal: dict) -> str:
    weapon = clean(goal.get("weapon"))
    camo = clean(goal.get("camo"))

    if not weapon:
        return ""

    if camo:
        return f"{weapon} ({camo})"

    return weapon


def format_natural_goal_reason(goal: dict) -> str:
    weapon = clean(goal.get("weapon"))
    camo = clean(goal.get("camo"))
    mode = clean(goal.get("mode"))
    challenge = clean(goal.get("challenge_text"))

    if not weapon:
        return "No natural weapon goal found."

    parts = []

    if mode:
        parts.append(mode)

    if camo:
        parts.append(camo)

    reason = " · ".join(parts)

    if challenge and reason:
        return f"{weapon}: {reason}. {challenge}"

    if challenge:
        return f"{weapon}: {challenge}"

    return f"{weapon}: {reason}" if reason else weapon


def primary_is_generic_placeholder(primary_weapon: str) -> bool:
    return clean(primary_weapon).lower() in GENERIC_PRIMARY_PLACEHOLDERS


def assigned_primary_for_loadout(template: dict, stop: dict, plan: dict, tasks: list[dict]) -> tuple[str, str]:
    primary_weapon = clean(template.get("primary_weapon"))
    primary_role = clean(template.get("primary_role"))
    route_type = clean(template.get("route_type"))
    assigned_weapon = assigned_objective_weapon(stop)
    weapon_class = clean(stop.get("weapon_class"))
    mode = clean(stop.get("mode") or plan.get("mode"))
    task_type = clean(stop.get("task_type"))

    natural_goal = closest_natural_weapon_goal(stop, plan, tasks)
    natural_weapon = format_natural_goal_weapon(natural_goal)

    if primary_role == "replace_with_assigned_weapon" and assigned_weapon:
        return assigned_weapon, "Using the objective weapon because this stop is weapon-specific."

    if (
        primary_role == "replace_with_assigned_weapon_if_sniper"
        and assigned_weapon
        and weapon_class == "Sniper Rifles"
    ):
        return assigned_weapon, "Using the assigned sniper because the objective is sniper-specific."

    if (
        primary_role == "replace_with_assigned_genesis_weapon_if_safe"
        and assigned_weapon
        and mode == "Co-Op / Endgame"
        and task_type == "camo"
    ):
        return (
            f"{assigned_weapon} if safe, otherwise {primary_weapon}",
            "Co-Op route: use the tracked weapon only if it does not risk the clear.",
        )

    if primary_role == "replace_with_best_unfinished_singularity_weapon":
        return (
            natural_weapon or primary_weapon or "Use the closest natural weapon goal",
            "Carrying the closest same-mode weapon goal while you complete the equipment objective.",
        )

    if assigned_weapon:
        return assigned_weapon, "Using the objective weapon because it directly moves this stop."

    if route_type == "scorestreak" and primary_weapon and not primary_is_generic_placeholder(primary_weapon):
        return primary_weapon, "Using the template weapon because this stop is equipment or scorestreak-driven."

    if primary_is_generic_placeholder(primary_weapon):
        return natural_weapon or "Use the closest natural weapon goal", "Using the closest same-mode weapon goal because the main objective is not a playable primary weapon."

    if primary_weapon:
        return primary_weapon, "Using the best matching loadout template primary."

    return natural_weapon or "Use the closest natural weapon goal", "No template primary found, so the closest natural weapon goal was selected."


def score_loadout_template(template: dict, stop: dict, plan: dict) -> int:
    score = safe_int(template.get("priority", 0), 0)

    mode = clean(stop.get("mode") or plan.get("mode"))
    template_mode = clean(template.get("mode"))
    task_type = clean(stop.get("task_type"))
    weapon_class = clean(stop.get("weapon_class"))
    route_type = clean(template.get("route_type"))
    template_class = clean(template.get("weapon_class"))
    category = clean(stop.get("category"))

    if template_mode == mode:
        score += 100

    if template_mode and template_mode != mode:
        score -= 100

    if weapon_class and template_class == weapon_class:
        score += 130

    if weapon_class == "Sniper Rifles" and clean(template.get("template_id")) == "mp_sniper":
        score += 180

    if task_type in {"camo", "mastery_badge_weapon", "weapon_prestige"} and route_type == "weapon_progress":
        score += 80

    if task_type == "mastery_badge_equipment" and "Scorestreak" in weapon_class and route_type == "scorestreak":
        score += 130

    if route_type == "scorestreak" and "Scorestreak" in category:
        score += 100

    if mode == "Co-Op / Endgame" and route_type == "operation":
        score += 80

    if task_type in {"endgame_operation", "endgame_unlock"} and route_type == "operation":
        score += 120

    if template_class == "Any" and route_type in {"scorestreak", "operation"}:
        score += 25

    return score


def empty_loadout_fallback(stop: dict, plan: dict, tasks: list[dict]) -> dict:
    natural_goal = closest_natural_weapon_goal(stop, plan, tasks)
    natural_goal_text = format_natural_goal_reason(natural_goal)
    natural_weapon = format_natural_goal_weapon(natural_goal)

    primary = assigned_objective_weapon(stop) or natural_weapon or "Use the closest natural weapon goal"
    primary_attachments, primary_attachment_note = primary_attachments_for_loadout(
        template={},
        primary=primary,
        plan=plan,
    )

    return {
        "template": {},
        "template_name": "Commander fallback",
        "primary": primary,
        "primary_attachments": primary_attachments,
        "primary_attachment_source": primary_attachment_note,
        "ttk_oracle_note": primary_attachment_note,
        "secondary": "Not controlled by Commander",
        "secondary_attachments": "Not controlled by Commander",
        "wildcard": verified_wildcard_for_stop(stop, plan, {}),
        "perks": verified_perks_for_stop(stop, plan, []),
        "tactical": tactical_for_stop(stop, {}),
        "lethal": lethal_for_stop(stop, {}),
        "field_upgrade": field_upgrade_for_stop(stop, {}),
        "scorestreaks": scorestreaks_for_stop(stop, []),
        "skill_tracks": "N/A",
        "reason": "No loadout template file found. Commander only selected the objective weapon/natural weapon goal.",
        "primary_reason": "Selected from the active objective or nearest same-mode natural weapon goal.",
        "natural_goal": natural_goal_text,
        "natural_goal_weapon": natural_weapon,
        "natural_goal_source": natural_goal_source_label(natural_goal, stop, plan),
        "score": 0,
    }



def build_loadout_for_stop(
    stop: dict,
    plan: dict,
    tasks: list[dict],
    templates: list[dict] | None = None,
) -> dict:
    templates = load_loadout_templates() if templates is None else templates

    if not templates:
        return empty_loadout_fallback(stop, plan, tasks)

    ranked = sorted(
        templates,
        key=lambda template: score_loadout_template(template, stop, plan),
        reverse=True,
    )

    template = ranked[0]

    perks = [
        clean(template.get(f"perk_{index}"))
        for index in range(1, 4)
        if clean(template.get(f"perk_{index}"))
    ]

    scorestreaks = [
        clean(template.get(f"scorestreak_{index}"))
        for index in range(1, 4)
        if clean(template.get(f"scorestreak_{index}"))
    ]

    skill_tracks = [
        clean(template.get(f"skill_track_{index}"))
        for index in range(1, 4)
        if clean(template.get(f"skill_track_{index}"))
    ]

    natural_goal = closest_natural_weapon_goal(stop, plan, tasks)
    primary, primary_reason = assigned_primary_for_loadout(template, stop, plan, tasks)
    primary_attachments, primary_attachment_note = primary_attachments_for_loadout(
        template=template,
        primary=primary,
        plan=plan,
    )

    return {
        "template": template,
        "template_name": clean(template.get("template_name")) or clean(template.get("template_id")),
        "primary": primary,
                "primary_attachments": primary_attachments,
        "primary_attachment_source": primary_attachment_note,
        "ttk_oracle_note": primary_attachment_note,
        "secondary": clean(template.get("secondary_weapon")) or "Not controlled by Commander",
        "secondary_attachments": clean(template.get("secondary_attachments")) or "Not controlled by Commander",
        "wildcard": verified_wildcard_for_stop(stop, plan, template),
        "perks": verified_perks_for_stop(stop, plan, perks),
        "tactical": tactical_for_stop(stop, template),
        "lethal": lethal_for_stop(stop, template),
        "field_upgrade": field_upgrade_for_stop(stop, template),
        "scorestreaks": scorestreaks_for_stop(stop, scorestreaks),
        "skill_tracks": " · ".join(skill_tracks) if skill_tracks else "N/A",
        "reason": clean(template.get("when_to_use") or template.get("notes")),
        "primary_reason": primary_reason,
        "natural_goal": format_natural_goal_reason(natural_goal),
        "natural_goal_weapon": format_natural_goal_weapon(natural_goal),
        "natural_goal_source": natural_goal_source_label(natural_goal, stop, plan),
        "score": score_loadout_template(template, stop, plan),
    }


def attach_loadouts_to_plan(
    plan: dict,
    tasks: list[dict],
    templates: list[dict] | None = None,
) -> dict:
    templates = load_loadout_templates() if templates is None else templates
    updated = dict(plan)
    stops = []

    for stop in plan.get("stops", []) or []:
        updated_stop = dict(stop)
        updated_stop["loadout"] = build_loadout_for_stop(updated_stop, plan, tasks, templates)
        stops.append(updated_stop)

    updated["stops"] = stops
    updated["loadout_source"] = "loadout_architect_v0"
    return updated


def copyable_plan_text(plan: dict, tasks: list[dict], templates: list[dict] | None = None) -> str:
    templates = load_loadout_templates() if templates is None else templates
    profile = plan.get("quick_profile", {})

    lines = [
        f"PERZEVOL COMMANDER PLAN: {plan.get('quick_button_label', plan.get('quick_preset_label', 'Commander Plan'))}",
        f"ENERGY: {plan.get('quick_energy_label', 'Manual')}",
        f"MODE REQUEST: {plan.get('quick_mode_label', plan.get('preferred_mode', 'Unknown'))}",
        f"MODE SELECTED: {plan.get('mode', 'Unknown')}",
        f"TIMEBOX: {plan.get('available_minutes', '?')} minutes",
        f"GOAL: {profile.get('session_goal', plan.get('commander_mode', 'Unknown'))}",
        f"ROUTE STYLE: {plan.get('commander_mode', 'Unknown')}",
        "RULE: No reroll unless impossible",
        "",
        "OBJECTIVES",
    ]

    for stop in plan.get("stops", []) or []:
        loadout = stop.get("loadout") or build_loadout_for_stop(stop, plan, tasks, templates)

        lines.extend(
            [
                "",
                f"{stop.get('stop_number', '?')}. {stop.get('weapon', 'Objective')} - {stop.get('camo', 'Target')}",
                f"   Mode: {stop.get('mode', plan.get('mode', 'Unknown'))}",
                f"   Type: {stop.get('task_type', 'objective')}",
                f"   Challenge: {stop.get('challenge_text', '')}",
                f"   Primary: {loadout.get('primary', 'N/A')}",
                f"   Primary reason: {loadout.get('primary_reason', 'N/A')}",
                f"   Natural goal: {loadout.get('natural_goal', 'N/A')}",
                f"   Natural goal source: {loadout.get('natural_goal_source', 'N/A')}",
                f"   Primary attachments: {loadout.get('primary_attachments', 'N/A')}",
                f"   Attachment source: {loadout.get('primary_attachment_source', loadout.get('ttk_oracle_note', 'N/A'))}",
                f"   Secondary: {loadout.get('secondary', 'N/A')}",
                f"   Perks: {loadout.get('perks', 'N/A')}",
                f"   Tactical/Lethal/Field: {loadout.get('tactical', 'N/A')} / {loadout.get('lethal', 'N/A')} / {loadout.get('field_upgrade', 'N/A')}",
            ]
        )

    return "\n".join(lines)


def recording_lines_for_plan(plan: dict) -> str:
    series_lines = series_recording_lines_for_plan(plan)

    if series_lines:
        return series_lines

    stops = plan.get("stops", []) or []
    first = stops[0] if stops else {}
    weapon = clean(first.get("weapon")) or "the first objective"
    camo = clean(first.get("camo")) or "the target"

    return "\n".join(
        [
            f"HOOK: I let the Commander choose the session. It picked {weapon}.",
            "RULE: No rerolls unless the objective is impossible.",
            f"OBJECTIVE: {weapon} - {camo}.",
            "PROOF: Show the Commander page, show the class, then show the unlock/progress screen.",
            "MID-SESSION: I am not picking the easy route. The Commander already locked the plan.",
            "ENDING: The AI chose the grind. I followed it. The debrief decides if it worked.",
        ]
    )

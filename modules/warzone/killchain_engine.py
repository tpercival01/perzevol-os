from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

try:
    from groq import Groq
except ImportError:  # pragma: no cover - optional dependency in some environments
    Groq = None  # type: ignore[assignment]


CLEAN_FOLDER = Path("data/bo7_clean")

ENERGY_LEVELS = ["Low", "Medium", "High", "Unstable"]

MOTIVATION_LEVELS = [
    "Barely functioning",
    "Low",
    "Decent",
    "Locked in",
]

MODES = [
    "Commander chooses",
    "Warzone",
    "Multiplayer",
    "Zombies",
    "Co-Op / Endgame",
    "Global Cleanup",
]

SESSION_GOALS = [
    "Fast dopamine / recordable progress",
    "Attack biggest bottleneck",
    "Balanced progress",
    "Content-first chaos",
    "Pain session",
]

COMMANDER_MODES = [
    "Optimise my grind",
    "Start from my itch",
    "Closest finishes",
    "Class cleanup",
    "Mode completion push",
    "Completion stack",
]

FOCUS_TARGETS = [
    "Launchers",
    "Pistols",
    "Scorestreaks",
    "Specials",
    "Melee",
    "Camos",
    "Weapon Mastery Badges",
    "Equipment Mastery Badges",
    "Reticles",
    "Calling Cards",
    "Weapon Prestige",
    "Operations / Missions",
    "Rewards / Unlocks",
    "Map Challenges",
    "Intel",
    "Non-camo completion",
]

ANCHOR_COLLECTIONS = [
    "Any stackable progress",
    "Camos",
    "Weapon Mastery Badges",
    "Equipment Mastery Badges",
    "Reticles",
    "Calling Cards",
    "Weapon Prestige",
    "Operations / Missions",
    "Rewards / Unlocks",
    "Map Challenges",
    "Intel",
    "Non-camo completion",
]

RESULT_OPTIONS = [
    "Camo completed",
    "Partial progress",
    "Blocked / wrong requirement",
    "Skipped",
    "Failed",
]

BLAME_OPTIONS = [
    "Successful operation",
    "Human avoidance",
    "Bad AI assignment",
    "Skill issue",
    "Time limit too short",
    "Requirement unclear",
    "Game nonsense",
]

BASE_CAMO_COUNT = 9
SPECIAL_CAMO_COUNT = 3

TRUE_VALUES = {"TRUE", "YES", "DONE", "COMPLETE", "COMPLETED", "✅"}
FALSE_VALUES = {"FALSE", "NO", "INCOMPLETE", "❌"}
NA_VALUES = {"N/A", "NA", "NONE", ""}

MP_WEAPON_BADGE_REQUIREMENTS = {
    "Assault Rifles": (100, 250, 500, 6),
    "Submachine Guns": (100, 250, 500, 6),
    "Shotguns": (100, 250, 500, 3),
    "LMGs": (100, 250, 500, 2),
    "Marksman Rifles": (100, 250, 500, 3),
    "Sniper Rifles": (100, 250, 500, 3),
    "Pistols": (50, 100, 250, 3),
    "Launchers": (25, 50, 100, 2),
    "Specials": (100, 250, 500, 2),
    "Melee": (50, 100, 250, 2),
}

ZM_WEAPON_BADGE_REQUIREMENTS = {
    "Assault Rifles": (500, 1500, 3000, 6),
    "Submachine Guns": (500, 1500, 3000, 6),
    "Shotguns": (500, 1500, 3000, 3),
    "LMGs": (500, 1500, 3000, 2),
    "Marksman Rifles": (500, 1500, 3000, 3),
    "Sniper Rifles": (500, 1500, 3000, 3),
    "Pistols": (500, 1500, 3000, 3),
    "Launchers": (500, 1500, 3000, 2),
    "Specials": (500, 1500, 3000, 2),
    "Melee": (500, 1500, 3000, 2),
    "Wonder Weapons": (500, 1500, 3000, 3),
}


def clean(value: Any) -> str:
    return str(value).strip()


def is_true(value: Any) -> bool:
    return clean(value).upper() in TRUE_VALUES


def is_false(value: Any) -> bool:
    return clean(value).upper() in FALSE_VALUES


def is_na(value: Any) -> bool:
    return clean(value).upper() in NA_VALUES


def is_applicable(value: Any) -> bool:
    return not is_na(value)

def counts_for_100_percent(row: dict[str, Any]) -> bool:
    """
    Calling card rows count towards the dashboard by default.

    Set counts_for_100_percent to FALSE for optional extras, especially
    leftover Dark Ops challenges after the actual Master card is unlocked.
    """
    value = clean(row.get("counts_for_100_percent", ""))

    if not value:
        return True

    return value.upper() not in {"FALSE", "NO", "0", "N", "OPTIONAL", "EXTRA"}

def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(clean(value).replace(",", ""))
    except (TypeError, ValueError):
        return fallback


def load_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    df = pd.read_csv(path, dtype=str).fillna("")
    return df.to_dict(orient="records")


def load_rules(path: Path) -> dict[str, dict[str, str]]:
    rules: dict[str, dict[str, str]] = {}

    if not path.exists():
        return rules

    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            rule_type = clean(row.get("rule_type", ""))
            key = clean(row.get("key", ""))
            value = clean(row.get("value", ""))

            if not rule_type:
                continue

            if rule_type not in rules:
                rules[rule_type] = {}

            rules[rule_type][key] = value

    return rules


def rules_path_for_status(path: Path) -> Path:
    return path.with_name(path.name.replace("_status.csv", "_rules.csv"))


def get_rule(
    rules: dict[str, dict[str, str]],
    rule_type: str,
    key: str,
    fallback: str = "",
) -> str:
    return rules.get(rule_type, {}).get(key, fallback)


def make_task(
    *,
    task_id: str,
    task_type: str,
    mode: str,
    chain: str,
    category: str,
    weapon_class: str = "",
    weapon: str = "",
    camo: str = "",
    challenge_text: str,
    raw_requirement: str = "",
    progress: float = 0.0,
    locked: bool = False,
    lock_reason: str = "Available.",
    recommended_mode: str = "",
    mode_reason: str = "",
    strategy: str = "",
    avoid: str = "",
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "task_type": task_type,
        "mode": mode,
        "chain": chain,
        "category": category,
        "weapon_class": weapon_class,
        "weapon": weapon or category,
        "camo": camo or challenge_text,
        "challenge_text": challenge_text,
        "raw_requirement": raw_requirement or challenge_text,
        "weapon_progress": round(progress, 2),
        "completed_on_session": False,
        "last_result": "",
        "locked": locked,
        "lock_reason": lock_reason,
        "recommended_mode": recommended_mode or default_recommended_mode(mode, task_type, category),
        "mode_reason": mode_reason or default_mode_reason(mode, task_type, category),
        "strategy": strategy or default_strategy(mode, task_type, category),
        "avoid": avoid or default_avoid(mode, task_type, category),
    }


def default_recommended_mode(mode: str, task_type: str, category: str) -> str:
    if mode == "Warzone":
        return "Resurgence Casual, or Battle Royale Casual if Resurgence Casual is unavailable"

    if mode == "Multiplayer":
        return "Small-map / high-engagement playlist"

    if mode == "Zombies":
        return "Fastest spawn-density route or the named map if required"

    if mode == "Co-Op / Endgame":
        return "Endgame route that directly supports the requirement"

    if task_type == "weapon_prestige":
        return "Stack with an active camo or mastery badge task"

    return "Best available mode for the active requirement"


def default_mode_reason(mode: str, task_type: str, category: str) -> str:
    if task_type == "weapon_prestige":
        return "Weapon prestige should usually be stacked with another active 100% objective."

    if task_type == "reticle":
        return "Reticle progress is best done while stacking weapon, camo, or prestige progress."

    return f"This recommendation prioritises measurable {category} progress."


def default_strategy(mode: str, task_type: str, category: str) -> str:
    if mode == "Warzone":
        return "Use the target weapon or optic, force repeat fights, and ignore wins unless the challenge requires placement."

    if mode == "Multiplayer":
        return "Build the exact class required and prioritise repeated engagements over scoreboard play."

    if mode == "Zombies":
        return "Farm the exact requirement directly. Avoid side quests unless the challenge requires them."

    if mode == "Co-Op / Endgame":
        return "Enter with the required weapon/setup and route directly towards the tracked objective."

    return "Only play actions that move the tracker."


def default_avoid(mode: str, task_type: str, category: str) -> str:
    if mode == "Warzone":
        return "Avoid Black Ops Royale for targeted weapon progress unless the weapon is easy to obtain there."

    if mode == "Multiplayer":
        return "Avoid slow playlists and comfort queues that do not produce repeated engagements."

    if mode == "Zombies":
        return "Avoid low-density wandering and long setup loops."

    if task_type == "dark_ops":
        return "Avoid assigning this randomly during low-energy sessions."

    return "Avoid anything that does not move the active tracker item."

def load_reticle_weapon_unlocks() -> list[dict[str, Any]]:
    return load_csv_rows(CLEAN_FOLDER / "reticle_weapon_unlocks.csv")


def weapon_level_lookup() -> dict[str, dict[str, Any]]:
    rows = load_csv_rows(CLEAN_FOLDER / "weapon_prestige.csv")
    return {clean(row.get("weapon", "")): row for row in rows if clean(row.get("weapon", ""))}


def source_weapon_unlock_is_available(source_weapon: str, unlock_level: int) -> bool:
    """
    Attachment unlocks are treated as available if the source weapon has reached
    the listed level, or if any prestige / later level milestone proves it has
    already passed its base cap before.
    """
    if unlock_level <= 0:
        return True

    row = weapon_level_lookup().get(clean(source_weapon))

    if not row:
        return False

    current_level = safe_int(row.get("current_level", 0), 0)

    if current_level >= unlock_level:
        return True

    milestone_columns = [
        "p1_complete",
        "p2_complete",
        "wpm_complete",
        "lvl_100_complete",
        "lvl_150_complete",
        "lvl_200_complete",
        "lvl_250_complete",
    ]

    return any(is_true(row.get(column, "")) for column in milestone_columns)


def best_reticle_for_mode(
    mode: str,
    available_tasks: list[dict[str, Any]],
    weapon: str = "",
    weapon_class: str = "",
) -> dict[str, Any] | None:
    """
    Returns the best active reticle task for a mode.

    If weapon_class is supplied, this becomes compatibility-aware using
    reticle_weapon_unlocks.csv. That prevents the Commander from suggesting
    an optic that the assigned weapon class cannot actually use.
    """
    reticle_candidates = [
        task for task in available_tasks
        if task.get("mode") == mode
        and task.get("task_type") == "reticle"
        and not task.get("locked", False)
    ]

    if not reticle_candidates:
        return None

    unlock_rows = load_reticle_weapon_unlocks()
    weapon_class = clean(weapon_class)
    weapon = clean(weapon)

    compatibility_notes: dict[str, str] = {}

    if weapon_class and unlock_rows:
        compatible_reticles: set[str] = set()

        for row in unlock_rows:
            reticle_name = clean(row.get("reticle", ""))
            row_weapon_class = clean(row.get("weapon_class", ""))
            source_weapon = clean(row.get("weapon", ""))
            unlock_type = clean(row.get("unlock_type", "")).lower()
            unlock_level = safe_int(row.get("unlock_level", 0), 0)

            class_matches = row_weapon_class in {weapon_class, "Any"}
            direct_weapon_matches = source_weapon == weapon

            if not class_matches and not direct_weapon_matches:
                continue

            if unlock_type == "armory":
                compatible_reticles.add(reticle_name)
                compatibility_notes.setdefault(reticle_name, "requires Armory Unlock")
                continue

            if source_weapon_unlock_is_available(source_weapon, unlock_level):
                compatible_reticles.add(reticle_name)
                compatibility_notes.setdefault(
                    reticle_name,
                    f"unlock source: {source_weapon} level {unlock_level}",
                )

        reticle_candidates = [
            task for task in reticle_candidates
            if clean(task.get("weapon", "")) in compatible_reticles
        ]

        if not reticle_candidates:
            return None

    reticle_candidates.sort(
        key=lambda task: (
            unlock_leverage_bonus(task),
            float(task.get("weapon_progress", 0.0)),
        ),
        reverse=True,
    )

    best = dict(reticle_candidates[0])
    reticle_name = clean(best.get("weapon", ""))

    if reticle_name in compatibility_notes:
        best["compatibility_note"] = compatibility_notes[reticle_name]

    return best
# ---------------------------------------------------------------------------
# CAMO CHAINS
# ---------------------------------------------------------------------------

def camo_columns(row: dict[str, Any]) -> list[str]:
    ignored = {"mode", "chain", "weapon_class", "weapon"}
    return [column for column in row.keys() if column not in ignored]


def split_camos(row: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    columns = camo_columns(row)

    base = columns[:BASE_CAMO_COUNT]
    special = columns[BASE_CAMO_COUNT:BASE_CAMO_COUNT + SPECIAL_CAMO_COUNT]
    mastery = columns[BASE_CAMO_COUNT + SPECIAL_CAMO_COUNT:]

    return base, special, mastery


def camo_completion_percent(row: dict[str, Any]) -> float:
    columns = camo_columns(row)

    if not columns:
        return 0.0

    completed = sum(1 for column in columns if is_true(row.get(column)))
    return (completed / len(columns)) * 100


def military_counts(rules: dict[str, dict[str, str]]) -> list[int]:
    raw = get_rule(rules, "military_counts", "default", "5|10|20|30|40|50|60|80|100")
    return [safe_int(item) for item in raw.split("|") if clean(item)]


def mastery_variant_rule_type(weapon_class: str) -> str:
    if weapon_class == "Pistols":
        return "mastery_challenge_pistol"

    if weapon_class == "Launchers":
        return "mastery_challenge_launcher"

    if weapon_class == "Melee":
        return "mastery_challenge_melee"

    if weapon_class == "Specials":
        return "mastery_challenge_special"

    return "mastery_challenge"


def camo_gate_group(weapon_class: str) -> set[str]:
    if weapon_class in {"Launchers", "Specials"}:
        return {"Launchers", "Specials"}

    return {weapon_class}


def count_completed_by_gate_group(
    rows: list[dict[str, Any]],
    weapon_class: str,
    camo_name: str,
) -> int:
    group = camo_gate_group(weapon_class)

    return sum(
        1
        for row in rows
        if clean(row.get("weapon_class", "")) in group and is_true(row.get(camo_name))
    )


def count_completed_global(rows: list[dict[str, Any]], camo_name: str) -> int:
    return sum(1 for row in rows if is_true(row.get(camo_name)))

def build_camo_challenge_text(
    row: dict[str, Any],
    camo_name: str,
    rules: dict[str, dict[str, str]],
) -> str:
    weapon = clean(row.get("weapon", ""))
    weapon_class = clean(row.get("weapon_class", ""))
    base, special, mastery = split_camos(row)

    if camo_name in base:
        counts = military_counts(rules)
        challenge_type = get_rule(
            rules,
            "weapon_military_challenge",
            weapon,
            get_rule(rules, "military_challenge", weapon_class, "Eliminations"),
        )

        remaining = [c for c in base if not is_true(row.get(c))]
        remaining_counts = []

        for c in remaining:
            idx = base.index(c)
            count = counts[idx] if idx < len(counts) else counts[-1]
            remaining_counts.append(count)

        if not remaining_counts:
            return f"Military camos complete for {weapon}."

        first_target = remaining_counts[0]
        final_target = remaining_counts[-1]

        if len(remaining) <= 1:
            return (
                f"Reach {first_target} total {challenge_type} with {weapon}. "
                f"Final military camo — completing this unlocks Special camos."
            )

        steps = " → ".join(str(c) for c in remaining_counts)

        return (
            f"Reach {first_target} total {challenge_type} to start. "
            f"{len(remaining)} military camos remaining for {weapon}: {steps}. "
            f"Stay on {weapon} until the final military target is reached: "
            f"{final_target} total {challenge_type.lower()}."
        )

    if camo_name in special:
        remaining = [c for c in special if not is_true(row.get(c))]
        count = len(remaining)

        if count <= 1:
            return (
                f"Complete the final Special camo for {weapon}. "
                f"Check the in-game camo panel for the exact requirement. "
                f"This unlocks Golden Damascus."
            )

        return (
            f"Complete {count} Special camos remaining for {weapon}. "
            f"Check each in-game. Do not leave {weapon} until all Specials are done — "
            f"they unlock Golden Damascus."
        )

    if camo_name in mastery:
        variant_rule = mastery_variant_rule_type(weapon_class)
        challenge = get_rule(
            rules,
            variant_rule,
            camo_name,
            get_rule(rules, "mastery_challenge", camo_name, "Check the in-game mastery requirement."),
        )
        return f"{camo_name}: {challenge}"

    return "Check the in-game requirement."
def build_camo_label(
    row: dict[str, Any],
    camo_name: str,
) -> str:
    """Display label reflecting the full remaining commitment at this camo tier."""
    base, special, mastery = split_camos(row)

    if camo_name in base:
        remaining = [c for c in base if not is_true(row.get(c))]
        count = len(remaining)
        if count <= 1:
            return f"{camo_name} (final military)"
        last = remaining[-1]
        try:
            start_num = camo_name.split()[-1]
            end_num = last.split()[-1]
            prefix = " ".join(camo_name.split()[:-1])
            return f"{prefix} {start_num}–{end_num} ({count} remaining)"
        except Exception:
            return f"{camo_name} ({count} remaining)"

    if camo_name in special:
        remaining = [c for c in special if not is_true(row.get(c))]
        count = len(remaining)
        if count <= 1:
            return f"{camo_name} (final special)"
        return f"Specials: {count} remaining"

    return camo_name

def camo_unlock_status(
    row: dict[str, Any],
    rows: list[dict[str, Any]],
    camo_name: str,
    rules: dict[str, dict[str, str]],
) -> tuple[bool, str]:
    weapon = clean(row.get("weapon", ""))
    weapon_class = clean(row.get("weapon_class", ""))
    base, special, mastery = split_camos(row)

    if camo_name in base:
        return True, "Base camo unlocked."

    if camo_name in special:
        if all(is_true(row.get(camo)) for camo in base):
            return True, "Special camos unlocked: all military camos complete for this weapon."

        return False, f"{camo_name} locked: complete all military camos for {weapon} first."

    if not mastery:
        return True, "No mastery camos configured."

    first_mastery = mastery[0]
    second_mastery = mastery[1] if len(mastery) > 1 else ""
    third_mastery = mastery[2] if len(mastery) > 2 else ""
    final_mastery = mastery[3] if len(mastery) > 3 else ""

    if camo_name == first_mastery:
        previous = base + special

        if all(is_true(row.get(camo)) for camo in previous):
            return True, f"{first_mastery} unlocked: all base and special camos complete."

        return False, f"{first_mastery} locked: complete all base and special camos for {weapon} first."

    if second_mastery and camo_name == second_mastery:
        required = safe_int(get_rule(rules, "class_gate", weapon_class, "999"), 999)
        current = count_completed_by_gate_group(rows, weapon_class, first_mastery)

        if current >= required:
            return True, f"{second_mastery} unlocked: {current}/{required} {first_mastery} completed for this gate group."

        return False, f"{second_mastery} locked: needs {required} {first_mastery}. Current: {current}/{required}."

    if third_mastery and camo_name == third_mastery:
        current = count_completed_global(rows, second_mastery)
        required = 30

        if current >= required:
            return True, f"{third_mastery} unlocked: {current}/{required} {second_mastery} completed."

        return False, f"{third_mastery} locked: needs 30 {second_mastery}. Current: {current}/30."

    if final_mastery and camo_name == final_mastery:
        current = count_completed_global(rows, third_mastery)
        weapon_has_previous = is_true(row.get(third_mastery))

        if current >= 30 and weapon_has_previous:
            return True, f"{final_mastery} unlocked: {current}/30 {third_mastery} completed and {weapon} has {third_mastery}."

        return False, f"{final_mastery} locked: needs 30 {third_mastery} globally and {third_mastery} on {weapon}. Current: {current}/30."

    return True, "No gate found."


def build_camo_tasks_from_status_file(path: Path) -> list[dict[str, Any]]:
    rows = load_csv_rows(path)
    rules = load_rules(rules_path_for_status(path))
    tasks: list[dict[str, Any]] = []

    for row in rows:
        mode = clean(row.get("mode", ""))
        chain = clean(row.get("chain", ""))
        weapon_class = clean(row.get("weapon_class", ""))
        weapon = clean(row.get("weapon", ""))

        if not mode or not chain or not weapon:
            continue

        for camo_name in camo_columns(row):
            if is_true(row.get(camo_name)):
                continue

            if not is_applicable(row.get(camo_name)):
                continue

            unlocked, lock_reason = camo_unlock_status(
                row=row,
                rows=rows,
                camo_name=camo_name,
                rules=rules,
            )

            challenge_text = build_camo_challenge_text(
                row=row,
                camo_name=camo_name,
                rules=rules,
            )

            recommended_mode = get_rule(rules, "recommended_mode", mode, default_recommended_mode(mode, "camo", chain))
            strategy = get_rule(rules, "strategy", mode, default_strategy(mode, "camo", chain))
            avoid = get_rule(rules, "avoid", mode, default_avoid(mode, "camo", chain))

            tasks.append(
                make_task(
                    task_id=f"Camo:{mode}:{chain}:{weapon}:{camo_name}",
                    task_type="camo",
                    mode=mode,
                    chain=chain,
                    category=f"{chain} Camos",
                    weapon_class=weapon_class,
                    weapon=weapon,
                    camo=build_camo_label(row=row, camo_name=camo_name),
                    challenge_text=challenge_text,
                    progress=camo_completion_percent(row),
                    locked=not unlocked,
                    lock_reason=lock_reason,
                    recommended_mode=recommended_mode,
                    mode_reason=f"{recommended_mode} is recommended for {chain} progress.",
                    strategy=strategy,
                    avoid=avoid,
                )
            )

            break

    return tasks


# ---------------------------------------------------------------------------
# WEAPON PRESTIGE
# ---------------------------------------------------------------------------

def load_weapon_prestige_rules() -> dict[str, dict[str, str]]:
    return load_rules(CLEAN_FOLDER / "weapon_prestige_rules.csv")


def weapon_prestige_order(rules: dict[str, dict[str, str]]) -> list[str]:
    raw = get_rule(
        rules,
        "task_order",
        "default",
        "p1_complete|p2_complete|wpm_complete|lvl_100_complete|lvl_150_complete|lvl_200_complete|lvl_250_complete",
    )

    return [clean(item) for item in raw.split("|") if clean(item)]


def weapon_prestige_progress(row: dict[str, Any], order: list[str]) -> float:
    applicable = [item for item in order if is_applicable(row.get(item))]

    if not applicable:
        return 100.0

    completed = sum(1 for item in applicable if is_true(row.get(item)))
    return (completed / len(applicable)) * 100


def build_weapon_prestige_tasks() -> list[dict[str, Any]]:
    path = CLEAN_FOLDER / "weapon_prestige.csv"
    rows = load_csv_rows(path)
    rules = load_weapon_prestige_rules()
    order = weapon_prestige_order(rules)
    tasks: list[dict[str, Any]] = []

    for row in rows:
        weapon_class = clean(row.get("weapon_class", ""))
        weapon = clean(row.get("weapon", ""))

        if not weapon:
            continue

        for stage in order:
            value = row.get(stage, "")

            if not is_applicable(value):
                continue

            if is_true(value):
                continue

            label = get_rule(rules, "task_label", stage, stage.replace("_", " ").replace(" complete", "").title())
            max_level = clean(row.get("max_level", ""))

            current_level = safe_int(row.get("current_level", 0), 0)
            max_level_int = safe_int(max_level, 0)

            level_cap_progress = 0.0

            if max_level_int > 0:
                level_cap_progress = min(100.0, (current_level / max_level_int) * 100)

            challenge_text = label

            if stage in {"p1_complete", "p2_complete"} and max_level:
                challenge_text = (
                    f"{label}. Current weapon level: {current_level}/{max_level}. "
                    f"Reach level cap, then prestige/reset in-game."
                )

            tasks.append(
                make_task(
                    task_id=f"Weapon Prestige:{weapon}:{stage}",
                    task_type="weapon_prestige",
                    mode="Global Cleanup",
                    chain="Weapon Prestige",
                    category="Weapon Prestige",
                    weapon_class=weapon_class,
                    weapon=weapon,
                    camo=label,
                    challenge_text=challenge_text,
                    progress=max(
                        weapon_prestige_progress(row, order),
                        level_cap_progress,
                    ),
                    locked=False,
                    lock_reason="Weapon prestige task available.",
                    recommended_mode=get_rule(rules, "recommended_mode", "default", "Stack weapon prestige with active camo tasks where possible"),
                    mode_reason="Weapon prestige should be stacked with camo or badge progress when possible.",
                    strategy=get_rule(rules, "strategy", "default", ""),
                    avoid=get_rule(rules, "avoid", "default", ""),
                )
            )

            break

    return tasks


# ---------------------------------------------------------------------------
# MASTERY BADGES
# ---------------------------------------------------------------------------

def badge_progress_from_columns(row: dict[str, Any], columns: list[str]) -> float:
    applicable = [column for column in columns if is_applicable(row.get(column))]

    if not applicable:
        return 100.0

    completed = sum(1 for column in applicable if is_true(row.get(column)))
    return (completed / len(applicable)) * 100


def count_weapon_badge_gold(
    rows: list[dict[str, Any]],
    weapon_class: str,
    mode_prefix: str,
) -> int:
    gold_column = f"{mode_prefix}_gold_complete"

    return sum(
        1
        for row in rows
        if clean(row.get("weapon_class", "")) == weapon_class and is_true(row.get(gold_column))
    )


def build_weapon_mastery_badge_tasks() -> list[dict[str, Any]]:
    path = CLEAN_FOLDER / "mastery_badges_weapons.csv"
    rows = load_csv_rows(path)
    tasks: list[dict[str, Any]] = []

    mode_configs = [
        {
            "prefix": "mp",
            "mode": "Multiplayer",
            "requirements": MP_WEAPON_BADGE_REQUIREMENTS,
            "challenge_label": "eliminations",
        },
        {
            "prefix": "zm",
            "mode": "Zombies",
            "requirements": ZM_WEAPON_BADGE_REQUIREMENTS,
            "challenge_label": "Zombie eliminations",
        },
    ]

    stages = ["bronze", "silver", "gold", "diamond"]

    for row in rows:
        weapon_class = clean(row.get("weapon_class", ""))
        weapon = clean(row.get("weapon", ""))

        if not weapon:
            continue

        for config in mode_configs:
            prefix = config["prefix"]
            mode = config["mode"]
            requirements = config["requirements"].get(weapon_class)

            if not requirements:
                continue

            bronze_req, silver_req, gold_req, diamond_req = requirements
            stage_requirements = {
                "bronze": bronze_req,
                "silver": silver_req,
                "gold": gold_req,
                "diamond": diamond_req,
            }

            columns = [f"{prefix}_{stage}_complete" for stage in stages]

            for stage in stages:
                column = f"{prefix}_{stage}_complete"
                value = row.get(column, "")

                if not is_applicable(value):
                    continue

                if is_true(value):
                    continue

                locked = False
                lock_reason = "Mastery badge task available."

                if stage == "diamond":
                    current_gold = count_weapon_badge_gold(rows, weapon_class, prefix)

                    if current_gold < diamond_req:
                        locked = True
                        lock_reason = f"Diamond locked: needs {diamond_req} Gold Mastery Badges for {weapon_class}. Current: {current_gold}/{diamond_req}."

                    challenge_text = f"Earn {diamond_req} Gold Mastery Badges for {weapon_class}."
                else:
                    target = stage_requirements[stage]
                    challenge_text = f"Get {target} {config['challenge_label']} with {weapon}."

                tasks.append(
                    make_task(
                        task_id=f"Mastery Badge:{mode}:{weapon}:{stage}",
                        task_type="mastery_badge_weapon",
                        mode=mode,
                        chain="Mastery Badges",
                        category="Weapon Mastery Badges",
                        weapon_class=weapon_class,
                        weapon=weapon,
                        camo=f"{mode} {stage.title()} Mastery Badge",
                        challenge_text=challenge_text,
                        progress=badge_progress_from_columns(row, columns),
                        locked=locked,
                        lock_reason=lock_reason,
                    )
                )

                break

    return tasks


def build_equipment_mastery_badge_tasks() -> list[dict[str, Any]]:
    files = [
        CLEAN_FOLDER / "mastery_badges_equipment_mp.csv",
        CLEAN_FOLDER / "mastery_badges_equipment_zombies.csv",
    ]

    tasks: list[dict[str, Any]] = []

    for path in files:
        rows = load_csv_rows(path)

        gold_count_by_mode_category: dict[tuple[str, str], int] = {}
        for source_row in rows:
            mode_key = clean(source_row.get("mode", ""))
            category_key = clean(source_row.get("category", ""))
            if not mode_key or not category_key:
                continue

            key = (mode_key, category_key)
            gold_count_by_mode_category.setdefault(key, 0)
            if is_true(source_row.get("gold_complete", "")):
                gold_count_by_mode_category[key] += 1

        for row in rows:
            mode = clean(row.get("mode", ""))
            category = clean(row.get("category", ""))
            item = clean(row.get("item", ""))

            if not mode or not category or not item:
                continue

            stage_columns = {
                "bronze": "bronze_complete",
                "silver": "silver_complete",
                "gold": "gold_complete",
                "diamond": "diamond_complete",
            }

            for stage, column in stage_columns.items():
                value = row.get(column, "")

                if not is_applicable(value):
                    continue

                if is_true(value):
                    continue

                locked = False
                lock_reason = "Equipment mastery badge task available."

                if stage == "diamond":
                    required = safe_int(row.get("diamond_required", 0), 0)
                    current_gold = gold_count_by_mode_category.get((mode, category), 0)

                    if required > 0 and current_gold < required:
                        locked = True
                        lock_reason = (
                            f"Diamond locked: needs {required} Gold Mastery Badges "
                            f"for {category}. Current: {current_gold}/{required}."
                        )

                    challenge_text = (
                        f"Confirm {item} Diamond Mastery Badge once the {category} "
                        f"Gold gate is complete ({current_gold}/{required})."
                    )
                else:
                    required = clean(row.get(f"{stage}_required", ""))
                    challenge_text = f"Complete {item} {stage.title()} Mastery Badge requirement: {required}."

                tasks.append(
                    make_task(
                        task_id=f"Equipment Badge:{mode}:{category}:{item}:{stage}",
                        task_type="mastery_badge_equipment",
                        mode=mode,
                        chain="Mastery Badges",
                        category=f"{category} Mastery Badges",
                        weapon_class=category,
                        weapon=item,
                        camo=f"{stage.title()} Mastery Badge",
                        challenge_text=challenge_text,
                        progress=badge_progress_from_columns(row, list(stage_columns.values())),
                        locked=locked,
                        lock_reason=lock_reason,
                    )
                )

                break

    return tasks


# ---------------------------------------------------------------------------
# MISC CHALLENGES
# ---------------------------------------------------------------------------

def next_misc_tier(row: dict[str, Any]) -> tuple[str, str] | None:
    tier_columns = [
        ("tier1_complete", "tier1_target", "Tier 1"),
        ("tier2_complete", "tier2_target", "Tier 2"),
        ("tier3_complete", "tier3_target", "Tier 3"),
        ("tier4_complete", "tier4_target", "Tier 4"),
        ("tier5_complete", "tier5_target", "Tier 5"),
    ]

    for complete_column, target_column, label in tier_columns:
        value = row.get(complete_column, "")

        if not is_applicable(value):
            continue

        if is_true(value):
            continue

        return label, clean(row.get(target_column, ""))

    return None


def misc_progress(row: dict[str, Any]) -> float:
    columns = [
        "tier1_complete",
        "tier2_complete",
        "tier3_complete",
        "tier4_complete",
        "tier5_complete",
    ]

    applicable = [column for column in columns if is_applicable(row.get(column))]

    if not applicable:
        return 0.0 if not is_true(row.get("completed", "")) else 100.0

    completed = sum(1 for column in applicable if is_true(row.get(column)))
    return (completed / len(applicable)) * 100


def misc_priority_bonus(category: str) -> float:
    if category == "Dark Ops":
        return -20

    if category == "Prestige":
        return 30

    if category == "Maps":
        return 25

    if category == "Hardened":
        return 10

    return 0


def build_misc_challenge_tasks() -> list[dict[str, Any]]:
    paths = [
        CLEAN_FOLDER / "misc_challenges_mp.csv",
        CLEAN_FOLDER / "misc_challenges_zombies.csv",
    ]

    tasks: list[dict[str, Any]] = []

    for path in paths:
        rows = load_csv_rows(path)

        for row in rows:
            mode = clean(row.get("mode", ""))
            category = clean(row.get("category", ""))
            sub_category = clean(row.get("sub_category", ""))
            challenge = clean(row.get("challenge", ""))
            requirement = clean(row.get("requirement", ""))

            if not mode or not category or not challenge:
                continue

            if is_true(row.get("completed", "")):
                continue

            next_tier = next_misc_tier(row)

            if next_tier:
                tier_label, tier_target = next_tier
                stage_label = f"{tier_label} target {tier_target}".strip()
            else:
                stage_label = "Completion"

            task_type = "dark_ops" if category == "Dark Ops" else "misc_challenge"

            tasks.append(
                make_task(
                    task_id=f"Misc:{mode}:{category}:{sub_category}:{challenge}:{stage_label}",
                    task_type=task_type,
                    mode=mode,
                    chain="Misc Challenges",
                    category=category,
                    weapon_class=sub_category,
                    weapon=challenge,
                    camo=stage_label,
                    challenge_text=requirement,
                    progress=misc_progress(row),
                    locked=False,
                    lock_reason="Misc challenge available.",
                    recommended_mode=default_recommended_mode(mode, task_type, category),
                    mode_reason=f"{category} challenge selected from clean 100% database.",
                    strategy=default_strategy(mode, task_type, category),
                    avoid=default_avoid(mode, task_type, category),
                )
            )

    return tasks


# ---------------------------------------------------------------------------
# RETICLES
# ---------------------------------------------------------------------------

def reticle_progress(row: dict[str, Any]) -> float:
    columns = [
        "stage_20_complete",
        "stage_40_complete",
        "stage_60_complete",
        "stage_80_complete",
        "stage_100_complete",
    ]

    applicable = [column for column in columns if is_applicable(row.get(column))]

    if not applicable:
        return 100.0

    completed = sum(1 for column in applicable if is_true(row.get(column)))
    return (completed / len(applicable)) * 100


def build_reticle_tasks() -> list[dict[str, Any]]:
    path = CLEAN_FOLDER / "reticles.csv"
    rows = load_csv_rows(path)
    rules = load_rules(CLEAN_FOLDER / "reticles_rules.csv")
    tasks: list[dict[str, Any]] = []

    stages = [
        ("20", "stage_20_required", "stage_20_complete"),
        ("40", "stage_40_required", "stage_40_complete"),
        ("60", "stage_60_required", "stage_60_complete"),
        ("80", "stage_80_required", "stage_80_complete"),
        ("100", "stage_100_required", "stage_100_complete"),
    ]

    for row in rows:
        mode = clean(row.get("mode", ""))
        classification = clean(row.get("classification", ""))
        reticle = clean(row.get("reticle", ""))

        if not mode or not reticle:
            continue

        for stage_percent, required_column, complete_column in stages:
            value = row.get(complete_column, "")

            if not is_applicable(value):
                continue

            if is_true(value):
                continue

            required = clean(row.get(required_column, ""))

            if required.upper() in {"TRUE", "FALSE", "YES", "NO", ""}:
                required = stage_percent

            challenge_text = f"Get {required} eliminations while using {reticle} in {mode}."

            recommended_mode = get_rule(rules, "recommended_mode", mode, default_recommended_mode(mode, "reticle", "Reticles"))
            strategy = get_rule(rules, "strategy", mode, default_strategy(mode, "reticle", "Reticles"))
            avoid = get_rule(rules, "avoid", mode, default_avoid(mode, "reticle", "Reticles"))

            tasks.append(
                make_task(
                    task_id=f"Reticle:{mode}:{reticle}:{stage_percent}",
                    task_type="reticle",
                    mode=mode,
                    chain="Reticles",
                    category="Reticles",
                    weapon_class=classification,
                    weapon=reticle,
                    camo=f"{stage_percent}% Reticle Progress",
                    challenge_text=challenge_text,
                    progress=reticle_progress(row),
                    locked=False,
                    lock_reason="Reticle task available.",
                    recommended_mode=recommended_mode,
                    mode_reason=f"{recommended_mode} is recommended for reticle progress.",
                    strategy=strategy,
                    avoid=avoid,
                )
            )

            break

    return tasks


# ---------------------------------------------------------------------------
# LOADING / SUMMARIES
# ---------------------------------------------------------------------------


def build_calling_card_tasks() -> list[dict[str, Any]]:
    """
    Loads calling card challenges from four mode-specific CSVs.
    Same tier structure as misc_challenges.
    """
    files = [
        CLEAN_FOLDER / "calling_cards_sp.csv",
        CLEAN_FOLDER / "calling_cards_mp.csv",
        CLEAN_FOLDER / "calling_cards_zm.csv",
        CLEAN_FOLDER / "calling_cards_wz.csv",
    ]

    tasks: list[dict[str, Any]] = []

    for path in files:
        rows = load_csv_rows(path)

        for row in rows:
            mode = clean(row.get("mode", ""))
            category = clean(row.get("category", ""))
            sub_category = clean(row.get("sub_category", ""))
            challenge = clean(row.get("challenge", ""))
            requirement = clean(row.get("requirement", ""))

            if not mode or not challenge:
                continue
                
            if not counts_for_100_percent(row):
                continue

            if is_true(row.get("completed", "")):
                continue

            # Tier columns definition
            tier_columns = [
                ("tier1_complete", "tier1_target", "Tier 1"),
                ("tier2_complete", "tier2_target", "Tier 2"),
                ("tier3_complete", "tier3_target", "Tier 3"),
                ("tier4_complete", "tier4_target", "Tier 4"),
                ("tier5_complete", "tier5_target", "Tier 5"),
            ]

            # Treat as complete if all applicable tiers are done,
            # even if the completed column was not set correctly in the CSV
            applicable_tiers = [
                c for c, target, _ in tier_columns
                if is_applicable(row.get(c, ""))
                and is_applicable(row.get(target, ""))
            ]
            if applicable_tiers and all(is_true(row.get(c, "")) for c in applicable_tiers):
                continue

            next_tier_label = "Completion"
            next_tier_target = ""

            for complete_col, target_col, label in tier_columns:
                val = row.get(complete_col, "")
                if not is_applicable(val) or not is_applicable(row.get(target_col, "")):
                    continue
                if not is_true(val):
                    next_tier_label = label
                    next_tier_target = clean(row.get(target_col, ""))
                    break

            stage_label = f"{next_tier_label} — target: {next_tier_target}".strip(" —")

            # Progress
            applicable = [
                c for c, target, _ in tier_columns
                if is_applicable(row.get(c, ""))
                and is_applicable(row.get(target, ""))
            ]
            completed_count = sum(
                1 for c in applicable if is_true(row.get(c, ""))
            )
            progress = (completed_count / len(applicable) * 100) if applicable else 0.0

            task_type = "dark_ops" if category == "Dark Ops" else "calling_card"

            tasks.append(
                make_task(
                    task_id=f"Card:{mode}:{category}:{sub_category}:{challenge}:{next_tier_label}",
                    task_type=task_type,
                    mode=mode,
                    chain="Calling Cards",
                    category=category,
                    weapon_class=sub_category,
                    weapon=challenge,
                    camo=stage_label,
                    challenge_text=requirement,
                    progress=progress,
                    locked=False,
                    lock_reason="Calling card task available.",
                    recommended_mode=default_recommended_mode(mode, task_type, category),
                    mode_reason=f"{category} calling card challenge selected.",
                    strategy=default_strategy(mode, task_type, category),
                    avoid=default_avoid(mode, task_type, category),
                )
            )

    return tasks


def build_title_tasks() -> list[dict[str, Any]]:
    """
    Loads title unlock challenges from titles.csv.
    Each title is a single completion — earned TRUE/FALSE.
    """
    path = CLEAN_FOLDER / "titles.csv"
    rows = load_csv_rows(path)
    tasks: list[dict[str, Any]] = []

    for row in rows:
        mode = clean(row.get("mode", "General"))
        title = clean(row.get("title", ""))
        earned = row.get("earned", "")
        criteria = clean(row.get("criteria", ""))

        if not title:
            continue

        if is_true(earned):
            continue

        if not is_applicable(earned):
            continue

        # Map mode label to Commander mode
        mode_map = {
            "General": "Global Cleanup",
            "Co-Op Campaign & Endgame": "Co-Op / Endgame",
            "Multiplayer": "Multiplayer",
            "Zombies": "Zombies",
            "Warzone": "Warzone",
        }
        commander_mode = mode_map.get(mode, "Global Cleanup")

        tasks.append(
            make_task(
                task_id=f"Title:{mode}:{title}",
                task_type="title",
                mode=commander_mode,
                chain="Titles",
                category="Titles",
                weapon_class=mode,
                weapon=title,
                camo="Earn Title",
                challenge_text=criteria,
                progress=0.0,
                locked=False,
                lock_reason="Title available to unlock.",
                recommended_mode=default_recommended_mode(commander_mode, "title", "Titles"),
                mode_reason=f"Title unlock requires: {criteria}",
                strategy=default_strategy(commander_mode, "title", "Titles"),
                avoid=default_avoid(commander_mode, "title", "Titles"),
            )
        )

    return tasks


def build_zombies_reward_tasks() -> list[dict[str, Any]]:
    path = CLEAN_FOLDER / "rewards_zombies.csv"
    rows = load_csv_rows(path)
    tasks: list[dict[str, Any]] = []

    for row in rows:
        map_name = clean(row.get("map", ""))
        category = clean(row.get("category", ""))
        item = clean(row.get("item", ""))

        if not map_name or not item:
            continue

        if is_true(row.get("earned", "")):
            continue

        tasks.append(
            make_task(
                task_id=f"Zombies Reward:{map_name}:{category}:{item}",
                task_type="zombies_reward",
                mode="Zombies",
                chain="Rewards",
                category=category or "Zombies Rewards",
                weapon_class=map_name,
                weapon=item,
                camo=category or "Reward",
                challenge_text=f"Earn {item} on {map_name}." + (f" Category: {category}." if category else ""),
                progress=0.0,
                locked=False,
                lock_reason="Zombies reward available.",
                recommended_mode=f"Play {map_name} and route directly towards this reward.",
                mode_reason="Zombies reward contributes to 100% completion outside weapon camos.",
                strategy="Prioritise the named reward objective, then stack camo, badge, reticle, and intel progress around it.",
                avoid="Avoid leaving the map or side-routing unless it helps this reward.",
            )
        )

    return tasks


def build_endgame_operation_tasks() -> list[dict[str, Any]]:
    path = CLEAN_FOLDER / "rewards_endgame_operations.csv"
    rows = load_csv_rows(path)
    tasks: list[dict[str, Any]] = []

    for row in rows:
        operation = clean(row.get("operation", ""))
        step = clean(row.get("step", ""))

        if not operation or not step:
            continue

        if is_true(row.get("earned", "")):
            continue

        tasks.append(
            make_task(
                task_id=f"Endgame Operation:{operation}:{step}",
                task_type="endgame_operation",
                mode="Co-Op / Endgame",
                chain="Endgame Operations",
                category=operation,
                weapon_class=operation,
                weapon=operation,
                camo=step,
                challenge_text=f"Complete {step} in {operation}.",
                progress=0.0,
                locked=False,
                lock_reason="Endgame operation step available.",
                recommended_mode="Endgame route that directly supports the selected operation step.",
                mode_reason="Operation steps are dedicated Endgame completion and should not be buried under Genesis camos.",
                strategy="Start the operation step first. Pick a Genesis-capable weapon only as secondary stacked progress.",
                avoid="Avoid free-roam camo grinding if the operation step can be advanced instead.",
            )
        )

    return tasks


def build_endgame_unlock_tasks() -> list[dict[str, Any]]:
    path = CLEAN_FOLDER / "rewards_endgame_unlocks.csv"
    rows = load_csv_rows(path)
    tasks: list[dict[str, Any]] = []

    for row in rows:
        category = clean(row.get("category", ""))
        operator = clean(row.get("operator", ""))
        item_type = clean(row.get("item_type", ""))
        item = clean(row.get("item", ""))
        unlock_criteria = clean(row.get("unlock_criteria", ""))
        source = clean(row.get("source", ""))

        if not item:
            continue

        if is_true(row.get("earned", "")):
            continue

        label = f"{item_type}: {item}" if item_type else item
        context = " · ".join(part for part in [operator, source] if part)

        tasks.append(
            make_task(
                task_id=f"Endgame Unlock:{category}:{operator}:{item_type}:{item}",
                task_type="endgame_unlock",
                mode="Co-Op / Endgame",
                chain="Endgame Unlocks",
                category=category or "Endgame Unlocks",
                weapon_class=category or "Endgame Unlocks",
                weapon=item,
                camo=label,
                challenge_text=unlock_criteria or f"Unlock {item}." + (f" Source: {source}." if source else ""),
                raw_requirement=unlock_criteria,
                progress=0.0,
                locked=False,
                lock_reason="Endgame unlock available.",
                recommended_mode="Endgame route matching the unlock source.",
                mode_reason=f"Endgame unlock cleanup: {context}" if context else "Endgame unlock cleanup.",
                strategy="Route to the unlock source first, then stack weapon/camo progress only if it does not slow the objective.",
                avoid="Avoid unrelated Genesis camo grinding until this unlock route is attempted.",
            )
        )

    return tasks


def build_intel_tasks() -> list[dict[str, Any]]:
    path = CLEAN_FOLDER / "intel.csv"
    rows = load_csv_rows(path)
    tasks: list[dict[str, Any]] = []

    for row in rows:
        mode = clean(row.get("mode", ""))
        map_name = clean(row.get("map", ""))
        category = clean(row.get("category", ""))
        item = clean(row.get("item", ""))

        if not mode or not item:
            continue

        if is_true(row.get("found", "")):
            continue

        tasks.append(
            make_task(
                task_id=f"Intel:{mode}:{map_name}:{category}:{item}",
                task_type="intel",
                mode=mode,
                chain="Intel",
                category=category or "Intel",
                weapon_class=map_name or mode,
                weapon=item,
                camo=f"{category} Intel" if category else "Intel",
                challenge_text=f"Find {item}" + (f" on {map_name}" if map_name else "") + ".",
                progress=0.0,
                locked=False,
                lock_reason="Intel item available.",
                recommended_mode=default_recommended_mode(mode, "intel", "Intel"),
                mode_reason="Intel is a non-camo completion item and should be paired with the relevant map/activity.",
                strategy="Route to the intel location while stacking any compatible weapon progress.",
                avoid="Avoid ending the session without checking the intel pickup if you entered the required map/activity.",
            )
        )

    return tasks


def build_colour_tasks() -> list[dict[str, Any]]:
    path = CLEAN_FOLDER / "colours.csv"
    rows = load_csv_rows(path)
    tasks: list[dict[str, Any]] = []

    for row in rows:
        colour = clean(row.get("colour", ""))
        level_required = clean(row.get("level_required", ""))

        if not colour:
            continue

        if is_true(row.get("unlocked", "")):
            continue

        tasks.append(
            make_task(
                task_id=f"Colour:{colour}",
                task_type="colour",
                mode="Global Cleanup",
                chain="Colours",
                category="Colours",
                weapon_class="Account Level",
                weapon=colour,
                camo="Colour Unlock",
                challenge_text=f"Unlock {colour}" + (f" at account level {level_required}." if level_required else "."),
                progress=0.0,
                locked=False,
                lock_reason="Colour unlock available.",
                recommended_mode="Any efficient XP route.",
                mode_reason="Colour unlock is account-level cleanup.",
                strategy="Stack account XP with the current best completion route.",
                avoid="Avoid playing only for colour unless it is one session away.",
            )
        )

    return tasks


def build_augment_tasks() -> list[dict[str, Any]]:
    path = CLEAN_FOLDER / "augments_zombies.csv"
    rows = load_csv_rows(path)
    tasks: list[dict[str, Any]] = []
    order = [
        ("minor1", "Minor 1"),
        ("major1", "Major 1"),
        ("minor2", "Minor 2"),
        ("major2", "Major 2"),
        ("minor3", "Minor 3"),
        ("major3", "Major 3"),
        ("minor4", "Minor 4"),
        ("major4", "Major 4"),
        ("extra_slot", "Extra Slot"),
    ]

    for row in rows:
        category = clean(row.get("category", ""))
        item = clean(row.get("item", ""))

        if not item:
            continue

        applicable = [column for column, _ in order if is_applicable(row.get(column, ""))]
        completed = sum(1 for column in applicable if is_true(row.get(column, "")))
        progress = (completed / len(applicable)) * 100 if applicable else 100.0

        for column, label in order:
            if column not in row:
                continue

            if not is_applicable(row.get(column, "")) or is_true(row.get(column, "")):
                continue

            tasks.append(
                make_task(
                    task_id=f"Augment:{category}:{item}:{column}",
                    task_type="augment",
                    mode="Zombies",
                    chain="Augments",
                    category=category or "Augments",
                    weapon_class=category or "Augments",
                    weapon=item,
                    camo=label,
                    challenge_text=f"Unlock {label} augment progress for {item}.",
                    progress=progress,
                    locked=False,
                    lock_reason="Zombies augment progress available.",
                    recommended_mode="Zombies XP route with high round speed.",
                    mode_reason="Augments are Zombies completion and stack naturally with camo/badge work.",
                    strategy="Use Zombies progression efficiently while doing another Zombies objective.",
                    avoid="Avoid low-density setup loops that do not produce augment XP.",
                )
            )
            break

    return tasks


def build_overclock_tasks() -> list[dict[str, Any]]:
    path = CLEAN_FOLDER / "overclocks_mp.csv"
    rows = load_csv_rows(path)
    tasks: list[dict[str, Any]] = []
    order = [("oc1_complete", "Overclock 1"), ("oc2_complete", "Overclock 2")]

    for row in rows:
        mode = clean(row.get("mode", "Multiplayer")) or "Multiplayer"
        category = clean(row.get("category", ""))
        item = clean(row.get("item", ""))

        if not item:
            continue

        applicable = [column for column, _ in order if is_applicable(row.get(column, ""))]
        completed = sum(1 for column in applicable if is_true(row.get(column, "")))
        progress = (completed / len(applicable)) * 100 if applicable else 100.0

        for column, label in order:
            if column not in row:
                continue

            if not is_applicable(row.get(column, "")) or is_true(row.get(column, "")):
                continue

            tasks.append(
                make_task(
                    task_id=f"Overclock:{mode}:{category}:{item}:{column}",
                    task_type="overclock",
                    mode=mode,
                    chain="Overclocks",
                    category=category or "Overclocks",
                    weapon_class=category or "Overclocks",
                    weapon=item,
                    camo=label,
                    challenge_text=f"Unlock {label} for {item}.",
                    progress=progress,
                    locked=False,
                    lock_reason="Overclock progress available.",
                    recommended_mode=default_recommended_mode(mode, "overclock", category or "Overclocks"),
                    mode_reason="Overclocks are Multiplayer completion and can stack with camo/calling-card work.",
                    strategy="Equip or use the relevant item while progressing a Multiplayer route.",
                    avoid="Avoid playlists that do not let you use this item consistently.",
                )
            )
            break

    return tasks

def load_tracker_tasks() -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []

    if not CLEAN_FOLDER.exists():
        return tasks

    for path in sorted(CLEAN_FOLDER.glob("*_status.csv")):
        tasks.extend(build_camo_tasks_from_status_file(path))

    tasks.extend(build_weapon_prestige_tasks())
    tasks.extend(build_weapon_mastery_badge_tasks())
    tasks.extend(build_equipment_mastery_badge_tasks())
    tasks.extend(build_misc_challenge_tasks())
    tasks.extend(build_reticle_tasks())
    tasks.extend(build_calling_card_tasks())
    tasks.extend(build_title_tasks())
    tasks.extend(build_zombies_reward_tasks())
    tasks.extend(build_endgame_operation_tasks())
    tasks.extend(build_endgame_unlock_tasks())
    tasks.extend(build_intel_tasks())
    tasks.extend(build_colour_tasks())
    tasks.extend(build_augment_tasks())
    tasks.extend(build_overclock_tasks())

    return tasks


def load_hub_progress() -> dict[str, float]:
    tasks = load_tracker_tasks()
    available = len(get_available_tasks(tasks))
    locked = len(get_locked_tasks(tasks))

    by_chain: dict[str, list[dict[str, Any]]] = {}

    for task in tasks:
        chain = task.get("chain", "Unknown")
        by_chain.setdefault(chain, []).append(task)

    progress: dict[str, float] = {
        "Available tasks": float(available),
        "Locked tasks": float(locked),
        "Loaded task groups": float(len(by_chain)),
    }

    for chain, chain_tasks in by_chain.items():
        if not chain_tasks:
            continue

        average_progress = sum(task.get("weapon_progress", 0.0) for task in chain_tasks) / len(chain_tasks)
        progress[chain] = round(average_progress, 2)

    return progress


def get_available_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        task
        for task in tasks
        if not task.get("locked", False)
        and not task.get("completed_on_session", False)
        and task.get("last_result") != "Camo completed"
    ]


def get_locked_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        task
        for task in tasks
        if task.get("locked", False)
        and not task.get("completed_on_session", False)
        and task.get("last_result") != "Camo completed"
    ]


def summarise_tasks(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(tasks)
    available = len(get_available_tasks(tasks))
    locked = len(get_locked_tasks(tasks))
    completed_or_hidden = total - available - locked

    by_mode: dict[str, int] = {}
    by_type: dict[str, int] = {}

    for task in get_available_tasks(tasks):
        by_mode[task["mode"]] = by_mode.get(task["mode"], 0) + 1
        by_type[task["task_type"]] = by_type.get(task["task_type"], 0) + 1

    return {
        "total": total,
        "available": available,
        "locked": locked,
        "completed": completed_or_hidden,
        "completion_rate": round((completed_or_hidden / total) * 100, 2) if total else 0,
        "by_mode": by_mode,
        "by_type": by_type,
    }


# ---------------------------------------------------------------------------
# SCORING / SELECTION
# ---------------------------------------------------------------------------

def task_type_bonus(task: dict[str, Any], session_goal: str) -> float:
    task_type = task.get("task_type", "")
    category = task.get("category", "")

    if session_goal == "Fast dopamine / recordable progress":
        if task_type == "camo":
            return 40
        if task_type == "mastery_badge_weapon":
            return 10
        if task_type == "reticle":
            return -30
        if task_type == "weapon_prestige":
            return -30
        if task_type == "dark_ops":
            return -80
        if task_type == "calling_card":
            return -20
        if task_type == "title":
            return -40


    if session_goal == "Attack biggest bottleneck":
        if task_type == "camo":
            return 40  # Camos drive all mastery gates — always the bottleneck
        if task_type == "mastery_badge_weapon":
            return 15  # Secondary contribution to 100%
        if task_type == "weapon_prestige":
            return -50  # Prestige unlocks nothing downstream — never a bottleneck
        if task_type in {"misc_challenge", "dark_ops"}:
            return -20
        if task_type in {"reticle", "mastery_badge_equipment"}:
            return -30

    if session_goal == "Pain session":
        if task_type in {"misc_challenge", "dark_ops"}:
            return 50
        if task.get("mode") == "Zombies":
            return 30

    if session_goal == "Content-first chaos":
        if task_type == "dark_ops":
            return 90
        if category in {"Prestige", "Maps"}:
            return 60

    return 0

def unlock_leverage_bonus(task: dict[str, Any]) -> float:
    """
    Rewards tasks that are likely to open another completion door.

    v1 uses only task metadata already available on the task object, so it is
    safe and does not need extra CSV reads.
    """
    task_type = task.get("task_type", "")
    category = task.get("category", "")
    camo = task.get("camo", "")
    challenge = task.get("challenge_text", "")
    progress = float(task.get("weapon_progress", 0.0))

    text = f"{camo} {challenge} {category}".lower()

    bonus = 0.0

    # Final military/special work unlocks the next camo gate for that weapon.
    if task_type == "camo":
        if "final military" in text:
            bonus += 45

        if "final special" in text:
            bonus += 55

        # Mastery camos are route-critical for class/global completion.
        if any(name in text for name in [
            "golden damascus",
            "starglass",
            "absolute zero",
            "apocalypse",
            "moonstone",
            "arclight",
            "doomsteel",
            "infestation",
            "solace",
            "soulfire",
            "soulsteel",
            "genesis",
        ]):
            bonus += 35

        if progress >= 85:
            bonus += 30
        elif progress >= 70:
            bonus += 15

    # Gold badge tasks move towards Diamond group unlocks.
    if task_type in {"mastery_badge_weapon", "mastery_badge_equipment"}:
        if "gold" in text:
            bonus += 45
        if "diamond" in text:
            bonus += 60
        if progress >= 66:
            bonus += 20

    # WPM and high-level prestige work matters, but should not drown out camos.
    if task_type == "weapon_prestige":
        if "wpm" in text or "weapon prestige master" in text:
            bonus += 30
        if any(level in text for level in ["level 100", "level 150", "level 200", "level 250"]):
            bonus += 20

    # Counted calling cards and mode 100-percenters should be meaningful.
    if task_type in {"calling_card", "dark_ops"}:
        if "100 percenter" in text:
            bonus += 80
        if "master" in text:
            bonus += 50
        if progress >= 80:
            bonus += 25

    return bonus


def task_search_text(task: dict[str, Any]) -> str:
    return " ".join(
        clean(task.get(key, ""))
        for key in [
            "mode",
            "task_type",
            "chain",
            "category",
            "weapon_class",
            "weapon",
            "camo",
            "challenge_text",
        ]
    ).lower()



def is_camo_like_task(task: dict[str, Any]) -> bool:
    return task.get("task_type", "") in {"camo", "weapon_prestige"}


def is_non_camo_completion_task(task: dict[str, Any]) -> bool:
    task_type = task.get("task_type", "")
    text = task_search_text(task)

    if task_type in {
        "calling_card",
        "dark_ops",
        "mastery_badge_weapon",
        "mastery_badge_equipment",
        "reticle",
        "title",
        "colour",
        "augment",
        "overclock",
        "reward",
        "zombies_reward",
        "endgame_operation",
        "endgame_unlock",
        "intel",
        "misc_challenge",
    }:
        return True

    return any(term in text for term in [
        "operation",
        "mission",
        "reward",
        "unlock",
        "intel",
        "calling card",
        "map",
        "kowakujō",
        "kowakujo",
        "king killer",
        "main quest",
        "dark ops",
        "title",
        "colour",
        "color",
        "augment",
        "overclock",
    ])


def collection_matches_task(task: dict[str, Any], anchor_collection: str) -> bool:
    task_type = task.get("task_type", "")
    text = task_search_text(task)

    if not anchor_collection or anchor_collection == "Any stackable progress":
        return True

    if anchor_collection == "Camos":
        return task_type == "camo"

    if anchor_collection == "Weapon Mastery Badges":
        return task_type == "mastery_badge_weapon"

    if anchor_collection == "Equipment Mastery Badges":
        return task_type == "mastery_badge_equipment"

    if anchor_collection == "Reticles":
        return task_type == "reticle"

    if anchor_collection == "Calling Cards":
        return task_type in {"calling_card", "dark_ops"}

    if anchor_collection == "Weapon Prestige":
        return task_type == "weapon_prestige"

    return False


def focus_target_bonus(task: dict[str, Any], focus_targets: list[str] | None) -> float:
    if not focus_targets:
        return 0.0

    task_type = task.get("task_type", "")
    weapon_class = clean(task.get("weapon_class", ""))
    category = clean(task.get("category", ""))
    text = task_search_text(task)

    bonus = 0.0

    for focus in focus_targets:
        if focus == "Launchers":
            if weapon_class == "Launchers" or "launcher" in text:
                bonus += 140
            elif task_type in {"camo", "mastery_badge_weapon"} and "launch" in text:
                bonus += 90

        elif focus == "Pistols":
            if weapon_class == "Pistols" or "pistol" in text or "handgun" in text:
                bonus += 140
            elif task_type in {"camo", "mastery_badge_weapon"} and "pistol" in text:
                bonus += 90

        elif focus == "Scorestreaks":
            if weapon_class == "Scorestreaks" or category == "Scorestreaks" or "scorestreak" in text or "streak" in text:
                bonus += 140
            elif task_type == "mastery_badge_equipment":
                bonus += 60

        elif focus == "Specials":
            if weapon_class == "Specials" or "special" in text:
                bonus += 120

        elif focus == "Melee":
            if weapon_class == "Melee" or "melee" in text:
                bonus += 120

        elif focus == "Camos" and task_type == "camo":
            bonus += 80

        elif focus == "Weapon Mastery Badges" and task_type == "mastery_badge_weapon":
            bonus += 100

        elif focus == "Equipment Mastery Badges" and task_type == "mastery_badge_equipment":
            bonus += 100

        elif focus == "Reticles" and task_type == "reticle":
            bonus += 80

        elif focus == "Calling Cards" and task_type in {"calling_card", "dark_ops"}:
            bonus += 80

        elif focus == "Weapon Prestige" and task_type == "weapon_prestige":
            bonus += 80

    return bonus


def guided_start_bonus(
    task: dict[str, Any],
    commander_mode: str = "Optimise my grind",
    anchor_weapon: str = "",
    anchor_class: str = "",
    anchor_collection: str = "",
) -> float:
    if commander_mode not in {"Start from my itch", "Class cleanup"}:
        return 0.0

    weapon = clean(task.get("weapon", ""))
    weapon_class = clean(task.get("weapon_class", ""))
    text = task_search_text(task)
    bonus = 0.0

    if anchor_weapon and weapon == anchor_weapon:
        bonus += 520

    if anchor_weapon and anchor_weapon.lower() in text:
        bonus += 220

    if anchor_class and weapon_class == anchor_class:
        bonus += 330

    if anchor_class and anchor_class.lower() in text:
        bonus += 160

    if anchor_collection and anchor_collection != "Any stackable progress":
        if collection_matches_task(task, anchor_collection):
            bonus += 180
        else:
            bonus -= 25

    if commander_mode == "Class cleanup" and anchor_class and weapon_class == anchor_class:
        bonus += 220

    return bonus


def closest_finish_bonus(
    task: dict[str, Any],
    commander_mode: str = "Optimise my grind",
    minimum_closeness: int = 80,
) -> float:
    if commander_mode != "Closest finishes":
        return 0.0

    progress = float(task.get("weapon_progress", 0.0))
    text = task_search_text(task)

    if progress < float(minimum_closeness):
        return -90 + (progress * 0.25)

    bonus = progress * 3.0

    if progress >= 95:
        bonus += 260
    elif progress >= 90:
        bonus += 220
    elif progress >= 80:
        bonus += 160
    elif progress >= 70:
        bonus += 100

    final_terms = [
        "final",
        "tier 5",
        "100%",
        "stage 100",
        "diamond",
        "apocalypse",
        "singularity",
        "infestation",
        "genesis",
        "level 250",
        "master",
        "100 percenter",
    ]

    if any(term in text for term in final_terms):
        bonus += 90

    return bonus


def task_meets_closeness(task: dict[str, Any], minimum_closeness: int) -> bool:
    progress = float(task.get("weapon_progress", 0.0))
    text = task_search_text(task)

    if progress >= float(minimum_closeness):
        return True

    one_step_terms = [
        "final",
        "tier 5",
        "stage 100",
        "diamond",
        "level 250",
        "100 percenter",
        "master",
    ]

    return any(term in text for term in one_step_terms)


def guided_anchor_filter(
    mode_tasks: list[dict[str, Any]],
    *,
    commander_mode: str,
    preferred_mode: str,
    anchor_weapon: str = "",
    anchor_class: str = "",
    anchor_collection: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Start from my itch should behave like a route anchor, not a tiny score bonus.

    Order:
    1. Exact selected weapon/item + selected collection.
    2. Selected class/category + selected collection.
    3. Selected collection in the chosen mode.
    4. No route, with an explanation, rather than drifting to unrelated work.
    """
    if commander_mode not in {"Start from my itch", "Class cleanup"}:
        return mode_tasks, []

    anchor_weapon = clean(anchor_weapon)
    anchor_class = clean(anchor_class)
    anchor_collection = clean(anchor_collection)
    has_collection_filter = bool(anchor_collection and anchor_collection != "Any stackable progress")

    notes: list[str] = []

    def weapon_matches(task: dict[str, Any]) -> bool:
        if not anchor_weapon:
            return False

        weapon = clean(task.get("weapon", ""))
        text = task_search_text(task)

        return weapon == anchor_weapon or anchor_weapon.lower() in text

    def class_matches(task: dict[str, Any]) -> bool:
        if not anchor_class:
            return False

        weapon_class = clean(task.get("weapon_class", ""))
        category = clean(task.get("category", ""))
        chain = clean(task.get("chain", ""))
        text = task_search_text(task)
        anchor = anchor_class.lower()

        return (
            weapon_class == anchor_class
            or category == anchor_class
            or chain == anchor_class
            or anchor in text
        )

    def collection_filter(candidate_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not has_collection_filter:
            return candidate_tasks

        return [
            task for task in candidate_tasks
            if collection_matches_task(task, anchor_collection)
        ]

    if anchor_weapon:
        weapon_tasks = [task for task in mode_tasks if weapon_matches(task)]

        if weapon_tasks:
            weapon_collection_tasks = collection_filter(weapon_tasks)

            if weapon_collection_tasks:
                notes.append(
                    f"Guided start locked onto {anchor_weapon}"
                    + (f" · {anchor_collection}." if has_collection_filter else ".")
                )
                return weapon_collection_tasks, notes

            notes.append(
                f"{anchor_weapon} has active {preferred_mode} tasks, but none for "
                f"{anchor_collection}. Treating that weapon/collection as done or unavailable."
            )
        else:
            notes.append(
                f"No active {preferred_mode} tasks found for {anchor_weapon}. "
                "It may already be done for this mode, locked, or not present in the selected collection."
            )

    if anchor_class:
        class_tasks = [task for task in mode_tasks if class_matches(task)]

        if class_tasks:
            class_collection_tasks = collection_filter(class_tasks)

            if class_collection_tasks:
                fallback = " Falling back to the selected class/category." if anchor_weapon else ""
                notes.append(
                    f"Guided start locked onto {anchor_class}"
                    + (f" · {anchor_collection}." if has_collection_filter else ".")
                    + fallback
                )
                return class_collection_tasks, notes

            notes.append(
                f"{anchor_class} has active {preferred_mode} tasks, but none for "
                f"{anchor_collection}. Treating that class/collection as done or unavailable."
            )
        else:
            notes.append(
                f"No active {preferred_mode} tasks found for {anchor_class}. "
                "It may already be done, locked, or not present in this mode."
            )

    if has_collection_filter:
        collection_tasks = collection_filter(mode_tasks)

        if collection_tasks:
            notes.append(
                f"Falling back to available {anchor_collection} tasks in {preferred_mode}."
            )
            return collection_tasks, notes

    notes.append(
        "Guided start found no matching active tasks, so no unrelated fallback route was generated."
    )
    return [], notes



def completion_stack_bonus(
    task: dict[str, Any],
    commander_mode: str = "Optimise my grind",
    anchor_collection: str = "",
) -> float:
    if commander_mode != "Completion stack":
        return 0.0

    task_type = task.get("task_type", "")
    text = task_search_text(task)
    bonus = 0.0

    if collection_matches_task(task, anchor_collection):
        bonus += 180

    if is_non_camo_completion_task(task):
        bonus += 160

    if any(term in text for term in [
        "operation",
        "mission",
        "act iv",
        "king killer",
        "step",
        "main quest",
        "map",
        "kowakujō",
        "kowakujo",
        "reward",
        "unlock",
        "intel",
    ]):
        bonus += 140

    if task_type in {"calling_card", "dark_ops"}:
        bonus += 120

    if task_type in {
        "reward",
        "zombies_reward",
        "endgame_operation",
        "endgame_unlock",
        "intel",
        "title",
        "colour",
        "augment",
        "overclock",
    }:
        bonus += 120

    if task_type == "camo":
        bonus -= 70

    if task_type == "weapon_prestige":
        bonus -= 50

    return bonus


def score_task(
    task: dict[str, Any],
    preferred_mode: str,
    avoided_mode: str,
    session_goal: str,
    motivation: str,
    commander_mode: str = "Optimise my grind",
    focus_targets: list[str] | None = None,
    anchor_weapon: str = "",
    anchor_class: str = "",
    anchor_collection: str = "",
    minimum_closeness: int = 80,
) -> float:
    if task.get("locked", False):
        return -999999

    score = 0.0
    mode = task.get("mode", "")
    task_type = task.get("task_type", "")
    progress = float(task.get("weapon_progress", 0.0))

    # --- MODE SCORING ---
    if preferred_mode == "Global Cleanup":
        # Open to everything — no task type gets a mode bonus here.
        # Let session goal scoring do all the work.
        score += 20
    elif mode == preferred_mode:
        score += 200

    if avoided_mode != "Global Cleanup" and mode == avoided_mode:
        score -= 200

    # --- SESSION GOAL SCORING ---
    if session_goal == "Fast dopamine / recordable progress":
        if task_type == "camo":
            score += progress * 2.2
            if progress >= 80:
                score += 70
        elif task_type == "mastery_badge_weapon":
            score += progress * 1.0
        else:
            score += progress * 0.2

    elif session_goal == "Attack biggest bottleneck":
        # Bottleneck = task closest to unlocking a mastery milestone.
        # High-progress camos unlock class gates and global gates.
        # Prestige and reticles unlock nothing downstream.
        if task_type == "weapon_prestige":
            score -= 60
        elif task_type in {"reticle", "mastery_badge_equipment"}:
            score -= 20
        elif progress >= 80:
            score += 90   # Near milestone — push it over the line
        elif progress >= 50:
            score += 60   # Mid-chain with meaningful gate leverage
        elif progress > 0:
            score += 30   # In progress but early
        else:
            score += 5    # Brand new weapon — not a bottleneck yet

    elif session_goal == "Pain session":
        score += 100 - progress

    elif session_goal == "Content-first chaos":
        score += 50 + task_type_bonus(task, session_goal)

    else:
        score += 50 + min(progress, 75)

    score += task_type_bonus(task, session_goal)

    # --- MOTIVATION MODIFIER ---
    if motivation in {"Barely functioning", "Low"}:
        if progress >= 70:
            score += 30
        if task_type == "dark_ops":
            score -= 100
        if mode == "Zombies":
            score -= 40
        if mode == "Warzone":
            score += 30

    # Prestige stacking bonus only applies during balanced or pain sessions.
    # Never during bottleneck or fast dopamine — it muddies the signal.
    if task_type == "weapon_prestige" and session_goal not in {
        "Attack biggest bottleneck",
        "Fast dopamine / recordable progress",
    }:
        score += 10

    if task.get("category") == "Reticles":
        score -= 10

    score += unlock_leverage_bonus(task)
    score += focus_target_bonus(task, focus_targets)
    score += guided_start_bonus(
        task=task,
        commander_mode=commander_mode,
        anchor_weapon=anchor_weapon,
        anchor_class=anchor_class,
        anchor_collection=anchor_collection,
    )
    score += closest_finish_bonus(
        task=task,
        commander_mode=commander_mode,
        minimum_closeness=minimum_closeness,
    )
    score += completion_stack_bonus(
        task=task,
        commander_mode=commander_mode,
        anchor_collection=anchor_collection,
    )

    return score

def select_next_task(
    tasks: list[dict[str, Any]],
    preferred_mode: str,
    avoided_mode: str,
    session_goal: str,
    motivation: str,
    commander_mode: str = "Optimise my grind",
    focus_targets: list[str] | None = None,
    anchor_weapon: str = "",
    anchor_class: str = "",
    anchor_collection: str = "",
    minimum_closeness: int = 80,
) -> dict[str, Any] | None:
    available_tasks = get_available_tasks(tasks)

    if not available_tasks:
        return None

    return sorted(
        available_tasks,
        key=lambda task: score_task(
            task=task,
            preferred_mode=preferred_mode,
            avoided_mode=avoided_mode,
            session_goal=session_goal,
            motivation=motivation,
            commander_mode=commander_mode,
            focus_targets=focus_targets,
            anchor_weapon=anchor_weapon,
            anchor_class=anchor_class,
            anchor_collection=anchor_collection,
            minimum_closeness=minimum_closeness,
        ),
        reverse=True,
    )[0]


def get_ranked_tasks(
    tasks: list[dict[str, Any]],
    preferred_mode: str,
    avoided_mode: str,
    session_goal: str,
    motivation: str,
    limit: int = 10,
    commander_mode: str = "Optimise my grind",
    focus_targets: list[str] | None = None,
    anchor_weapon: str = "",
    anchor_class: str = "",
    anchor_collection: str = "",
    minimum_closeness: int = 80,
) -> list[dict[str, Any]]:
    return sorted(
        get_available_tasks(tasks),
        key=lambda task: score_task(
            task=task,
            preferred_mode=preferred_mode,
            avoided_mode=avoided_mode,
            session_goal=session_goal,
            motivation=motivation,
            commander_mode=commander_mode,
            focus_targets=focus_targets,
            anchor_weapon=anchor_weapon,
            anchor_class=anchor_class,
            anchor_collection=anchor_collection,
            minimum_closeness=minimum_closeness,
        ),
        reverse=True,
    )[:limit]


# ---------------------------------------------------------------------------
# MISSIONS / RESULTS / CHAT
# ---------------------------------------------------------------------------

def time_limit_for_session(available_minutes: int, energy: str) -> int:
    available_minutes = int(available_minutes)

    if energy == "Low":
        return min(available_minutes, 45)

    if energy == "Medium":
        return min(available_minutes, 90)

    if energy == "High":
        return min(available_minutes, 120)

    return min(available_minutes, 75)


def build_stop_explanation(stop: dict[str, Any]) -> list[str]:
    """Return compact, human-readable reasons for why a planner stop was chosen."""
    explanation: list[str] = []

    recommended_mode = clean(stop.get("recommended_mode", ""))
    if recommended_mode:
        explanation.append(f"Recommended mode: {recommended_mode}")

    mode_reason = clean(stop.get("mode_reason", ""))
    if mode_reason:
        explanation.append(f"Why this mode: {mode_reason}")

    strategy = clean(stop.get("strategy", ""))
    if strategy:
        explanation.append(f"Execution: {strategy}")

    progress = float(stop.get("weapon_progress", 0.0) or 0.0)
    if progress >= 80:
        explanation.append("Progress signal: this stop is already near-complete and is a strong finish point.")
    elif progress >= 40:
        explanation.append("Progress signal: this stop should feel rewarding now and keep momentum high.")
    else:
        explanation.append("Progress signal: this is a clean, low-friction objective for the current session.")

    stacking_hint = clean(stop.get("stacking_hint", ""))
    if stacking_hint:
        explanation.append(f"Stacking: {stacking_hint}")
    elif stop.get("companion_objectives"):
        companion_preview = ", ".join(str(item) for item in stop.get("companion_objectives", [])[:2])
        explanation.append(f"Stacking: {companion_preview}")

    return explanation


def build_recovery_suggestions(
    tasks: list[dict[str, Any]],
    current_stop: dict[str, Any],
    *,
    preferred_mode: str = "",
    avoided_mode: str = "",
    session_goal: str = "Balanced progress",
    motivation: str = "Decent",
    commander_mode: str = "Optimise my grind",
    focus_targets: list[str] | None = None,
    anchor_weapon: str = "",
    anchor_class: str = "",
    anchor_collection: str = "",
    minimum_closeness: int = 80,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return ranked alternatives when the active stop becomes blocked or skipped."""
    current_id = clean(current_stop.get("task_id", ""))
    remaining_tasks = [
        task
        for task in tasks
        if clean(task.get("task_id", "")) != current_id
    ]

    if not remaining_tasks:
        return []

    return get_ranked_tasks(
        remaining_tasks,
        preferred_mode,
        avoided_mode,
        session_goal,
        motivation,
        limit=limit,
        commander_mode=commander_mode,
        focus_targets=focus_targets,
        anchor_weapon=anchor_weapon,
        anchor_class=anchor_class,
        anchor_collection=anchor_collection,
        minimum_closeness=minimum_closeness,
    )


def build_recovery_plan(
    tasks: list[dict[str, Any]],
    current_stop: dict[str, Any],
    *,
    preferred_mode: str,
    avoided_mode: str,
    session_goal: str,
    motivation: str,
    remaining_minutes: int,
    commander_mode: str = "Optimise my grind",
    focus_targets: list[str] | None = None,
    anchor_weapon: str = "",
    anchor_class: str = "",
    anchor_collection: str = "",
    minimum_closeness: int = 80,
    completed_task_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Rebuild the session plan after a blocked or skipped stop so the commander adapts immediately."""
    completed = list(completed_task_ids or [])
    current_id = clean(current_stop.get("task_id", ""))
    if current_id and current_id not in completed:
        completed.append(current_id)

    return rebuild_plan_after_progress(
        tasks=tasks,
        preferred_mode=preferred_mode,
        session_goal=session_goal,
        motivation=motivation,
        completed_task_ids=completed,
        remaining_minutes=remaining_minutes,
        commander_mode=commander_mode,
        focus_targets=focus_targets,
        anchor_weapon=anchor_weapon,
        anchor_class=anchor_class,
        anchor_collection=anchor_collection,
        minimum_closeness=minimum_closeness,
        avoided_mode=avoided_mode,
    )


def generate_ai_commentary(task: dict[str, Any], motivation: str) -> str:
    task_type = task.get("task_type", "")
    mode = task.get("mode", "")
    progress = float(task.get("weapon_progress", 0.0))

    if task_type == "dark_ops":
        return "Dark Ops detected. This is not productivity. This is theatre."

    if progress >= 85:
        return "Near-complete target detected. Finish the visible win before requesting comfort."

    if task_type == "weapon_prestige":
        return "Weapon prestige selected. Stack it with camo progress where possible."

    if mode == "Multiplayer":
        return "Multiplayer bottleneck selected. The tracker has found pain with measurable value."

    if mode == "Zombies":
        return "Zombies route selected. Farm the requirement directly; do not wander."

    if mode == "Warzone":
        return "Warzone authorised. Dopamine and visible progress are acceptable today."

    if motivation in {"Barely functioning", "Low"}:
        return "Motivation is compromised. Assigning controlled progress instead of heroic fantasy."

    return "Mission selected. Human negotiation privileges revoked."

# ──────────────────────────────────────────────────────────────────────────────
# SESSION PLANNER
# ──────────────────────────────────────────────────────────────────────────────


def cluster_key(task: dict[str, Any]) -> str:
    """
    Returns the grouping key used to cluster a task with related tasks
    in the same session. Camo/prestige/mastery tasks cluster by weapon
    class. Calling cards and titles cluster by sub-category, since that's
    their natural grouping (e.g. "Mission Report", "Embrace the Nightmare").
    """
    task_type = task.get("task_type", "")

    if task_type in {
        "calling_card",
        "dark_ops",
        "title",
        "intel",
        "zombies_reward",
        "endgame_operation",
        "endgame_unlock",
        "colour",
        "augment",
        "overclock",
    }:
        sub = task.get("weapon_class", "") or task.get("category", "")
        return f"{task_type}:{sub}"

    weapon_class = task.get("weapon_class", "")
    return f"class:{weapon_class}" if weapon_class else f"other:{task_type}"


def cluster_label(task: dict[str, Any]) -> str:
    task_type = task.get("task_type", "")

    if task_type in {
        "calling_card",
        "dark_ops",
        "title",
        "intel",
        "zombies_reward",
        "endgame_operation",
        "endgame_unlock",
        "colour",
        "augment",
        "overclock",
    }:
        return task.get("weapon_class", "") or task.get("category", "Misc")

    return task.get("weapon_class", "Unclassified")


def build_clusters(
    tasks_in_mode: list[dict[str, Any]],
    preferred_mode: str = "",
    session_goal: str = "Balanced progress",
    motivation: str = "Decent",
    commander_mode: str = "Optimise my grind",
    focus_targets: list[str] | None = None,
    anchor_weapon: str = "",
    anchor_class: str = "",
    anchor_collection: str = "",
    minimum_closeness: int = 80,
) -> list[dict[str, Any]]:
    """
    Groups available tasks within a single mode into clusters using
    cluster_key().

    Cluster ranking now combines:
    - close-to-completion density
    - average progress
    - cluster size
    - Commander task score, so session_goal and motivation actually affect plans
    """
    groups: dict[str, list[dict[str, Any]]] = {}

    for task in tasks_in_mode:
        key = cluster_key(task)
        groups.setdefault(key, []).append(task)

    clusters: list[dict[str, Any]] = []

    for key, group_tasks in groups.items():
        scored_tasks = sorted(
            group_tasks,
            key=lambda task: score_task(
                task=task,
                preferred_mode=preferred_mode or task.get("mode", ""),
                avoided_mode="",
                session_goal=session_goal,
                motivation=motivation,
                commander_mode=commander_mode,
                focus_targets=focus_targets,
                anchor_weapon=anchor_weapon,
                anchor_class=anchor_class,
                anchor_collection=anchor_collection,
                minimum_closeness=minimum_closeness,
            ),
            reverse=True,
        )

        progress_values = [
            float(task.get("weapon_progress", 0.0))
            for task in scored_tasks
        ]

        close_count = sum(1 for value in progress_values if value >= 50)
        average_progress = (
            sum(progress_values) / len(progress_values)
            if progress_values
            else 0.0
        )

        average_commander_score = (
            sum(
                score_task(
                    task=task,
                    preferred_mode=preferred_mode or task.get("mode", ""),
                    avoided_mode="",
                    session_goal=session_goal,
                    motivation=motivation,
                    commander_mode=commander_mode,
                    focus_targets=focus_targets,
                    anchor_weapon=anchor_weapon,
                    anchor_class=anchor_class,
                    anchor_collection=anchor_collection,
                    minimum_closeness=minimum_closeness,
                )
                for task in scored_tasks
            ) / len(scored_tasks)
            if scored_tasks
            else 0.0
        )

        if commander_mode == "Completion stack":
            cluster_score = (
                close_count * 10
                + average_progress * 0.25
                + len(scored_tasks) * 3
                + average_commander_score * 1.0
            )
        else:
            cluster_score = (
                close_count * 100
                + average_progress
                + len(scored_tasks) * 2
                + average_commander_score * 0.35
            )

        clusters.append(
            {
                "key": key,
                "label": cluster_label(scored_tasks[0]) if scored_tasks else key,
                "tasks": scored_tasks,
                "close_count": close_count,
                "average_progress": round(average_progress, 2),
                "average_commander_score": round(average_commander_score, 2),
                "score": round(cluster_score, 2),
            }
        )

    return sorted(
        clusters,
        key=lambda cluster: cluster["score"],
        reverse=True,
    )

def stops_for_available_minutes(available_minutes: int) -> int:
    """
    Scales the number of plan stops to the time available, roughly
    one stop per 15 minutes, with a floor and ceiling so short
    sessions still get a real plan and long sessions don't turn
    into a full backlog dump.
    """
    raw = available_minutes // 15
    return max(3, min(raw, 12))

def build_route_summary(stops: list[dict[str, Any]], available_minutes: int) -> dict[str, Any]:
    """
    Summarises the generated session route in human terms.
    """
    if not stops:
        return {
            "primary_route": "No route generated",
            "estimated_minutes": 0,
            "available_minutes": available_minutes,
            "main_unlock_value": "No active stops.",
            "stacked_cleanup": "None.",
            "task_mix": {},
        }

    task_mix: dict[str, int] = {}
    cluster_mix: dict[str, int] = {}

    estimated_minutes = 0
    stacked_count = 0

    for stop in stops:
        task_type = stop.get("task_type", "unknown")
        cluster = stop.get("cluster_label", "Unclassified")

        task_mix[task_type] = task_mix.get(task_type, 0) + 1
        cluster_mix[cluster] = cluster_mix.get(cluster, 0) + 1

        estimated_minutes += int(stop.get("estimated_minutes", 0) or 0)

        if stop.get("stacking_hint"):
            stacked_count += 1

    primary_cluster = max(cluster_mix, key=cluster_mix.get)
    primary_task_type = max(task_mix, key=task_mix.get)

    task_type_labels = {
        "camo": "camo route",
        "reticle": "reticle cleanup",
        "weapon_prestige": "weapon prestige route",
        "mastery_badge_weapon": "weapon mastery badge route",
        "mastery_badge_equipment": "equipment mastery badge route",
        "calling_card": "calling-card route",
        "dark_ops": "Dark Ops route",
        "title": "title cleanup",
        "zombies_reward": "Zombies reward route",
        "endgame_operation": "Endgame operation route",
        "endgame_unlock": "Endgame unlock route",
        "intel": "intel cleanup",
        "colour": "colour cleanup",
        "augment": "augment route",
        "overclock": "overclock route",
    }

    primary_route = f"{primary_cluster} {task_type_labels.get(primary_task_type, primary_task_type)}"

    high_value_terms = [
        "doomsteel",
        "moonstone",
        "starglass",
        "arclight",
        "absolute zero",
        "apocalypse",
        "soulsteel",
        "genesis",
        "gold",
        "diamond",
        "100 percenter",
        "master",
    ]

    high_value_count = 0

    for stop in stops:
        text = f"{stop.get('camo', '')} {stop.get('challenge_text', '')}".lower()
        if any(term in text for term in high_value_terms):
            high_value_count += 1

    if high_value_count:
        main_unlock_value = f"{high_value_count} high-leverage unlock-focused stop(s)."
    else:
        main_unlock_value = "General cleanup progress."

    if stacked_count:
        stacked_cleanup = f"{stacked_count} stop(s) include stacking advice."
    else:
        stacked_cleanup = "No stacked cleanup detected."

    return {
        "primary_route": primary_route,
        "estimated_minutes": estimated_minutes,
        "available_minutes": available_minutes,
        "main_unlock_value": main_unlock_value,
        "stacked_cleanup": stacked_cleanup,
        "task_mix": task_mix,
    }

def build_plan_diagnostics(
    *,
    preferred_mode: str,
    mode_task_count: int,
    clusters: list[dict[str, Any]],
    stops: list[dict[str, Any]],
    max_stops: int,
    available_minutes: int,
    session_goal: str,
    motivation: str,
) -> dict[str, Any]:
    """
    Explains how strong the generated plan is.

    This does not change ranking yet. It tells the operator whether the plan
    is dense, thin, or compromised.
    """
    reasons: list[str] = []
    confidence_score = 0

    if mode_task_count >= max_stops * 2:
        confidence_score += 30
        reasons.append(f"{preferred_mode} has a deep task pool for this session.")
    elif mode_task_count >= max_stops:
        confidence_score += 20
        reasons.append(f"{preferred_mode} has enough available tasks for the requested time.")
    elif mode_task_count > 0:
        confidence_score += 10
        reasons.append(f"{preferred_mode} has limited available tasks, so the plan may be thin.")
    else:
        reasons.append(f"No available tasks found in {preferred_mode}.")

    if clusters:
        top_cluster = clusters[0]
        close_count = int(top_cluster.get("close_count", 0))
        average_progress = float(top_cluster.get("average_progress", 0))

        if close_count >= 3:
            confidence_score += 30
            reasons.append(
                f"Top cluster has {close_count} near-complete items, giving strong cleanup value."
            )
        elif close_count >= 1:
            confidence_score += 20
            reasons.append(
                f"Top cluster has {close_count} near-complete item, giving visible progress."
            )
        else:
            confidence_score += 10
            reasons.append(
                f"Top cluster average progress is {average_progress:.1f}%, but few items are close."
            )

        if len(clusters) >= 3:
            confidence_score += 20
            reasons.append("Multiple backup clusters are available if the route stalls.")
        elif len(clusters) >= 2:
            confidence_score += 10
            reasons.append("One backup cluster is available if the route stalls.")
        else:
            reasons.append("Only one useful cluster is available, so flexibility is low.")

    if len(stops) >= max_stops:
        confidence_score += 20
        reasons.append("Plan fully fills the requested session length.")
    elif stops:
        confidence_score += 10
        reasons.append("Plan has fewer stops than requested, likely due to limited task density.")

    if motivation in {"Barely functioning", "Low"}:
        reasons.append("Low motivation detected, plan should favour controlled visible progress.")

    if session_goal == "Attack biggest bottleneck":
        reasons.append("Goal is bottleneck attack, so high-leverage gated work should be prioritised.")
    elif session_goal == "Fast dopamine / recordable progress":
        reasons.append("Goal is fast dopamine, so near-complete visible wins should be prioritised.")

    if confidence_score >= 70:
        confidence = "High"
    elif confidence_score >= 40:
        confidence = "Medium"
    else:
        confidence = "Low"

    return {
        "confidence": confidence,
        "confidence_score": confidence_score,
        "rationale": reasons,
    }

def mode_major_collection_is_done(preferred_mode: str, tasks: list[dict[str, Any]]) -> bool:
    """
    Detects whether a mode's major completion routes are effectively done,
    leaving only low-leverage cleanup like reticles.

    v1 is intentionally task-based:
    - if the mode has camo, calling card, mastery badge, or title work left,
      the mode is not exhausted
    - if the only remaining mode tasks are reticles, prestige, or misc cleanup,
      treat it as exhausted for normal planning
    """
    major_task_types = {
        "camo",
        "calling_card",
        "dark_ops",
        "mastery_badge_weapon",
        "mastery_badge_equipment",
        "title",
    }

    mode_tasks = [
        task for task in get_available_tasks(tasks)
        if task.get("mode") == preferred_mode
    ]

    if not mode_tasks:
        return True

    return not any(
        task.get("task_type") in major_task_types
        for task in mode_tasks
    )

def estimate_task_minutes(task: dict[str, Any]) -> int:
    """
    Rough practical estimate for how long a stop is likely to take.

    v1 uses mode + task type + challenge text.
    Later this can be trained from session_log.csv.
    """
    mode = task.get("mode", "")
    task_type = task.get("task_type", "")
    camo = task.get("camo", "")
    challenge = task.get("challenge_text", "")

    text = f"{camo} {challenge}".lower()

    if mode == "Co-Op / Endgame":
        if task_type in {"endgame_operation", "endgame_unlock"}:
            return 45
        if task_type == "intel":
            return 25
        return 45

    if mode == "Zombies":
        if task_type in {"zombies_reward", "augment", "intel"}:
            return 35
        if "elite zombie" in text or "elite zombies" in text:
            return 45
        if task_type == "camo":
            return 35
        if task_type in {"mastery_badge_weapon", "mastery_badge_equipment"}:
            return 35
        if task_type == "calling_card":
            return 40
        if task_type == "reticle":
            return 30
        return 35

    if mode == "Multiplayer":
        if task_type == "overclock":
            return 25
        if task_type == "camo":
            return 25
        if task_type in {"mastery_badge_weapon", "mastery_badge_equipment"}:
            return 25
        if task_type == "reticle":
            return 25
        if task_type == "calling_card":
            return 30
        return 25

    if mode == "Warzone":
        if task_type == "camo":
            return 45
        if task_type == "reticle":
            return 45
        if task_type == "calling_card":
            return 60
        if task_type == "dark_ops":
            return 75
        return 45

    if task_type == "weapon_prestige":
        return 30

    if task_type in {"colour", "intel", "reward", "zombies_reward", "endgame_unlock", "endgame_operation", "augment", "overclock"}:
        return 30

    return 30

def build_weapon_prestige_hint(task: dict[str, Any], available_tasks: list[dict[str, Any]]) -> str:
    if task.get("task_type") != "weapon_prestige":
        return ""

    weapon = clean(task.get("weapon", ""))

    same_weapon_tasks = [
        candidate for candidate in available_tasks
        if clean(candidate.get("weapon", "")) == weapon
        and candidate.get("task_id") != task.get("task_id")
        and not candidate.get("locked", False)
        and candidate.get("task_type") in {
            "camo",
            "mastery_badge_weapon",
            "reticle",
            "calling_card",
            "dark_ops",
        }
    ]

    if same_weapon_tasks:
        same_weapon_tasks.sort(
            key=lambda candidate: (
                unlock_leverage_bonus(candidate),
                candidate.get("weapon_progress", 0),
            ),
            reverse=True,
        )

        best = same_weapon_tasks[0]

        return (
            f"Do not prestige in isolation. Play {best.get('mode', 'the best mode')} "
            f"and stack this with {best.get('camo', best.get('category', 'active progress'))}."
        )

    mode_priority = [
        "Zombies",
        "Multiplayer",
        "Warzone",
        "Co-Op / Endgame",
    ]

    mode_counts = {}

    for candidate in available_tasks:
        if candidate.get("locked", False):
            continue

        candidate_mode = candidate.get("mode", "")
        candidate_type = candidate.get("task_type", "")

        if candidate_mode not in mode_priority:
            continue

        if candidate_type not in {"camo", "reticle", "mastery_badge_weapon", "calling_card", "dark_ops"}:
            continue

        mode_counts[candidate_mode] = mode_counts.get(candidate_mode, 0) + 1

    if mode_counts:
        best_mode = max(
            mode_counts,
            key=lambda mode: (mode_counts[mode], -mode_priority.index(mode)),
        )

        return (
            f"Prestige route needs an anchor. Play {best_mode} and use {weapon} "
            f"while clearing active {best_mode} objectives. Do not level the weapon in isolation."
        )

    return (
        f"Pure prestige cleanup. Use {weapon} in the fastest XP mode available. "
        f"This is a low-stacking route."
    )


def build_stacking_hint(stop: dict[str, Any], available_tasks: list[dict[str, Any]]) -> str:
    """
    Gives practical stacking advice for tasks that should not be done in isolation.

    v1 covers:
    - Reticles: stack with camo, weapon prestige, or mastery badge work.
    - Weapon prestige: anchor to a playable mode and objective.
    """
    task_type = stop.get("task_type", "")

    if task_type == "reticle":
        return build_reticle_stacking_hint(stop, available_tasks)

    if task_type == "weapon_prestige":
        return build_weapon_prestige_stacking_hint(stop, available_tasks)

    return ""


def build_reticle_stacking_hint(stop: dict[str, Any], available_tasks: list[dict[str, Any]]) -> str:
    mode = stop.get("mode", "")

    stackable_types = {
        "camo",
        "weapon_prestige",
        "mastery_badge_weapon",
    }

    candidates = [
        task for task in available_tasks
        if task.get("mode") in {mode, "Global Cleanup"}
        and task.get("task_type") in stackable_types
        and not task.get("locked", False)
    ]

    if not candidates:
        return "Reticle cleanup only. No obvious weapon, camo, or prestige stack found."

    candidates = sorted(
        candidates,
        key=lambda task: (
            unlock_leverage_bonus(task),
            float(task.get("weapon_progress", 0.0)),
        ),
        reverse=True,
    )

    best = candidates[0]

    return (
        f"Stack this reticle with {best.get('weapon', 'a weapon')} - "
        f"{best.get('camo', best.get('category', 'active weapon progress'))}. "
        f"Do not farm the reticle in isolation."
    )


def build_weapon_prestige_stacking_hint(stop: dict[str, Any], available_tasks: list[dict[str, Any]]) -> str:
    weapon = clean(stop.get("weapon", ""))

    if not weapon:
        return "Prestige route needs an anchor. Use the assigned weapon while clearing another active objective."

    same_weapon_anchor_types = {
        "camo",
        "mastery_badge_weapon",
    }

    same_weapon_candidates = [
        task for task in available_tasks
        if clean(task.get("weapon", "")) == weapon
        and task.get("task_id") != stop.get("task_id")
        and task.get("task_type") in same_weapon_anchor_types
        and not task.get("locked", False)
    ]

    if same_weapon_candidates:
        same_weapon_candidates = sorted(
            same_weapon_candidates,
            key=lambda task: (
                unlock_leverage_bonus(task),
                float(task.get("weapon_progress", 0.0)),
            ),
            reverse=True,
        )

        best = same_weapon_candidates[0]

        anchor_mode = best.get("mode", "the best mode")
        reticle = best_reticle_for_mode(anchor_mode, available_tasks, weapon=weapon, weapon_class=stop.get("weapon_class", ""))

        reticle_text = ""
        if reticle:
            compatibility_note = reticle.get("compatibility_note", "")
            note_text = f" ({compatibility_note})" if compatibility_note else ""
            reticle_text = (
                f" Also equip {reticle.get('weapon', 'an active reticle')} "
                f"for {reticle.get('camo', 'reticle progress')}{note_text}."
            )

        return (
            f"Prestige anchor found. Play {anchor_mode} with {weapon} "
            f"and stack prestige with {best.get('camo', best.get('category', 'active progress'))}. "
            f"The objective comes first, weapon XP happens passively."
            f"{reticle_text}"
        )

    playable_anchor_types = {
        "camo",
        "reticle",
        "mastery_badge_weapon",
        "mastery_badge_equipment",
        "calling_card",
        "dark_ops",
        "title",
    }

    mode_priority = [
        "Zombies",
        "Multiplayer",
        "Warzone",
        "Co-Op / Endgame",
    ]

    mode_scores: dict[str, float] = {}

    for task in available_tasks:
        if task.get("locked", False):
            continue

        candidate_mode = task.get("mode", "")
        candidate_type = task.get("task_type", "")

        if candidate_mode not in mode_priority:
            continue

        if candidate_type not in playable_anchor_types:
            continue

        mode_scores[candidate_mode] = mode_scores.get(candidate_mode, 0.0) + (
            1.0 + unlock_leverage_bonus(task) / 100.0
        )

    if mode_scores:
        best_mode = max(
            mode_scores,
            key=lambda mode: (
                mode_scores[mode],
                -mode_priority.index(mode),
            ),
        )

        reticle = best_reticle_for_mode(best_mode, available_tasks, weapon=weapon, weapon_class=stop.get("weapon_class", ""))

        reticle_text = ""
        if reticle:
            compatibility_note = reticle.get("compatibility_note", "")
            note_text = f" ({compatibility_note})" if compatibility_note else ""
            reticle_text = (
                f" Equip {reticle.get('weapon', 'an active reticle')} "
                f"for {reticle.get('camo', 'reticle progress')}{note_text}."
            )

        return (
            f"Prestige route needs an anchor. Play {best_mode} and use {weapon} "
            f"while clearing active {best_mode} objectives. Do not level the weapon in isolation."
            f"{reticle_text}"
        )

    return (
        f"Pure prestige cleanup. Use {weapon} in the fastest Weapon XP mode available. "
        f"This is a low-stacking route."
    )


def build_companion_objectives(
    stop: dict[str, Any],
    available_tasks: list[dict[str, Any]],
    max_items: int = 4,
) -> list[str]:
    mode = stop.get("mode", "")
    weapon = clean(stop.get("weapon", ""))
    weapon_class = clean(stop.get("weapon_class", ""))
    stop_task_id = stop.get("task_id", "")
    stop_task_type = stop.get("task_type", "")

    candidates: list[tuple[float, dict[str, Any]]] = []

    for task in available_tasks:
        if task.get("locked", False):
            continue

        if task.get("task_id") == stop_task_id:
            continue

        task_mode = task.get("mode", "")
        task_type = task.get("task_type", "")
        task_weapon = clean(task.get("weapon", ""))
        task_weapon_class = clean(task.get("weapon_class", ""))
        text = task_search_text(task)

        if task_mode not in {mode, "Global Cleanup"}:
            continue

        score = 0.0

        if task_weapon and weapon and task_weapon == weapon:
            score += 120

        if task_weapon_class and weapon_class and task_weapon_class == weapon_class:
            score += 80

        if task_type in {"calling_card", "dark_ops"}:
            score += 90

        if task_type in {"mastery_badge_weapon", "mastery_badge_equipment"}:
            score += 80

        if task_type == "reticle":
            score += 70

        if task_type in {"zombies_reward", "endgame_operation", "endgame_unlock", "intel", "title", "colour", "augment", "overclock"}:
            score += 90

        if any(term in text for term in [
            "operation",
            "mission",
            "king killer",
            "main quest",
            "map",
            "kowakujō",
            "kowakujo",
            "reward",
            "unlock",
            "intel",
            "calling card",
        ]):
            score += 80

        if stop_task_type != "camo" and task_type == "camo":
            score += 45

        if stop_task_type != "weapon_prestige" and task_type == "weapon_prestige":
            score += 35

        score += min(float(task.get("weapon_progress", 0.0)), 100.0) * 0.4
        score += unlock_leverage_bonus(task)

        if score <= 0:
            continue

        candidates.append((score, task))

    candidates.sort(key=lambda item: item[0], reverse=True)

    companion_lines: list[str] = []

    for _, task in candidates[:max_items]:
        task_type = task.get("task_type", "objective")
        weapon = task.get("weapon", "")
        camo = task.get("camo", "")
        challenge = task.get("challenge_text", "")

        label = camo or challenge or task_type

        if weapon and weapon != label:
            companion_lines.append(f"{weapon}: {label}")
        else:
            companion_lines.append(label)

    return companion_lines


def score_candidate_plan(plan: dict[str, Any]) -> float:
    stops = plan.get("stops", [])

    if not stops:
        return -999999.0

    diagnostics = plan.get("diagnostics", {})
    route_summary = plan.get("route_summary", {})
    task_mix = route_summary.get("task_mix", {}) if isinstance(route_summary, dict) else {}

    score = float(diagnostics.get("confidence_score", 0) or 0)
    score += len(stops) * 8
    score += sum(len(stop.get("companion_objectives", [])) for stop in stops) * 5
    score += sum(1 for stop in stops if is_non_camo_completion_task(stop)) * 35
    score -= sum(1 for stop in stops if stop.get("task_type") == "camo") * 8

    estimated = int(plan.get("estimated_minutes", 0) or 0)
    available = int(plan.get("available_minutes", 0) or 0)
    if available > 0:
        if estimated <= available:
            score += 20
        elif estimated <= available + 15:
            score += 8
        else:
            score -= 20

    if task_mix.get("endgame_operation", 0) or task_mix.get("zombies_reward", 0) or task_mix.get("endgame_unlock", 0):
        score += 30

    return score

def build_session_plan(
    tasks: list[dict[str, Any]],
    preferred_mode: str,
    session_goal: str,
    motivation: str,
    available_minutes: int = 90,
    max_stops: int | None = None,
    commander_mode: str = "Optimise my grind",
    focus_targets: list[str] | None = None,
    anchor_weapon: str = "",
    anchor_class: str = "",
    anchor_collection: str = "",
    minimum_closeness: int = 80,
    avoided_mode: str = "",
) -> dict[str, Any]:
    """
    Builds an ordered, ranked session plan.

    Normal mode locks to preferred_mode.
    Closest finishes can use all modes when preferred_mode is Global Cleanup.
    Start from my itch keeps the chosen mode but uses weapon/class/collection as
    the centre of gravity.
    """
    if max_stops is None:
        max_stops = stops_for_available_minutes(available_minutes)

    focus_targets = focus_targets or []
    available = get_available_tasks(tasks)

    if preferred_mode == "Commander chooses":
        excluded_modes = {"Commander chooses", "Global Cleanup"}
        if avoided_mode:
            excluded_modes.add(avoided_mode)

        candidate_modes = [
            mode for mode in MODES
            if mode not in excluded_modes
        ]
        candidate_plans = [
            build_session_plan(
                tasks=tasks,
                preferred_mode=mode,
                session_goal=session_goal,
                motivation=motivation,
                available_minutes=available_minutes,
                max_stops=max_stops,
                commander_mode=commander_mode,
                focus_targets=focus_targets,
                anchor_weapon=anchor_weapon,
                anchor_class=anchor_class,
                anchor_collection=anchor_collection,
                minimum_closeness=minimum_closeness,
                avoided_mode=avoided_mode,
            )
            for mode in candidate_modes
        ]
        candidate_plans = [plan for plan in candidate_plans if plan.get("stops")]

        if not candidate_plans:
            return {
                "mode": "Commander chooses",
                "preferred_mode": "Commander chooses",
                "available_minutes": available_minutes,
                "estimated_minutes": 0,
                "stops": [],
                "cluster_summary": [],
                "note": "Commander could not find any available route across all modes.",
                "diagnostics": {
                    "confidence": "Low",
                    "confidence_score": 0,
                    "rationale": ["No available tasks found across all modes."],
                },
                "route_summary": build_route_summary([], available_minutes),
                "commander_mode": commander_mode,
                "focus_targets": focus_targets,
                "anchor_weapon": anchor_weapon,
                "anchor_class": anchor_class,
                "anchor_collection": anchor_collection,
                "minimum_closeness": minimum_closeness,
                "avoided_mode": avoided_mode,
                "mode_candidates": [],
            }

        scored_candidates = sorted(
            ((score_candidate_plan(plan), plan) for plan in candidate_plans),
            key=lambda item: item[0],
            reverse=True,
        )
        best_score, best_plan = scored_candidates[0]

        candidate_summary = [
            {
                "mode": plan.get("mode", ""),
                "score": round(score, 1),
                "estimated_minutes": plan.get("estimated_minutes", 0),
                "stops": len(plan.get("stops", [])),
                "primary_route": plan.get("route_summary", {}).get("primary_route", ""),
            }
            for score, plan in scored_candidates
        ]

        best_plan["preferred_mode"] = "Commander chooses"
        best_plan["selected_mode"] = best_plan.get("mode", "")
        best_plan["mode_candidates"] = candidate_summary
        best_plan.setdefault("diagnostics", {}).setdefault("rationale", []).insert(
            0,
            f"Commander chose {best_plan.get('mode', 'Unknown')} after comparing all active modes.",
        )
        return best_plan

    if commander_mode == "Closest finishes" and preferred_mode == "Global Cleanup":
        mode_tasks = available
        effective_mode = "Any Mode"
    else:
        mode_tasks = [t for t in available if t.get("mode") == preferred_mode]
        effective_mode = preferred_mode

    if (
        commander_mode != "Closest finishes"
        and preferred_mode != "Global Cleanup"
        and mode_major_collection_is_done(preferred_mode, tasks)
    ):
        meaningful_modes = [
            mode for mode in MODES
            if mode not in {preferred_mode, "Global Cleanup"}
            and not mode_major_collection_is_done(mode, tasks)
        ]

        if meaningful_modes:
            best_fallback_mode = meaningful_modes[0]

            return build_session_plan(
                tasks=tasks,
                preferred_mode=best_fallback_mode,
                session_goal=session_goal,
                motivation=motivation,
                available_minutes=available_minutes,
                max_stops=max_stops,
                commander_mode=commander_mode,
                focus_targets=focus_targets,
                anchor_weapon=anchor_weapon,
                anchor_class=anchor_class,
                anchor_collection=anchor_collection,
                minimum_closeness=minimum_closeness,
                avoided_mode=avoided_mode,
            )

    original_mode_task_count = len(mode_tasks)
    guided_notes: list[str] = []

    if commander_mode in {"Start from my itch", "Class cleanup", "Completion stack"}:
        mode_tasks, guided_notes = guided_anchor_filter(
            mode_tasks,
            commander_mode=(
                "Start from my itch"
                if commander_mode == "Completion stack" and (anchor_weapon or anchor_class)
                else commander_mode
            ),
            preferred_mode=preferred_mode,
            anchor_weapon=anchor_weapon,
            anchor_class=anchor_class,
            anchor_collection=anchor_collection,
        )

    if commander_mode == "Closest finishes":
        close_tasks = [
            task for task in mode_tasks
            if task_meets_closeness(task, minimum_closeness)
        ]

        if close_tasks:
            mode_tasks = close_tasks

    if not mode_tasks:
        return {
            "mode": effective_mode,
            "preferred_mode": preferred_mode,
            "available_minutes": available_minutes,
            "stops": [],
            "cluster_summary": [],
            "note": " ".join(guided_notes) if guided_notes else f"No available tasks found for {effective_mode}.",
            "commander_mode": commander_mode,
            "focus_targets": focus_targets,
            "anchor_weapon": anchor_weapon,
            "anchor_class": anchor_class,
            "anchor_collection": anchor_collection,
            "minimum_closeness": minimum_closeness,
            "avoided_mode": avoided_mode,
            "diagnostics": {
                "confidence": "Low",
                "confidence_score": 0,
                "rationale": guided_notes or [f"No available tasks found for {effective_mode}."],
            },
        }

    clusters = build_clusters(
        tasks_in_mode=mode_tasks,
        preferred_mode=preferred_mode if effective_mode != "Any Mode" else "Global Cleanup",
        session_goal=session_goal,
        motivation=motivation,
        commander_mode=commander_mode,
        focus_targets=focus_targets,
        anchor_weapon=anchor_weapon,
        anchor_class=anchor_class,
        anchor_collection=anchor_collection,
        minimum_closeness=minimum_closeness,
    )

    stops: list[dict[str, Any]] = []
    cluster_summary: list[dict[str, Any]] = []
    estimated_used_minutes = 0
    overflow_allowance_minutes = 15

    for cluster in clusters:
        if len(stops) >= max_stops:
            break

        if estimated_used_minutes >= available_minutes:
            break

        cluster_summary.append(
            {
                "label": cluster["label"],
                "close_count": cluster["close_count"],
                "average_progress": cluster["average_progress"],
                "average_commander_score": cluster.get("average_commander_score", 0),
                "score": cluster.get("score", 0),
            }
        )

        for task in cluster["tasks"]:
            if len(stops) >= max_stops:
                break

            estimated_minutes = estimate_task_minutes(task)

            would_exceed_budget = (
                estimated_used_minutes + estimated_minutes
                > available_minutes + overflow_allowance_minutes
            )

            if stops and would_exceed_budget:
                break

            companion_objectives = build_companion_objectives(
                stop=task,
                available_tasks=available,
            )

            stops.append(
                {
                    "stop_number": len(stops) + 1,
                    "cluster_label": cluster["label"],
                    "weapon": task.get("weapon", ""),
                    "camo": task.get("camo", ""),
                    "challenge_text": task.get("challenge_text", ""),
                    "weapon_progress": task.get("weapon_progress", 0.0),
                    "task_type": task.get("task_type", ""),
                    "task_id": task.get("task_id", ""),
                    "mode": task.get("mode", ""),
                    "chain": task.get("chain", ""),
                    "category": task.get("category", ""),
                    "weapon_class": task.get("weapon_class", ""),
                    "recommended_mode": task.get("recommended_mode", ""),
                    "estimated_minutes": estimated_minutes,
                    "stacking_hint": build_stacking_hint(task, available) or build_weapon_prestige_hint(task, available),
                    "companion_objectives": companion_objectives,
                }
            )

            estimated_used_minutes += estimated_minutes

    diagnostics = build_plan_diagnostics(
        preferred_mode=effective_mode,
        mode_task_count=len(mode_tasks),
        clusters=clusters,
        stops=stops,
        max_stops=max_stops,
        available_minutes=available_minutes,
        session_goal=session_goal,
        motivation=motivation,
    )

    if guided_notes:
        diagnostics.setdefault("rationale", []).extend(guided_notes)

    if commander_mode == "Closest finishes" and len(mode_tasks) != original_mode_task_count:
        diagnostics.setdefault("rationale", []).append(
            f"Closest-finish filter kept {len(mode_tasks)} of {original_mode_task_count} available task(s) at {minimum_closeness}%+ or final-step equivalent."
        )

    route_summary = build_route_summary(
        stops=stops,
        available_minutes=available_minutes,
    )

    return {
        "mode": effective_mode,
        "preferred_mode": preferred_mode,
        "available_minutes": available_minutes,
        "estimated_minutes": estimated_used_minutes,
        "stops": stops,
        "cluster_summary": cluster_summary,
        "note": "",
        "diagnostics": diagnostics,
        "route_summary": route_summary,
        "commander_mode": commander_mode,
        "focus_targets": focus_targets,
        "anchor_weapon": anchor_weapon,
        "anchor_class": anchor_class,
        "anchor_collection": anchor_collection,
        "minimum_closeness": minimum_closeness,
        "avoided_mode": avoided_mode,
    }



def rebuild_plan_after_progress(
    tasks: list[dict[str, Any]],
    preferred_mode: str,
    session_goal: str,
    motivation: str,
    completed_task_ids: list[str],
    remaining_minutes: int,
    commander_mode: str = "Optimise my grind",
    focus_targets: list[str] | None = None,
    anchor_weapon: str = "",
    anchor_class: str = "",
    anchor_collection: str = "",
    minimum_closeness: int = 80,
    avoided_mode: str = "",
) -> dict[str, Any]:
    """
    Called after logging progress mid-session. Re-runs build_session_plan()
    on the current task state, preserving guided-start and closest-finish
    controls from the original plan.
    """
    remaining_tasks = [
        t for t in tasks if t.get("task_id") not in completed_task_ids
    ]

    return build_session_plan(
        tasks=remaining_tasks,
        preferred_mode=preferred_mode,
        session_goal=session_goal,
        motivation=motivation,
        available_minutes=remaining_minutes,
        commander_mode=commander_mode,
        focus_targets=focus_targets,
        anchor_weapon=anchor_weapon,
        anchor_class=anchor_class,
        anchor_collection=anchor_collection,
        minimum_closeness=minimum_closeness,
        avoided_mode=avoided_mode,
    )

def _generate_mission_supporting_text(
    task: dict[str, Any],
    session_goal: str,
    motivation: str,
    available_minutes: int,
    energy: str,
    *,
    field_name: str,
    fallback: str,
) -> str:
    if not task:
        return fallback

    prompt = (
        "You are the BO7 Completion Commander. Write one concise mission-card sentence for the requested field. "
        "Keep it tactical, clear, and human-readable.\n\n"
        f"Field: {field_name}\n"
        f"Task: {task.get('weapon', 'Unknown')} — {task.get('camo', 'Objective')}\n"
        f"Mode: {task.get('mode', 'Unknown')}\n"
        f"Recommended mode: {task.get('recommended_mode', 'Best available')}\n"
        f"Session goal: {session_goal}\n"
        f"Motivation: {motivation}\n"
        f"Available time: {available_minutes} minutes\n"
        f"Energy: {energy}"
    )

    groq_reply = _try_groq_text(prompt)
    if groq_reply:
        return groq_reply

    return fallback


def generate_mission(
    tasks: list[dict[str, Any]],
    available_minutes: int,
    energy: str,
    motivation: str,
    preferred_mode: str,
    avoided_mode: str,
    session_goal: str,
    operator_note: str = "",
) -> dict[str, Any]:
    task = select_next_task(
        tasks=tasks,
        preferred_mode=preferred_mode,
        avoided_mode=avoided_mode,
        session_goal=session_goal,
        motivation=motivation,
    )

    if task is None:
        locked_count = len(get_locked_tasks(tasks))

        return {
            "mission_id": datetime.now().strftime("BO7-%Y%m%d-%H%M%S"),
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "command": "No unlocked clean-data tasks detected. Prerequisite cleanup required.",
            "mode": "Blocked",
            "target": "Locked 100% database",
            "target_value": 0.0,
            "target_detail": f"No available unlocked tasks found. Locked tasks remaining: {locked_count}.",
            "challenge_text": "Complete prerequisite tasks first or update clean CSV data.",
            "recommended_mode": "N/A",
            "mode_reason": "No available task.",
            "strategy": "Inspect locked tasks and update clean CSVs after prerequisites are complete.",
            "avoid": "Do not manually assign locked tasks.",
            "time_limit": "0 minutes",
            "success_condition": "Reload clean CSVs after prerequisites are complete.",
            "why_this_target": "The commander refuses to assign locked tasks.",
            "stacked_progress": "Prerequisite cleanup.",
            "fallback": "Inspect locked tasks.",
            "reward": "None.",
            "next_if_completed": "Reload clean CSVs after prerequisites are complete.",
            "operator_note": operator_note,
            "ai_commentary": "Locked task protection activated.",
            "task_id": None,
        }

    time_limit = time_limit_for_session(available_minutes, energy)

    command = generate_mission_command(
        task,
        session_goal=session_goal,
        motivation=motivation,
        available_minutes=available_minutes,
        energy=energy,
    )

    rationale_fallback = (
        f"{task['weapon']} is {task['weapon_progress']:.2f}% through its current tracked route. "
        f"The commander selected it for: {session_goal}."
    )
    stacked_fallback = f"{task['category']}, {task['chain']}, session footage, and overall 100% progress."
    fallback_fallback = "If the task is wrong, impossible, or blocked, log 'Blocked / wrong requirement'. Do not silently switch tasks."
    reward_fallback = "After completion, generate the next order. No free-choice match until the log is updated."
    next_step_fallback = "Log completion, then generate the next highest-value unlocked task."

    return {
        "mission_id": datetime.now().strftime("BO7-%Y%m%d-%H%M%S"),
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "command": command,
        "mode": task["mode"],
        "target": f"{task['weapon']} — {task['camo']}",
        "target_value": task["weapon_progress"],
        "target_detail": (
            f"Task type: {task['task_type']}\n\n"
            f"Category: {task['category']}\n\n"
            f"Class/Subcategory: {task['weapon_class']}\n\n"
            f"Target: {task['weapon']}\n\n"
            f"Objective: {task['camo']}\n\n"
            f"Chain: {task['chain']}\n\n"
            f"Unlock status: {task.get('lock_reason', 'Available')}"
        ),
        "challenge_text": task["challenge_text"],
        "recommended_mode": task["recommended_mode"],
        "mode_reason": task["mode_reason"],
        "strategy": task["strategy"],
        "avoid": task["avoid"],
        "time_limit": f"{time_limit} minutes",
        "success_condition": f"Tick 'Camo completed' once this task is complete: {task['weapon']} — {task['camo']}.",
        "why_this_target": _generate_mission_supporting_text(
            task,
            session_goal,
            motivation,
            available_minutes,
            energy,
            field_name="why_this_target",
            fallback=rationale_fallback,
        ),
        "stacked_progress": _generate_mission_supporting_text(
            task,
            session_goal,
            motivation,
            available_minutes,
            energy,
            field_name="stacked_progress",
            fallback=stacked_fallback,
        ),
        "fallback": _generate_mission_supporting_text(
            task,
            session_goal,
            motivation,
            available_minutes,
            energy,
            field_name="fallback",
            fallback=fallback_fallback,
        ),
        "reward": _generate_mission_supporting_text(
            task,
            session_goal,
            motivation,
            available_minutes,
            energy,
            field_name="reward",
            fallback=reward_fallback,
        ),
        "next_if_completed": _generate_mission_supporting_text(
            task,
            session_goal,
            motivation,
            available_minutes,
            energy,
            field_name="next_if_completed",
            fallback=next_step_fallback,
        ),
        "operator_note": operator_note.strip() or "No human excuse supplied.",
        "ai_commentary": generate_ai_commentary(task, motivation),
        "task_id": task["task_id"],
    }


def apply_mission_result(
    tasks: list[dict[str, Any]],
    mission: dict[str, Any],
    result: str,
) -> list[dict[str, Any]]:
    task_id = mission.get("task_id")

    if not task_id:
        return tasks

    for task in tasks:
        if task["task_id"] == task_id:
            task["last_result"] = result

            if result == "Camo completed":
                task["completed_on_session"] = True

            break

    return tasks


def summarise_sessions(session_log: list[dict[str, Any]]) -> dict[str, int]:
    total = len(session_log)

    return {
        "total": total,
        "completed": sum(1 for row in session_log if row.get("result") == "Camo completed"),
        "partial": sum(1 for row in session_log if row.get("result") == "Partial progress"),
        "failed": sum(1 for row in session_log if row.get("result") == "Failed"),
        "blocked": sum(1 for row in session_log if row.get("result") == "Blocked / wrong requirement"),
        "skipped": sum(1 for row in session_log if row.get("result") == "Skipped"),
    }


def _build_groq_prompt(message: str, tasks: list[dict[str, Any]], latest_mission: dict[str, Any] | None, session_log: list[dict[str, Any]]) -> str:
    summary = summarise_tasks(tasks)
    mission_line = "No active mission."
    if latest_mission:
        mission_line = (
            f"Active mission: {latest_mission.get('command', 'N/A')} | "
            f"Target: {latest_mission.get('target', 'N/A')}"
        )

    mode_summary = ", ".join(
        f"{mode}:{count}" for mode, count in sorted(summary.get("by_mode", {}).items())[:6]
    ) or "none"

    return (
        "You are the BO7 Completion Commander. Reply in concise, tactical language. "
        "Keep it under 90 words, focus on the next best action, and avoid fluff.\n\n"
        f"Player message: {message}\n"
        f"Mission state: {mission_line}\n"
        f"Available task counts by mode: {mode_summary}\n"
        f"Session log entries: {len(session_log)}"
    )


def _try_groq_text(prompt: str, *, system_prompt: str = "You are a concise Black Ops 7 completion commander.") -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or Groq is None:
        return ""

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
            max_tokens=180,
        )
        content = getattr(response.choices[0].message, "content", "")
        return str(content).strip() if content else ""
    except Exception:
        return ""


def _try_groq_reply(message: str, tasks: list[dict[str, Any]], latest_mission: dict[str, Any] | None, session_log: list[dict[str, Any]]) -> str:
    return _try_groq_text(
        _build_groq_prompt(message, tasks, latest_mission, session_log),
        system_prompt="You are a concise Black Ops 7 completion commander.",
    )


def generate_plan_brief(plan: dict[str, Any], tasks: list[dict[str, Any]], session_log: list[dict[str, Any]] | None = None) -> str:
    if not plan:
        return ""

    mode = plan.get("mode", "Unknown")
    commander_mode = plan.get("commander_mode", "Optimise my grind")
    stops = plan.get("stops", [])
    available_minutes = plan.get("available_minutes", 0)
    focus_targets = plan.get("focus_targets") or []
    anchor_weapon = plan.get("anchor_weapon", "")
    anchor_collection = plan.get("anchor_collection", "")

    prompt = (
        "You are the BO7 Completion Commander. Write a short, tactical update for the active session plan. "
        "Keep it under 80 words and mention the current mode, route style, available time, and any important anchor.\n\n"
        f"Mode: {mode}\n"
        f"Commander mode: {commander_mode}\n"
        f"Stops planned: {len(stops)}\n"
        f"Available minutes: {available_minutes}\n"
        f"Focus targets: {', '.join(focus_targets) if focus_targets else 'none'}\n"
        f"Anchor weapon: {anchor_weapon or 'none'}\n"
        f"Anchor collection: {anchor_collection or 'none'}\n"
        f"Session log entries: {len(session_log or [])}"
    )

    groq_reply = _try_groq_text(prompt)
    if groq_reply:
        return groq_reply

    focus_text = ", ".join(focus_targets) if focus_targets else "general progress"
    anchor_text = anchor_weapon or anchor_collection or "the current target"
    return (
        f"Commander brief: {mode} route is set for {commander_mode}. "
        f"You have {len(stops)} stop(s) planned over {available_minutes} minutes, "
        f"with focus on {focus_text} and an anchor around {anchor_text}."
    )


def generate_mission_command(task: dict[str, Any], session_goal: str, motivation: str, available_minutes: int, energy: str) -> str:
    if not task:
        return "No mission assigned."

    prompt = (
        "You are the BO7 Completion Commander. Rewrite the mission order as a short, punchy in-game command. "
        "Keep it under 40 words, clear, and tactical.\n\n"
        f"Task: {task.get('weapon', 'Unknown')} — {task.get('camo', 'Objective')}\n"
        f"Mode: {task.get('mode', 'Unknown')}\n"
        f"Recommended mode: {task.get('recommended_mode', 'Best available')}\n"
        f"Session goal: {session_goal}\n"
        f"Motivation: {motivation}\n"
        f"Available time: {available_minutes} minutes\n"
        f"Energy: {energy}"
    )

    groq_reply = _try_groq_text(prompt)
    if groq_reply:
        return groq_reply

    return (
        f"Use {task.get('weapon', 'the target')} in {task.get('mode', 'the selected mode')} and finish the assigned objective. "
        f"No switching until the tracker is updated."
    )


def generate_commander_reply(
    message: str,
    tasks: list[dict[str, Any]],
    latest_mission: dict[str, Any] | None,
    session_log: list[dict[str, Any]],
) -> str:
    text = message.lower()
    summary = summarise_tasks(tasks)

    if "next" in text or "mission" in text or "what should" in text:
        if latest_mission:
            return (
                f"Active mission remains: {latest_mission['command']}\n\n"
                f"Challenge: {latest_mission['challenge_text']}\n"
                f"Recommended mode: {latest_mission['recommended_mode']}\n\n"
                "Complete or log the result before requesting a new order."
            )

        return "No active mission. Generate orders from Mission Control."

    if "locked" in text or "prereq" in text or "prerequisite" in text:
        locked_tasks = get_locked_tasks(tasks)[:20]

        if not locked_tasks:
            return "No locked tasks detected."

        lines = [
            f"- {task['mode']} | {task['weapon']} — {task['camo']}: {task['lock_reason']}"
            for task in locked_tasks
        ]

        return "Locked task preview:\n\n" + "\n".join(lines)

    if "status" in text or "summary" in text:
        mode_lines = "\n".join(
            f"- {mode}: {count} available"
            for mode, count in sorted(summary.get("by_mode", {}).items())
        )

        type_lines = "\n".join(
            f"- {task_type}: {count} available"
            for task_type, count in sorted(summary.get("by_type", {}).items())
        )

        return (
            f"Loaded tasks: {summary['total']}.\n"
            f"Available unlocked tasks: {summary['available']}.\n"
            f"Locked tasks: {summary['locked']}.\n"
            f"Completed/hidden this session: {summary['completed']}.\n"
            f"Session log entries: {len(session_log)}.\n\n"
            f"By mode:\n{mode_lines if mode_lines else '- None'}\n\n"
            f"By type:\n{type_lines if type_lines else '- None'}"
        )

    groq_reply = _try_groq_reply(message, tasks, latest_mission, session_log)
    if groq_reply:
        return groq_reply

    return (
        "Completion Commander online. Ask for status, locked tasks, or next mission. "
        "The clean 100% database is active."
    )



TRUE_SET = {"TRUE", "YES", "DONE", "COMPLETE", "COMPLETED"}
NA_SET = {"N/A", "NA", "NONE", ""}
 
 
def _is_true(v) -> bool:
    return str(v).strip().upper() in TRUE_SET
 
 
def _is_na(v) -> bool:
    return str(v).strip().upper() in NA_SET
 
 
def _load(clean_folder: Path, filename: str) -> pd.DataFrame:
    path = clean_folder / filename
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")
 
 
def _pct(done: int, total: int) -> float:
    return round((done / total * 100), 2) if total else 0.0
 
 
# ---------------------------------------------------------------------------
# CAMO CHAINS (already built — kept here for completeness)
# ---------------------------------------------------------------------------
 
FINAL_CAMO_COLUMN = {
    "apocalypse_status.csv": "Apocalypse",
    "singularity_status.csv": "Singularity",
    "infestation_status.csv": "Infestation",
    "genesis_status.csv": "Genesis",
}
CHAIN_LABELS = {
    "apocalypse_status.csv": "Apocalypse (Warzone)",
    "singularity_status.csv": "Singularity (Multiplayer)",
    "infestation_status.csv": "Infestation (Zombies)",
    "genesis_status.csv": "Genesis (Co-Op / Endgame)",
}
# Base (military+special) camo columns end before the 4 mastery columns
BASE_CAMO_END_OFFSET = 4  # last 4 columns are: Golden_X, Gate1, Gate2, Final
 
 
def compute_camo_dashboard(clean_folder: Path) -> dict[str, Any]:
    result = {}

    mastery_unlock_required = 30

    for filename, final_col in FINAL_CAMO_COLUMN.items():
        df = _load(clean_folder, filename)
        label = CHAIN_LABELS[filename]

        if df.empty or final_col not in df.columns:
            result[label] = {
                "base_done": 0,
                "base_total": 0,
                "mastery_unlock_done": 0,
                "mastery_unlock_total": mastery_unlock_required,
                "mastery_unlock_complete": False,
                "mastery_done": 0,
                "mastery_total": 0,
            }
            continue

        all_cols = [c for c in df.columns if c not in ("mode", "chain", "weapon_class", "weapon")]
        base_cols = all_cols[:-BASE_CAMO_END_OFFSET]

        applicable = ~df[final_col].str.strip().str.upper().isin(NA_SET)
        df_app = df[applicable]

        base_total = 0
        base_done = 0

        for col in base_cols:
            mask = ~df_app[col].str.strip().str.upper().isin(NA_SET)
            base_total += mask.sum()
            base_done += df_app[col][mask].apply(_is_true).sum()

        mastery_total = len(df_app)
        mastery_done = int(df_app[final_col].apply(_is_true).sum())

        result[label] = {
            "base_done": int(base_done),
            "base_total": int(base_total),

            # Official 30-camo unlock / calling-card threshold
            "mastery_unlock_done": min(mastery_done, mastery_unlock_required),
            "mastery_unlock_total": mastery_unlock_required,
            "mastery_unlock_complete": mastery_done >= mastery_unlock_required,

            # True full account completion
            "mastery_done": mastery_done,
            "mastery_total": int(mastery_total),
        }

    return result

# ---------------------------------------------------------------------------
# WEAPON PRESTIGE
# ---------------------------------------------------------------------------
 
def compute_prestige_summary(clean_folder: Path) -> dict[str, Any]:
    df = _load(clean_folder, "weapon_prestige.csv")

    stage_order = [
        "p1_complete",
        "p2_complete",
        "wpm_complete",
        "lvl_100_complete",
        "lvl_150_complete",
        "lvl_200_complete",
        "lvl_250_complete",
    ]

    stage_labels = {
        "p1_complete": "Prestige 1",
        "p2_complete": "Prestige 2",
        "wpm_complete": "WPM",
        "lvl_100_complete": "Level 100",
        "lvl_150_complete": "Level 150",
        "lvl_200_complete": "Level 200",
        "lvl_250_complete": "Level 250",
    }

    if df.empty:
        return {
            "wpm_done": 0,
            "total": 0,
            "stages": {
                stage: {
                    "label": stage_labels[stage],
                    "done": 0,
                    "total": 0,
                }
                for stage in stage_order
            },
        }

    def stage_is_complete_backwards(row, stage_index: int) -> bool:
        """
        Counts later completion as earlier completion.

        Example:
        lvl_250_complete TRUE means this weapon also counts as complete for
        lvl_200, lvl_150, lvl_100, WPM, Prestige 2, and Prestige 1.
        """
        later_or_equal_stages = stage_order[stage_index:]

        return any(
            stage in df.columns
            and not _is_na(row.get(stage, ""))
            and _is_true(row.get(stage, ""))
            for stage in later_or_equal_stages
        )

    stages = {}

    for stage_index, stage in enumerate(stage_order):
        if stage not in df.columns:
            stages[stage] = {
                "label": stage_labels[stage],
                "done": 0,
                "total": 0,
            }
            continue

        applicable_rows = df[
            df[stage].fillna("").apply(lambda value: not _is_na(value))
        ]

        done = applicable_rows.apply(
            lambda row: stage_is_complete_backwards(row, stage_index),
            axis=1,
        ).sum()

        stages[stage] = {
            "label": stage_labels[stage],
            "done": int(done),
            "total": int(len(applicable_rows)),
        }

    wpm = stages["wpm_complete"]

    return {
        "wpm_done": wpm["done"],
        "total": wpm["total"],
        "stages": stages,
    }
 
 
# ---------------------------------------------------------------------------
# MASTERY BADGES — weapons + equipment
# ---------------------------------------------------------------------------
 
def compute_mastery_badges_summary(clean_folder: Path) -> dict[str, Any]:
    weapons = _load(clean_folder, "mastery_badges_weapons.csv")
    eq_mp = _load(clean_folder, "mastery_badges_equipment_mp.csv")
    eq_zm = _load(clean_folder, "mastery_badges_equipment_zombies.csv")

    def applicable(value: Any) -> bool:
        return not _is_na(value)

    def count_stage_with_backfill(df: pd.DataFrame, stage_columns: list[str], stage_index: int) -> tuple[int, int]:
        """
        Counts a stage as complete if that stage OR any later stage is TRUE.

        Example:
        gold TRUE counts as bronze and silver too.
        """
        stage_col = stage_columns[stage_index]

        if df.empty or stage_col not in df.columns:
            return 0, 0

        total = 0
        done = 0
        later_or_equal_columns = stage_columns[stage_index:]

        for _, row in df.iterrows():
            if not applicable(row.get(stage_col, "")):
                continue

            total += 1

            if any(
                column in df.columns
                and applicable(row.get(column, ""))
                and _is_true(row.get(column, ""))
                for column in later_or_equal_columns
            ):
                done += 1

        return int(done), int(total)

    def count_raw_column(df: pd.DataFrame, column: str) -> tuple[int, int]:
        if df.empty or column not in df.columns:
            return 0, 0

        mask = df[column].fillna("").apply(applicable)
        done = df.loc[mask, column].apply(_is_true).sum()
        return int(done), int(mask.sum())

    def weapon_diamond_group_summary(prefix: str, requirements: dict[str, tuple[int, int, int, int]]) -> dict[str, int]:
        if weapons.empty:
            return {"done": 0, "total": 0}

        gold_col = f"{prefix}_gold_complete"
        diamond_col = f"{prefix}_diamond_complete"

        if gold_col not in weapons.columns:
            return {"done": 0, "total": 0}

        done = 0
        total = 0

        for weapon_class, requirement_tuple in requirements.items():
            required_gold = requirement_tuple[3]
            class_rows = weapons[weapons["weapon_class"].fillna("").str.strip() == weapon_class]

            if class_rows.empty:
                continue

            total += 1

            gold_count = 0
            for _, row in class_rows.iterrows():
                gold_done = _is_true(row.get(gold_col, ""))
                diamond_done = _is_true(row.get(diamond_col, ""))
                if gold_done or diamond_done:
                    gold_count += 1

            any_diamond_ticked = (
                diamond_col in class_rows.columns
                and class_rows[diamond_col].apply(_is_true).any()
            )

            if gold_count >= required_gold or any_diamond_ticked:
                done += 1

        return {"done": int(done), "total": int(total)}

    def equipment_diamond_group_summary(df: pd.DataFrame) -> dict[str, int]:
        if df.empty or "category" not in df.columns:
            return {"done": 0, "total": 0}

        done = 0
        total = 0

        for category, group in df.groupby("category"):
            if not str(category).strip():
                continue

            total += 1

            required_values = [
                safe_int(value, 0)
                for value in group.get("diamond_required", pd.Series(dtype=str)).tolist()
                if str(value).strip()
            ]
            required_gold = max(required_values) if required_values else 0

            gold_count = 0
            for _, row in group.iterrows():
                gold_done = _is_true(row.get("gold_complete", ""))
                diamond_done = _is_true(row.get("diamond_complete", ""))
                if gold_done or diamond_done:
                    gold_count += 1

            any_diamond_ticked = (
                "diamond_complete" in group.columns
                and group["diamond_complete"].apply(_is_true).any()
            )

            if required_gold > 0 and (gold_count >= required_gold or any_diamond_ticked):
                done += 1

        return {"done": int(done), "total": int(total)}

    weapon_mp_stage_columns = [
        "mp_bronze_complete",
        "mp_silver_complete",
        "mp_gold_complete",
    ]
    weapon_zm_stage_columns = [
        "zm_bronze_complete",
        "zm_silver_complete",
        "zm_gold_complete",
    ]
    equipment_stage_columns = [
        "bronze_complete",
        "silver_complete",
        "gold_complete",
    ]

    weapon_mp_bronze = count_stage_with_backfill(weapons, weapon_mp_stage_columns, 0)
    weapon_mp_silver = count_stage_with_backfill(weapons, weapon_mp_stage_columns, 1)
    weapon_mp_gold = count_stage_with_backfill(weapons, weapon_mp_stage_columns, 2)

    weapon_zm_bronze = count_stage_with_backfill(weapons, weapon_zm_stage_columns, 0)
    weapon_zm_silver = count_stage_with_backfill(weapons, weapon_zm_stage_columns, 1)
    weapon_zm_gold = count_stage_with_backfill(weapons, weapon_zm_stage_columns, 2)

    equipment_mp_bronze = count_stage_with_backfill(eq_mp, equipment_stage_columns, 0)
    equipment_mp_silver = count_stage_with_backfill(eq_mp, equipment_stage_columns, 1)
    equipment_mp_gold = count_stage_with_backfill(eq_mp, equipment_stage_columns, 2)

    equipment_zm_bronze = count_stage_with_backfill(eq_zm, equipment_stage_columns, 0)
    equipment_zm_silver = count_stage_with_backfill(eq_zm, equipment_stage_columns, 1)
    equipment_zm_gold = count_stage_with_backfill(eq_zm, equipment_stage_columns, 2)

    weapon_mp_diamond_groups = weapon_diamond_group_summary("mp", MP_WEAPON_BADGE_REQUIREMENTS)
    weapon_zm_diamond_groups = weapon_diamond_group_summary("zm", ZM_WEAPON_BADGE_REQUIREMENTS)
    equipment_mp_diamond_groups = equipment_diamond_group_summary(eq_mp)
    equipment_zm_diamond_groups = equipment_diamond_group_summary(eq_zm)

    weapon_stage_done = (
        weapon_mp_bronze[0] + weapon_mp_silver[0] + weapon_mp_gold[0]
        + weapon_zm_bronze[0] + weapon_zm_silver[0] + weapon_zm_gold[0]
    )
    weapon_stage_total = (
        weapon_mp_bronze[1] + weapon_mp_silver[1] + weapon_mp_gold[1]
        + weapon_zm_bronze[1] + weapon_zm_silver[1] + weapon_zm_gold[1]
    )

    weapon_diamond_group_done = weapon_mp_diamond_groups["done"] + weapon_zm_diamond_groups["done"]
    weapon_diamond_group_total = weapon_mp_diamond_groups["total"] + weapon_zm_diamond_groups["total"]

    weapon_done = weapon_stage_done + weapon_diamond_group_done
    weapon_total = weapon_stage_total + weapon_diamond_group_total

    support_stage_done = (
        equipment_mp_bronze[0] + equipment_mp_silver[0] + equipment_mp_gold[0]
        + equipment_zm_bronze[0] + equipment_zm_silver[0] + equipment_zm_gold[0]
    )
    support_stage_total = (
        equipment_mp_bronze[1] + equipment_mp_silver[1] + equipment_mp_gold[1]
        + equipment_zm_bronze[1] + equipment_zm_silver[1] + equipment_zm_gold[1]
    )

    support_diamond_group_done = equipment_mp_diamond_groups["done"] + equipment_zm_diamond_groups["done"]
    support_diamond_group_total = equipment_mp_diamond_groups["total"] + equipment_zm_diamond_groups["total"]

    support_done = support_stage_done + support_diamond_group_done
    support_total = support_stage_total + support_diamond_group_total

    total_done = weapon_done + support_done
    total_count = weapon_total + support_total

    weapon_mp_diamond_rows = count_raw_column(weapons, "mp_diamond_complete")
    weapon_zm_diamond_rows = count_raw_column(weapons, "zm_diamond_complete")
    equipment_mp_diamond_rows = count_raw_column(eq_mp, "diamond_complete")
    equipment_zm_diamond_rows = count_raw_column(eq_zm, "diamond_complete")

    return {
        "total": {"done": int(total_done), "total": int(total_count)},
        "weapon": {"done": int(weapon_done), "total": int(weapon_total)},
        "support": {"done": int(support_done), "total": int(support_total)},

        "weapon_stages": {
            "mp_bronze": weapon_mp_bronze,
            "mp_silver": weapon_mp_silver,
            "mp_gold": weapon_mp_gold,
            "zm_bronze": weapon_zm_bronze,
            "zm_silver": weapon_zm_silver,
            "zm_gold": weapon_zm_gold,
        },

        "support_stages": {
            "mp_bronze": equipment_mp_bronze,
            "mp_silver": equipment_mp_silver,
            "mp_gold": equipment_mp_gold,
            "zm_bronze": equipment_zm_bronze,
            "zm_silver": equipment_zm_silver,
            "zm_gold": equipment_zm_gold,
        },

        "diamond_groups": {
            "weapon_mp": weapon_mp_diamond_groups,
            "weapon_zm": weapon_zm_diamond_groups,
            "equipment_mp": equipment_mp_diamond_groups,
            "equipment_zm": equipment_zm_diamond_groups,
            "mp": {
                "done": weapon_mp_diamond_groups["done"] + equipment_mp_diamond_groups["done"],
                "total": weapon_mp_diamond_groups["total"] + equipment_mp_diamond_groups["total"],
            },
            "zm": {
                "done": weapon_zm_diamond_groups["done"] + equipment_zm_diamond_groups["done"],
                "total": weapon_zm_diamond_groups["total"] + equipment_zm_diamond_groups["total"],
            },
        },

        "individual_diamond_rows": {
            "weapon_mp": {"done": weapon_mp_diamond_rows[0], "total": weapon_mp_diamond_rows[1]},
            "weapon_zm": {"done": weapon_zm_diamond_rows[0], "total": weapon_zm_diamond_rows[1]},
            "equipment_mp": {"done": equipment_mp_diamond_rows[0], "total": equipment_mp_diamond_rows[1]},
            "equipment_zm": {"done": equipment_zm_diamond_rows[0], "total": equipment_zm_diamond_rows[1]},
        },

        # Legacy keys so the current dashboard will not break before the UI patch.
        "weapon_mp_gold": weapon_mp_gold,
        "weapon_mp_diamond": weapon_mp_diamond_rows,
        "weapon_zm_gold": weapon_zm_gold,
        "weapon_zm_diamond": weapon_zm_diamond_rows,
        "equipment_mp_gold": equipment_mp_gold,
        "equipment_mp_diamond": equipment_mp_diamond_rows,
        "equipment_zm_gold": equipment_zm_gold,
        "equipment_zm_diamond": equipment_zm_diamond_rows,
    }

# ---------------------------------------------------------------------------
# CALLING CARDS — by mode
# ---------------------------------------------------------------------------
 
CALLING_CARD_FILES = {
    "Co-Op / Endgame": "calling_cards_sp.csv",
    "Multiplayer": "calling_cards_mp.csv",
    "Zombies": "calling_cards_zm.csv",
    "Warzone": "calling_cards_wz.csv",
}
 
def compute_calling_cards_summary(clean_folder: Path) -> dict[str, tuple]:
    result = {}

    mode_master_cards = {
        "Co-Op / Endgame": "Co-Op Campaign 100 Percenter",
        "Warzone": "Warzone 100 Percenter",
    }

    excluded_values = {"FALSE", "NO", "0", "N", "OPTIONAL", "EXTRA"}

    for mode, filename in CALLING_CARD_FILES.items():
        df = _load(clean_folder, filename)

        if df.empty:
            result[mode] = (0, 0)
            continue

        if "counts_for_100_percent" in df.columns:
            counted_df = df[
                df["counts_for_100_percent"]
                .fillna("")
                .apply(lambda value: str(value).strip().upper() not in excluded_values)
            ]
        else:
            counted_df = df

        if counted_df.empty or "completed" not in counted_df.columns:
            result[mode] = (0, 0)
            continue

        total = len(counted_df)

        master_card = mode_master_cards.get(mode)
        if master_card and "challenge" in counted_df.columns:
            master_rows = counted_df[
                counted_df["challenge"].fillna("").str.strip() == master_card
            ]

            if not master_rows.empty and master_rows["completed"].apply(_is_true).any():
                result[mode] = (total, total)
                continue

        done = counted_df["completed"].apply(_is_true).sum()
        result[mode] = (int(done), total)

    return result

# ---------------------------------------------------------------------------
# RETICLES — by mode
# ---------------------------------------------------------------------------
 
def compute_reticles_summary(clean_folder: Path) -> dict[str, Any]:
    df = _load(clean_folder, "reticles.csv")

    stage_columns = [
        "stage_20_complete",
        "stage_40_complete",
        "stage_60_complete",
        "stage_80_complete",
        "stage_100_complete",
    ]

    stage_labels = {
        "stage_20_complete": "20%",
        "stage_40_complete": "40%",
        "stage_60_complete": "60%",
        "stage_80_complete": "80%",
        "stage_100_complete": "100%",
    }

    if df.empty:
        return {
            "total": {"done": 0, "total": 0},
            "by_mode": {},
            "by_stage": {},
            "stage_100_by_mode": {},
        }

    def stage_complete_with_backfill(row, stage_index: int) -> bool:
        """
        Counts later reticle stages as earlier stages.

        Example:
        stage_100_complete TRUE also counts as 80, 60, 40, and 20 complete.
        """
        later_or_equal_columns = stage_columns[stage_index:]

        return any(
            column in df.columns
            and not _is_na(row.get(column, ""))
            and _is_true(row.get(column, ""))
            for column in later_or_equal_columns
        )

    def count_rows(rows: pd.DataFrame, stage_index: int) -> tuple[int, int]:
        stage_col = stage_columns[stage_index]

        if rows.empty or stage_col not in rows.columns:
            return 0, 0

        total = 0
        done = 0

        for _, row in rows.iterrows():
            if _is_na(row.get(stage_col, "")):
                continue

            total += 1

            if stage_complete_with_backfill(row, stage_index):
                done += 1

        return int(done), int(total)

    total_done = 0
    total_count = 0
    by_mode = {}
    by_stage = {}
    stage_100_by_mode = {}

    for stage_index, stage_col in enumerate(stage_columns):
        done, total = count_rows(df, stage_index)

        by_stage[stage_col] = {
            "label": stage_labels[stage_col],
            "done": done,
            "total": total,
        }

        total_done += done
        total_count += total

    if "mode" in df.columns:
        for mode in df["mode"].unique():
            mode_rows = df[df["mode"] == mode]

            mode_done = 0
            mode_total = 0

            for stage_index, _stage_col in enumerate(stage_columns):
                done, total = count_rows(mode_rows, stage_index)
                mode_done += done
                mode_total += total

            stage_100_done, stage_100_total = count_rows(mode_rows, 4)

            by_mode[mode] = {
                "done": int(mode_done),
                "total": int(mode_total),
            }

            stage_100_by_mode[mode] = {
                "done": int(stage_100_done),
                "total": int(stage_100_total),
            }

    return {
        "total": {"done": int(total_done), "total": int(total_count)},
        "by_mode": by_mode,
        "by_stage": by_stage,
        "stage_100_by_mode": stage_100_by_mode,

        # Legacy mode keys so old UI code will not instantly explode.
        **{
            mode: (data["done"], data["total"])
            for mode, data in stage_100_by_mode.items()
        },
    }
 
 
# ---------------------------------------------------------------------------
# TITLES — by mode
# ---------------------------------------------------------------------------
 
def compute_titles_summary(clean_folder: Path) -> dict[str, Any]:
    df = _load(clean_folder, "titles.csv")

    if df.empty or "earned" not in df.columns:
        return {
            "total": {"done": 0, "total": 0},
            "by_mode": {},
        }

    mode_label_map = {
        "General": "Global Cleanup",
        "Co-Op Campaign & Endgame": "Co-Op / Endgame",
        "Co-Op / Endgame": "Co-Op / Endgame",
        "Multiplayer": "Multiplayer",
        "Zombies": "Zombies",
        "Warzone": "Warzone",
    }

    if "mode" not in df.columns:
        df["mode"] = "Global Cleanup"

    df = df.copy()
    df["_dashboard_mode"] = df["mode"].fillna("").apply(
        lambda value: mode_label_map.get(str(value).strip(), str(value).strip() or "Global Cleanup")
    )

    total_done = int(df["earned"].apply(_is_true).sum())
    total_count = int(len(df))

    by_mode = {}

    for mode in df["_dashboard_mode"].unique():
        sub = df[df["_dashboard_mode"] == mode]
        done = int(sub["earned"].apply(_is_true).sum())
        total = int(len(sub))

        by_mode[mode] = {
            "done": done,
            "total": total,
        }

    return {
        "total": {
            "done": total_done,
            "total": total_count,
        },
        "by_mode": by_mode,
    }
 
 
# ---------------------------------------------------------------------------
# COLOURS — single percentage
# ---------------------------------------------------------------------------
 
def compute_colours_summary(clean_folder: Path) -> dict[str, Any]:
    df = _load(clean_folder, "colours.csv")

    if df.empty or "unlocked" not in df.columns:
        return {
            "total": {"done": 0, "total": 0},
            "by_category": {},
            "by_source": {},
        }

    total_done = int(df["unlocked"].apply(_is_true).sum())
    total_count = int(len(df))

    by_category = {}
    by_source = {}

    if "category" in df.columns:
        for category in df["category"].fillna("").unique():
            label = str(category).strip() or "Uncategorised"
            sub = df[df["category"].fillna("").str.strip() == str(category).strip()]
            done = int(sub["unlocked"].apply(_is_true).sum())
            total = int(len(sub))

            by_category[label] = {
                "done": done,
                "total": total,
            }

    if "source" in df.columns:
        for source in df["source"].fillna("").unique():
            label = str(source).strip() or "Unknown Source"
            sub = df[df["source"].fillna("").str.strip() == str(source).strip()]
            done = int(sub["unlocked"].apply(_is_true).sum())
            total = int(len(sub))

            by_source[label] = {
                "done": done,
                "total": total,
            }

    return {
        "total": {
            "done": total_done,
            "total": total_count,
        },
        "by_category": by_category,
        "by_source": by_source,

        # Legacy keys in case any old code still checks tuple-style values later.
        "done": total_done,
        "count": total_count,
    }
 
# ---------------------------------------------------------------------------
# AUGMENTS — Zombies only
# ---------------------------------------------------------------------------
 
def compute_augments_summary(clean_folder: Path) -> tuple:
    df = _load(clean_folder, "augments_zombies.csv")
    if df.empty:
        return (0, 0)
    cols = ["minor1","major1","minor2","major2","minor3","major3","minor4","major4","extra_slot"]
    total = len(df) * len(cols)
    done = sum(df[c].apply(_is_true).sum() for c in cols)
    return (int(done), int(total))
 
 
# ---------------------------------------------------------------------------
# OVERCLOCKS — Multiplayer only
# ---------------------------------------------------------------------------
 
def compute_overclocks_summary(clean_folder: Path) -> tuple:
    df = _load(clean_folder, "overclocks_mp.csv")
    if df.empty:
        return (0, 0)
    total = len(df) * 2
    done = df["oc1_complete"].apply(_is_true).sum() + df["oc2_complete"].apply(_is_true).sum()
    return (int(done), int(total))
 
 
# ---------------------------------------------------------------------------
# INTEL — by map
# ---------------------------------------------------------------------------
 
def compute_intel_summary(clean_folder: Path) -> dict[str, tuple]:
    df = _load(clean_folder, "intel.csv")
    if df.empty:
        return {}
    result = {}
    for map_name in df["map"].unique():
        sub = df[df["map"] == map_name]
        done = sub["found"].apply(_is_true).sum()
        result[map_name] = (int(done), len(sub))
    return result
 
 
# ---------------------------------------------------------------------------
# REWARDS — zombies maps + endgame operations
# ---------------------------------------------------------------------------
 
def compute_rewards_summary(clean_folder: Path) -> dict[str, Any]:
    result = {}
 
    rz = _load(clean_folder, "rewards_zombies.csv")
    if not rz.empty:
        by_map = {}
        for map_name in rz["map"].unique():
            sub = rz[rz["map"] == map_name]
            done = sub["earned"].apply(_is_true).sum()
            by_map[map_name] = (int(done), len(sub))
        result["zombies_by_map"] = by_map
        total_done = rz["earned"].apply(_is_true).sum()
        result["zombies_total"] = (int(total_done), len(rz))
 
    re_ops = _load(clean_folder, "rewards_endgame_operations.csv")
    if not re_ops.empty:
        by_op = {}
        for op in re_ops["operation"].unique():
            sub = re_ops[re_ops["operation"] == op]
            done = sub["earned"].apply(_is_true).sum()
            by_op[op] = (int(done), len(sub))
        result["endgame_operations_by_act"] = by_op
        total_done = re_ops["earned"].apply(_is_true).sum()
        result["endgame_operations_total"] = (int(total_done), len(re_ops))

    re_unlocks = _load(clean_folder, "rewards_endgame_unlocks.csv")
    if not re_unlocks.empty and "earned" in re_unlocks.columns:
        by_category = {}
        for category in re_unlocks["category"].unique():
            sub = re_unlocks[re_unlocks["category"] == category]
            done = sub["earned"].apply(_is_true).sum()
            by_category[category] = (int(done), len(sub))
        result["endgame_unlocks_by_category"] = by_category
        total_done = re_unlocks["earned"].apply(_is_true).sum()
        result["endgame_unlocks_total"] = (int(total_done), len(re_unlocks))
 
    return result
 
 
# ---------------------------------------------------------------------------
# MASTER SUMMARY — single call for the whole Tracker tab
# ---------------------------------------------------------------------------
 
def compute_full_tracker_summary(clean_folder: Path) -> dict[str, Any]:
    return {
        "camos": compute_camo_dashboard(clean_folder),
        "prestige": compute_prestige_summary(clean_folder),
        "mastery_badges": compute_mastery_badges_summary(clean_folder),
        "calling_cards": compute_calling_cards_summary(clean_folder),
        "reticles": compute_reticles_summary(clean_folder),
        "titles": compute_titles_summary(clean_folder),
        "colours": compute_colours_summary(clean_folder),
        "augments": compute_augments_summary(clean_folder),
        "overclocks": compute_overclocks_summary(clean_folder),
        "intel": compute_intel_summary(clean_folder),
        "rewards": compute_rewards_summary(clean_folder),
    }

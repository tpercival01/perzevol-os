from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


CLEAN_FOLDER = Path("data/bo7_clean")

ENERGY_LEVELS = ["Low", "Medium", "High", "Unstable"]

MOTIVATION_LEVELS = [
    "Barely functioning",
    "Low",
    "Decent",
    "Locked in",
]

MODES = [
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

        if len(remaining) <= 1:
            return (
                f"Get {remaining_counts[0]} {challenge_type} with {weapon}. "
                f"Final military camo — completing this unlocks Special camos."
            )

        total = sum(remaining_counts)
        steps = " → ".join(str(c) for c in remaining_counts)
        return (
            f"Get {remaining_counts[0]} {challenge_type} to start. "
            f"{len(remaining)} military camos remaining for {weapon}: {steps}. "
            f"Stay on {weapon} until all military camos are done "
            f"({total} total {challenge_type.lower()} remaining)."
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

            challenge_text = label

            if stage in {"p1_complete", "p2_complete"} and max_level:
                challenge_text = f"{label}. Weapon max level is {max_level}."

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
                    progress=weapon_prestige_progress(row, order),
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

                if stage == "diamond":
                    required = clean(row.get("diamond_required", ""))
                    challenge_text = f"Earn {required} Gold Mastery Badges for {category}."
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
                c for c, _, _ in tier_columns
                if is_applicable(row.get(c, ""))
            ]
            if applicable_tiers and all(is_true(row.get(c, "")) for c in applicable_tiers):
                continue

            next_tier_label = "Completion"
            next_tier_target = ""

            for complete_col, target_col, label in tier_columns:
                val = row.get(complete_col, "")
                if not is_applicable(val):
                    continue
                if not is_true(val):
                    next_tier_label = label
                    next_tier_target = clean(row.get(target_col, ""))
                    break

            stage_label = f"{next_tier_label} — target: {next_tier_target}".strip(" —")

            # Progress
            applicable = [
                c for c, _, _ in tier_columns
                if is_applicable(row.get(c, ""))
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
    tasks.extend(build_calling_card_tasks())   # NEW
    tasks.extend(build_title_tasks())           # NEW

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

def score_task(
    task: dict[str, Any],
    preferred_mode: str,
    avoided_mode: str,
    session_goal: str,
    motivation: str,
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

    return score

def select_next_task(
    tasks: list[dict[str, Any]],
    preferred_mode: str,
    avoided_mode: str,
    session_goal: str,
    motivation: str,
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
) -> list[dict[str, Any]]:
    return sorted(
        get_available_tasks(tasks),
        key=lambda task: score_task(
            task=task,
            preferred_mode=preferred_mode,
            avoided_mode=avoided_mode,
            session_goal=session_goal,
            motivation=motivation,
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

    if task_type in {"calling_card", "dark_ops", "title"}:
        sub = task.get("weapon_class", "") or task.get("category", "")
        return f"card:{sub}"

    weapon_class = task.get("weapon_class", "")
    return f"class:{weapon_class}" if weapon_class else f"other:{task_type}"


def cluster_label(task: dict[str, Any]) -> str:
    task_type = task.get("task_type", "")

    if task_type in {"calling_card", "dark_ops", "title"}:
        return task.get("weapon_class", "") or task.get("category", "Misc")

    return task.get("weapon_class", "Unclassified")


def build_clusters(
    tasks_in_mode: list[dict[str, Any]],
    preferred_mode: str = "",
    session_goal: str = "Balanced progress",
    motivation: str = "Decent",
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
                )
                for task in scored_tasks
            ) / len(scored_tasks)
            if scored_tasks
            else 0.0
        )

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
        return 45

    if mode == "Zombies":
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

    return 30

def build_stacking_hint(stop: dict[str, Any], available_tasks: list[dict[str, Any]]) -> str:
    """
    Gives practical stacking advice for tasks that should not be done in isolation.
    """
    if stop.get("task_type") != "reticle":
        return ""

    mode = stop.get("mode", "")
    reticle_progress = float(stop.get("weapon_progress", 0.0))

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
        f"Stack this reticle with {best.get('weapon', 'a weapon')} — "
        f"{best.get('camo', best.get('category', 'active weapon progress'))}. "
        f"Do not farm the reticle in isolation."
    )

def build_session_plan(
    tasks: list[dict[str, Any]],
    preferred_mode: str,
    session_goal: str,
    motivation: str,
    available_minutes: int = 90,
    max_stops: int | None = None,
) -> dict[str, Any]:
    """
    Builds an ordered, ranked session plan within a single locked mode.

    Returns a dict with:
      - mode
      - stops: ordered list of {weapon/challenge, objective, progress, cluster_label}
      - cluster_summary: which clusters were pulled from and why
    """
    if max_stops is None:
        max_stops = stops_for_available_minutes(available_minutes)

    available = get_available_tasks(tasks)
    mode_tasks = [t for t in available if t.get("mode") == preferred_mode]

    if mode_major_collection_is_done(preferred_mode, tasks):
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
            )

    if not mode_tasks:
        return {
            "mode": preferred_mode,
            "available_minutes": available_minutes,
            "stops": [],
            "cluster_summary": [],
            "note": f"No available tasks found in {preferred_mode}.",
            "diagnostics": {
                "confidence": "Low",
                "confidence_score": 0,
                "rationale": [f"No available tasks found in {preferred_mode}."],
            },
        }

    clusters = build_clusters(
        tasks_in_mode=mode_tasks,
        preferred_mode=preferred_mode,
        session_goal=session_goal,
        motivation=motivation,
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
                    "estimated_minutes": estimated_minutes,
                    "stacking_hint": build_stacking_hint(task, available),
                }
            )

            estimated_used_minutes += estimated_minutes
 
    diagnostics = build_plan_diagnostics(
        preferred_mode=preferred_mode,
        mode_task_count=len(mode_tasks),
        clusters=clusters,
        stops=stops,
        max_stops=max_stops,
        available_minutes=available_minutes,
        session_goal=session_goal,
        motivation=motivation,
    )

    route_summary = build_route_summary(
        stops=stops,
        available_minutes=available_minutes,
    )

    return {
        "mode": preferred_mode,
        "available_minutes": available_minutes,
        "estimated_minutes": estimated_used_minutes,
        "stops": stops,
        "cluster_summary": cluster_summary,
        "note": "",
        "diagnostics": diagnostics,
        "route_summary": route_summary,
    }


def rebuild_plan_after_progress(
    tasks: list[dict[str, Any]],
    preferred_mode: str,
    session_goal: str,
    motivation: str,
    completed_task_ids: list[str],
    remaining_minutes: int,
) -> dict[str, Any]:
    """
    Called after logging progress mid-session. Re-runs build_session_plan()
    on the current task state (which already reflects the logged result),
    excluding anything just completed, and rescales stop count to whatever
    time is actually left. This is what gives the "dynamic" behaviour —
    if you only get through stop 1, the next call naturally re-ranks and
    re-sizes the plan based on what's actually left, rather than blindly
    continuing a stale list.
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
    )

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

    command = (
        f"Use {task['weapon']} / {task['camo']} in {task['mode']}. "
        f"Complete the assigned objective. No switching until the result is logged."
    )

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
        "why_this_target": (
            f"{task['weapon']} is {task['weapon_progress']:.2f}% through its current tracked route. "
            f"The commander selected it for: {session_goal}."
        ),
        "stacked_progress": f"{task['category']}, {task['chain']}, session footage, and overall 100% progress.",
        "fallback": "If the task is wrong, impossible, or blocked, log 'Blocked / wrong requirement'. Do not silently switch tasks.",
        "reward": "After completion, generate the next order. No free-choice match until the log is updated.",
        "next_if_completed": "Log completion, then generate the next highest-value unlocked task.",
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

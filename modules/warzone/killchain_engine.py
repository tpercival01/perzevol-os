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
        mastery_display = ["Golden Damascus", "Starglass", "Absolute Zero", "Apocalypse"]
        try:
            prefix = mastery_display[mastery.index(camo_name)]
        except (ValueError, IndexError):
            prefix = camo_name
        return f"{prefix}: {challenge}"

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
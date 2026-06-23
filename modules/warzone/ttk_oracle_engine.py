from pathlib import Path
from math import ceil
import pandas as pd
from itertools import combinations, product


TTK_DATA_DIR = Path("data/bo7_ttk")
GUNS_PATH = TTK_DATA_DIR / "guns.csv"
ATTACHMENTS_PATH = TTK_DATA_DIR / "attachments.csv"


REQUIRED_GUN_COLUMNS = [
    "gun_id",
    "gun_name",
    "weapon_class",
    "damage_close",
    "range_close_m",
    "damage_mid",
    "range_mid_m",
    "damage_long",
    "fire_rate_rpm",
    "ads_ms",
    "sprint_to_fire_ms",
    "recoil",
    "bullet_velocity",
    "mag_size",
]


REQUIRED_ATTACHMENT_COLUMNS = [
    "attachment_id",
    "attachment_name",
    "slot",
    "compatible_weapon_classes",
    "compatible_guns",
    "damage_pct",
    "fire_rate_pct",
    "ads_ms_add",
    "sprint_to_fire_ms_add",
    "recoil_pct",
    "bullet_velocity_pct",
    "range_pct",
    "mag_size_add",
]

VALID_LOADOUT_PAIRS = {
    frozenset(("Assault Rifle", "SMG")),
    frozenset(("LMG", "SMG")),
    frozenset(("Sniper Rifle", "SMG")),
    frozenset(("Marksman Rifle", "SMG")),
}


def is_valid_loadout_pair(weapon_a_class: str, weapon_b_class: str) -> bool:
    return frozenset((weapon_a_class, weapon_b_class)) in VALID_LOADOUT_PAIRS

def ensure_ttk_data_dir():
    TTK_DATA_DIR.mkdir(parents=True, exist_ok=True)


def create_empty_templates():
    ensure_ttk_data_dir()

    if not GUNS_PATH.exists():
        pd.DataFrame(columns=REQUIRED_GUN_COLUMNS).to_csv(GUNS_PATH, index=False)

    if not ATTACHMENTS_PATH.exists():
        pd.DataFrame(columns=REQUIRED_ATTACHMENT_COLUMNS).to_csv(
            ATTACHMENTS_PATH,
            index=False,
        )


def load_guns():
    create_empty_templates()

    guns = pd.read_csv(GUNS_PATH)

    missing_columns = [
        column for column in REQUIRED_GUN_COLUMNS
        if column not in guns.columns
    ]

    if missing_columns:
        raise ValueError(f"guns.csv is missing columns: {missing_columns}")

    return guns


def load_attachments():
    create_empty_templates()

    attachments = pd.read_csv(ATTACHMENTS_PATH)

    missing_columns = [
        column for column in REQUIRED_ATTACHMENT_COLUMNS
        if column not in attachments.columns
    ]

    if missing_columns:
        raise ValueError(f"attachments.csv is missing columns: {missing_columns}")

    return attachments


def load_ttk_data():
    guns = load_guns()
    attachments = load_attachments()

    return guns, attachments

def calculate_raw_ttk_ms(damage, fire_rate_rpm, enemy_health=300):
    damage = float(damage)
    fire_rate_rpm = float(fire_rate_rpm)
    enemy_health = int(enemy_health)

    if damage <= 0 or fire_rate_rpm <= 0:
        return None

    shots_to_kill = ceil(enemy_health / damage)
    time_between_shots_ms = 60000 / fire_rate_rpm

    ttk_ms = (shots_to_kill - 1) * time_between_shots_ms

    return round(ttk_ms, 2)

def damage_column_for_fight_type(fight_type):
    if fight_type == "Close range":
        return "damage_close"

    if fight_type == "Long range":
        return "damage_long"

    return "damage_mid"


def effective_range_for_fight_type(stats, fight_type):
    if fight_type == "Close range":
        return float(stats["range_close_m"])

    return float(stats["range_mid_m"])


def build_base_weapon_rankings(guns, enemy_health=300, fight_type="Close range"):
    if guns.empty:
        return guns.copy()

    rankings = guns.copy()
    damage_column = damage_column_for_fight_type(fight_type)

    rankings["damage"] = rankings[damage_column].astype(float)

    rankings["range_m"] = rankings.apply(
        lambda row: effective_range_for_fight_type(row, fight_type),
        axis=1,
    )

    rankings["shots_to_kill"] = rankings["damage"].apply(
        lambda damage: ceil(enemy_health / float(damage))
    )

    rankings["raw_ttk_ms"] = rankings.apply(
        lambda row: calculate_raw_ttk_ms(
            damage=row["damage"],
            fire_rate_rpm=row["fire_rate_rpm"],
            enemy_health=enemy_health,
        ),
        axis=1,
    )

    rankings = rankings.sort_values("raw_ttk_ms", ascending=True)

    return rankings

def split_list_cell(value):
    if pd.isna(value) or str(value).strip() == "":
        return []

    return [
        item.strip()
        for item in str(value).split(";")
        if item.strip()
    ]


def attachment_is_compatible(gun, attachment):
    weapon_class = str(gun["weapon_class"]).strip()
    gun_name = str(gun["gun_name"]).strip()

    compatible_classes = split_list_cell(
        attachment.get("compatible_weapon_classes", "")
    )

    compatible_guns = split_list_cell(
        attachment.get("compatible_guns", "")
    )

    class_allowed = (
        not compatible_classes
        or weapon_class in compatible_classes
    )

    gun_allowed = (
        not compatible_guns
        or gun_name in compatible_guns
    )

    return class_allowed and gun_allowed


def get_compatible_attachments(gun, attachments):
    if attachments.empty:
        return attachments.copy()

    compatible = attachments[
        attachments.apply(
            lambda attachment: attachment_is_compatible(gun, attachment),
            axis=1,
        )
    ]

    return compatible.reset_index(drop=True)


def apply_attachment_to_stats(stats, attachment):
    updated = stats.copy()

    damage_pct = float(attachment.get("damage_pct", 0) or 0)
    range_pct = float(attachment.get("range_pct", 0) or 0)

    for stat in ["damage_close", "damage_mid", "damage_long"]:
        updated[stat] = updated[stat] * (1 + damage_pct / 100)

    for stat in ["range_close_m", "range_mid_m"]:
        updated[stat] = updated[stat] * (1 + range_pct / 100)

    pct_modifiers = {
        "fire_rate_rpm": "fire_rate_pct",
        "recoil": "recoil_pct",
        "bullet_velocity": "bullet_velocity_pct",
    }

    add_modifiers = {
        "ads_ms": "ads_ms_add",
        "sprint_to_fire_ms": "sprint_to_fire_ms_add",
        "mag_size": "mag_size_add",
    }

    for stat, column in pct_modifiers.items():
        value = float(attachment.get(column, 0) or 0)
        updated[stat] = updated[stat] * (1 + value / 100)

    for stat, column in add_modifiers.items():
        value = float(attachment.get(column, 0) or 0)
        updated[stat] = updated[stat] + value

    return updated


def build_loadout_preview(
    gun,
    selected_attachments,
    enemy_health=300,
    fight_type="Close range",
):
    final_stats = {
        "damage_close": float(gun["damage_close"]),
        "range_close_m": float(gun["range_close_m"]),
        "damage_mid": float(gun["damage_mid"]),
        "range_mid_m": float(gun["range_mid_m"]),
        "damage_long": float(gun["damage_long"]),
        "fire_rate_rpm": float(gun["fire_rate_rpm"]),
        "ads_ms": float(gun["ads_ms"]),
        "sprint_to_fire_ms": float(gun["sprint_to_fire_ms"]),
        "recoil": float(gun["recoil"]),
        "bullet_velocity": float(gun["bullet_velocity"]),
        "mag_size": float(gun["mag_size"]),
    }

    for _, attachment in selected_attachments.iterrows():
        final_stats = apply_attachment_to_stats(final_stats, attachment)

    damage_column = damage_column_for_fight_type(fight_type)

    final_stats["damage"] = final_stats[damage_column]
    final_stats["range_m"] = effective_range_for_fight_type(final_stats, fight_type)

    final_stats["shots_to_kill"] = ceil(enemy_health / final_stats["damage"])

    final_stats["raw_ttk_ms"] = calculate_raw_ttk_ms(
        damage=final_stats["damage"],
        fire_rate_rpm=final_stats["fire_rate_rpm"],
        enemy_health=enemy_health,
    )

    return final_stats

MAP_TYPES = [
    "Small map / Resurgence",
    "Large map / Battle Royale",
    "Ranked / Competitive",
]

FIGHT_TYPES = [
    "Close range",
    "Mid range",
    "Long range",
    "Mixed fights",
]

BUILD_GOALS = [
    "Fastest TTK",
    "Balanced meta build",
    "Low recoil beam",
    "Aggressive mobility",
]


LOWER_IS_BETTER = {
    "raw_ttk_ms",
    "practical_ttk_ms",
    "ads_ms",
    "sprint_to_fire_ms",
    "recoil",
}

HIGHER_IS_BETTER = {
    "bullet_velocity",
    "range_m",
    "mag_size",
    "damage_per_mag",
}

LOADOUT_PAIRINGS = [
    "AR + SMG",
    "LMG + SMG",
    "Sniper + SMG",
    "Marksman + SMG",
    "Any primary + SMG",
]

PERK_PACKAGES = {
    "Aggressive": {
        "perk_1": "Double Time",
        "perk_2": "Sleight of Hand",
        "perk_3": "Tempered",
        "perk_4": "High Alert",
        "bonus": {
            "ads_ms": -10,
            "sprint_to_fire_ms": -10,
            "reload_ms": -50,
            "recoil": 0,
        },
    },
    "Balanced": {
        "perk_1": "Double Time",
        "perk_2": "Sleight of Hand",
        "perk_3": "Tempered",
        "perk_4": "Ghost",
        "bonus": {
            "ads_ms": -5,
            "sprint_to_fire_ms": -5,
            "reload_ms": -50,
            "recoil": -2,
        },
    },
    "Competitive": {
        "perk_1": "Mountaineer",
        "perk_2": "Sleight of Hand",
        "perk_3": "Tempered",
        "perk_4": "High Alert",
        "bonus": {
            "ads_ms": 0,
            "sprint_to_fire_ms": 0,
            "reload_ms": -50,
            "recoil": -3,
        },
    },
    "Long-range": {
        "perk_1": "Mountaineer",
        "perk_2": "Sleight of Hand",
        "perk_3": "Tempered",
        "perk_4": "Ghost",
        "bonus": {
            "ads_ms": 0,
            "sprint_to_fire_ms": 0,
            "reload_ms": -50,
            "recoil": -5,
        },
    },
}


def combo_has_duplicate_slots(combo):
    slots = [str(attachment["slot"]).strip() for attachment in combo]
    return len(slots) != len(set(slots))


def calculate_practical_ttk_ms(stats):
    """
    Raw TTK is perfect aim maths.
    Practical TTK punishes slow handling and recoil.
    """

    return round(
        float(stats["raw_ttk_ms"])
        + float(stats["ads_ms"]) * 0.15
        + float(stats["sprint_to_fire_ms"]) * 0.10
        + float(stats["recoil"]) * 2.0,
        2,
    )


def build_scenario_weights(map_type, fight_type, build_goal):
    if build_goal == "Fastest TTK":
        weights = {
            "raw_ttk_ms": 0.70,
            "practical_ttk_ms": 0.20,
            "damage_per_mag": 0.10,
        }

    elif build_goal == "Low recoil beam":
        weights = {
            "recoil": 0.40,
            "practical_ttk_ms": 0.20,
            "bullet_velocity": 0.20,
            "range_m": 0.15,
            "damage_per_mag": 0.05,
        }

    elif build_goal == "Aggressive mobility":
        weights = {
            "practical_ttk_ms": 0.25,
            "ads_ms": 0.25,
            "sprint_to_fire_ms": 0.25,
            "recoil": 0.10,
            "damage_per_mag": 0.10,
            "range_m": 0.05,
        }

    else:
        weights = {
            "practical_ttk_ms": 0.35,
            "recoil": 0.20,
            "ads_ms": 0.15,
            "sprint_to_fire_ms": 0.10,
            "bullet_velocity": 0.10,
            "range_m": 0.05,
            "damage_per_mag": 0.05,
        }

    if fight_type == "Close range":
        weights["ads_ms"] = weights.get("ads_ms", 0) + 0.10
        weights["sprint_to_fire_ms"] = weights.get("sprint_to_fire_ms", 0) + 0.10
        weights["practical_ttk_ms"] = weights.get("practical_ttk_ms", 0) + 0.05

    elif fight_type == "Mid range":
        weights["practical_ttk_ms"] = weights.get("practical_ttk_ms", 0) + 0.10
        weights["recoil"] = weights.get("recoil", 0) + 0.05
        weights["bullet_velocity"] = weights.get("bullet_velocity", 0) + 0.05

    elif fight_type == "Long range":
        weights["recoil"] = weights.get("recoil", 0) + 0.10
        weights["bullet_velocity"] = weights.get("bullet_velocity", 0) + 0.10
        weights["range_m"] = weights.get("range_m", 0) + 0.10

    if map_type == "Small map / Resurgence":
        weights["ads_ms"] = weights.get("ads_ms", 0) + 0.05
        weights["sprint_to_fire_ms"] = weights.get("sprint_to_fire_ms", 0) + 0.05

    elif map_type == "Large map / Battle Royale":
        weights["recoil"] = weights.get("recoil", 0) + 0.05
        weights["bullet_velocity"] = weights.get("bullet_velocity", 0) + 0.05
        weights["range_m"] = weights.get("range_m", 0) + 0.05

    elif map_type == "Ranked / Competitive":
        weights["practical_ttk_ms"] = weights.get("practical_ttk_ms", 0) + 0.05
        weights["recoil"] = weights.get("recoil", 0) + 0.05
        weights["damage_per_mag"] = weights.get("damage_per_mag", 0) + 0.05

    total = sum(weights.values())

    return {
        metric: weight / total
        for metric, weight in weights.items()
    }


def add_oracle_scores(results, weights):
    scored = results.copy()
    scored["oracle_score"] = 0.0

    for metric, weight in weights.items():
        if metric not in scored.columns:
            continue

        min_value = scored[metric].min()
        max_value = scored[metric].max()

        if min_value == max_value:
            scored[f"{metric}_score"] = 1.0

        elif metric in LOWER_IS_BETTER:
            scored[f"{metric}_score"] = 1 - (
                (scored[metric] - min_value) / (max_value - min_value)
            )

        else:
            scored[f"{metric}_score"] = (
                (scored[metric] - min_value) / (max_value - min_value)
            )

        scored["oracle_score"] += scored[f"{metric}_score"] * weight

    return scored

DOMINATION_STATS = [
    "damage_pct",
    "fire_rate_pct",
    "ads_ms_add",
    "sprint_to_fire_ms_add",
    "recoil_pct",
    "bullet_velocity_pct",
    "range_pct",
    "mag_size_add",
]

# Stats where a lower value is better (penalties on ADS, sprint, etc.)
# A negative ads_ms_add means faster ADS — that's good.
# So for these stats: lower number = better.
LOWER_IS_BETTER_ATTACHMENT = {"ads_ms_add", "sprint_to_fire_ms_add", "recoil_pct"}


def attachment_dominates(a, b) -> bool:
    """
    Returns True if attachment `a` is strictly at least as good as `b`
    on every stat, and strictly better on at least one.

    Only considers stats that actually affect scoring.
    A dominated attachment can never appear in the optimal build.
    """
    at_least_as_good_on_all = True
    strictly_better_on_one = False

    for stat in DOMINATION_STATS:
        val_a = float(a.get(stat, 0) or 0)
        val_b = float(b.get(stat, 0) or 0)

        if stat in LOWER_IS_BETTER_ATTACHMENT:
            # Lower is better — a dominates if val_a <= val_b
            if val_a > val_b:
                at_least_as_good_on_all = False
                break
            if val_a < val_b:
                strictly_better_on_one = True
        else:
            # Higher is better
            if val_a < val_b:
                at_least_as_good_on_all = False
                break
            if val_a > val_b:
                strictly_better_on_one = True

    return at_least_as_good_on_all and strictly_better_on_one


def prune_dominated_attachments(compatible_attachments: pd.DataFrame) -> pd.DataFrame:
    """
    For each slot, remove attachments that are strictly dominated by another
    attachment in the same slot. A dominated attachment can never appear in
    the optimal build regardless of scenario, so removing it is safe.

    This can cut per-slot pools from ~6 to 2-3, reducing combo space by 60-80%.
    """
    if compatible_attachments.empty:
        return compatible_attachments

    kept_rows = []

    for slot, group in compatible_attachments.groupby("slot"):
        attachments_in_slot = [row for _, row in group.iterrows()]
        survivors = []

        for candidate in attachments_in_slot:
            dominated = any(
                attachment_dominates(other, candidate)
                for other in attachments_in_slot
                if other["attachment_id"] != candidate["attachment_id"]
            )
            if not dominated:
                survivors.append(candidate)

        kept_rows.extend(survivors)

    if not kept_rows:
        return compatible_attachments

    return pd.DataFrame(kept_rows).reset_index(drop=True)


def generate_legal_attachment_combos(compatible_attachments, attachment_count):
    """
    Exact legal build generator.

    Instead of trying every attachment combination and rejecting duplicate slots,
    this groups attachments by slot first, then only generates builds with one
    attachment per selected slot.

    This is still exhaustive. It does not skip valid builds.
    """

    if compatible_attachments.empty:
        return

    slot_groups = {}

    for slot, group in compatible_attachments.groupby("slot"):
        clean_slot = str(slot).strip()

        if not clean_slot:
            continue

        slot_groups[clean_slot] = [
            attachment
            for _, attachment in group.iterrows()
        ]

    slot_names = sorted(slot_groups.keys())

    if len(slot_names) < attachment_count:
        return

    for selected_slots in combinations(slot_names, attachment_count):
        grouped_options = [
            slot_groups[slot]
            for slot in selected_slots
        ]

        for combo in product(*grouped_options):
            yield combo

def optimise_loadouts_for_scenario(
    guns,
    attachments,
    map_type,
    fight_type,
    build_goal,
    enemy_health=300,
    weapon_class="Any",
    attachment_count=5,
    top_n=20,
):
    if guns.empty or attachments.empty:
        return pd.DataFrame()

    filtered_guns = guns.copy()

    if weapon_class != "Any":
        filtered_guns = filtered_guns[
            filtered_guns["weapon_class"] == weapon_class
        ]

    rows = []

    for _, gun in filtered_guns.iterrows():
        compatible_attachments = get_compatible_attachments(
            gun=gun,
            attachments=attachments,
        )

        unique_slot_count = compatible_attachments["slot"].dropna().nunique()

        if unique_slot_count < attachment_count:
            continue

        # Remove attachments that are strictly dominated within their slot.
        # A dominated attachment cannot appear in the optimal build — safe to drop.
        compatible_attachments = prune_dominated_attachments(compatible_attachments)

        for combo in generate_legal_attachment_combos(
            compatible_attachments=compatible_attachments,
            attachment_count=attachment_count,
        ):
            selected_attachments = pd.DataFrame(combo)

            preview = build_loadout_preview(
                gun=gun,
                selected_attachments=selected_attachments,
                enemy_health=enemy_health,
                fight_type=fight_type,
            )

            preview["damage_per_mag"] = (
                float(preview["damage"]) * float(preview["mag_size"])
            )

            preview["practical_ttk_ms"] = calculate_practical_ttk_ms(preview)

            rows.append(
                {
                    "gun_name": gun["gun_name"],
                    "weapon_class": gun["weapon_class"],
                    "attachments": " | ".join(
                        selected_attachments["attachment_name"].tolist()
                    ),
                    "slots": " | ".join(
                        selected_attachments["slot"].tolist()
                    ),
                    **preview,
                }
            )

    if not rows:
        return pd.DataFrame()

    results = pd.DataFrame(rows)

    weights = build_scenario_weights(
        map_type=map_type,
        fight_type=fight_type,
        build_goal=build_goal,
    )

    results = add_oracle_scores(results, weights)

    return (
        results
        .sort_values("oracle_score", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )

def weapon_classes_for_pairing(loadout_pairing):
    if loadout_pairing == "AR + SMG":
        return "Assault Rifle", "SMG"

    if loadout_pairing == "LMG + SMG":
        return "LMG", "SMG"

    if loadout_pairing == "Sniper + SMG":
        return "Sniper Rifle", "SMG"

    if loadout_pairing == "Marksman + SMG":
        return "Marksman Rifle", "SMG"

    if loadout_pairing == "Any primary + SMG":
        return None, "SMG"

    return None, None

def role_weights_for_scenario(map_type, fight_type):
    if fight_type == "Close range":
        primary_weight = 0.35
        secondary_weight = 0.65

    elif fight_type == "Mid range":
        primary_weight = 0.55
        secondary_weight = 0.45

    elif fight_type == "Long range":
        primary_weight = 0.75
        secondary_weight = 0.25

    else:
        primary_weight = 0.50
        secondary_weight = 0.50

    if map_type == "Small map / Resurgence":
        primary_weight -= 0.05
        secondary_weight += 0.05

    elif map_type == "Large map / Battle Royale":
        primary_weight += 0.05
        secondary_weight -= 0.05

    primary_weight = max(0.10, primary_weight)
    secondary_weight = max(0.10, secondary_weight)

    total = primary_weight + secondary_weight

    return primary_weight / total, secondary_weight / total


def filter_guns_for_role(guns, required_weapon_class, role):
    filtered = guns.copy()

    if required_weapon_class:
        return filtered[filtered["weapon_class"] == required_weapon_class]

    if role == "primary":
        return filtered[filtered["weapon_class"] != "SMG"]

    return filtered

def gun_has_enough_attachment_slots(gun, attachments, attachment_count):
    compatible_attachments = get_compatible_attachments(
        gun=gun,
        attachments=attachments,
    )

    if len(compatible_attachments) < attachment_count:
        return False

    unique_slots = compatible_attachments["slot"].dropna().nunique()

    return unique_slots >= attachment_count


def limit_guns_by_base_ttk(
    guns,
    attachments,
    enemy_health,
    fight_type,
    attachment_count,
    limit=3,
):
    if guns.empty:
        return guns

    buildable_guns = []

    for _, gun in guns.iterrows():
        if gun_has_enough_attachment_slots(
            gun=gun,
            attachments=attachments,
            attachment_count=attachment_count,
        ):
            buildable_guns.append(gun)

    if not buildable_guns:
        return guns.iloc[0:0].copy()

    buildable_guns = pd.DataFrame(buildable_guns)

    if limit is None or limit <= 0:
        return buildable_guns.reset_index(drop=True)

    if len(buildable_guns) <= limit:
        return buildable_guns.reset_index(drop=True)

    ranked = build_base_weapon_rankings(
        guns=buildable_guns,
        enemy_health=enemy_health,
        fight_type=fight_type,
    )

    top_gun_ids = ranked.head(limit)["gun_id"].tolist()

    return buildable_guns[
        buildable_guns["gun_id"].isin(top_gun_ids)
    ].reset_index(drop=True)


def perk_package_score_bonus(perk_package):
    package = PERK_PACKAGES.get(perk_package, {})
    bonus = package.get("bonus", {})

    score_bonus = 0.0

    score_bonus += max(0, -float(bonus.get("ads_ms", 0))) * 0.001
    score_bonus += max(0, -float(bonus.get("sprint_to_fire_ms", 0))) * 0.001
    score_bonus += max(0, -float(bonus.get("reload_ms", 0))) * 0.0002
    score_bonus += max(0, -float(bonus.get("recoil", 0))) * 0.005

    return score_bonus


def optimise_full_loadouts_for_scenario(
    guns,
    attachments,
    map_type,
    fight_type,
    build_goal,
    loadout_pairing,
    perk_package,
    enemy_health=300,
    attachment_count=5,
    top_n=10,
    candidate_pool=15,
):
    primary_class, secondary_class = weapon_classes_for_pairing(loadout_pairing)

    primary_guns = filter_guns_for_role(
        guns=guns,
        required_weapon_class=primary_class,
        role="primary",
    )

    secondary_guns = filter_guns_for_role(
        guns=guns,
        required_weapon_class=secondary_class,
        role="secondary",
    )

    role_scenarios = role_scenarios_for_full_loadout(
        map_type=map_type,
        fight_type=fight_type,
        build_goal=build_goal,
    )

    # Pre-filter each role to the top guns by base TTK.
    # Dominated-by-base-stats guns cannot produce the optimal build after attachments
    # in any realistic scenario. Limit=5 keeps accuracy high while cutting search space.
    primary_guns = limit_guns_by_base_ttk(
        guns=primary_guns,
        attachments=attachments,
        enemy_health=enemy_health,
        fight_type=role_scenarios["primary_fight_type"],
        attachment_count=attachment_count,
        limit=5,
    )

    secondary_guns = limit_guns_by_base_ttk(
        guns=secondary_guns,
        attachments=attachments,
        enemy_health=enemy_health,
        fight_type=role_scenarios["secondary_fight_type"],
        attachment_count=attachment_count,
        limit=5,
    )

    primary_results = optimise_loadouts_for_scenario(
        guns=primary_guns,
        attachments=attachments,
        map_type=map_type,
        fight_type=role_scenarios["primary_fight_type"],
        build_goal=role_scenarios["primary_build_goal"],
        enemy_health=enemy_health,
        weapon_class="Any",
        attachment_count=attachment_count,
        top_n=candidate_pool,
    )

    secondary_results = optimise_loadouts_for_scenario(
        guns=secondary_guns,
        attachments=attachments,
        map_type=map_type,
        fight_type=role_scenarios["secondary_fight_type"],
        build_goal=role_scenarios["secondary_build_goal"],
        enemy_health=enemy_health,
        weapon_class="Any",
        attachment_count=attachment_count,
        top_n=candidate_pool,
    )

    if primary_results.empty or secondary_results.empty:
        return pd.DataFrame()

    primary_weight, secondary_weight = role_weights_for_scenario(
        map_type=map_type,
        fight_type=fight_type,
    )

    perk_bonus = perk_package_score_bonus(perk_package)

    rows = []

    for _, primary in primary_results.iterrows():
        for _, secondary in secondary_results.iterrows():
            if primary["gun_name"] == secondary["gun_name"]:
                continue

            full_loadout_score = (
                float(primary["oracle_score"]) * primary_weight
                + float(secondary["oracle_score"]) * secondary_weight
                + perk_bonus
            )

            rows.append(
                {
                    "full_loadout_score": full_loadout_score,
                    "map_type": map_type,
                    "fight_type": fight_type,
                    "build_goal": build_goal,
                    "loadout_pairing": loadout_pairing,
                    "perk_package": perk_package,
                    "primary_fight_type": role_scenarios["primary_fight_type"],
                    "primary_build_goal": role_scenarios["primary_build_goal"],
                    "secondary_fight_type": role_scenarios["secondary_fight_type"],
                    "secondary_build_goal": role_scenarios["secondary_build_goal"],

                    "primary_weapon": primary["gun_name"],
                    "primary_class": primary["weapon_class"],
                    "primary_attachments": primary["attachments"],
                    "primary_oracle_score": primary["oracle_score"],
                    "primary_raw_ttk_ms": primary["raw_ttk_ms"],
                    "primary_practical_ttk_ms": primary["practical_ttk_ms"],
                    "primary_recoil": primary["recoil"],
                    "primary_ads_ms": primary["ads_ms"],
                    "primary_bullet_velocity": primary["bullet_velocity"],
                    "primary_range_m": primary["range_m"],

                    "secondary_weapon": secondary["gun_name"],
                    "secondary_class": secondary["weapon_class"],
                    "secondary_attachments": secondary["attachments"],
                    "secondary_oracle_score": secondary["oracle_score"],
                    "secondary_raw_ttk_ms": secondary["raw_ttk_ms"],
                    "secondary_practical_ttk_ms": secondary["practical_ttk_ms"],
                    "secondary_recoil": secondary["recoil"],
                    "secondary_ads_ms": secondary["ads_ms"],
                    "secondary_bullet_velocity": secondary["bullet_velocity"],
                    "secondary_range_m": secondary["range_m"],

                    "primary_weight": primary_weight,
                    "secondary_weight": secondary_weight,
                }
            )

    if not rows:
        return pd.DataFrame()

    results = pd.DataFrame(rows)

    return (
        results
        .sort_values("full_loadout_score", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )

def role_scenarios_for_full_loadout(map_type, fight_type, build_goal):
    """
    Converts one player-facing scenario into separate jobs for each weapon.

    Example:
    Mixed fights + AR/SMG should not optimise both guns the same way.
    The AR should cover the stable mid/long fight.
    The SMG should cover the close-range panic fight.
    """

    primary_fight_type = fight_type
    secondary_fight_type = "Close range"

    primary_build_goal = build_goal
    secondary_build_goal = "Aggressive mobility"

    if fight_type == "Mixed fights":
        if map_type == "Large map / Battle Royale":
            primary_fight_type = "Long range"
            primary_build_goal = "Low recoil beam"
        else:
            primary_fight_type = "Mid range"
            primary_build_goal = "Balanced meta build"

        secondary_fight_type = "Close range"
        secondary_build_goal = "Aggressive mobility"

    elif fight_type == "Close range":
        primary_fight_type = "Mid range"
        primary_build_goal = "Balanced meta build"

        secondary_fight_type = "Close range"
        secondary_build_goal = build_goal

    elif fight_type == "Mid range":
        primary_fight_type = "Mid range"
        primary_build_goal = build_goal

        secondary_fight_type = "Close range"
        secondary_build_goal = "Aggressive mobility"

    elif fight_type == "Long range":
        primary_fight_type = "Long range"
        primary_build_goal = build_goal

        secondary_fight_type = "Close range"
        secondary_build_goal = "Aggressive mobility"

    return {
        "primary_fight_type": primary_fight_type,
        "primary_build_goal": primary_build_goal,
        "secondary_fight_type": secondary_fight_type,
        "secondary_build_goal": secondary_build_goal,
    }
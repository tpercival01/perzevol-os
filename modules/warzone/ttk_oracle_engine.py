from pathlib import Path
from math import ceil
import re
from html import unescape
import pandas as pd
from itertools import combinations, product


TTK_DATA_DIR = Path("data/bo7_ttk")
GUNS_PATH = TTK_DATA_DIR / "guns.csv"
ATTACHMENTS_PATH = TTK_DATA_DIR / "attachments.csv"

DEFAULT_STATS_PROFILE = "Multiplayer"
LEGACY_STATS_PROFILE = "Multiplayer"
SUPPORTED_STATS_PROFILES = [
    "Warzone",
    "Multiplayer",
    "Zombies",
    "Co-Op / Endgame",
]


REQUIRED_GUN_COLUMNS = [
    "gun_id",
    "gun_name",
    "weapon_class",
    "stats_profile",
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
    "stats_profile",
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

# Extended columns are optional for backwards compatibility with the current CSV.
# They let the Oracle store Codmunity-style percentage modifiers without
# manually converting each one into fixed millisecond deltas.
OPTIONAL_ATTACHMENT_COLUMNS = [
    "ads_pct",
    "sprint_to_fire_pct",
    "reload_pct",
    "jump_ads_pct",
    "jump_sprint_to_fire_pct",
    "movement_pct",
    "sprint_pct",
    "crouch_movement_pct",
    "ads_movement_pct",
    "gun_kick_pct",
    "horizontal_recoil_pct",
    "vertical_recoil_pct",
    "first_shot_recoil_pct",
    "kick_reset_speed_pct",
    "flinch_resistance_pct",
    "raw_stat_text",
    "source",
    "source_date",
    "verification_status",
    "verification_notes",
]

EXTENDED_ATTACHMENT_COLUMNS = REQUIRED_ATTACHMENT_COLUMNS + [
    column for column in OPTIONAL_ATTACHMENT_COLUMNS
    if column not in REQUIRED_ATTACHMENT_COLUMNS
]

ATTACHMENT_NUMERIC_COLUMNS = {
    "damage_pct",
    "fire_rate_pct",
    "ads_ms_add",
    "sprint_to_fire_ms_add",
    "recoil_pct",
    "bullet_velocity_pct",
    "range_pct",
    "mag_size_add",
    "ads_pct",
    "sprint_to_fire_pct",
    "reload_pct",
    "jump_ads_pct",
    "jump_sprint_to_fire_pct",
    "movement_pct",
    "sprint_pct",
    "crouch_movement_pct",
    "ads_movement_pct",
    "gun_kick_pct",
    "horizontal_recoil_pct",
    "vertical_recoil_pct",
    "first_shot_recoil_pct",
    "kick_reset_speed_pct",
    "flinch_resistance_pct",
}


# Columns that are actually modelled by the optimiser.
# Rows with no modelled effect are useful for data entry, but must not be
# allowed into "best build" output as if they were proven.
MODELLED_ATTACHMENT_EFFECT_COLUMNS = [
    "damage_pct",
    "fire_rate_pct",
    "ads_ms_add",
    "sprint_to_fire_ms_add",
    "recoil_pct",
    "bullet_velocity_pct",
    "range_pct",
    "mag_size_add",
    "ads_pct",
    "sprint_to_fire_pct",
    "reload_pct",
    "jump_ads_pct",
    "jump_sprint_to_fire_pct",
    "movement_pct",
    "sprint_pct",
    "crouch_movement_pct",
    "ads_movement_pct",
    "gun_kick_pct",
    "horizontal_recoil_pct",
    "vertical_recoil_pct",
    "first_shot_recoil_pct",
    "kick_reset_speed_pct",
    "flinch_resistance_pct",
]

UNMODELLED_ATTACHMENT_NAME_HINTS = {
    "akimbo",
    "slug",
    "launcher kit",
    "conversion",
    "kit",
}

BLOCKED_VERIFICATION_STATUSES = {
    "exclude",
    "excluded",
    "invalid",
    "broken",
    "do_not_use",
    "unmodelled",
    "conversion_unmodelled",
}

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
        pd.DataFrame(columns=EXTENDED_ATTACHMENT_COLUMNS).to_csv(
            ATTACHMENTS_PATH,
            index=False,
        )


def numeric_cell(value, fallback: float = 0.0) -> float:
    if pd.isna(value):
        return fallback

    text = str(value).strip().replace("%", "").replace(",", "")

    if text == "":
        return fallback

    try:
        return float(text)
    except ValueError:
        return fallback


def normalise_numeric_columns(dataframe: pd.DataFrame, columns: set[str]) -> pd.DataFrame:
    updated = dataframe.copy()

    for column in columns:
        if column in updated.columns:
            updated[column] = updated[column].apply(lambda value: numeric_cell(value, 0.0))

    return updated


def normalise_stats_profile(value, fallback: str = LEGACY_STATS_PROFILE) -> str:
    text = str(value or "").strip()

    if not text:
        return fallback

    aliases = {
        "wz": "Warzone",
        "warzone": "Warzone",
        "mp": "Multiplayer",
        "multiplayer": "Multiplayer",
        "zombies": "Zombies",
        "zm": "Zombies",
        "coop": "Co-Op / Endgame",
        "co-op": "Co-Op / Endgame",
        "co-op / endgame": "Co-Op / Endgame",
        "endgame": "Co-Op / Endgame",
    }

    return aliases.get(text.lower(), text)


def ensure_profile_column(dataframe: pd.DataFrame, fallback: str = LEGACY_STATS_PROFILE) -> pd.DataFrame:
    updated = dataframe.copy()

    if "stats_profile" not in updated.columns:
        updated["stats_profile"] = fallback

    updated["stats_profile"] = updated["stats_profile"].apply(
        lambda value: normalise_stats_profile(value, fallback)
    )

    return updated


def filter_ttk_data_by_profile(
    guns: pd.DataFrame,
    attachments: pd.DataFrame,
    stats_profile: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    profile = normalise_stats_profile(stats_profile, DEFAULT_STATS_PROFILE)

    filtered_guns = ensure_profile_column(guns, LEGACY_STATS_PROFILE)
    filtered_attachments = ensure_profile_column(attachments, LEGACY_STATS_PROFILE)

    filtered_guns = filtered_guns[filtered_guns["stats_profile"] == profile].reset_index(drop=True)
    filtered_attachments = filtered_attachments[filtered_attachments["stats_profile"] == profile].reset_index(drop=True)

    return filtered_guns, filtered_attachments


def ensure_attachment_columns(attachments: pd.DataFrame) -> pd.DataFrame:
    updated = attachments.copy()

    for column in EXTENDED_ATTACHMENT_COLUMNS:
        if column not in updated.columns:
            updated[column] = 0.0 if column in ATTACHMENT_NUMERIC_COLUMNS else ""

    return normalise_numeric_columns(updated, ATTACHMENT_NUMERIC_COLUMNS)


def slugify(value: str) -> str:
    value = unescape(str(value or "").strip()).lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", str(value or ""))
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def load_guns():
    create_empty_templates()

    guns = pd.read_csv(GUNS_PATH)
    guns = ensure_profile_column(guns, LEGACY_STATS_PROFILE)

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
    attachments = ensure_profile_column(attachments, LEGACY_STATS_PROFILE)

    missing_columns = [
        column for column in REQUIRED_ATTACHMENT_COLUMNS
        if column not in attachments.columns
    ]

    if missing_columns:
        raise ValueError(f"attachments.csv is missing columns: {missing_columns}")

    return ensure_attachment_columns(attachments)


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

def is_headshot_build_goal(build_goal: str = "") -> bool:
    text = normalise_match_value(build_goal)
    return "headshot" in text or "military camo" in text


def damage_column_for_fight_type(fight_type, build_goal: str = ""):
    use_head_damage = is_headshot_build_goal(build_goal)
    prefix = "head_damage_" if use_head_damage else "damage_"

    if fight_type == "Close range":
        return f"{prefix}close"

    if fight_type == "Long range":
        return f"{prefix}long"

    return f"{prefix}mid"


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

    shotgun_metrics = rankings.apply(
        lambda row: shotgun_truth_metrics(row.to_dict(), enemy_health=enemy_health, fight_type=fight_type)
        if is_shotgun_weapon_class(row.get("weapon_class", ""))
        else default_shotgun_truth_metrics(),
        axis=1,
    )

    for column in SHOTGUN_TRUTH_COLUMNS:
        rankings[column] = shotgun_metrics.apply(lambda data: data.get(column, ""))

    rankings["practical_ttk_ms"] = rankings.apply(
        lambda row: calculate_practical_ttk_ms(row.to_dict()),
        axis=1,
    )

    rankings = rankings.sort_values("practical_ttk_ms", ascending=True)

    return rankings

def split_list_cell(value):
    if pd.isna(value) or str(value).strip() == "":
        return []

    return [
        item.strip()
        for item in str(value).split(";")
        if item.strip()
    ]


def normalise_match_value(value):
    return str(value or "").strip().lower()


def normalise_match_key(value):
    """
    Compatibility matching should not fail because one source says SG12 and
    another says SG-12. The display name stays untouched, this key is only for
    matching CSV compatibility cells.
    """
    return re.sub(r"[^a-z0-9]+", "", normalise_match_value(value))


WEAPON_CLASS_ALIASES = {
    "ar": "assaultrifle",
    "ars": "assaultrifle",
    "assaultrifles": "assaultrifle",
    "smg": "smg",
    "smgs": "smg",
    "submachinegun": "smg",
    "submachineguns": "smg",
    "lmg": "lmg",
    "lmgs": "lmg",
    "shotgun": "shotgun",
    "shotguns": "shotgun",
    "sniperrifle": "sniperrifle",
    "sniperrifles": "sniperrifle",
    "marksmanrifle": "marksmanrifle",
    "marksmanrifles": "marksmanrifle",
    "pistol": "pistol",
    "pistols": "pistol",
    "launcher": "launcher",
    "launchers": "launcher",
    "special": "special",
    "specials": "special",
    "melee": "melee",
}


def normalise_weapon_class_key(value):
    key = normalise_match_key(value)
    return WEAPON_CLASS_ALIASES.get(key, key)


def matches_compatible_value(actual, allowed_values, *, weapon_class=False):
    if not allowed_values:
        return True

    if weapon_class:
        actual_key = normalise_weapon_class_key(actual)
        allowed_keys = {normalise_weapon_class_key(item) for item in allowed_values}
    else:
        actual_key = normalise_match_key(actual)
        allowed_keys = {normalise_match_key(item) for item in allowed_values}

    return actual_key in allowed_keys


def attachment_is_compatible(gun, attachment):
    gun_profile = normalise_stats_profile(gun.get("stats_profile", LEGACY_STATS_PROFILE), LEGACY_STATS_PROFILE)
    attachment_profile = normalise_stats_profile(attachment.get("stats_profile", LEGACY_STATS_PROFILE), LEGACY_STATS_PROFILE)

    if gun_profile != attachment_profile:
        return False

    weapon_class = str(gun["weapon_class"]).strip()
    gun_name = str(gun["gun_name"]).strip()

    compatible_classes = split_list_cell(
        attachment.get("compatible_weapon_classes", "")
    )

    compatible_guns = split_list_cell(
        attachment.get("compatible_guns", "")
    )

    class_allowed = matches_compatible_value(
        weapon_class,
        compatible_classes,
        weapon_class=True,
    )

    gun_allowed = matches_compatible_value(
        gun_name,
        compatible_guns,
        weapon_class=False,
    )

    return class_allowed and gun_allowed


def attachment_modelled_effect_count(attachment) -> int:
    return sum(
        1
        for column in MODELLED_ATTACHMENT_EFFECT_COLUMNS
        if abs(numeric_cell(attachment.get(column, 0), 0.0)) > 0
    )


def attachment_modelled_effect_summary(attachment) -> str:
    parts = []

    for column in MODELLED_ATTACHMENT_EFFECT_COLUMNS:
        value = numeric_cell(attachment.get(column, 0), 0.0)
        if value == 0:
            continue

        label = column.replace("_pct", "%").replace("_add", "").replace("_", " ")
        suffix = "%" if column.endswith("_pct") else ""
        parts.append(f"{label}: {value:g}{suffix}")

    return " | ".join(parts)


def attachment_has_unmodelled_name_hint(attachment) -> bool:
    name = normalise_match_value(attachment.get("attachment_name", ""))
    return any(hint in name for hint in UNMODELLED_ATTACHMENT_NAME_HINTS)


def attachment_is_blocked_for_oracle(attachment) -> bool:
    status = normalise_match_value(attachment.get("verification_status", ""))
    if status in BLOCKED_VERIFICATION_STATUSES:
        return True

    return attachment_has_unmodelled_name_hint(attachment)


def attachment_is_neutral_oracle_filler(attachment) -> bool:
    """
    Allows a verified zero-stat optic to fill the extra Gunfighter slot.

    Normal zero-effect rows are still excluded. This exception is needed because
    Multiplayer Gunfighter can produce a valid 8-attachment class where the
    optic is a real attachment but has no measurable TTK/stat delta.
    """
    slot = normalise_match_value(attachment.get("slot", ""))
    status = normalise_match_value(attachment.get("verification_status", ""))

    return slot == "optic" and status in {"neutral", "verified_neutral", "verified"}


def attachment_is_modelled_for_oracle(attachment) -> bool:
    if attachment_is_blocked_for_oracle(attachment):
        return False

    if attachment_modelled_effect_count(attachment) > 0:
        return True

    return attachment_is_neutral_oracle_filler(attachment)


def prepare_oracle_attachment_pool(compatible_attachments: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only attachments with a modelled effect for optimiser output.

    Zero-effect rows are still valid CSV inventory, but including them in a
    brute-force optimiser creates fake confidence and random-looking builds.
    Conversion-style rows such as slugs, akimbo, and launcher kits are also
    blocked until their changed damage model is entered directly.
    """
    if compatible_attachments.empty:
        return compatible_attachments.copy()

    updated = compatible_attachments.copy()

    updated["_modelled_effect_count"] = updated.apply(
        attachment_modelled_effect_count,
        axis=1,
    )
    updated["_blocked_for_oracle"] = updated.apply(
        attachment_is_blocked_for_oracle,
        axis=1,
    )
    updated["_modelled_for_oracle"] = updated.apply(
        attachment_is_modelled_for_oracle,
        axis=1,
    )
    updated["_effect_summary"] = updated.apply(
        attachment_modelled_effect_summary,
        axis=1,
    )

    return updated[updated["_modelled_for_oracle"]].reset_index(drop=True)


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


def effective_recoil_pct(attachment) -> float:
    detailed_recoil_values = [
        numeric_cell(attachment.get("gun_kick_pct", 0), 0.0),
        numeric_cell(attachment.get("horizontal_recoil_pct", 0), 0.0),
        numeric_cell(attachment.get("vertical_recoil_pct", 0), 0.0),
    ]

    detailed_recoil_values = [
        value for value in detailed_recoil_values
        if value != 0
    ]

    generic_recoil = numeric_cell(attachment.get("recoil_pct", 0), 0.0)

    if detailed_recoil_values:
        return generic_recoil + (sum(detailed_recoil_values) / len(detailed_recoil_values))

    return generic_recoil


def apply_attachment_to_stats(stats, attachment):
    updated = stats.copy()

    damage_pct = numeric_cell(attachment.get("damage_pct", 0), 0.0)
    range_pct = numeric_cell(attachment.get("range_pct", 0), 0.0)

    for stat in [
        "damage_close",
        "damage_mid",
        "damage_long",
        "head_damage_close",
        "head_damage_mid",
        "head_damage_long",
    ]:
        if stat in updated:
            updated[stat] = updated[stat] * (1 + damage_pct / 100)

    for stat in ["range_close_m", "range_mid_m"]:
        updated[stat] = updated[stat] * (1 + range_pct / 100)

    pct_modifiers = {
        "fire_rate_rpm": "fire_rate_pct",
        "bullet_velocity": "bullet_velocity_pct",
    }

    for stat, column in pct_modifiers.items():
        value = numeric_cell(attachment.get(column, 0), 0.0)
        updated[stat] = updated[stat] * (1 + value / 100)

    recoil_pct = effective_recoil_pct(attachment)
    updated["recoil"] = updated["recoil"] * (1 + recoil_pct / 100)

    # Existing hand-entered data can still use fixed millisecond deltas.
    updated["ads_ms"] = updated["ads_ms"] + numeric_cell(attachment.get("ads_ms_add", 0), 0.0)
    updated["sprint_to_fire_ms"] = updated["sprint_to_fire_ms"] + numeric_cell(
        attachment.get("sprint_to_fire_ms_add", 0),
        0.0,
    )

    # Codmunity-style data uses percentages. A negative percentage means faster.
    ads_pct = numeric_cell(attachment.get("ads_pct", 0), 0.0)
    sprint_to_fire_pct = numeric_cell(attachment.get("sprint_to_fire_pct", 0), 0.0)

    # BO7 shotgun attachment tables often expose jump ADS / jump sprint-to-fire
    # instead of plain ADS / sprint-to-fire. Use them as a conservative handling
    # proxy so close-range builds are not scored as random zero-effect fillers.
    if ads_pct == 0:
        ads_pct = numeric_cell(attachment.get("jump_ads_pct", 0), 0.0) * 0.60

    if sprint_to_fire_pct == 0:
        sprint_to_fire_pct = numeric_cell(attachment.get("jump_sprint_to_fire_pct", 0), 0.0) * 0.80

    updated["ads_ms"] = updated["ads_ms"] * (1 + ads_pct / 100)
    updated["sprint_to_fire_ms"] = updated["sprint_to_fire_ms"] * (1 + sprint_to_fire_pct / 100)

    updated["mag_size"] = updated["mag_size"] + numeric_cell(attachment.get("mag_size_add", 0), 0.0)

    return updated

def is_shotgun_weapon_class(value) -> bool:
    return normalise_weapon_class_key(value) == "shotgun"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def default_shotgun_truth_metrics() -> dict:
    return {
        "is_shotgun": False,
        "shotgun_one_shot_potential": "",
        "shotgun_two_shot_consistency": "",
        "shotgun_range_coverage": "",
        "shotgun_handling_index": "",
        "shotgun_mag_safety": "",
        "shotgun_truth_score": "",
        "shotgun_truth_note": "",
    }


def shotgun_truth_metrics(stats: dict, enemy_health: int = 300, fight_type: str = "Close range") -> dict:
    """
    Shotguns need a separate trust model.

    Without pellet-count and spread data, v1 uses conservative proxies:
    damage bracket, effective range coverage, handling, and mag safety.
    Field Test Log still decides whether the build is actually trusted.
    """
    damage = max(0.0, float(stats.get("damage", 0.0) or 0.0))
    range_m = max(0.0, float(stats.get("range_m", 0.0) or 0.0))
    ads_ms = max(0.0, float(stats.get("ads_ms", 0.0) or 0.0))
    sprint_to_fire_ms = max(0.0, float(stats.get("sprint_to_fire_ms", 0.0) or 0.0))
    mag_size = max(0.0, float(stats.get("mag_size", 0.0) or 0.0))
    health = max(1, int(enemy_health or 300))

    shots_to_kill = max(1, ceil(health / max(damage, 1.0)))
    target_range = SHOTGUN_RANGE_TARGETS_M.get(str(fight_type or "").strip(), 12.0)

    one_shot_potential = damage >= health
    two_shot_consistency = shots_to_kill <= 2

    # Range coverage above 1.0 is useful but capped so it cannot mask bad handling.
    range_coverage = _clamp(range_m / max(target_range, 1.0), 0.0, 1.25)

    # Shotguns are usually won or lost on sprint-to-fire more than ADS.
    handling_pressure = (ads_ms * 0.35) + (sprint_to_fire_ms * 0.65)
    handling_index = _clamp(1.20 - (handling_pressure / 520.0), 0.0, 1.0)

    # A two-shot shotgun with only one or two follow-up attempts is fragile.
    required_shells = max(1, shots_to_kill * 3)
    mag_safety = _clamp(mag_size / required_shells, 0.0, 1.25)

    lethality_score = 1.0 if one_shot_potential else _clamp((damage / health) * 1.15, 0.0, 0.95)
    consistency_score = 1.0 if two_shot_consistency else _clamp(1.0 - ((shots_to_kill - 2) * 0.22), 0.0, 0.80)

    truth_score = (
        lethality_score * 0.30
        + consistency_score * 0.24
        + _clamp(range_coverage, 0.0, 1.0) * 0.20
        + handling_index * 0.16
        + _clamp(mag_safety, 0.0, 1.0) * 0.10
    )

    if not two_shot_consistency:
        note = "DATA-LIMITED: requires more than two shots on the current health profile. Treat as fragile until field tested."
    elif not one_shot_potential:
        note = "DATA-LIMITED: no one-shot guarantee from current damage data. Field test pellet reliability before trusting."
    elif range_coverage < 0.75:
        note = "DATA-LIMITED: one-shot maths exists, but range coverage is weak for this fight profile."
    else:
        note = "SHOTGUN TRUTH V1: score uses damage bracket, range coverage, handling, and mag safety. Pellet spread still needs field testing."

    return {
        "is_shotgun": True,
        "shotgun_one_shot_potential": "YES" if one_shot_potential else "NO",
        "shotgun_two_shot_consistency": "YES" if two_shot_consistency else "NO",
        "shotgun_range_coverage": round(range_coverage, 3),
        "shotgun_handling_index": round(handling_index, 3),
        "shotgun_mag_safety": round(mag_safety, 3),
        "shotgun_truth_score": round(_clamp(truth_score, 0.0, 1.0), 3),
        "shotgun_truth_note": note,
    }


def calculate_shotgun_practical_ttk_ms(stats: dict) -> float:
    raw_ttk = float(stats.get("raw_ttk_ms", 0.0) or 0.0)
    ads_ms = float(stats.get("ads_ms", 0.0) or 0.0)
    sprint_to_fire_ms = float(stats.get("sprint_to_fire_ms", 0.0) or 0.0)
    shots_to_kill = float(stats.get("shots_to_kill", 1.0) or 1.0)
    truth_score = float(stats.get("shotgun_truth_score", 0.0) or 0.0)
    range_coverage = float(stats.get("shotgun_range_coverage", 0.0) or 0.0)

    extra_shot_penalty = max(0.0, shots_to_kill - 2.0) * 120.0
    range_penalty = max(0.0, 1.0 - min(range_coverage, 1.0)) * 160.0
    reliability_penalty = max(0.0, 1.0 - truth_score) * 220.0

    return round(
        raw_ttk
        + ads_ms * 0.08
        + sprint_to_fire_ms * 0.18
        + extra_shot_penalty
        + range_penalty
        + reliability_penalty,
        2,
    )


def add_shotgun_truth_to_results(results: pd.DataFrame, weights: dict) -> tuple[pd.DataFrame, dict]:
    if results.empty or "is_shotgun" not in results.columns:
        return results, weights

    scored = results.copy()
    shotgun_mask = scored["is_shotgun"].astype(str).str.lower().isin({"true", "1", "yes"})

    if not shotgun_mask.any():
        return scored, weights

    for column in SHOTGUN_TRUTH_COLUMNS:
        if column not in scored.columns:
            scored[column] = ""

    # Dedicated shotgun optimisation should actively reward consistency.
    # Mixed-class optimisation already feels the shotgun penalty through practical_ttk_ms.
    if shotgun_mask.all():
        updated_weights = dict(weights)
        updated_weights["shotgun_truth_score"] = updated_weights.get("shotgun_truth_score", 0.0) + 0.18
        updated_weights["practical_ttk_ms"] = updated_weights.get("practical_ttk_ms", 0.0) + 0.07

        total = sum(updated_weights.values())
        if total > 0:
            updated_weights = {
                metric: weight / total
                for metric, weight in updated_weights.items()
            }

        return scored, updated_weights

    return scored, weights


def build_loadout_preview(
    gun,
    selected_attachments,
    enemy_health=300,
    fight_type="Close range",
    build_goal: str = "",
):
    damage_close = float(gun["damage_close"])
    damage_mid = float(gun["damage_mid"])
    damage_long = float(gun["damage_long"])

    final_stats = {
        "damage_close": damage_close,
        "range_close_m": float(gun["range_close_m"]),
        "damage_mid": damage_mid,
        "range_mid_m": float(gun["range_mid_m"]),
        "damage_long": damage_long,
        "head_damage_close": numeric_cell(gun.get("head_damage_close", damage_close), damage_close),
        "head_damage_mid": numeric_cell(gun.get("head_damage_mid", damage_mid), damage_mid),
        "head_damage_long": numeric_cell(gun.get("head_damage_long", damage_long), damage_long),
        "fire_rate_rpm": float(gun["fire_rate_rpm"]),
        "ads_ms": float(gun["ads_ms"]),
        "sprint_to_fire_ms": float(gun["sprint_to_fire_ms"]),
        "recoil": float(gun["recoil"]),
        "bullet_velocity": float(gun["bullet_velocity"]),
        "mag_size": float(gun["mag_size"]),
        "weapon_class": str(gun.get("weapon_class", "")),
    }

    for _, attachment in selected_attachments.iterrows():
        final_stats = apply_attachment_to_stats(final_stats, attachment)

    damage_column = damage_column_for_fight_type(fight_type, build_goal)

    if damage_column not in final_stats:
        damage_column = damage_column_for_fight_type(fight_type)

    final_stats["damage"] = final_stats[damage_column]
    final_stats["damage_model"] = "headshot" if is_headshot_build_goal(build_goal) else "body"
    final_stats["range_m"] = effective_range_for_fight_type(final_stats, fight_type)

    final_stats["shots_to_kill"] = ceil(enemy_health / final_stats["damage"])

    final_stats["raw_ttk_ms"] = calculate_raw_ttk_ms(
        damage=final_stats["damage"],
        fire_rate_rpm=final_stats["fire_rate_rpm"],
        enemy_health=enemy_health,
    )

    if is_shotgun_weapon_class(final_stats.get("weapon_class", "")):
        final_stats.update(
            shotgun_truth_metrics(
                final_stats,
                enemy_health=enemy_health,
                fight_type=fight_type,
            )
        )
    else:
        final_stats.update(default_shotgun_truth_metrics())

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
    "Military Camo Headshots",
    "Special Camo TTK",
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
    "shotgun_truth_score",
    "shotgun_range_coverage",
    "shotgun_mag_safety",
}

SHOTGUN_RANGE_TARGETS_M = {
    "Close range": 7.0,
    "Mid range": 14.0,
    "Long range": 24.0,
    "Mixed fights": 12.0,
}

SHOTGUN_TRUTH_COLUMNS = [
    "is_shotgun",
    "shotgun_one_shot_potential",
    "shotgun_two_shot_consistency",
    "shotgun_range_coverage",
    "shotgun_handling_index",
    "shotgun_mag_safety",
    "shotgun_truth_score",
    "shotgun_truth_note",
]

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

    Normal guns punish handling and recoil.
    Shotguns use a separate truth model because pellet reliability, one-shot
    potential, and two-shot consistency matter more than recoil beams.
    """
    is_shotgun = str(stats.get("is_shotgun", "")).strip().lower() in {"true", "1", "yes"}

    if is_shotgun:
        return calculate_shotgun_practical_ttk_ms(stats)

    return round(
        float(stats["raw_ttk_ms"])
        + float(stats["ads_ms"]) * 0.15
        + float(stats["sprint_to_fire_ms"]) * 0.10
        + float(stats["recoil"]) * 2.0,
        2,
    )


def build_scenario_weights(map_type, fight_type, build_goal):
    if build_goal == "Military Camo Headshots":
        weights = {
            "recoil": 0.42,
            "ads_ms": 0.16,
            "sprint_to_fire_ms": 0.10,
            "bullet_velocity": 0.12,
            "range_m": 0.10,
            "practical_ttk_ms": 0.07,
            "damage_per_mag": 0.03,
        }

    elif build_goal == "Special Camo TTK":
        weights = {
            "raw_ttk_ms": 0.55,
            "practical_ttk_ms": 0.25,
            "ads_ms": 0.08,
            "sprint_to_fire_ms": 0.06,
            "damage_per_mag": 0.06,
        }

    elif build_goal == "Fastest TTK":
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
    "ads_pct",
    "sprint_to_fire_pct",
    "reload_pct",
    "jump_ads_pct",
    "jump_sprint_to_fire_pct",
    "gun_kick_pct",
    "horizontal_recoil_pct",
    "vertical_recoil_pct",
    "first_shot_recoil_pct",
    "kick_reset_speed_pct",
    "flinch_resistance_pct",
    "movement_pct",
    "sprint_pct",
    "crouch_movement_pct",
    "ads_movement_pct",
]

# Stats where a lower value is better. For Codmunity percentage fields,
# negative ADS/recoil values are improvements and positive values are penalties.
LOWER_IS_BETTER_ATTACHMENT = {
    "ads_ms_add",
    "sprint_to_fire_ms_add",
    "recoil_pct",
    "ads_pct",
    "sprint_to_fire_pct",
    "reload_pct",
    "jump_ads_pct",
    "jump_sprint_to_fire_pct",
    "gun_kick_pct",
    "horizontal_recoil_pct",
    "vertical_recoil_pct",
    "first_shot_recoil_pct",
    "kick_reset_speed_pct",
    "flinch_resistance_pct",
}


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
        val_a = numeric_cell(a.get(stat, 0), 0.0)
        val_b = numeric_cell(b.get(stat, 0), 0.0)

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

def estimate_legal_attachment_combo_count(slot_counts: dict[str, int], attachment_count: int) -> int:
    """
    Count legal one-attachment-per-slot combinations without generating them.

    This powers the TTK page's workload warning so 8-attachment scans are visible
    before a deep brute-force pass starts.
    """
    slot_names = sorted(
        slot
        for slot, count in slot_counts.items()
        if str(slot).strip() and int(count or 0) > 0
    )

    if len(slot_names) < attachment_count:
        return 0

    total = 0

    for selected_slots in combinations(slot_names, attachment_count):
        product_count = 1

        for slot in selected_slots:
            product_count *= int(slot_counts.get(slot, 0) or 0)

        total += product_count

    return int(total)


def estimate_optimizer_combo_count(
    guns: pd.DataFrame,
    attachments: pd.DataFrame,
    map_type: str,
    fight_type: str,
    build_goal: str,
    enemy_health: int = 300,
    weapon_class: str = "Any",
    attachment_count: int = 5,
    optimiser_mode: str = "Fast",
    candidate_limit_per_slot: int = 3,
) -> pd.DataFrame:
    """
    Estimate the build search space using the same slot rules and pool pruning
    as the optimiser. It does not score builds and does not generate combos.
    """
    if guns.empty or attachments.empty:
        return pd.DataFrame()

    filtered_guns = guns.copy()

    if weapon_class != "Any":
        filtered_guns = filtered_guns[
            filtered_guns["weapon_class"] == weapon_class
        ]

    rows = []
    use_fast_mode = normalise_match_value(optimiser_mode) != "deep"

    for _, gun in filtered_guns.iterrows():
        compatible_attachments = get_compatible_attachments(
            gun=gun,
            attachments=attachments,
        )

        full_compatible_count = len(compatible_attachments)
        compatible_attachments = prepare_oracle_attachment_pool(compatible_attachments)
        modelled_compatible_count = len(compatible_attachments)
        ignored_count = max(0, full_compatible_count - modelled_compatible_count)

        if compatible_attachments.empty:
            rows.append(
                {
                    "gun_name": gun.get("gun_name", ""),
                    "weapon_class": gun.get("weapon_class", ""),
                    "attachment_count": attachment_count,
                    "optimiser_mode": "Fast" if use_fast_mode else "Deep",
                    "full_compatible_rows": full_compatible_count,
                    "modelled_rows": modelled_compatible_count,
                    "ignored_rows": ignored_count,
                    "usable_slots": 0,
                    "pool_rows_after_pruning": 0,
                    "estimated_combinations": 0,
                    "slot_pool_summary": "",
                    "buildable": False,
                }
            )
            continue

        compatible_attachments = prune_dominated_attachments(compatible_attachments)

        if use_fast_mode:
            compatible_attachments = reduce_attachment_pool_for_fast_mode(
                compatible_attachments=compatible_attachments,
                map_type=map_type,
                fight_type=fight_type,
                build_goal=build_goal,
                candidate_limit_per_slot=candidate_limit_per_slot,
                hard_limit_per_slot=3,
            )
        else:
            compatible_attachments = prune_dominated_attachments(compatible_attachments)

        slot_counts = {
            str(slot).strip(): int(len(group))
            for slot, group in compatible_attachments.groupby("slot")
            if str(slot).strip()
        }

        combo_count = estimate_legal_attachment_combo_count(
            slot_counts=slot_counts,
            attachment_count=attachment_count,
        )

        rows.append(
            {
                "gun_name": gun.get("gun_name", ""),
                "weapon_class": gun.get("weapon_class", ""),
                "attachment_count": attachment_count,
                "optimiser_mode": "Fast" if use_fast_mode else "Deep",
                "full_compatible_rows": full_compatible_count,
                "modelled_rows": modelled_compatible_count,
                "ignored_rows": ignored_count,
                "usable_slots": len(slot_counts),
                "pool_rows_after_pruning": int(sum(slot_counts.values())),
                "estimated_combinations": int(combo_count),
                "slot_pool_summary": " | ".join(
                    f"{slot}:{count}"
                    for slot, count in sorted(slot_counts.items())
                ),
                "buildable": combo_count > 0,
            }
        )

    return pd.DataFrame(rows)

def best_index_by_numeric(group: pd.DataFrame, column: str, prefer_high: bool = True):
    if column not in group.columns:
        return None

    values = group[column].apply(lambda value: numeric_cell(value, 0.0))

    if values.abs().sum() == 0:
        return None

    return values.idxmax() if prefer_high else values.idxmin()


def best_index_by_recoil(group: pd.DataFrame):
    if group.empty:
        return None

    values = group.apply(lambda row: effective_recoil_pct(row), axis=1)

    if values.abs().sum() == 0:
        return None

    return values.idxmin()


def attachment_fast_candidate_score(attachment, map_type, fight_type, build_goal) -> float:
    """
    Scenario-aware attachment shortlist score.

    This is not the final Oracle score. It only decides which attachments are
    worth sending into combo generation.
    """
    score = 0.0

    build_goal_text = normalise_match_value(build_goal)
    fight_type_text = normalise_match_value(fight_type)
    map_type_text = normalise_match_value(map_type)

    ads_weight = 1.0
    sprint_to_fire_weight = 1.0
    recoil_weight = 1.0
    range_weight = 0.8
    bullet_velocity_weight = 0.8
    mag_weight = 0.7

    if "headshot" in build_goal_text or "military camo" in build_goal_text:
        recoil_weight += 1.8
        ads_weight += 0.3
        sprint_to_fire_weight += 0.2
        range_weight += 0.5
        bullet_velocity_weight += 0.4

    if "special camo" in build_goal_text or "ttk" in build_goal_text:
        ads_weight += 0.3
        sprint_to_fire_weight += 0.3

    if "aggressive" in build_goal_text or "close" in fight_type_text:
        ads_weight += 0.7
        sprint_to_fire_weight += 0.8
        mag_weight += 0.2

    if "low recoil" in build_goal_text or "long" in fight_type_text:
        recoil_weight += 1.0
        range_weight += 0.6
        bullet_velocity_weight += 0.6

    if "large map" in map_type_text or "battle royale" in map_type_text:
        recoil_weight += 0.4
        range_weight += 0.5
        bullet_velocity_weight += 0.5
        mag_weight += 0.4

    score += numeric_cell(attachment.get("damage_pct", 0), 0.0) * 4.0
    score += numeric_cell(attachment.get("fire_rate_pct", 0), 0.0) * 3.5
    score += numeric_cell(attachment.get("range_pct", 0), 0.0) * range_weight
    score += numeric_cell(attachment.get("bullet_velocity_pct", 0), 0.0) * bullet_velocity_weight
    score += numeric_cell(attachment.get("mag_size_add", 0), 0.0) * mag_weight

    score += -numeric_cell(attachment.get("ads_pct", 0), 0.0) * ads_weight
    score += -numeric_cell(attachment.get("sprint_to_fire_pct", 0), 0.0) * sprint_to_fire_weight
    score += -numeric_cell(attachment.get("jump_ads_pct", 0), 0.0) * 0.35
    score += -numeric_cell(attachment.get("jump_sprint_to_fire_pct", 0), 0.0) * 0.35
    score += -numeric_cell(attachment.get("reload_pct", 0), 0.0) * 0.35

    score += -effective_recoil_pct(attachment) * recoil_weight
    score += -numeric_cell(attachment.get("first_shot_recoil_pct", 0), 0.0) * 0.20
    score += -numeric_cell(attachment.get("kick_reset_speed_pct", 0), 0.0) * 0.10

    score += numeric_cell(attachment.get("movement_pct", 0), 0.0) * 0.35
    score += numeric_cell(attachment.get("sprint_pct", 0), 0.0) * 0.25
    score += numeric_cell(attachment.get("crouch_movement_pct", 0), 0.0) * 0.15
    score += numeric_cell(attachment.get("ads_movement_pct", 0), 0.0) * 0.35

    return float(score)


def reduce_attachment_pool_for_fast_mode(
    compatible_attachments: pd.DataFrame,
    map_type: str,
    fight_type: str,
    build_goal: str,
    candidate_limit_per_slot: int = 2,
    hard_limit_per_slot: int = 3,
) -> pd.DataFrame:
    """
    Keeps a scenario-aware shortlist per slot.

    Fast mode deliberately stops being exhaustive. It keeps the best few
    candidates per slot, while preserving important attachment types like
    biggest mag, fastest mag, rapid fire, range, bullet velocity, recoil,
    ADS, and sprint-to-fire.
    """
    if compatible_attachments.empty:
        return compatible_attachments

    if candidate_limit_per_slot <= 0:
        return compatible_attachments

    kept_groups = []

    for slot, group in compatible_attachments.groupby("slot"):
        group = group.copy()

        clean_slot = normalise_match_value(slot)

        group["_fast_candidate_score"] = group.apply(
            lambda row: attachment_fast_candidate_score(
                attachment=row,
                map_type=map_type,
                fight_type=fight_type,
                build_goal=build_goal,
            ),
            axis=1,
        )

        forced_indices = []

        def force(index):
            if index is not None and index not in forced_indices:
                forced_indices.append(index)

        if clean_slot == "magazine":
            force(best_index_by_numeric(group, "mag_size_add", prefer_high=True))
            force(best_index_by_numeric(group, "reload_pct", prefer_high=False))

        elif clean_slot == "fire mods":
            force(best_index_by_numeric(group, "fire_rate_pct", prefer_high=True))
            force(best_index_by_numeric(group, "bullet_velocity_pct", prefer_high=True))
            force(best_index_by_numeric(group, "range_pct", prefer_high=True))
            force(best_index_by_recoil(group))

        elif clean_slot == "barrel":
            force(best_index_by_numeric(group, "range_pct", prefer_high=True))
            force(best_index_by_numeric(group, "bullet_velocity_pct", prefer_high=True))
            force(best_index_by_numeric(group, "ads_pct", prefer_high=False))

        elif clean_slot == "muzzle":
            force(best_index_by_numeric(group, "range_pct", prefer_high=True))
            force(best_index_by_numeric(group, "bullet_velocity_pct", prefer_high=True))
            force(best_index_by_recoil(group))

        elif clean_slot == "rear grip":
            force(best_index_by_numeric(group, "ads_pct", prefer_high=False))
            force(best_index_by_numeric(group, "sprint_to_fire_pct", prefer_high=False))
            force(best_index_by_recoil(group))

        elif clean_slot == "stock":
            force(best_index_by_numeric(group, "ads_pct", prefer_high=False))
            force(best_index_by_numeric(group, "ads_movement_pct", prefer_high=True))
            force(best_index_by_numeric(group, "movement_pct", prefer_high=True))
            force(best_index_by_recoil(group))

        elif clean_slot == "underbarrel":
            force(best_index_by_numeric(group, "movement_pct", prefer_high=True))
            force(best_index_by_numeric(group, "ads_movement_pct", prefer_high=True))
            force(best_index_by_recoil(group))

        elif clean_slot == "laser":
            force(best_index_by_numeric(group, "ads_pct", prefer_high=False))
            force(best_index_by_numeric(group, "sprint_to_fire_pct", prefer_high=False))
            force(best_index_by_numeric(group, "range_pct", prefer_high=True))

        target_limit = max(
            candidate_limit_per_slot,
            min(len(forced_indices), hard_limit_per_slot),
        )

        selected_indices = list(forced_indices)

        for index in group.sort_values("_fast_candidate_score", ascending=False).index:
            if index not in selected_indices:
                selected_indices.append(index)

            if len(selected_indices) >= target_limit:
                break

        kept = group.loc[selected_indices].copy()
        kept_groups.append(kept)

    if not kept_groups:
        return compatible_attachments

    reduced = pd.concat(kept_groups, ignore_index=True)

    if "_fast_candidate_score" in reduced.columns:
        reduced = reduced.drop(columns=["_fast_candidate_score"])

    return reduced.reset_index(drop=True)

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
    optimiser_mode="Fast",
    candidate_limit_per_slot=3,
):
    if guns.empty or attachments.empty:
        return pd.DataFrame()

    filtered_guns = guns.copy()

    if weapon_class != "Any":
        filtered_guns = filtered_guns[
            filtered_guns["weapon_class"] == weapon_class
        ]

    rows = []
    use_fast_mode = normalise_match_value(optimiser_mode) != "deep"

    for _, gun in filtered_guns.iterrows():
        compatible_attachments = get_compatible_attachments(
            gun=gun,
            attachments=attachments,
        )

        full_compatible_count = len(compatible_attachments)
        compatible_attachments = prepare_oracle_attachment_pool(compatible_attachments)
        unmodelled_attachments_ignored = max(0, full_compatible_count - len(compatible_attachments))

        unique_slot_count = compatible_attachments["slot"].dropna().nunique()

        if unique_slot_count < attachment_count:
            continue

        compatible_attachments = prune_dominated_attachments(compatible_attachments)

        if use_fast_mode:
            compatible_attachments = reduce_attachment_pool_for_fast_mode(
                compatible_attachments=compatible_attachments,
                map_type=map_type,
                fight_type=fight_type,
                build_goal=build_goal,
                candidate_limit_per_slot=candidate_limit_per_slot,
                hard_limit_per_slot=3,
            )
        else:
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
                build_goal=build_goal,
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
                    "modelled_attachment_count": int(
                        selected_attachments.get("_modelled_effect_count", pd.Series(dtype=float)).fillna(0).astype(float).gt(0).sum()
                    ) if "_modelled_effect_count" in selected_attachments.columns else len(selected_attachments),
                    "unmodelled_attachments_ignored": unmodelled_attachments_ignored,
                    "attachment_effects": " || ".join(
                        f"{row.get('attachment_name', '')}: {row.get('_effect_summary', '')}"
                        for _, row in selected_attachments.iterrows()
                    ),
                    "attachment_trust_note": (
                        f"Only modelled attachments were allowed. Ignored {unmodelled_attachments_ignored} "
                        "zero-effect or unmodelled conversion row(s)."
                    ),
                    "optimiser_mode": "Fast" if use_fast_mode else "Deep",
                    "slot_candidate_limit": int(candidate_limit_per_slot) if use_fast_mode else "",
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

    results, weights = add_shotgun_truth_to_results(results, weights)

    results = add_oracle_scores(results, weights)

    return (
        results
        .sort_values("oracle_score", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )

CODMUNITY_STAT_MAP = {
    "ads speed": "ads_pct",
    "sprint to fire": "sprint_to_fire_pct",
    "sprint to fire speed": "sprint_to_fire_pct",
    "reload speed": "reload_pct",
    "jump ads": "jump_ads_pct",
    "jump sprint to fire speed": "jump_sprint_to_fire_pct",
    "slide to fire": "sprint_to_fire_pct",
    "slide to fire speed": "sprint_to_fire_pct",
    "dive to fire": "sprint_to_fire_pct",
    "dive to fire speed": "sprint_to_fire_pct",
    "bullet velocity": "bullet_velocity_pct",
    "horizontal recoil": "horizontal_recoil_pct",
    "vertical recoil": "vertical_recoil_pct",
    "gun kick": "gun_kick_pct",
    "first shot recoil scale": "first_shot_recoil_pct",
    "kick reset speed": "kick_reset_speed_pct",
    "magazine size": "mag_size_add",
    "range": "range_pct",
    "damage": "damage_pct",
    "fire rate": "fire_rate_pct",
    "rpm": "fire_rate_pct",
    "movement": "movement_pct",
    "sprint": "sprint_pct",
    "crouch movement": "crouch_movement_pct",
    "ads movement": "ads_movement_pct",
    "flinch resistance": "flinch_resistance_pct",
}


def normalise_codmunity_stat_label(label: str) -> str:
    label = strip_html(label).lower()
    label = re.sub(r"\s+", " ", label)
    return label.strip()


def apply_codmunity_stat_to_attachment_row(row: dict, value: str, label: str):
    clean_label = normalise_codmunity_stat_label(label)
    column = CODMUNITY_STAT_MAP.get(clean_label)

    if not column:
        return

    row[column] = numeric_cell(value, 0.0)


def parse_codmunity_attachment_html(
    html_text: str,
    compatible_weapon_classes: str = "",
    compatible_guns: str = "",
    source: str = "codmunity.gg",
    source_date: str = "",
) -> pd.DataFrame:
    """
    Parses copied Codmunity attachment-table HTML into Oracle attachment rows.

    This is designed for data entry, not blind trust. Parsed rows should be
    spot-checked against one or two in-game expanded-stat screenshots before
    they are appended to the master CSV.
    """
    rows = []
    html_text = str(html_text or "")

    for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html_text, flags=re.I | re.S):
        name_match = re.search(
            r'class="[^"]*attachment-name[^"]*"[^>]*>(.*?)</span>',
            row_html,
            flags=re.I | re.S,
        )
        slot_match = re.search(
            r'class="[^"]*slot[^"]*"[^>]*>(.*?)</span>',
            row_html,
            flags=re.I | re.S,
        )

        if not name_match or not slot_match:
            continue

        attachment_name = strip_html(name_match.group(1))
        slot = strip_html(slot_match.group(1))

        label_match = re.search(
            r'class="[^"]*label[^"]*"[^>]*>(.*?)</span>',
            row_html,
            flags=re.I | re.S,
        )
        unlock_match = re.search(
            r'class="[^"]*unlock[^"]*"[^>]*>(.*?)</span>',
            row_html,
            flags=re.I | re.S,
        )

        label = strip_html(label_match.group(1)) if label_match else ""
        unlock = strip_html(unlock_match.group(1)) if unlock_match else ""

        attachment_row = {
            column: 0.0 if column in ATTACHMENT_NUMERIC_COLUMNS else ""
            for column in EXTENDED_ATTACHMENT_COLUMNS
        }

        attachment_row.update({
            "attachment_id": slugify(f"{normalise_stats_profile(stats_profile, DEFAULT_STATS_PROFILE)}_{compatible_guns or compatible_weapon_classes}_{attachment_name}"),
            "attachment_name": attachment_name,
            "slot": slot,
            "stats_profile": normalise_stats_profile(stats_profile, DEFAULT_STATS_PROFILE),
            "compatible_weapon_classes": compatible_weapon_classes,
            "compatible_guns": compatible_guns,
            "source": source,
            "source_date": source_date,
            "verification_status": "needs_verification",
            "verification_notes": f"Label: {label}. Unlock: {unlock}.".strip(),
        })

        raw_stat_parts = []

        stat_items = re.findall(
            r'class="[^"]*attachment-stats-item[^"]*"[^>]*>(.*?)</div>',
            row_html,
            flags=re.I | re.S,
        )

        for stat_html in stat_items:
            highlight_match = re.search(
                r'class="[^"]*highlight[^"]*"[^>]*>(.*?)</span>',
                stat_html,
                flags=re.I | re.S,
            )

            if not highlight_match:
                continue

            value = strip_html(highlight_match.group(1))
            label_html = re.sub(
                r'<span[^>]*class="[^"]*highlight[^"]*"[^>]*>.*?</span>',
                " ",
                stat_html,
                flags=re.I | re.S,
            )
            stat_label = strip_html(label_html)

            if value and stat_label:
                raw_stat_parts.append(f"{value} {stat_label}")
                apply_codmunity_stat_to_attachment_row(
                    attachment_row,
                    value=value,
                    label=stat_label,
                )

        attachment_row["raw_stat_text"] = " | ".join(raw_stat_parts)

        rows.append(attachment_row)

    if not rows:
        return pd.DataFrame(columns=EXTENDED_ATTACHMENT_COLUMNS)

    dataframe = pd.DataFrame(rows)

    return ensure_attachment_columns(dataframe)[EXTENDED_ATTACHMENT_COLUMNS]


def build_attachment_verification_rows(
    gun,
    parsed_attachments: pd.DataFrame,
    sample_size: int = 2,
    random_state: int = 7,
) -> pd.DataFrame:
    """
    Builds a small before/after stat check sheet for manual verification.

    Thomas can compare these expected values against in-game expanded stats
    for one or two attachments before we commit a weapon's attachment data.
    """
    if parsed_attachments.empty:
        return pd.DataFrame()

    candidates = parsed_attachments.copy()

    if "raw_stat_text" in candidates.columns:
        non_empty = candidates[candidates["raw_stat_text"].astype(str).str.strip() != ""]
        if not non_empty.empty:
            candidates = non_empty

    sample_size = min(sample_size, len(candidates))

    if sample_size <= 0:
        return pd.DataFrame()

    sample = candidates.sample(n=sample_size, random_state=random_state)

    base_stats = {
        "damage_close": numeric_cell(gun["damage_close"], 0.0),
        "range_close_m": numeric_cell(gun["range_close_m"], 0.0),
        "damage_mid": numeric_cell(gun["damage_mid"], 0.0),
        "range_mid_m": numeric_cell(gun["range_mid_m"], 0.0),
        "damage_long": numeric_cell(gun["damage_long"], 0.0),
        "fire_rate_rpm": numeric_cell(gun["fire_rate_rpm"], 0.0),
        "ads_ms": numeric_cell(gun["ads_ms"], 0.0),
        "sprint_to_fire_ms": numeric_cell(gun["sprint_to_fire_ms"], 0.0),
        "recoil": numeric_cell(gun["recoil"], 0.0),
        "bullet_velocity": numeric_cell(gun["bullet_velocity"], 0.0),
        "mag_size": numeric_cell(gun["mag_size"], 0.0),
    }

    rows = []

    for _, attachment in sample.iterrows():
        after = apply_attachment_to_stats(base_stats, attachment)

        rows.append({
            "attachment_name": attachment.get("attachment_name", ""),
            "slot": attachment.get("slot", ""),
            "raw_stat_text": attachment.get("raw_stat_text", ""),
            "base_ads_ms": round(base_stats["ads_ms"], 2),
            "expected_ads_ms": round(after["ads_ms"], 2),
            "base_sprint_to_fire_ms": round(base_stats["sprint_to_fire_ms"], 2),
            "expected_sprint_to_fire_ms": round(after["sprint_to_fire_ms"], 2),
            "base_recoil": round(base_stats["recoil"], 2),
            "expected_recoil": round(after["recoil"], 2),
            "base_bullet_velocity": round(base_stats["bullet_velocity"], 2),
            "expected_bullet_velocity": round(after["bullet_velocity"], 2),
            "base_mag_size": round(base_stats["mag_size"], 2),
            "expected_mag_size": round(after["mag_size"], 2),
        })

    return pd.DataFrame(rows)



def find_gun_by_name(guns: pd.DataFrame, weapon_name: str) -> pd.DataFrame:
    """
    Case-insensitive gun lookup used by the Commander Weapon Optimiser.

    Also tolerates punctuation differences such as SG12 vs SG-12.
    """
    if guns.empty or not weapon_name:
        return guns.iloc[0:0].copy()

    target = normalise_match_key(weapon_name)

    return guns[
        guns["gun_name"].apply(normalise_match_key) == target
    ].reset_index(drop=True)


def describe_weapon_build_data(
    guns: pd.DataFrame,
    attachments: pd.DataFrame,
    weapon_name: str,
    attachment_count: int = 5,
) -> dict:
    """
    Reports whether a selected weapon has enough trusted attachment data to build.

    Compatible attachment inventory is not enough. The optimiser only trusts
    rows with modelled stat effects, and it blocks conversion-style parts until
    their changed damage model is entered directly.
    """
    matched_guns = find_gun_by_name(guns, weapon_name)

    if matched_guns.empty:
        return {
            "buildable": False,
            "weapon_found": False,
            "compatible_attachments": 0,
            "compatible_slots": 0,
            "trusted_attachments": 0,
            "trusted_slots": 0,
            "slots": [],
            "trusted_slots_list": [],
            "ignored_attachments": 0,
            "message": f"{weapon_name} is not in guns.csv.",
        }

    gun = matched_guns.iloc[0]
    compatible_attachments = get_compatible_attachments(gun, attachments)
    trusted_attachments = prepare_oracle_attachment_pool(compatible_attachments)

    slots = sorted(
        str(slot).strip()
        for slot in compatible_attachments["slot"].dropna().unique().tolist()
        if str(slot).strip()
    )

    trusted_slots_list = sorted(
        str(slot).strip()
        for slot in trusted_attachments["slot"].dropna().unique().tolist()
        if str(slot).strip()
    )

    compatible_count = len(compatible_attachments)
    trusted_count = len(trusted_attachments)
    compatible_slots = len(slots)
    trusted_slots = len(trusted_slots_list)
    ignored_attachments = max(0, compatible_count - trusted_count)
    buildable = trusted_slots >= attachment_count

    if buildable:
        message = (
            f"{gun['gun_name']} has {trusted_count} trusted/modelled attachments "
            f"across {trusted_slots} slot(s). Ignoring {ignored_attachments} "
            "zero-effect or unmodelled conversion row(s)."
        )
    elif trusted_slots == 0:
        message = (
            f"{gun['gun_name']} has compatible attachment rows, but none have trusted "
            "modelled effects yet. The Oracle will not fake a best build."
        )
    else:
        message = (
            f"{gun['gun_name']} only has {trusted_slots} trusted/modelled slot(s): "
            f"{', '.join(trusted_slots_list)}. Needs {attachment_count} for this run. "
            f"Ignoring {ignored_attachments} zero-effect or unmodelled conversion row(s)."
        )

    return {
        "buildable": buildable,
        "weapon_found": True,
        "compatible_attachments": compatible_count,
        "compatible_slots": compatible_slots,
        "trusted_attachments": trusted_count,
        "trusted_slots": trusted_slots,
        "slots": slots,
        "trusted_slots_list": trusted_slots_list,
        "ignored_attachments": ignored_attachments,
        "message": message,
    }


def optimise_single_weapon_build(
    guns: pd.DataFrame,
    attachments: pd.DataFrame,
    weapon_name: str,
    map_type: str,
    fight_type: str,
    build_goal: str,
    enemy_health: int = 300,
    attachment_count: int = 5,
    top_n: int = 10,
    optimiser_mode: str = "Fast",
    candidate_limit_per_slot: int = 3,
) -> pd.DataFrame:
    """
    Brute-force the best build for one exact Commander-assigned weapon.

    This is intentionally different from the full-loadout optimiser. It must
    not dodge the assigned weapon just because another gun has a better score.
    """
    matched_guns = find_gun_by_name(guns, weapon_name)

    if matched_guns.empty:
        return pd.DataFrame()

    data_status = describe_weapon_build_data(
        guns=guns,
        attachments=attachments,
        weapon_name=weapon_name,
        attachment_count=attachment_count,
    )

    if not data_status.get("buildable", False):
        return pd.DataFrame()

    return optimise_loadouts_for_scenario(
        guns=matched_guns,
        attachments=attachments,
        map_type=map_type,
        fight_type=fight_type,
        build_goal=build_goal,
        enemy_health=enemy_health,
        weapon_class="Any",
        attachment_count=attachment_count,
        top_n=top_n,
        optimiser_mode=optimiser_mode,
        candidate_limit_per_slot=candidate_limit_per_slot,
    )


def build_ttk_data_warnings(
    guns: pd.DataFrame,
    attachments: pd.DataFrame,
    attachment_count: int = 5,
) -> list[str]:
    """
    Build data warnings using the real compatibility engine.

    The older page-level check only looked at compatible_guns, which falsely
    flagged guns that rely on class-wide attachment rows.
    """
    warnings: list[str] = []

    if guns.empty:
        warnings.append("guns.csv is empty.")
        return warnings

    if attachments.empty:
        warnings.append("attachments.csv is empty.")
        return warnings

    missing_data = []
    limited_data = []

    for _, gun in guns.iterrows():
        compatible = get_compatible_attachments(gun, attachments)
        trusted = prepare_oracle_attachment_pool(compatible)
        slots = sorted(
            str(slot).strip()
            for slot in trusted["slot"].dropna().unique().tolist()
            if str(slot).strip()
        )

        if not slots:
            missing_data.append(str(gun.get("gun_name", "Unknown")))
        elif len(slots) < attachment_count:
            limited_data.append(
                f"{gun.get('gun_name', 'Unknown')} ({len(slots)}/{attachment_count} trusted/modelled slots)"
            )

    if missing_data:
        warnings.append(
            f"{len(missing_data)} gun(s) have no compatible attachment data: "
            + ", ".join(missing_data)
        )

    if limited_data:
        warnings.append(
            f"{len(limited_data)} gun(s) have partial attachment data for {attachment_count}-attachment builds: "
            + ", ".join(limited_data)
        )

    duplicate_guns = guns[guns.duplicated(subset=["gun_id"], keep=False)]
    if not duplicate_guns.empty:
        warnings.append(
            "Duplicate gun_id rows found: "
            + ", ".join(sorted(duplicate_guns["gun_id"].astype(str).unique().tolist()))
        )

    duplicate_attachments = attachments[
        attachments.duplicated(subset=["attachment_id"], keep=False)
    ]
    if not duplicate_attachments.empty:
        warnings.append(
            "Duplicate attachment_id rows found: "
            + ", ".join(sorted(duplicate_attachments["attachment_id"].astype(str).unique().tolist()))
        )

    return warnings



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


def loadout_role_label(role, weapon_class, fight_type, build_goal):
    weapon_class = str(weapon_class or "").strip()
    fight_type = str(fight_type or "").strip()
    build_goal = str(build_goal or "").strip()

    if role == "primary":
        if fight_type == "Long range" or build_goal == "Low recoil beam":
            return "RANGE ANCHOR"
        if weapon_class in {"Sniper Rifle", "Marksman Rifle"}:
            return "PICK TOOL"
        if fight_type == "Mid range":
            return "MID-RANGE ANCHOR"
        return "PRIMARY COVERAGE"

    if fight_type == "Close range" or build_goal == "Aggressive mobility":
        return "CLOSE RESCUE"

    return "SECONDARY COVERAGE"


def _role_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def loadout_role_balance_score(primary_score, secondary_score):
    primary_score = _role_float(primary_score, 0.0)
    secondary_score = _role_float(secondary_score, 0.0)

    if primary_score <= 0 or secondary_score <= 0:
        return 0.0

    return round(min(primary_score, secondary_score) / max(primary_score, secondary_score), 4)


def loadout_role_verdict(
    *,
    primary_weapon,
    primary_class,
    primary_role_label,
    primary_score,
    secondary_weapon,
    secondary_class,
    secondary_role_label,
    secondary_score,
    role_balance_score,
    primary_is_shotgun=False,
    primary_shotgun_truth_score=0.0,
    secondary_is_shotgun=False,
    secondary_shotgun_truth_score=0.0,
):
    primary_score = _role_float(primary_score, 0.0)
    secondary_score = _role_float(secondary_score, 0.0)
    role_balance_score = _role_float(role_balance_score, 0.0)
    primary_shotgun_truth_score = _role_float(primary_shotgun_truth_score, 0.0)
    secondary_shotgun_truth_score = _role_float(secondary_shotgun_truth_score, 0.0)

    primary_name = str(primary_weapon or "Primary").strip()
    secondary_name = str(secondary_weapon or "Secondary").strip()
    primary_label = str(primary_role_label or "PRIMARY").strip()
    secondary_label = str(secondary_role_label or "SECONDARY").strip()

    if role_balance_score >= 0.90:
        verdict = (
            f"Balanced two-weapon lab result: {primary_name} covers {primary_label}, "
            f"{secondary_name} covers {secondary_label}."
        )
    elif primary_score + 0.08 < secondary_score:
        verdict = (
            f"{secondary_name} is carrying the loadout. Field test whether "
            f"{primary_name} is strong enough as the {primary_label}."
        )
    elif secondary_score + 0.08 < primary_score:
        verdict = (
            f"{primary_name} is the stronger half. Field test whether "
            f"{secondary_name} is reliable enough as the {secondary_label}."
        )
    else:
        verdict = (
            f"Usable role split: {primary_name} handles {primary_label}, "
            f"{secondary_name} handles {secondary_label}."
        )

    shotgun_notes = []

    if str(primary_is_shotgun).strip().lower() in {"true", "1", "yes"}:
        if primary_shotgun_truth_score >= 0.70:
            shotgun_notes.append(f"{primary_name} passes the conservative shotgun truth gate.")
        else:
            shotgun_notes.append(f"{primary_name} needs shotgun field proof before trust.")

    if str(secondary_is_shotgun).strip().lower() in {"true", "1", "yes"}:
        if secondary_shotgun_truth_score >= 0.70:
            shotgun_notes.append(f"{secondary_name} passes the conservative shotgun truth gate.")
        else:
            shotgun_notes.append(f"{secondary_name} needs shotgun field proof before trust.")

    if shotgun_notes:
        verdict += " " + " ".join(shotgun_notes)

    return verdict



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
    optimiser_mode: str = "Fast",
    candidate_limit_per_slot: int = 3,
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
        optimiser_mode=optimiser_mode,
        candidate_limit_per_slot=candidate_limit_per_slot,
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
        optimiser_mode=optimiser_mode,
        candidate_limit_per_slot=candidate_limit_per_slot,
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

            primary_role_score = float(primary["oracle_score"])
            secondary_role_score = float(secondary["oracle_score"])
            role_balance = loadout_role_balance_score(
                primary_role_score,
                secondary_role_score,
            )
            primary_role_label = loadout_role_label(
                "primary",
                primary.get("weapon_class", ""),
                role_scenarios["primary_fight_type"],
                role_scenarios["primary_build_goal"],
            )
            secondary_role_label = loadout_role_label(
                "secondary",
                secondary.get("weapon_class", ""),
                role_scenarios["secondary_fight_type"],
                role_scenarios["secondary_build_goal"],
            )

            full_loadout_score = (
                primary_role_score * primary_weight
                + secondary_role_score * secondary_weight
                + perk_bonus
            )
            role_verdict = loadout_role_verdict(
                primary_weapon=primary["gun_name"],
                primary_class=primary["weapon_class"],
                primary_role_label=primary_role_label,
                primary_score=primary_role_score,
                secondary_weapon=secondary["gun_name"],
                secondary_class=secondary["weapon_class"],
                secondary_role_label=secondary_role_label,
                secondary_score=secondary_role_score,
                role_balance_score=role_balance,
                primary_is_shotgun=primary.get("is_shotgun", ""),
                primary_shotgun_truth_score=primary.get("shotgun_truth_score", 0.0),
                secondary_is_shotgun=secondary.get("is_shotgun", ""),
                secondary_shotgun_truth_score=secondary.get("shotgun_truth_score", 0.0),
            )

            rows.append(
                {
                    "full_loadout_score": full_loadout_score,
                    "role_balance_score": role_balance,
                    "loadout_role_verdict": role_verdict,
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
                    "primary_role_label": primary_role_label,
                    "primary_attachments": primary["attachments"],
                    "primary_oracle_score": primary["oracle_score"],
                    "primary_role_score": primary_role_score,
                    "primary_raw_ttk_ms": primary["raw_ttk_ms"],
                    "primary_practical_ttk_ms": primary["practical_ttk_ms"],
                    "primary_recoil": primary["recoil"],
                    "primary_ads_ms": primary["ads_ms"],
                    "primary_bullet_velocity": primary["bullet_velocity"],
                    "primary_range_m": primary["range_m"],
                    "primary_is_shotgun": primary.get("is_shotgun", ""),
                    "primary_shotgun_truth_score": primary.get("shotgun_truth_score", ""),
                    "primary_shotgun_one_shot_potential": primary.get("shotgun_one_shot_potential", ""),
                    "primary_shotgun_two_shot_consistency": primary.get("shotgun_two_shot_consistency", ""),
                    "primary_shotgun_range_coverage": primary.get("shotgun_range_coverage", ""),
                    "primary_shotgun_handling_index": primary.get("shotgun_handling_index", ""),
                    "primary_shotgun_mag_safety": primary.get("shotgun_mag_safety", ""),
                    "primary_shotgun_truth_note": primary.get("shotgun_truth_note", ""),

                    "secondary_weapon": secondary["gun_name"],
                    "secondary_class": secondary["weapon_class"],
                    "secondary_role_label": secondary_role_label,
                    "secondary_attachments": secondary["attachments"],
                    "secondary_oracle_score": secondary["oracle_score"],
                    "secondary_role_score": secondary_role_score,
                    "secondary_raw_ttk_ms": secondary["raw_ttk_ms"],
                    "secondary_practical_ttk_ms": secondary["practical_ttk_ms"],
                    "secondary_recoil": secondary["recoil"],
                    "secondary_ads_ms": secondary["ads_ms"],
                    "secondary_bullet_velocity": secondary["bullet_velocity"],
                    "secondary_range_m": secondary["range_m"],
                    "secondary_is_shotgun": secondary.get("is_shotgun", ""),
                    "secondary_shotgun_truth_score": secondary.get("shotgun_truth_score", ""),
                    "secondary_shotgun_one_shot_potential": secondary.get("shotgun_one_shot_potential", ""),
                    "secondary_shotgun_two_shot_consistency": secondary.get("shotgun_two_shot_consistency", ""),
                    "secondary_shotgun_range_coverage": secondary.get("shotgun_range_coverage", ""),
                    "secondary_shotgun_handling_index": secondary.get("shotgun_handling_index", ""),
                    "secondary_shotgun_mag_safety": secondary.get("shotgun_mag_safety", ""),
                    "secondary_shotgun_truth_note": secondary.get("shotgun_truth_note", ""),

                    "primary_weight": primary_weight,
                    "secondary_weight": secondary_weight,
                    "optimiser_mode": "Deep" if normalise_match_value(optimiser_mode) == "deep" else "Fast",
                    "slot_candidate_limit": int(candidate_limit_per_slot) if normalise_match_value(optimiser_mode) != "deep" else "",
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
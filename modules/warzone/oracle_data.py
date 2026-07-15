"""TTK Oracle data loading, schema normalisation and shared identifiers.

This module is deliberately independent from the optimiser. It owns CSV paths,
schema defaults, normalisation and data loading so the weapon engine does not
also act as the repository layer.
"""

from pathlib import Path
import re
from html import unescape

import pandas as pd


TTK_DATA_DIR = Path("data/bo7_ttk")
GUNS_PATH = TTK_DATA_DIR / "guns.csv"
ATTACHMENTS_PATH = TTK_DATA_DIR / "attachments.csv"

LOADOUT_DATA_DIR = Path("data/bo7_loadouts")
PERKS_PATH = LOADOUT_DATA_DIR / "perks.csv"
WILDCARDS_PATH = LOADOUT_DATA_DIR / "wildcards.csv"
WILDCARD_EFFECTS_PATH = LOADOUT_DATA_DIR / "wildcard_effects.csv"
EQUIPMENT_PATH = LOADOUT_DATA_DIR / "equipment.csv"
FIELD_UPGRADES_PATH = LOADOUT_DATA_DIR / "field_upgrades.csv"
OVERCLOCKS_PATH = LOADOUT_DATA_DIR / "overclocks.csv"
SPECIALTIES_PATH = LOADOUT_DATA_DIR / "specialties.csv"
SPECIALTY_RULES_PATH = LOADOUT_DATA_DIR / "specialty_rules.csv"
LOADOUT_RULES_PATH = LOADOUT_DATA_DIR / "loadout_rules.csv"
LOADOUT_SLOTS_PATH = LOADOUT_DATA_DIR / "loadout_slots.csv"
LOADOUT_TEMPLATES_PATH = LOADOUT_DATA_DIR / "loadout_templates.csv"
SCORESTREAKS_PATH = LOADOUT_DATA_DIR / "scorestreaks.csv"
SCORESTREAK_OVERCLOCKS_PATH = LOADOUT_DATA_DIR / "scorestreak_overclocks.csv"

DEFAULT_STATS_PROFILE = "multiplayer"
LEGACY_STATS_PROFILE = "multiplayer"
SUPPORTED_STATS_PROFILES = [
    "warzone",
    "multiplayer",
    "zombies",
    "co_op_endgame",
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
    "aiming_idle_sway_pct",
    "visual_recoil_pct",
    "slide_to_fire_pct",
    "dive_to_fire_pct",
    "hipfire_spread_pct",
    "jump_hipfire_spread_pct",
    "slide_hipfire_spread_pct",
    "dive_hipfire_spread_pct",
    "mags_add",
    "optic_zoom",
    "unlock_level",
    "optic_type",
    "attachment_type",
    "unlock_weapon",
    "unlock_level",
    "unlock_method",
    "head_damage_pct",
    "head_damage_close_pct",
    "head_damage_mid_pct",
    "head_damage_long_pct",
    "head_damage_close_add",
    "head_damage_mid_add",
    "head_damage_long_add",
    "head_damage_close",
    "head_damage_mid",
    "head_damage_long",
    "head_multiplier",
    "head_multiplier_pct",
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
    "aiming_idle_sway_pct",
    "visual_recoil_pct",
    "slide_to_fire_pct",
    "dive_to_fire_pct",
    "hipfire_spread_pct",
    "jump_hipfire_spread_pct",
    "slide_hipfire_spread_pct",
    "dive_hipfire_spread_pct",
    "mags_add",
    "optic_zoom",
    "head_damage_pct",
    "head_damage_close_pct",
    "head_damage_mid_pct",
    "head_damage_long_pct",
    "head_damage_close_add",
    "head_damage_mid_add",
    "head_damage_long_add",
    "head_damage_close",
    "head_damage_mid",
    "head_damage_long",
    "head_multiplier",
    "head_multiplier_pct",
}


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
    "ar": "assault_rifle",
    "ars": "assault_rifle",
    "assaultrifle": "assault_rifle",
    "assaultrifles": "assault_rifle",
    "smg": "smg",
    "smgs": "smg",
    "submachinegun": "smg",
    "submachineguns": "smg",
    "lmg": "lmg",
    "lmgs": "lmg",
    "shotgun": "shotgun",
    "shotguns": "shotgun",
    "sniperrifle": "sniper_rifle",
    "sniperrifles": "sniper_rifle",
    "marksmanrifle": "marksman_rifle",
    "marksmanrifles": "marksman_rifle",
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
        number = float(text)
    except ValueError:
        return fallback

    if pd.isna(number) or number in {float("inf"), float("-inf")}:
        return fallback

    return number


def normalise_numeric_columns(dataframe: pd.DataFrame, columns: set[str]) -> pd.DataFrame:
    updated = dataframe.copy()

    for column in columns:
        if column in updated.columns:
            updated[column] = updated[column].apply(lambda value: numeric_cell(value, 0.0))

    return updated


def normalise_schema_value(value: str) -> str:
    text = unescape(str(value or "").strip()).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def normalise_stats_profile(value, fallback: str = LEGACY_STATS_PROFILE) -> str:
    text = normalise_schema_value(value)

    if not text:
        return fallback

    aliases = {
        "wz": "warzone",
        "warzone": "warzone",
        "mp": "multiplayer",
        "multiplayer": "multiplayer",
        "zombies": "zombies",
        "zm": "zombies",
        "coop": "co_op_endgame",
        "co_op": "co_op_endgame",
        "co_op_endgame": "co_op_endgame",
        "co_op_and_endgame": "co_op_endgame",
        "endgame": "co_op_endgame",
    }

    return aliases.get(text, text)


def ensure_profile_column(dataframe: pd.DataFrame, fallback: str = LEGACY_STATS_PROFILE) -> pd.DataFrame:
    updated = dataframe.copy()

    if "stats_profile" not in updated.columns:
        updated["stats_profile"] = fallback

    updated["stats_profile"] = updated["stats_profile"].apply(
        lambda value: normalise_stats_profile(value, fallback)
    )

    return updated


SLOT_ALIASES = {
    "fire_mod": "fire_mod",
    "fire_mods": "fire_mod",
    "firemods": "fire_mod",
    "firemod": "fire_mod",
    "rear_grip": "rear_grip",
    "reargrip": "rear_grip",
    "under_barrel": "underbarrel",
    "underbarrel": "underbarrel",
    "optic": "optic",
    "optics": "optic",
    "sight": "optic",
    "scope": "optic",
}


def normalise_slot_value(value) -> str:
    key = normalise_schema_value(value)
    return SLOT_ALIASES.get(key, key)


def normalise_list_cell(value, normaliser) -> str:
    items = split_list_cell(value)
    normalised_items = []

    for item in items:
        normalised = normaliser(item)
        if normalised and normalised not in normalised_items:
            normalised_items.append(normalised)

    return ";".join(normalised_items)


def normalise_weapon_class_value(value) -> str:
    return normalise_weapon_class_key(value)


def normalise_ttk_guns_dataframe(guns: pd.DataFrame) -> pd.DataFrame:
    updated = ensure_profile_column(guns, LEGACY_STATS_PROFILE)

    if "gun_id" in updated.columns:
        updated["gun_id"] = updated["gun_id"].apply(slugify)

    if "weapon_class" in updated.columns:
        updated["weapon_class"] = updated["weapon_class"].apply(normalise_weapon_class_value)

    if "verification_status" in updated.columns:
        updated["verification_status"] = updated["verification_status"].apply(normalise_schema_value)

    return updated


def normalise_ttk_attachments_dataframe(attachments: pd.DataFrame) -> pd.DataFrame:
    updated = ensure_profile_column(attachments, LEGACY_STATS_PROFILE)

    if "attachment_id" in updated.columns:
        updated["attachment_id"] = updated["attachment_id"].apply(slugify)

    if "slot" in updated.columns:
        updated["slot"] = updated["slot"].apply(normalise_slot_value)

    if "compatible_weapon_classes" in updated.columns:
        updated["compatible_weapon_classes"] = updated["compatible_weapon_classes"].apply(
            lambda value: normalise_list_cell(value, normalise_weapon_class_value)
        )

    if "compatible_guns" in updated.columns:
        updated["compatible_guns"] = updated["compatible_guns"].apply(
            lambda value: normalise_list_cell(value, slugify)
        )

    if "verification_status" in updated.columns:
        updated["verification_status"] = updated["verification_status"].apply(normalise_schema_value)

    if "optic_type" in updated.columns:
        updated["optic_type"] = updated["optic_type"].apply(normalise_schema_value)

    if "attachment_type" in updated.columns:
        updated["attachment_type"] = updated["attachment_type"].apply(normalise_schema_value)

    return updated


def filter_ttk_data_by_profile(
    guns: pd.DataFrame,
    attachments: pd.DataFrame,
    stats_profile: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    profile = normalise_stats_profile(stats_profile, DEFAULT_STATS_PROFILE)

    filtered_guns = normalise_ttk_guns_dataframe(guns)
    filtered_attachments = normalise_ttk_attachments_dataframe(ensure_attachment_columns(attachments))

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
    guns = normalise_ttk_guns_dataframe(guns)

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
    attachments = normalise_ttk_attachments_dataframe(attachments)

    missing_columns = [
        column for column in REQUIRED_ATTACHMENT_COLUMNS
        if column not in attachments.columns
    ]

    if missing_columns:
        raise ValueError(f"attachments.csv is missing columns: {missing_columns}")

    return normalise_ttk_attachments_dataframe(ensure_attachment_columns(attachments))


def load_ttk_data():
    guns = load_guns()
    attachments = load_attachments()

    return guns, attachments


__all__ = [
    "TTK_DATA_DIR",
    "GUNS_PATH",
    "ATTACHMENTS_PATH",
    "DEFAULT_STATS_PROFILE",
    "LEGACY_STATS_PROFILE",
    "SUPPORTED_STATS_PROFILES",
    "REQUIRED_GUN_COLUMNS",
    "REQUIRED_ATTACHMENT_COLUMNS",
    "OPTIONAL_ATTACHMENT_COLUMNS",
    "EXTENDED_ATTACHMENT_COLUMNS",
    "ATTACHMENT_NUMERIC_COLUMNS",
    "numeric_cell",
    "normalise_numeric_columns",
    "normalise_schema_value",
    "normalise_stats_profile",
    "ensure_profile_column",
    "normalise_slot_value",
    "normalise_list_cell",
    "normalise_weapon_class_value",
    "normalise_weapon_class_key",
    "normalise_ttk_guns_dataframe",
    "normalise_ttk_attachments_dataframe",
    "filter_ttk_data_by_profile",
    "ensure_attachment_columns",
    "slugify",
    "strip_html",
    "split_list_cell",
    "normalise_match_value",
    "normalise_match_key",
    "load_guns",
    "load_attachments",
    "load_ttk_data",
]

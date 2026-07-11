from pathlib import Path
from math import ceil
import json
import re
from html import unescape
import pandas as pd
from itertools import combinations, product


TTK_DATA_DIR = Path("data/bo7_ttk")
GUNS_PATH = TTK_DATA_DIR / "guns.csv"
ATTACHMENTS_PATH = TTK_DATA_DIR / "attachments.csv"

LOADOUT_DATA_DIR = Path("data/bo7_loadouts")
PERKS_PATH = LOADOUT_DATA_DIR / "perks.csv"
WILDCARDS_PATH = LOADOUT_DATA_DIR / "wildcards.csv"
WILDCARD_EFFECTS_PATH = LOADOUT_DATA_DIR / "wildcard_effects.csv"
EQUIPMENT_PATH = LOADOUT_DATA_DIR / "equipment.csv"
FIELD_UPGRADES_PATH = LOADOUT_DATA_DIR / "field_upgrades.csv"
SPECIALTIES_PATH = LOADOUT_DATA_DIR / "specialties.csv"
SPECIALTY_RULES_PATH = LOADOUT_DATA_DIR / "specialty_rules.csv"
LOADOUT_RULES_PATH = LOADOUT_DATA_DIR / "loadout_rules.csv"
LOADOUT_SLOTS_PATH = LOADOUT_DATA_DIR / "loadout_slots.csv"
LOADOUT_TEMPLATES_PATH = LOADOUT_DATA_DIR / "loadout_templates.csv"

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
    "optic_type",
    "attachment_type",
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
    "aiming_idle_sway_pct",
    "visual_recoil_pct",
    "slide_to_fire_pct",
    "dive_to_fire_pct",
    "hipfire_spread_pct",
    "jump_hipfire_spread_pct",
    "slide_hipfire_spread_pct",
    "dive_hipfire_spread_pct",
    "mags_add",
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

PRIMARY_WEAPON_CLASSES = {
    "assault_rifle",
    "smg",
    "shotgun",
    "lmg",
    "marksman_rifle",
    "sniper_rifle",
}

STANDARD_SECONDARY_WEAPON_CLASSES = {
    "pistol",
    "launcher",
    "special",
}

NON_MELEE_WEAPON_CLASSES = PRIMARY_WEAPON_CLASSES | STANDARD_SECONDARY_WEAPON_CLASSES

OVERKILL_PRIMARY_PAIRINGS = {
    frozenset(("assault_rifle", "smg")),
    frozenset(("lmg", "smg")),
    frozenset(("sniper_rifle", "smg")),
    frozenset(("marksman_rifle", "smg")),
    frozenset(("shotgun", "smg")),
}

VALID_LOADOUT_PAIRS = OVERKILL_PRIMARY_PAIRINGS


def is_primary_weapon_class(value: str) -> bool:
    return normalise_weapon_class_value(value) in PRIMARY_WEAPON_CLASSES


def is_standard_secondary_weapon_class(value: str) -> bool:
    return normalise_weapon_class_value(value) in STANDARD_SECONDARY_WEAPON_CLASSES


def is_valid_loadout_pair(weapon_a_class: str, weapon_b_class: str) -> bool:
    weapon_a = normalise_weapon_class_value(weapon_a_class)
    weapon_b = normalise_weapon_class_value(weapon_b_class)

    if weapon_a in PRIMARY_WEAPON_CLASSES and weapon_b in STANDARD_SECONDARY_WEAPON_CLASSES:
        return True

    return frozenset((weapon_a, weapon_b)) in VALID_LOADOUT_PAIRS

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


def load_csv_if_exists(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns or [])

    try:
        dataframe = pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=columns or [])

    if columns:
        for column in columns:
            if column not in dataframe.columns:
                dataframe[column] = ""

    return dataframe


def load_loadout_catalogue() -> dict:
    return {
        "perks": load_csv_if_exists(PERKS_PATH),
        "wildcards": load_csv_if_exists(WILDCARDS_PATH),
        "wildcard_effects": load_csv_if_exists(WILDCARD_EFFECTS_PATH),
        "equipment": load_csv_if_exists(EQUIPMENT_PATH),
        "field_upgrades": load_csv_if_exists(FIELD_UPGRADES_PATH),
        "specialties": load_csv_if_exists(SPECIALTIES_PATH),
        "specialty_rules": load_csv_if_exists(SPECIALTY_RULES_PATH),
        "loadout_rules": load_csv_if_exists(LOADOUT_RULES_PATH),
        "loadout_slots": load_csv_if_exists(LOADOUT_SLOTS_PATH),
        "loadout_templates": load_csv_if_exists(LOADOUT_TEMPLATES_PATH),
    }


def wildcard_id_from_selection(value: str) -> str:
    text = normalise_schema_value(value)

    aliases = {
        "": "oracle_recommends",
        "oracle_recommends": "oracle_recommends",
        "auto": "oracle_recommends",
        "best": "oracle_recommends",
        "none": "none",
        "no_wildcard": "none",
        "overkill": "overkill",
        "gunfighter": "gunfighter",
        "perk_greed": "perk_greed",
        "tac_expert": "tac_expert",
        "danger_close": "danger_close",
        "prepper": "prepper",
        "flyswatter": "flyswatter",
        "high_roller": "high_roller",
        "specialist": "specialist",
    }

    return aliases.get(text, text)


def wildcard_name_from_id(wildcard_id: str) -> str:
    wildcard_id = wildcard_id_from_selection(wildcard_id)

    names = {
        "oracle_recommends": "Oracle recommends",
        "none": "None",
        "overkill": "Overkill",
        "gunfighter": "Gunfighter",
        "perk_greed": "Perk Greed",
        "tac_expert": "Tac Expert",
        "danger_close": "Danger Close",
        "prepper": "Prepper",
        "flyswatter": "Flyswatter",
        "high_roller": "High Roller",
        "specialist": "Specialist",
    }

    return names.get(wildcard_id, wildcard_id.replace("_", " ").title())


def loadout_pairing_requires_overkill(loadout_pairing: str) -> bool:
    text = normalise_match_value(loadout_pairing)
    return "overkill" in text


def loadout_pairing_uses_standard_secondary(loadout_pairing: str) -> bool:
    return "standard secondary" in normalise_match_value(loadout_pairing)


def recommend_wildcard_id(
    *,
    loadout_pairing: str,
    attachment_count: int,
    build_goal: str,
    fight_type: str,
    challenge_requirements: str = "",
    tactical_goal: str = "Auto from build goal / challenge",
    playlist_style: str = "Auto",
) -> str:
    combined = normalise_match_value(
        " ".join(
            [
                loadout_pairing,
                build_goal,
                fight_type,
                challenge_requirements,
                tactical_goal,
                playlist_style,
            ]
        )
    )

    if loadout_pairing_requires_overkill(loadout_pairing):
        return "overkill"

    if int(attachment_count or 0) >= 8 or "8 attachment" in combined or "gunfighter" in combined:
        return "gunfighter"

    if "field upgrade" in combined:
        return "prepper"

    if "tactical" in combined or "detected" in combined or "affected" in combined:
        return "tac_expert"

    if "lethal" in combined or "explosive" in combined:
        return "danger_close"

    if "scorestreak" in combined:
        return "high_roller"

    return "perk_greed"


def effective_wildcard_id(
    selected_wildcard: str,
    *,
    loadout_pairing: str,
    attachment_count: int,
    build_goal: str,
    fight_type: str,
    challenge_requirements: str = "",
    tactical_goal: str = "Auto from build goal / challenge",
    playlist_style: str = "Auto",
) -> str:
    selected = wildcard_id_from_selection(selected_wildcard)

    if selected == "oracle_recommends":
        return recommend_wildcard_id(
            loadout_pairing=loadout_pairing,
            attachment_count=attachment_count,
            build_goal=build_goal,
            fight_type=fight_type,
            challenge_requirements=challenge_requirements,
            tactical_goal=tactical_goal,
            playlist_style=playlist_style,
        )

    return selected


def loadout_legality_warnings(
    *,
    loadout_pairing: str,
    wildcard_id: str,
    attachment_count: int,
) -> list[str]:
    warnings = []
    wildcard_id = wildcard_id_from_selection(wildcard_id)

    if loadout_pairing_requires_overkill(loadout_pairing) and wildcard_id != "overkill":
        warnings.append("Two-primary pairings require the Overkill wildcard.")

    if int(attachment_count or 0) >= 8 and wildcard_id != "gunfighter":
        warnings.append("Eight primary attachments require the Gunfighter wildcard.")

    if loadout_pairing_requires_overkill(loadout_pairing) and int(attachment_count or 0) >= 8:
        warnings.append("Overkill and Gunfighter cannot both be active in one standard BO7 Multiplayer loadout.")

    return warnings



def _context_blob(
    *,
    build_goal: str = "",
    fight_type: str = "",
    challenge_requirements: str = "",
    tactical_goal: str = "Auto from build goal / challenge",
    map_size: str = "Auto",
    playlist_style: str = "Auto",
) -> str:
    return " ".join(
        str(item or "").lower()
        for item in [
            build_goal,
            fight_type,
            challenge_requirements,
            tactical_goal,
            map_size,
            playlist_style,
        ]
    )


def standard_secondary_class_fit_score(
    weapon_class: str,
    *,
    build_goal: str = "",
    fight_type: str = "",
    challenge_requirements: str = "",
    tactical_goal: str = "Auto from build goal / challenge",
    map_size: str = "Auto",
    playlist_style: str = "Auto",
) -> float:
    """
    Score the legal secondary category before every secondary weapon has full TTK data.

    The intent is not to pretend a launcher beats a pistol in a duel. It picks
    the closest legal secondary role for the current mastery/challenge context.
    """
    weapon_class = normalise_weapon_class_value(weapon_class)
    context = _context_blob(
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=tactical_goal,
        map_size=map_size,
        playlist_style=playlist_style,
    )

    scores = {
        "pistol": 0.58,
        "launcher": 0.62,
        "special": 0.48,
    }

    scorestreak_terms = [
        "scorestreak",
        "aerial",
        "vehicle",
        "equipment",
        "field upgrade",
        "destroy",
        "destruction",
        "flyswatter",
    ]
    if any(term in context for term in scorestreak_terms):
        scores["launcher"] += 0.30
        scores["special"] += 0.06

    if "launcher" in context or "direct hit" in context:
        scores["launcher"] += 0.35

    headshot_terms = ["headshot", "military camo", "small", "fast respawn", "close range"]
    if any(term in context for term in headshot_terms):
        scores["pistol"] += 0.18
        scores["launcher"] += 0.06

    objective_terms = ["objective", "domination", "hardpoint", "hill", "flag", "control"]
    if any(term in context for term in objective_terms):
        scores["launcher"] += 0.13
        scores["pistol"] += 0.07
        scores["special"] += 0.04

    if "shortly after switching" in context or "switching weapons" in context:
        scores["pistol"] += 0.35

    if "hipfire" in context or "sprint" in context or "moving" in context:
        scores["pistol"] += 0.10

    if "special" in context or "utility" in context:
        scores["special"] += 0.16

    if "longshot" in context or "one shot" in context or "large" in context:
        scores["launcher"] += 0.10
        scores["pistol"] += 0.03

    return round(max(0.0, scores.get(weapon_class, 0.35)), 4)


def recommend_standard_secondary_slot(
    *,
    build_goal: str = "",
    fight_type: str = "",
    challenge_requirements: str = "",
    tactical_goal: str = "Auto from build goal / challenge",
    map_size: str = "Auto",
    playlist_style: str = "Auto",
    available_classes=None,
) -> dict:
    available_classes = {
        normalise_weapon_class_value(item)
        for item in (available_classes or STANDARD_SECONDARY_WEAPON_CLASSES)
        if normalise_weapon_class_value(item) in STANDARD_SECONDARY_WEAPON_CLASSES
    } or set(STANDARD_SECONDARY_WEAPON_CLASSES)

    scores = {
        weapon_class: standard_secondary_class_fit_score(
            weapon_class,
            build_goal=build_goal,
            fight_type=fight_type,
            challenge_requirements=challenge_requirements,
            tactical_goal=tactical_goal,
            map_size=map_size,
            playlist_style=playlist_style,
        )
        for weapon_class in available_classes
    }

    chosen_class = max(scores, key=scores.get) if scores else "launcher"
    context = _context_blob(
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=tactical_goal,
        map_size=map_size,
        playlist_style=playlist_style,
    )

    labels = {
        "launcher": "Launcher support",
        "pistol": "Emergency sidearm",
        "special": "Special utility",
    }

    if chosen_class == "launcher":
        reason = (
            "Launcher is the closest legal secondary for this context because it adds scorestreak, equipment, "
            "and objective-lane utility without spending Overkill."
        )
        role = "Scorestreak control / utility pressure"
    elif chosen_class == "pistol":
        reason = (
            "Pistol is the closest legal secondary for this context because it protects the primary grind when "
            "you are caught reloading, rotating, or forced into a quick swap fight."
        )
        role = "Emergency swap / finishing tool"
    else:
        reason = (
            "Special weapon is the closest legal secondary for this context because the request is more about "
            "utility or a specific mastery action than raw gunfight coverage."
        )
        role = "Challenge utility / specialist pressure"

    warnings = []
    if chosen_class == "launcher" and not any(term in context for term in ["scorestreak", "destroy", "objective", "launcher"]):
        warnings.append("Launcher is a support pick, not a duel winner. Treat the primary as the kill engine.")

    if chosen_class == "pistol":
        warnings.append("Pistol recommendation is role-based until pistol attachment/base-stat coverage is complete.")

    return {
        "recommended_secondary_class": chosen_class,
        "secondary_slot_recommendation": labels.get(chosen_class, chosen_class),
        "secondary_field_role": role,
        "secondary_advisor_summary": reason,
        "secondary_class_scores": scores,
        "secondary_advisor_warnings": " || ".join(warnings),
        "secondary_advisor_evidence_json": json.dumps(
            {
                "advisor": "standard_secondary_slot",
                "legal_classes": sorted(STANDARD_SECONDARY_WEAPON_CLASSES),
                "available_classes": sorted(available_classes),
                "selected_class": chosen_class,
                "class_scores": scores,
                "build_goal": build_goal,
                "fight_type": fight_type,
                "challenge_requirements": challenge_requirements,
                "tactical_goal": tactical_goal,
                "map_size": map_size,
                "playlist_style": playlist_style,
            },
            indent=2,
        ),
    }


def standard_secondary_placeholder_result(advice: dict | None = None) -> pd.DataFrame:
    advice = advice or recommend_standard_secondary_slot()
    recommended_class = str(advice.get("recommended_secondary_class", "launcher") or "launcher").strip()
    recommendation = str(advice.get("secondary_slot_recommendation", "Standard secondary") or "Standard secondary").strip()
    summary = str(advice.get("secondary_advisor_summary", "") or "").strip()

    return pd.DataFrame(
        [
            {
                "gun_name": recommendation,
                "weapon_class": recommended_class,
                "attachments": (
                    f"Pick a {recommended_class}, then re-run once base stats are captured. "
                    "Secondary weapon stats are not captured in guns.csv yet."
                ),
                "slots": "",
                "oracle_score": 0.0,
                "raw_ttk_ms": 0.0,
                "practical_ttk_ms": 0.0,
                "recoil": 0.0,
                "ads_ms": 0.0,
                "sprint_to_fire_ms": 0.0,
                "bullet_velocity": 0.0,
                "range_m": 0.0,
                "is_shotgun": False,
                "shotgun_truth_score": "",
                "shotgun_one_shot_potential": "",
                "shotgun_two_shot_consistency": "",
                "shotgun_range_coverage": "",
                "shotgun_handling_index": "",
                "shotgun_mag_safety": "",
                "shotgun_truth_note": "",
                "challenge_requirements": "",
                "build_reason_summary": summary or "Standard secondary is advisory until pistol, launcher, and special weapon stats are entered.",
                "score_weight_summary": "",
                "optic_status": "",
                "selected_attachment_notes": "",
                "rejected_breakpoint_notes": "",
                "lab_evidence_json": advice.get("secondary_advisor_evidence_json", ""),
                "secondary_slot_source": "advisory_placeholder",
                "secondary_slot_recommendation": recommendation,
                "secondary_field_role": advice.get("secondary_field_role", ""),
                "secondary_advisor_summary": summary,
                "secondary_advisor_warnings": advice.get("secondary_advisor_warnings", ""),
                "secondary_advisor_evidence_json": advice.get("secondary_advisor_evidence_json", ""),
            }
        ]
    )


def base_only_standard_secondary_result(
    gun,
    *,
    enemy_health: int,
    fight_type: str,
    build_goal: str,
    class_fit_score: float,
    advisor: dict,
) -> dict:
    ranked = build_base_weapon_rankings(
        pd.DataFrame([gun]),
        enemy_health=enemy_health,
        fight_type=fight_type,
        build_goal=build_goal,
    )

    stats = ranked.iloc[0].to_dict() if not ranked.empty else dict(gun)
    practical_ttk = numeric_cell(stats.get("practical_ttk_ms", 0), 0.0)
    raw_ttk = numeric_cell(stats.get("raw_ttk_ms", 0), 0.0)

    # Base stats matter once they exist, but role fit still decides whether the
    # legal secondary is a launcher, pistol, or special for mastery work.
    ttk_component = 0.0
    if practical_ttk > 0:
        ttk_component = max(0.0, min(0.35, (900.0 - practical_ttk) / 900.0 * 0.35))

    recoil = numeric_cell(stats.get("recoil", base_recoil_value(stats)), 0.0)
    recoil_component = max(0.0, min(0.08, (60.0 - recoil) / 60.0 * 0.08)) if recoil > 0 else 0.0

    final_score = round(class_fit_score + ttk_component + recoil_component, 4)
    weapon_class = normalise_weapon_class_value(stats.get("weapon_class", gun.get("weapon_class", "")))

    evidence = {
        "advisor": "standard_secondary_weapon",
        "selected_weapon": stats.get("gun_name", ""),
        "weapon_class": weapon_class,
        "class_fit_score": class_fit_score,
        "ttk_component": round(ttk_component, 4),
        "recoil_component": round(recoil_component, 4),
        "final_score": final_score,
        "raw_ttk_ms": raw_ttk,
        "practical_ttk_ms": practical_ttk,
        "base_only": True,
        "advisor_context": json.loads(advisor.get("secondary_advisor_evidence_json", "{}") or "{}"),
    }

    return {
        "gun_name": stats.get("gun_name", gun.get("gun_name", "")),
        "weapon_class": weapon_class,
        "attachments": "Base secondary. Attachments are not optimised for this slot yet.",
        "slots": "",
        "oracle_score": final_score,
        "raw_ttk_ms": raw_ttk,
        "practical_ttk_ms": practical_ttk,
        "recoil": recoil,
        "ads_ms": numeric_cell(stats.get("ads_ms", 0), 0.0),
        "sprint_to_fire_ms": numeric_cell(stats.get("sprint_to_fire_ms", 0), 0.0),
        "bullet_velocity": numeric_cell(stats.get("bullet_velocity", 0), 0.0),
        "range_m": numeric_cell(stats.get("range_m", stats.get("range_mid_m", 0)), 0.0),
        "is_shotgun": False,
        "shotgun_truth_score": "",
        "shotgun_one_shot_potential": "",
        "shotgun_two_shot_consistency": "",
        "shotgun_range_coverage": "",
        "shotgun_handling_index": "",
        "shotgun_mag_safety": "",
        "shotgun_truth_note": "",
        "challenge_requirements": "",
        "build_reason_summary": (
            f"{stats.get('gun_name', 'Secondary')} is the closest captured standard secondary for "
            f"{advisor.get('secondary_slot_recommendation', 'this role')}. Attachments are not optimised yet."
        ),
        "score_weight_summary": (
            f"Secondary advisor score = category fit {class_fit_score:.3f}"
            + (f" + base TTK component {ttk_component:.3f}" if ttk_component else "")
            + (f" + recoil component {recoil_component:.3f}" if recoil_component else "")
        ),
        "optic_status": "",
        "selected_attachment_notes": "",
        "rejected_breakpoint_notes": "",
        "lab_evidence_json": json.dumps(evidence, indent=2),
        "secondary_slot_source": "base_stats",
        "secondary_slot_recommendation": advisor.get("secondary_slot_recommendation", ""),
        "secondary_field_role": advisor.get("secondary_field_role", ""),
        "secondary_advisor_summary": advisor.get("secondary_advisor_summary", ""),
        "secondary_advisor_warnings": advisor.get("secondary_advisor_warnings", ""),
        "secondary_advisor_evidence_json": json.dumps(evidence, indent=2),
    }


def optimise_standard_secondaries_for_scenario(
    *,
    guns: pd.DataFrame,
    attachments: pd.DataFrame,
    enemy_health: int,
    fight_type: str,
    build_goal: str,
    challenge_requirements: str = "",
    tactical_goal: str = "Auto from build goal / challenge",
    map_size: str = "Auto",
    playlist_style: str = "Auto",
    top_n: int = 10,
) -> pd.DataFrame:
    del attachments  # Reserved for pistol attachments once that data is captured.

    available_classes = set()
    if not guns.empty and "weapon_class" in guns.columns:
        available_classes = {
            normalise_weapon_class_value(item)
            for item in guns["weapon_class"].dropna().tolist()
            if normalise_weapon_class_value(item) in STANDARD_SECONDARY_WEAPON_CLASSES
        }

    advisor = recommend_standard_secondary_slot(
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=tactical_goal,
        map_size=map_size,
        playlist_style=playlist_style,
        available_classes=available_classes or STANDARD_SECONDARY_WEAPON_CLASSES,
    )

    if guns.empty:
        return standard_secondary_placeholder_result(advisor)

    rows = []
    for _, gun in guns.iterrows():
        weapon_class = normalise_weapon_class_value(gun.get("weapon_class", ""))
        if weapon_class not in STANDARD_SECONDARY_WEAPON_CLASSES:
            continue

        class_fit = standard_secondary_class_fit_score(
            weapon_class,
            build_goal=build_goal,
            fight_type=fight_type,
            challenge_requirements=challenge_requirements,
            tactical_goal=tactical_goal,
            map_size=map_size,
            playlist_style=playlist_style,
        )

        rows.append(
            base_only_standard_secondary_result(
                gun,
                enemy_health=enemy_health,
                fight_type=fight_type,
                build_goal=build_goal,
                class_fit_score=class_fit,
                advisor=advisor,
            )
        )

    if not rows:
        return standard_secondary_placeholder_result(advisor)

    return (
        pd.DataFrame(rows)
        .sort_values("oracle_score", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )



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
    close_range = numeric_cell(stats.get("range_close_m", 0), 0.0)
    mid_range = numeric_cell(stats.get("range_mid_m", close_range), close_range)

    if fight_type == "Close range":
        return close_range

    return mid_range


def build_base_weapon_rankings(
    guns,
    enemy_health=300,
    fight_type="Close range",
    build_goal: str = "",
):
    if guns.empty:
        return guns.copy()

    rankings = guns.copy()
    rankings["recoil"] = rankings.apply(
        lambda row: base_recoil_value(row),
        axis=1,
    )
    rankings["range_close_m"] = rankings["range_close_m"].apply(
        lambda value: numeric_cell(value, 0.0)
    )
    rankings["range_mid_m"] = rankings.apply(
        lambda row: numeric_cell(row.get("range_mid_m", 0), numeric_cell(row.get("range_close_m", 0), 0.0)),
        axis=1,
    )
    preferred_damage_column = damage_column_for_fight_type(fight_type, build_goal)
    fallback_damage_column = damage_column_for_fight_type(fight_type, "")

    if preferred_damage_column in rankings.columns:
        preferred_damage = rankings[preferred_damage_column].apply(
            lambda value: numeric_cell(value, 0.0)
        )
    else:
        preferred_damage = pd.Series([0.0] * len(rankings), index=rankings.index)

    fallback_damage = rankings[fallback_damage_column].apply(
        lambda value: numeric_cell(value, 0.0)
    )

    rankings["damage"] = preferred_damage.where(preferred_damage > 0, fallback_damage)
    rankings["damage_model"] = "headshot" if is_headshot_build_goal(build_goal) else "body"
    rankings.loc[preferred_damage <= 0, "damage_model"] = "body"

    rankings["range_m"] = rankings.apply(
        lambda row: effective_range_for_fight_type(row, fight_type),
        axis=1,
    )

    rankings["shots_to_kill"] = rankings["damage"].apply(
        lambda damage: ceil(enemy_health / max(float(damage), 1.0))
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

    weapon_class = normalise_weapon_class_value(gun.get("weapon_class", ""))
    gun_identifiers = [
        gun.get("gun_id", ""),
        gun.get("gun_name", ""),
    ]

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

    gun_allowed = (
        not compatible_guns
        or any(
            matches_compatible_value(
                identifier,
                compatible_guns,
                weapon_class=False,
            )
            for identifier in gun_identifiers
            if str(identifier or "").strip()
        )
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
        numeric_cell(attachment.get("visual_recoil_pct", 0), 0.0) * 0.75,
        numeric_cell(attachment.get("aiming_idle_sway_pct", 0), 0.0) * 0.35,
    ]

    detailed_recoil_values = [
        value for value in detailed_recoil_values
        if value != 0
    ]

    generic_recoil = numeric_cell(attachment.get("recoil_pct", 0), 0.0)

    if detailed_recoil_values:
        return generic_recoil + (sum(detailed_recoil_values) / len(detailed_recoil_values))

    return generic_recoil


def base_recoil_value(source) -> float:
    """
    Return a finite recoil proxy for scoring.

    Some newer gun rows store detailed recoil components but leave the legacy
    recoil column blank. Practical TTK and Oracle Score must not inherit NaN
    from that blank legacy field.
    """
    generic_recoil = numeric_cell(source.get("recoil", 0), 0.0)
    if generic_recoil > 0:
        return generic_recoil

    detailed_recoil_values = [
        numeric_cell(source.get("gun_kick", 0), 0.0),
        numeric_cell(source.get("horizontal_recoil", 0), 0.0),
        numeric_cell(source.get("vertical_recoil", 0), 0.0),
    ]
    detailed_recoil_values = [
        value for value in detailed_recoil_values
        if value > 0
    ]

    if detailed_recoil_values:
        return round(sum(detailed_recoil_values) / len(detailed_recoil_values), 4)

    return 0.0


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

    # Optional headshot-only attachment modifiers.
    # This keeps Military Camo Headshots aware of head damage breakpoints without
    # changing body-damage builds or inventing accuracy assumptions.
    head_damage_pct = numeric_cell(attachment.get("head_damage_pct", 0), 0.0)
    head_multiplier_pct = numeric_cell(attachment.get("head_multiplier_pct", 0), 0.0)
    head_multiplier = numeric_cell(attachment.get("head_multiplier", 0), 0.0)

    for range_name in ["close", "mid", "long"]:
        head_stat = f"head_damage_{range_name}"
        body_stat = f"damage_{range_name}"

        if head_stat not in updated:
            continue

        if head_damage_pct != 0:
            updated[head_stat] = updated[head_stat] * (1 + head_damage_pct / 100)

        range_head_pct = numeric_cell(attachment.get(f"head_damage_{range_name}_pct", 0), 0.0)
        if range_head_pct != 0:
            updated[head_stat] = updated[head_stat] * (1 + range_head_pct / 100)

        range_head_add = numeric_cell(attachment.get(f"head_damage_{range_name}_add", 0), 0.0)
        if range_head_add != 0:
            updated[head_stat] = updated[head_stat] + range_head_add

        if head_multiplier_pct != 0 and body_stat in updated:
            updated[head_stat] = updated[body_stat] * (1 + head_multiplier_pct / 100)

        # Treat head_multiplier as a direct multiplier only when it looks like
        # a real multiplier, e.g. 1.35. This avoids turning a badly-entered
        # percentage like 35 into impossible damage.
        if 0 < head_multiplier <= 5 and body_stat in updated:
            updated[head_stat] = updated[body_stat] * head_multiplier

        # Absolute head damage from the in-game panel is the strongest source.
        # If the row stores both a multiplier and a visible absolute value,
        # the visible value wins for that range.
        range_head_absolute = numeric_cell(attachment.get(f"head_damage_{range_name}", 0), 0.0)
        if range_head_absolute > 0:
            updated[head_stat] = range_head_absolute

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

    # Secondary movement and spread effects are percentage rows from in-game detail
    # screens. They do not change raw TTK, but they matter for close-range
    # practical comfort and must not be treated as zero-effect filler.
    for stat in [
        "slide_to_fire_pct",
        "dive_to_fire_pct",
        "hipfire_spread_pct",
        "jump_hipfire_spread_pct",
        "slide_hipfire_spread_pct",
        "dive_hipfire_spread_pct",
    ]:
        updated[stat] = numeric_cell(updated.get(stat, 0), 0.0) + numeric_cell(
            attachment.get(stat, 0),
            0.0,
        )

    updated["mags"] = numeric_cell(updated.get("mags", 0), 0.0) + numeric_cell(
        attachment.get("mags_add", 0),
        0.0,
    )

    return updated

def is_shotgun_weapon_class(value) -> bool:
    return normalise_weapon_class_value(value) == "shotgun"


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
    damage_close = numeric_cell(gun.get("damage_close", 0), 0.0)
    damage_mid = numeric_cell(gun.get("damage_mid", 0), damage_close)
    damage_long = numeric_cell(gun.get("damage_long", 0), damage_mid)
    range_close = numeric_cell(gun.get("range_close_m", 0), 0.0)
    range_mid = numeric_cell(gun.get("range_mid_m", 0), range_close)

    final_stats = {
        "damage_close": damage_close,
        "range_close_m": range_close,
        "damage_mid": damage_mid,
        "range_mid_m": range_mid,
        "damage_long": damage_long,
        "head_damage_close": numeric_cell(gun.get("head_damage_close", damage_close), damage_close),
        "head_damage_mid": numeric_cell(gun.get("head_damage_mid", damage_mid), damage_mid),
        "head_damage_long": numeric_cell(gun.get("head_damage_long", damage_long), damage_long),
        "fire_rate_rpm": numeric_cell(gun.get("fire_rate_rpm", 0), 0.0),
        "ads_ms": numeric_cell(gun.get("ads_ms", 0), 0.0),
        "sprint_to_fire_ms": numeric_cell(gun.get("sprint_to_fire_ms", 0), 0.0),
        "recoil": base_recoil_value(gun),
        "bullet_velocity": numeric_cell(gun.get("bullet_velocity", 0), 0.0),
        "mag_size": numeric_cell(gun.get("mag_size", 0), 0.0),
        "mags": numeric_cell(gun.get("mags", 0), 0.0),
        "slide_to_fire_pct": 0.0,
        "dive_to_fire_pct": 0.0,
        "hipfire_spread_pct": 0.0,
        "jump_hipfire_spread_pct": 0.0,
        "slide_hipfire_spread_pct": 0.0,
        "dive_hipfire_spread_pct": 0.0,
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
    "Any primary + standard secondary",
    "AR + standard secondary",
    "SMG + standard secondary",
    "Shotgun + standard secondary",
    "LMG + standard secondary",
    "Marksman + standard secondary",
    "Sniper + standard secondary",
    "AR + SMG (Overkill)",
    "LMG + SMG (Overkill)",
    "Sniper + SMG (Overkill)",
    "Marksman + SMG (Overkill)",
    "Any primary + SMG (Overkill)",
]

OVERKILL_LOADOUT_PAIRINGS = {
    "AR + SMG (Overkill)",
    "LMG + SMG (Overkill)",
    "Sniper + SMG (Overkill)",
    "Marksman + SMG (Overkill)",
    "Any primary + SMG (Overkill)",
}

WILDCARD_SELECTION_OPTIONS = [
    "Oracle recommends",
    "None",
    "Overkill",
    "Gunfighter",
    "Perk Greed",
    "Tac Expert",
    "Danger Close",
    "Prepper",
    "Flyswatter",
    "High Roller",
    "Specialist",
]

PERK_PACKAGES = {
    "Aggressive": {
        "perk_1": "Gung Ho",
        "perk_2": "Scavenger",
        "perk_3": "Dexterity",
        "perk_4": "",
        "specialty": "Enforcer",
        "bonus": {
            "ads_ms": -8,
            "sprint_to_fire_ms": -12,
            "reload_ms": 0,
            "recoil": 0,
        },
    },
    "Balanced": {
        "perk_1": "Lightweight",
        "perk_2": "Fast Hands",
        "perk_3": "Tracker",
        "perk_4": "",
        "specialty": "None",
        "bonus": {
            "ads_ms": -5,
            "sprint_to_fire_ms": -5,
            "reload_ms": 0,
            "recoil": -1,
        },
    },
    "Objective": {
        "perk_1": "Flak Jacket",
        "perk_2": "Tech Mask",
        "perk_3": "Guardian",
        "perk_4": "",
        "specialty": "Strategist",
        "bonus": {
            "ads_ms": 0,
            "sprint_to_fire_ms": 0,
            "reload_ms": 0,
            "recoil": -2,
        },
    },
    "Stealth": {
        "perk_1": "Ninja",
        "perk_2": "Vigilance",
        "perk_3": "Cold-Blooded",
        "perk_4": "",
        "specialty": "Recon",
        "bonus": {
            "ads_ms": 0,
            "sprint_to_fire_ms": 0,
            "reload_ms": 0,
            "recoil": -2,
        },
    },
    "Long-range": {
        "perk_1": "Ghost",
        "perk_2": "Vigilance",
        "perk_3": "Cold-Blooded",
        "perk_4": "",
        "specialty": "Recon",
        "bonus": {
            "ads_ms": 0,
            "sprint_to_fire_ms": 0,
            "reload_ms": 0,
            "recoil": -5,
        },
    },
}


PERK_SELECTION_OPTIONS = [
    "Oracle recommends",
    *PERK_PACKAGES.keys(),
]


PERK_PACKAGE_PROFILES = {
    "Aggressive": {
        "role": "Attempt farm",
        "tags": ["mobility", "fast_respawn", "sprint", "moving", "hipfire", "pressure"],
        "strengths": [
            "Best fit when the grind needs repeated fights and fast re-entry.",
            "Uses BO7 perk rows that favour movement, aggression, and attempt volume.",
        ],
        "risks": [
            "Can over-push no-damage or long-lane challenges if the player chases spawns.",
        ],
    },
    "Balanced": {
        "role": "Default grind shell",
        "tags": ["balanced", "headshots", "general", "weapon_grinding"],
        "strengths": [
            "Best default when the challenge needs many repeatable eliminations without over-specialising.",
            "Mixes movement, weapon handling support, and tracking pressure.",
        ],
        "risks": [
            "Does not force a Combat Specialty because it mixes perk families.",
        ],
    },
    "Objective": {
        "role": "Objective anchor",
        "tags": ["objective", "survivability", "hardpoint", "domination", "support", "underbarrel_launcher"],
        "strengths": [
            "Best fit for objective kills, launcher attempts into clustered traffic, and hardpoint/domination pressure.",
            "Uses a Strategist shell for equipment speed, objective score, and survival under utility pressure.",
        ],
        "risks": [
            "Less aggressive than a pure attempt-farm package.",
        ],
    },
    "Stealth": {
        "role": "Flank / survival",
        "tags": ["stealth", "no_damage", "flanking", "headshots", "thermal_counter"],
        "strengths": [
            "Best fit when staying hidden, avoiding third-party deaths, or grinding careful headshots matters.",
            "Uses a Recon shell for stealth and information pressure.",
        ],
        "risks": [
            "Can be slower than Objective or Aggressive in pure respawn chaos.",
        ],
    },
    "Long-range": {
        "role": "Lane holder",
        "tags": ["longshots", "optic_4x", "headshots", "range", "stability", "stealth"],
        "strengths": [
            "Best fit for long lanes, magnified optics, and recoil-stability challenges.",
            "Uses Recon-style survival and visibility tools rather than pure entry speed.",
        ],
        "risks": [
            "Can feel too passive on tiny maps or close-range sprint challenges.",
        ],
    },
}


TACTICAL_GOAL_OPTIONS = [
    "Auto from build goal / challenge",
    "Military headshots",
    "Objective kills",
    "Hipfire kills",
    "Longshots",
    "Kills while moving",
    "Sprint kills",
    "Slide / dive / wall-jump kills",
    "No-damage kills",
    "Suppressor kills",
    "4.0x+ optic kills",
    "Underbarrel launcher kills",
    "5+ attachments",
    "8 attachments",
]

TACTICAL_MAP_SIZE_OPTIONS = [
    "Auto",
    "Small map",
    "Medium map",
    "Large map",
]

TACTICAL_PLAYLIST_STYLE_OPTIONS = [
    "Auto",
    "Fast respawn objective",
    "Objective anchor",
    "Long-range lanes",
    "Passive survival",
    "Weapon levelling",
]

OPTIC_PREFERENCE_OPTIONS = [
    "Any optic",
    "Non-thermal preferred",
    "Reflex / holo preferred",
    "Use my own optic",
    "Force current Oracle optic",
]

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

    movement_comfort_pct = (
        numeric_cell(stats.get("slide_to_fire_pct", 0), 0.0)
        + numeric_cell(stats.get("dive_to_fire_pct", 0), 0.0)
    ) / 2

    spread_comfort_pct = (
        numeric_cell(stats.get("hipfire_spread_pct", 0), 0.0)
        + numeric_cell(stats.get("jump_hipfire_spread_pct", 0), 0.0)
        + numeric_cell(stats.get("slide_hipfire_spread_pct", 0), 0.0)
        + numeric_cell(stats.get("dive_hipfire_spread_pct", 0), 0.0)
    ) / 4

    # Negative percentages are better. Convert them into a small practical
    # comfort adjustment without letting movement stats overpower TTK/recoil.
    close_range_comfort_adjustment_ms = (
        movement_comfort_pct * 0.35
        + spread_comfort_pct * 0.20
    )

    raw_ttk_ms = numeric_cell(stats.get("raw_ttk_ms", 0), 0.0)
    ads_ms = numeric_cell(stats.get("ads_ms", 0), 0.0)
    sprint_to_fire_ms = numeric_cell(stats.get("sprint_to_fire_ms", 0), 0.0)
    recoil = numeric_cell(stats.get("recoil", 0), 0.0)

    return round(
        raw_ttk_ms
        + ads_ms * 0.15
        + sprint_to_fire_ms * 0.10
        + recoil * 2.0
        + close_range_comfort_adjustment_ms,
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

        metric_values = pd.to_numeric(scored[metric], errors="coerce")

        if metric_values.isna().all():
            scored[f"{metric}_score"] = 0.0
            continue

        if metric in LOWER_IS_BETTER:
            fill_value = metric_values.max()
        else:
            fill_value = metric_values.min()

        metric_values = metric_values.fillna(fill_value)
        scored[metric] = metric_values

        min_value = metric_values.min()
        max_value = metric_values.max()

        if min_value == max_value:
            scored[f"{metric}_score"] = 1.0

        elif metric in LOWER_IS_BETTER:
            scored[f"{metric}_score"] = 1 - (
                (metric_values - min_value) / (max_value - min_value)
            )

        else:
            scored[f"{metric}_score"] = (
                (metric_values - min_value) / (max_value - min_value)
            )

        scored["oracle_score"] += scored[f"{metric}_score"].fillna(0.0) * weight

    scored["oracle_score"] = pd.to_numeric(scored["oracle_score"], errors="coerce").fillna(0.0)

    return scored


def safe_round(value, decimals: int = 2, fallback: float = 0.0):
    try:
        number = float(value)
        if pd.isna(number):
            return fallback
        return round(number, decimals)
    except (TypeError, ValueError):
        return fallback


def format_metric_value(value, decimals: int = 1) -> str:
    number = safe_round(value, decimals, 0.0)

    if decimals == 0:
        return f"{number:.0f}"

    text = f"{number:.{decimals}f}"
    return text.rstrip("0").rstrip(".")


EFFECT_DISPLAY_LABELS = {
    "damage_pct": "damage",
    "fire_rate_pct": "fire rate",
    "ads_ms_add": "ADS",
    "sprint_to_fire_ms_add": "sprint-to-fire",
    "recoil_pct": "recoil",
    "bullet_velocity_pct": "bullet velocity",
    "range_pct": "range",
    "mag_size_add": "mag size",
    "ads_pct": "ADS",
    "sprint_to_fire_pct": "sprint-to-fire",
    "reload_pct": "reload",
    "jump_ads_pct": "jump ADS",
    "jump_sprint_to_fire_pct": "jump sprint-to-fire",
    "movement_pct": "movement",
    "sprint_pct": "sprint speed",
    "crouch_movement_pct": "crouch movement",
    "ads_movement_pct": "ADS movement",
    "gun_kick_pct": "gun kick",
    "horizontal_recoil_pct": "horizontal recoil",
    "vertical_recoil_pct": "vertical recoil",
    "first_shot_recoil_pct": "first shot recoil",
    "kick_reset_speed_pct": "kick reset speed",
    "flinch_resistance_pct": "flinch resistance",
    "aiming_idle_sway_pct": "aiming idle sway",
    "visual_recoil_pct": "visual recoil",
    "optic_zoom": "optic zoom",
    "head_damage_pct": "head damage",
    "head_damage_close_pct": "close head damage",
    "head_damage_mid_pct": "mid head damage",
    "head_damage_long_pct": "long head damage",
    "head_damage_close_add": "close head damage",
    "head_damage_mid_add": "mid head damage",
    "head_damage_long_add": "long head damage",
    "head_damage_close": "close head damage",
    "head_damage_mid": "mid head damage",
    "head_damage_long": "long head damage",
    "head_multiplier": "head multiplier",
    "head_multiplier_pct": "head multiplier",
    "slide_to_fire_pct": "slide-to-fire",
    "dive_to_fire_pct": "dive-to-fire",
    "hipfire_spread_pct": "hipfire spread",
    "jump_hipfire_spread_pct": "jump hipfire spread",
    "slide_hipfire_spread_pct": "slide hipfire spread",
    "dive_hipfire_spread_pct": "dive hipfire spread",
    "mags_add": "mag reserves",
}

ABSOLUTE_EFFECT_COLUMNS = {
    "ads_ms_add",
    "sprint_to_fire_ms_add",
    "mag_size_add",
    "head_damage_close",
    "head_damage_mid",
    "head_damage_long",
    "head_damage_close_add",
    "head_damage_mid_add",
    "head_damage_long_add",
    "head_multiplier",
    "optic_zoom",
    "mags_add",
}


def format_attachment_effect(column: str, value) -> str:
    number = numeric_cell(value, 0.0)
    label = EFFECT_DISPLAY_LABELS.get(column, column.replace("_", " "))

    if column == "optic_zoom":
        return f"{label} {format_metric_value(number)}x"

    if column == "head_multiplier":
        return f"{label} x{format_metric_value(number, 2)}"

    sign = "+" if number > 0 else ""

    if column.endswith("_pct") or column in {
        "slide_to_fire_pct",
        "dive_to_fire_pct",
        "hipfire_spread_pct",
        "jump_hipfire_spread_pct",
        "slide_hipfire_spread_pct",
        "dive_hipfire_spread_pct",
    }:
        return f"{label} {sign}{format_metric_value(number)}%"

    if column in {"ads_ms_add", "sprint_to_fire_ms_add"}:
        return f"{label} {sign}{format_metric_value(number, 0)} ms"

    return f"{label} {sign}{format_metric_value(number)}"


def attachment_effect_items(attachment) -> list[str]:
    items = []

    for column in MODELLED_ATTACHMENT_EFFECT_COLUMNS:
        value = numeric_cell(attachment.get(column, 0), 0.0)

        if value == 0:
            continue

        # Absolute head-damage columns describe the post-attachment value rather
        # than a delta, so they are still useful for explanation.
        items.append(format_attachment_effect(column, value))

    return items


def attachment_has_headshot_effect(attachment) -> bool:
    head_columns = [
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
    ]

    return any(
        numeric_cell(attachment.get(column, 0), 0.0) != 0
        for column in head_columns
    )


def attachment_reason_tags(attachment, build_goal: str = "") -> list[str]:
    tags = []
    slot = normalise_slot_value(attachment.get("slot", ""))

    recoil_value = effective_recoil_pct(attachment)
    visual_recoil = numeric_cell(attachment.get("visual_recoil_pct", 0), 0.0)
    idle_sway = numeric_cell(attachment.get("aiming_idle_sway_pct", 0), 0.0)

    ads_delta = (
        numeric_cell(attachment.get("ads_pct", 0), 0.0)
        + numeric_cell(attachment.get("ads_ms_add", 0), 0.0)
    )
    sprint_to_fire_delta = (
        numeric_cell(attachment.get("sprint_to_fire_pct", 0), 0.0)
        + numeric_cell(attachment.get("sprint_to_fire_ms_add", 0), 0.0)
    )

    if slot == "optic":
        optic_zoom = numeric_cell(attachment.get("optic_zoom", 0), 0.0)
        optic_type = normalise_schema_value(attachment.get("optic_type", ""))
        if optic_zoom > 0:
            tags.append(f"{format_metric_value(optic_zoom)}x optic")
        elif optic_type:
            tags.append(f"{optic_type.replace('_', ' ')} optic")
        else:
            tags.append("optic / sight picture")

    if is_headshot_build_goal(build_goal) and attachment_has_headshot_effect(attachment):
        tags.append("headshot damage candidate")

    if recoil_value < 0 or visual_recoil < 0 or idle_sway < 0:
        tags.append("stability gain")
    elif recoil_value > 0 or visual_recoil > 0 or idle_sway > 0:
        tags.append("stability trade-off")

    if ads_delta < 0:
        tags.append("faster ADS")
    elif ads_delta > 0:
        tags.append("ADS penalty")

    if sprint_to_fire_delta < 0:
        tags.append("faster sprint-to-fire")
    elif sprint_to_fire_delta > 0:
        tags.append("sprint-to-fire penalty")

    if numeric_cell(attachment.get("range_pct", 0), 0.0) > 0:
        tags.append("range gain")

    if numeric_cell(attachment.get("bullet_velocity_pct", 0), 0.0) > 0:
        tags.append("bullet velocity gain")

    if numeric_cell(attachment.get("mag_size_add", 0), 0.0) > 0:
        tags.append("magazine safety")

    if not tags:
        tags.append("best combo fit")

    return tags


def selected_attachment_reasoning_lines(selected_attachments: pd.DataFrame, build_goal: str) -> list[str]:
    if selected_attachments.empty:
        return []

    lines = []

    for _, attachment in selected_attachments.iterrows():
        name = str(attachment.get("attachment_name", "") or "").strip()
        slot = normalise_slot_value(attachment.get("slot", ""))
        tags = ", ".join(attachment_reason_tags(attachment, build_goal)[:4])
        effects = "; ".join(attachment_effect_items(attachment))
        raw_text = str(attachment.get("raw_stat_text", "") or "").strip()

        if not effects and raw_text:
            effects = raw_text

        if not effects:
            effects = "no direct modelled stat shown"

        lines.append(
            f"{name} [{slot}] - {tags}. Modelled effects: {effects}."
        )

    return lines


def score_weight_summary(map_type: str, fight_type: str, build_goal: str) -> str:
    weights = build_scenario_weights(
        map_type=map_type,
        fight_type=fight_type,
        build_goal=build_goal,
    )

    parts = []

    for metric, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True):
        parts.append(f"{metric.replace('_', ' ')} {weight * 100:.0f}%")

    return " | ".join(parts)


def build_goal_reason_summary(build_goal: str, fight_type: str, enemy_health: int, preview: dict) -> str:
    damage_model = str(preview.get("damage_model", "body") or "body").strip()
    shots = int(numeric_cell(preview.get("shots_to_kill", 0), 0.0) or 0)
    damage = numeric_cell(preview.get("damage", 0), 0.0)

    if is_headshot_build_goal(build_goal):
        return (
            f"{build_goal} uses {damage_model} damage for shots-to-kill, then rewards stability and handling so headshots are easier to repeat. "
            f"At {enemy_health} HP this build models {format_metric_value(damage)} damage per {damage_model} hit and needs {shots} shot(s) in the selected {fight_type.lower()} profile."
        )

    if build_goal == "Fastest TTK":
        return (
            f"{build_goal} favours raw TTK first, then practical TTK and damage-per-mag as tie-breakers. "
            f"At {enemy_health} HP this build needs {shots} shot(s) in the selected {fight_type.lower()} profile."
        )

    return (
        f"{build_goal} is scored against the selected {fight_type.lower()} profile using the modelled damage, handling, recoil, range, velocity, and magazine values. "
        f"At {enemy_health} HP this build needs {shots} shot(s)."
    )


def optic_status_for_build(selected_attachments: pd.DataFrame, challenge_requirements: str = "", challenge_required_slots: str = "") -> str:
    if selected_attachments.empty or "slot" not in selected_attachments.columns:
        return "No optic selected."

    optic_rows = selected_attachments[
        selected_attachments["slot"].apply(normalise_slot_value).eq("optic")
    ]

    if optic_rows.empty:
        return "No optic selected."

    optic = optic_rows.iloc[0]
    optic_name = str(optic.get("attachment_name", "optic") or "optic").strip()
    optic_zoom = numeric_cell(optic.get("optic_zoom", 0), 0.0)
    zoom_text = f" ({format_metric_value(optic_zoom)}x)" if optic_zoom > 0 else ""

    challenge_text = normalise_match_value(challenge_requirements) + " " + normalise_match_value(challenge_required_slots)
    if "optic" in challenge_text or "4.0" in challenge_text or "4x" in challenge_text:
        return f"{optic_name}{zoom_text} was forced by the challenge lock."

    return f"{optic_name}{zoom_text} was selected by the optimiser, not forced by a challenge lock."


def swap_attachment_for_candidate(selected_attachments: pd.DataFrame, candidate) -> pd.DataFrame:
    candidate_slot = normalise_slot_value(candidate.get("slot", ""))
    updated_rows = []

    for _, attachment in selected_attachments.iterrows():
        if normalise_slot_value(attachment.get("slot", "")) == candidate_slot:
            continue
        updated_rows.append(attachment)

    updated_rows.append(candidate)

    return pd.DataFrame(updated_rows)


def rejected_headshot_breakpoint_notes(
    *,
    gun,
    selected_attachments: pd.DataFrame,
    full_compatible_attachments: pd.DataFrame,
    selected_preview: dict,
    enemy_health: int,
    fight_type: str,
    build_goal: str,
    limit: int = 4,
) -> list[str]:
    if not is_headshot_build_goal(build_goal):
        return []

    if full_compatible_attachments.empty or selected_attachments.empty:
        return []

    selected_keys = {
        attachment_row_key(row)
        for _, row in selected_attachments.iterrows()
    }
    selected_slots = {
        normalise_slot_value(row.get("slot", ""))
        for _, row in selected_attachments.iterrows()
    }

    selected_damage = numeric_cell(selected_preview.get("damage", 0), 0.0)
    selected_stk = int(numeric_cell(selected_preview.get("shots_to_kill", 0), 0.0) or 0)
    selected_recoil = numeric_cell(selected_preview.get("recoil", 0), 0.0)
    selected_practical = numeric_cell(selected_preview.get("practical_ttk_ms", 0), 0.0)

    notes = []
    candidates = []

    for _, candidate in ensure_attachment_columns(full_compatible_attachments).iterrows():
        if attachment_row_key(candidate) in selected_keys:
            continue

        if not attachment_has_headshot_effect(candidate):
            continue

        candidate_slot = normalise_slot_value(candidate.get("slot", ""))
        if candidate_slot not in selected_slots:
            # This explanation is about rejected alternatives inside the chosen
            # slot structure. If the slot was not selected at all, the trade-off
            # involves the whole 8-slot combination and becomes less precise.
            continue

        candidate_selected = swap_attachment_for_candidate(selected_attachments, candidate)
        candidate_preview = build_loadout_preview(
            gun=gun,
            selected_attachments=candidate_selected,
            enemy_health=enemy_health,
            fight_type=fight_type,
            build_goal=build_goal,
        )
        candidate_preview["damage_per_mag"] = (
            numeric_cell(candidate_preview.get("damage", 0), 0.0)
            * numeric_cell(candidate_preview.get("mag_size", 0), 0.0)
        )
        candidate_preview["practical_ttk_ms"] = calculate_practical_ttk_ms(candidate_preview)

        candidate_damage = numeric_cell(candidate_preview.get("damage", 0), 0.0)
        candidate_stk = int(numeric_cell(candidate_preview.get("shots_to_kill", 0), 0.0) or 0)
        candidate_recoil = numeric_cell(candidate_preview.get("recoil", 0), 0.0)
        candidate_practical = numeric_cell(candidate_preview.get("practical_ttk_ms", 0), 0.0)

        if candidate_damage <= selected_damage:
            continue

        candidates.append(
            {
                "name": str(candidate.get("attachment_name", "") or "").strip(),
                "slot": candidate_slot,
                "damage": candidate_damage,
                "shots_to_kill": candidate_stk,
                "recoil": candidate_recoil,
                "practical_ttk_ms": candidate_practical,
                "damage_gain": candidate_damage - selected_damage,
                "recoil_delta": candidate_recoil - selected_recoil,
                "practical_delta": candidate_practical - selected_practical,
            }
        )

    candidates = sorted(
        candidates,
        key=lambda item: (item["shots_to_kill"], -item["damage_gain"], item["practical_delta"]),
    )

    for candidate in candidates[:limit]:
        if candidate["shots_to_kill"] < selected_stk:
            notes.append(
                f"{candidate['name']} [{candidate['slot']}] creates a headshot breakpoint "
                f"({selected_stk}->{candidate['shots_to_kill']} shots at {enemy_health} HP), "
                f"but the full build still lost the scoring pass after recoil/handling trade-offs "
                f"(recoil {format_metric_value(selected_recoil)}->{format_metric_value(candidate['recoil'])}, "
                f"practical TTK {format_metric_value(selected_practical, 0)}->{format_metric_value(candidate['practical_ttk_ms'], 0)} ms)."
            )
        elif candidate["shots_to_kill"] == selected_stk:
            notes.append(
                f"{candidate['name']} [{candidate['slot']}] raises head damage "
                f"{format_metric_value(selected_damage)}->{format_metric_value(candidate['damage'])}, "
                f"but it still needs {selected_stk} shot(s) at {enemy_health} HP. "
                f"The Oracle rejected the trade because recoil/practical TTK worsened "
                f"({format_metric_value(selected_recoil)}->{format_metric_value(candidate['recoil'])}, "
                f"{format_metric_value(selected_practical, 0)}->{format_metric_value(candidate['practical_ttk_ms'], 0)} ms)."
            )
        else:
            notes.append(
                f"{candidate['name']} [{candidate['slot']}] raises head damage "
                f"{format_metric_value(selected_damage)}->{format_metric_value(candidate['damage'])}, "
                f"but its modelled setup needs more shots than the selected build at {enemy_health} HP."
            )

    return notes


def build_lab_evidence_packet(
    *,
    gun,
    selected_attachments: pd.DataFrame,
    preview: dict,
    map_type: str,
    fight_type: str,
    build_goal: str,
    enemy_health: int,
    challenge_requirements: str,
    challenge_required_slots: str,
    rejected_notes: list[str],
) -> str:
    """Compact JSON packet for a future strict Groq lab-note pass."""
    selected = []

    for _, attachment in selected_attachments.iterrows():
        selected.append(
            {
                "name": str(attachment.get("attachment_name", "") or "").strip(),
                "slot": normalise_slot_value(attachment.get("slot", "")),
                "modelled_effects": attachment_effect_items(attachment),
                "raw_stat_text": str(attachment.get("raw_stat_text", "") or "").strip(),
                "optic_zoom": safe_round(attachment.get("optic_zoom", 0), 2),
                "optic_type": normalise_schema_value(attachment.get("optic_type", "")),
                "attachment_type": normalise_schema_value(attachment.get("attachment_type", "")),
                "verification_status": normalise_schema_value(attachment.get("verification_status", "")),
                "verification_notes": str(attachment.get("verification_notes", "") or "").strip(),
            }
        )

    packet = {
        "weapon": str(gun.get("gun_name", "") or "").strip(),
        "weapon_class": normalise_weapon_class_value(gun.get("weapon_class", "")),
        "map_type": map_type,
        "fight_type": fight_type,
        "build_goal": build_goal,
        "enemy_health": int(enemy_health or 0),
        "damage_model": str(preview.get("damage_model", "") or "").strip(),
        "damage": safe_round(preview.get("damage", 0), 2),
        "shots_to_kill": int(numeric_cell(preview.get("shots_to_kill", 0), 0.0) or 0),
        "raw_ttk_ms": safe_round(preview.get("raw_ttk_ms", 0), 2),
        "practical_ttk_ms": safe_round(preview.get("practical_ttk_ms", 0), 2),
        "recoil": safe_round(preview.get("recoil", 0), 2),
        "ads_ms": safe_round(preview.get("ads_ms", 0), 2),
        "sprint_to_fire_ms": safe_round(preview.get("sprint_to_fire_ms", 0), 2),
        "challenge_requirements": challenge_requirements,
        "challenge_required_slots": challenge_required_slots,
        "score_weights": build_scenario_weights(map_type, fight_type, build_goal),
        "selected_attachments": selected,
        "rejected_headshot_breakpoint_notes": rejected_notes,
    }

    return json.dumps(packet, ensure_ascii=False)


def explain_weapon_build(
    *,
    gun,
    selected_attachments: pd.DataFrame,
    full_compatible_attachments: pd.DataFrame,
    preview: dict,
    map_type: str,
    fight_type: str,
    build_goal: str,
    enemy_health: int,
    challenge_requirements: str = "",
    challenge_required_slots: str = "",
) -> dict:
    """Generate deterministic, data-backed explanation fields for UI/Groq.

    This does not invent feel or meta claims. It only describes modelled stats,
    scoring weights, challenge locks, optics, and breakpoint trade-offs.
    """
    selected_lines = selected_attachment_reasoning_lines(selected_attachments, build_goal)
    rejected_notes = rejected_headshot_breakpoint_notes(
        gun=gun,
        selected_attachments=selected_attachments,
        full_compatible_attachments=full_compatible_attachments,
        selected_preview=preview,
        enemy_health=enemy_health,
        fight_type=fight_type,
        build_goal=build_goal,
    )
    optic_status = optic_status_for_build(
        selected_attachments,
        challenge_requirements=challenge_requirements,
        challenge_required_slots=challenge_required_slots,
    )

    summary = build_goal_reason_summary(
        build_goal=build_goal,
        fight_type=fight_type,
        enemy_health=enemy_health,
        preview=preview,
    )

    evidence = build_lab_evidence_packet(
        gun=gun,
        selected_attachments=selected_attachments,
        preview=preview,
        map_type=map_type,
        fight_type=fight_type,
        build_goal=build_goal,
        enemy_health=enemy_health,
        challenge_requirements=challenge_requirements,
        challenge_required_slots=challenge_required_slots,
        rejected_notes=rejected_notes,
    )

    return {
        "build_reason_summary": summary,
        "score_weight_summary": score_weight_summary(map_type, fight_type, build_goal),
        "optic_status": optic_status,
        "selected_attachment_notes": " || ".join(selected_lines),
        "rejected_breakpoint_notes": " || ".join(rejected_notes),
        "lab_evidence_json": evidence,
    }



def normalise_tactical_text(value: str) -> str:
    return normalise_schema_value(value).replace("_", " ")


def _tactical_strings(*values) -> str:
    return " ".join(str(value or "").strip().lower() for value in values if str(value or "").strip())


def _append_unique(items: list[str], additions: list[str]):
    for item in additions:
        if item and item not in items:
            items.append(item)


def selected_optic_from_evidence(row=None, prefix: str = "") -> dict:
    if row is None:
        return {}

    try:
        evidence_text = str(row.get(f"{prefix}lab_evidence_json", "") or "").strip()
    except AttributeError:
        evidence_text = ""

    if not evidence_text:
        try:
            evidence_text = str(row.get("lab_evidence_json", "") or "").strip()
        except AttributeError:
            evidence_text = ""

    if not evidence_text:
        return {}

    try:
        packet = json.loads(evidence_text)
    except (TypeError, json.JSONDecodeError):
        return {}

    for attachment in packet.get("selected_attachments", []) or []:
        if normalise_slot_value(attachment.get("slot", "")) == "optic":
            return attachment

    return {}


def _goal_flags(
    *,
    build_goal: str,
    fight_type: str,
    challenge_requirements: str,
    tactical_goal: str,
    playlist_style: str,
) -> dict[str, bool]:
    text = _tactical_strings(build_goal, fight_type, challenge_requirements, tactical_goal, playlist_style)

    return {
        "headshots": any(token in text for token in ["headshot", "headshots", "military headshots", "military camo"]),
        "objective": "objective" in text,
        "hipfire": "hipfire" in text or "hip fire" in text,
        "longshots": "longshot" in text or "long shot" in text or "long-range lanes" in text,
        "moving": "moving" in text or "movement" in text,
        "sprint": "sprint" in text or "sprinting" in text,
        "slide_dive": "slide" in text or "dive" in text or "wall-jump" in text or "wall jump" in text,
        "no_damage": "no-damage" in text or "without taking damage" in text or "passive survival" in text,
        "suppressor": "suppressor" in text or "supressor" in text,
        "optic_4x": "4.0x" in text or "4x" in text or "optic kills" in text,
        "underbarrel_launcher": "underbarrel launcher" in text or "launcher kills" in text,
        "five_plus": "5+" in text or "5 attachments" in text,
        "eight": "8 attachments" in text or "gunfighter" in text,
    }


def build_tactical_advice(
    *,
    build_goal: str,
    fight_type: str,
    challenge_requirements: str = "",
    tactical_goal: str = "Auto from build goal / challenge",
    map_size: str = "Auto",
    playlist_style: str = "Auto",
    optic_preference: str = "Any optic",
    row=None,
    prefix: str = "",
) -> dict:
    """Return deterministic tactical recommendations for the current Oracle result.

    This is deliberately not Groq. It is a rules-based tactical packet that can
    later be handed to a strict LLM summariser.
    """
    flags = _goal_flags(
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=tactical_goal,
        playlist_style=playlist_style,
    )

    recommended_modes: list[str] = []
    avoid_modes: list[str] = []
    priorities: list[str] = []
    warnings: list[str] = []

    _append_unique(avoid_modes, ["Search & Destroy"])

    if flags["headshots"]:
        _append_unique(recommended_modes, ["Domination", "Hardpoint", "Control-style objective respawn"])
        _append_unique(avoid_modes, ["Team Deathmatch if lobbies are slow or scattered"])
        _append_unique(priorities, [
            "Play predictable objective traffic instead of chasing random spawns.",
            "Hold chest-to-head height lanes and let enemies enter the reticle.",
            "Prioritise recoil control, visual clarity, and flinch resistance over pure raw TTK.",
        ])

    if flags["objective"]:
        _append_unique(recommended_modes, ["Domination", "Hardpoint"])
        _append_unique(priorities, [
            "Build around repeated objective contact and survivability.",
            "Use cover around flags or hills rather than wide roaming routes.",
        ])

    if flags["hipfire"] or flags["slide_dive"]:
        _append_unique(recommended_modes, ["Small-map moshpit", "Hardpoint", "Domination"])
        _append_unique(priorities, [
            "Lean into close-range routes, fast respawns, and repeated entry fights.",
            "Prefer mobility, sprint-to-fire, slide/dive handling, and hipfire spread improvements.",
        ])

    if flags["moving"] or flags["sprint"]:
        _append_unique(recommended_modes, ["Hardpoint", "Domination", "Small-map respawn"])
        _append_unique(priorities, [
            "Stay mobile through predictable routes rather than anchoring one lane.",
            "Value sprint-to-fire, ADS speed, and movement speed more than long-range comfort.",
        ])

    if flags["longshots"] or flags["optic_4x"]:
        _append_unique(recommended_modes, ["Domination on medium/large maps", "Long-lane objective playlists"])
        _append_unique(avoid_modes, ["Tiny chaos maps unless the challenge only needs optic-equipped eliminations"])
        _append_unique(priorities, [
            "Pick maps with repeatable long lanes and predictable objective crossings.",
            "Do not judge the build only by close-range TTK if the challenge requires magnification or distance.",
        ])

    if flags["no_damage"]:
        _append_unique(recommended_modes, ["Domination", "Hardpoint with anchor play", "Slower respawn playlists only if you can control angles"])
        _append_unique(avoid_modes, ["Small-map chaos when you need clean first-shot fights"])
        _append_unique(priorities, [
            "Play pre-aimed angles and reset after each kill.",
            "Survivability and information perks matter more than pure speed.",
        ])

    if flags["suppressor"]:
        _append_unique(recommended_modes, ["Domination", "Hardpoint", "Kill Confirmed"])
        _append_unique(priorities, [
            "Use the suppressor as a challenge lock first; only trust the rest of the build after field testing recoil and velocity.",
        ])

    if flags["underbarrel_launcher"]:
        _append_unique(recommended_modes, ["Hardpoint", "Domination", "Objective chokepoint playlists"])
        _append_unique(avoid_modes, ["Team Deathmatch if enemies spread out"])
        _append_unique(priorities, [
            "Treat the gun as a launcher carrier platform, not a pure TTK build.",
            "Play clustered objective traffic and pre-load launcher routes.",
        ])
        warnings.append("Underbarrel launcher kills are challenge-specific. Weapon TTK does not model blast reliability, ammo economy, or direct-hit consistency.")

    if flags["five_plus"] or flags["eight"]:
        _append_unique(recommended_modes, ["Fast respawn objective modes"])
        _append_unique(priorities, [
            "The attachment count is a hard compliance target. Field test whether the extra slot improves comfort or just satisfies the camo rule.",
        ])

    if not recommended_modes:
        _append_unique(recommended_modes, ["Domination", "Hardpoint", "Fast respawn modes"])

    if not priorities:
        _append_unique(priorities, [
            "Use the Oracle build as a candidate, then field test recoil comfort, sight picture, and lobby flow.",
        ])

    map_key = normalise_tactical_text(map_size)
    if "small map" in map_key:
        if flags["headshots"]:
            warnings.append("Small maps create more headshot attempts, but optic clutter and thermal overlays can become a real comfort risk.")
        if flags["optic_4x"]:
            warnings.append("4.0x+ optics are challenge-compliant on small maps, but not automatically comfortable. Treat the optic as FIELD TEST REQUIRED.")
    elif "large map" in map_key:
        _append_unique(priorities, ["Large maps increase value for bullet velocity, range, recoil stability, and clean optics."])

    playlist_key = normalise_tactical_text(playlist_style)
    if "fast respawn" in playlist_key:
        _append_unique(recommended_modes, ["Small-map objective respawn"])
        _append_unique(priorities, ["Maximise attempts per minute. Do not waste time in low-engagement playlists."])
    elif "objective anchor" in playlist_key:
        _append_unique(recommended_modes, ["Domination", "Hardpoint"])
        _append_unique(priorities, ["Anchor a repeatable lane near the objective rather than sprinting through the whole map."])
    elif "long range" in playlist_key:
        _append_unique(recommended_modes, ["Domination on medium/large maps"])
        _append_unique(priorities, ["Avoid short sightline maps even if the build's raw TTK looks strong."])
    elif "passive survival" in playlist_key:
        _append_unique(priorities, ["Slow the pace, take first-shot advantage, and reset after each engagement."])

    optic = selected_optic_from_evidence(row, prefix=prefix)
    optic_note = ""

    if optic:
        optic_name = str(optic.get("name", "") or "").strip()
        optic_type = normalise_schema_value(optic.get("optic_type", ""))
        optic_zoom = numeric_cell(optic.get("optic_zoom", 0), 0.0)
        verification_status = normalise_schema_value(optic.get("verification_status", ""))

        optic_parts = [f"Selected optic: {optic_name}"]
        if optic_type:
            optic_parts.append(f"type={optic_type}")
        if optic_zoom:
            optic_parts.append(f"zoom={optic_zoom:g}x")
        optic_note = " | ".join(optic_parts)

        if optic_type == "thermal":
            warnings.append("THERMAL SIGHT PICTURE UNMODELLED: the optic may score well on recoil/stability while still feeling poor for small-map headshot grinding.")

        if verification_status in {"needs_review", "partial"}:
            warnings.append(f"Optic data is {verification_status}. Trust the modelled numbers, but field test the sight picture.")

        preference_key = normalise_tactical_text(optic_preference)
        if "non thermal" in preference_key and optic_type == "thermal":
            warnings.append("Optic preference conflict: the Oracle selected a thermal optic while non-thermal is preferred.")
        if "reflex" in preference_key and optic_type not in {"reflex", "holo"}:
            warnings.append("Optic preference conflict: this is not a reflex/holo optic. Keep the build shell and swap to your preferred reticle if needed.")
        if "use my own optic" in preference_key:
            warnings.append("You selected 'Use my own optic'. Treat the optic recommendation as replaceable and keep the non-optic build shell.")

    elif "optic" in _tactical_strings(challenge_requirements, tactical_goal):
        warnings.append("The tactical context expects an optic, but no optic was detected in the winning build evidence.")

    summary_bits = []

    if flags["headshots"]:
        summary_bits.append("Headshot grind: favour predictable objective traffic, recoil stability, and clean sight picture.")
    elif flags["objective"]:
        summary_bits.append("Objective grind: optimise for repeated contact around flags or hills.")
    elif flags["underbarrel_launcher"]:
        summary_bits.append("Launcher grind: use the weapon as a challenge carrier and farm clustered objective traffic.")
    else:
        summary_bits.append("General grind: use fast respawn modes and field test the candidate before trusting it.")

    if map_size and map_size != "Auto":
        summary_bits.append(f"Map bias: {map_size}.")
    if playlist_style and playlist_style != "Auto":
        summary_bits.append(f"Playlist bias: {playlist_style}.")

    return {
        "summary": " ".join(summary_bits),
        "recommended_modes": recommended_modes,
        "avoid_modes": avoid_modes,
        "priorities": priorities,
        "warnings": warnings,
        "optic_note": optic_note,
        "tactical_goal": tactical_goal,
        "map_size": map_size,
        "playlist_style": playlist_style,
        "optic_preference": optic_preference,
    }


def _perk_text_flags(
    *,
    build_goal: str,
    fight_type: str,
    challenge_requirements: str,
    tactical_goal: str,
    map_size: str,
    playlist_style: str,
) -> dict[str, bool]:
    flags = _goal_flags(
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=tactical_goal,
        playlist_style=playlist_style,
    )

    text = _tactical_strings(build_goal, fight_type, challenge_requirements, tactical_goal, map_size, playlist_style)
    flags["small_map"] = "small map" in text
    flags["large_map"] = "large map" in text
    flags["fast_respawn"] = "fast respawn" in text
    flags["anchor"] = "anchor" in text or "objective anchor" in text
    flags["weapon_levelling"] = "weapon levelling" in text or "weapon leveling" in text
    return flags


def perk_package_fit_score(
    perk_package: str,
    *,
    build_goal: str,
    fight_type: str,
    challenge_requirements: str = "",
    tactical_goal: str = "Auto from build goal / challenge",
    map_size: str = "Auto",
    playlist_style: str = "Auto",
) -> float:
    """Small deterministic score add-on for the full-loadout optimiser.

    Weapon TTK remains the main score. This only lets the Oracle choose between
    known package shells when Thomas asks it to recommend perks.
    """
    package = str(perk_package or "").strip()
    flags = _perk_text_flags(
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=tactical_goal,
        map_size=map_size,
        playlist_style=playlist_style,
    )

    score = 0.0

    if package == "Aggressive":
        if flags["hipfire"] or flags["moving"] or flags["sprint"] or flags["slide_dive"]:
            score += 0.055
        if flags["objective"] or flags["fast_respawn"]:
            score += 0.030
        if flags["headshots"]:
            score += 0.015
        if flags["no_damage"] or flags["longshots"] or flags["optic_4x"]:
            score -= 0.010

    elif package == "Balanced":
        score += 0.015
        if flags["headshots"] or flags["suppressor"]:
            score += 0.035
        if flags["objective"] or flags["weapon_levelling"]:
            score += 0.025
        if flags["five_plus"] or flags["eight"]:
            score += 0.015

    elif package == "Objective":
        if flags["objective"] or flags["underbarrel_launcher"] or flags["anchor"]:
            score += 0.060
        if flags["fast_respawn"]:
            score += 0.025
        if flags["no_damage"]:
            score += 0.015
        if flags["longshots"] and not flags["objective"]:
            score -= 0.010

    elif package == "Stealth":
        if flags["no_damage"]:
            score += 0.060
        if flags["headshots"]:
            score += 0.040
        if flags["suppressor"]:
            score += 0.030
        if flags["small_map"] and (flags["hipfire"] or flags["sprint"] or flags["slide_dive"]):
            score -= 0.010

    elif package == "Long-range":
        if flags["longshots"] or flags["optic_4x"] or str(fight_type).strip() == "Long range":
            score += 0.060
        if flags["headshots"]:
            score += 0.035
        if flags["large_map"]:
            score += 0.025
        if flags["small_map"] and not flags["longshots"]:
            score -= 0.015
        if flags["sprint"] or flags["slide_dive"] or flags["hipfire"]:
            score -= 0.020

    return round(score, 4)


def _perk_join(items: list[str]) -> str:
    return " || ".join(item for item in items if str(item or "").strip())




def forced_attachment_rules_summary(forced_attachment_rules) -> str:
    if not forced_attachment_rules:
        return ""

    labels = []
    for rule in forced_attachment_rules:
        if not isinstance(rule, dict):
            continue
        label = str(rule.get("label", "") or "").strip()
        if label and label not in labels:
            labels.append(label)

    return " | ".join(labels)



def recommend_perk_package(
    *,
    build_goal: str,
    fight_type: str,
    challenge_requirements: str = "",
    tactical_goal: str = "Auto from build goal / challenge",
    map_size: str = "Auto",
    playlist_style: str = "Auto",
) -> str:
    scores = {}

    for package_name in PERK_PACKAGES:
        scores[package_name] = (
            perk_package_score_bonus(package_name)
            + perk_package_fit_score(
                package_name,
                build_goal=build_goal,
                fight_type=fight_type,
                challenge_requirements=challenge_requirements,
                tactical_goal=tactical_goal,
                map_size=map_size,
                playlist_style=playlist_style,
            )
        )

    if not scores:
        return "Balanced"

    return max(scores, key=scores.get)



def build_perk_loadout_advice(
    *,
    perk_package: str,
    build_goal: str,
    fight_type: str,
    challenge_requirements: str = "",
    tactical_goal: str = "Auto from build goal / challenge",
    map_size: str = "Auto",
    playlist_style: str = "Auto",
    loadout_pairing: str = "",
    wildcard_id: str = "none",
    loadout_legality_notes: list[str] | None = None,
) -> dict:
    package_name = str(perk_package or "").strip()
    package = PERK_PACKAGES.get(package_name, {})
    profile = PERK_PACKAGE_PROFILES.get(package_name, {})
    flags = _perk_text_flags(
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=tactical_goal,
        map_size=map_size,
        playlist_style=playlist_style,
    )
    wildcard_id = wildcard_id_from_selection(wildcard_id)
    wildcard_name = wildcard_name_from_id(wildcard_id)
    loadout_legality_notes = loadout_legality_notes or []

    reasons = []
    warnings = []
    equipment_priorities = []
    playstyle_notes = []

    role = profile.get("role", "Loadout shell")
    strengths = profile.get("strengths", [])
    risks = profile.get("risks", [])

    reasons.extend(strengths)

    if flags["headshots"]:
        reasons.append("Headshot grinding values stability, repeatable lanes, and staying alive long enough to chain attempts.")
        equipment_priorities.extend([
            "Use tactical/equipment choices that create first-shot advantage or slow enemies entering your lane.",
            "Avoid equipment that forces you to sprint blindly into random gunfights.",
        ])
        playstyle_notes.append("Hold predictable chest-to-head-height traffic rather than chasing every red dot.")

    if flags["objective"]:
        reasons.append("Objective kills need repeatable contact around flags, hills, or chokepoints.")
        equipment_priorities.append("Prioritise objective-entry or objective-hold tools over pure damage padding.")
        playstyle_notes.append("Play around the objective edge, not the middle of the hill.")

    if flags["underbarrel_launcher"]:
        reasons.append("Underbarrel launcher challenges are about farming clustered traffic, not proving the gun's bullet TTK.")
        equipment_priorities.append("Prioritise ammo sustain and objective chokepoint pressure if those options exist in your class setup.")
        playstyle_notes.append("Treat the weapon as a launcher carrier. Pre-aim entry routes and reload/reset after the launcher attempt.")

    if flags["longshots"] or flags["optic_4x"]:
        reasons.append("Magnified optic or longshot requirements need lane control and visibility more than close-range speed.")
        equipment_priorities.append("Prioritise information and lane-control tools over panic-entry tools.")
        playstyle_notes.append("Back out of tiny-map chaos unless the challenge only checks optic-equipped eliminations.")

    if flags["no_damage"]:
        reasons.append("No-damage kills reward first-shot advantage, information, and survival over raw rushing.")
        equipment_priorities.append("Prioritise tools that let you reset, isolate, or pre-aim fights.")
        playstyle_notes.append("After each kill, reposition instead of ego-challenging the next angle.")

    if flags["hipfire"] or flags["sprint"] or flags["moving"] or flags["slide_dive"]:
        reasons.append("Movement challenges need attempts per minute and close-range repeatability.")
        equipment_priorities.append("Prioritise entry tools and fast-reset routes.")
        playstyle_notes.append("Route through predictable close-range paths instead of holding long lanes.")

    if not reasons:
        reasons.append("No specialised perk pressure detected. Use the package as a general grind shell and field test lobby flow.")

    warnings.extend(risks)

    if package_name == "Aggressive" and (flags["no_damage"] or flags["longshots"]):
        warnings.append("Aggressive is attempt-rich but can fight the challenge if it makes you over-push.")
    if package_name == "Long-range" and (flags["small_map"] or flags["hipfire"] or flags["slide_dive"]):
        warnings.append("Long-range is stable, but may feel too passive for small-map movement challenges.")
    if flags["underbarrel_launcher"]:
        warnings.append("The Oracle cannot model blast radius, direct-hit consistency, or launcher ammo economy yet.")

    warnings.extend(loadout_legality_notes)

    recommended_tactical = "Pinpoint Grenade" if flags["headshots"] else "Stim Shot"
    recommended_lethal = "Molotov" if flags["objective"] else "Frag"
    recommended_field_upgrade = "Trophy System" if flags["objective"] else "Assault Pack"

    if flags["underbarrel_launcher"]:
        recommended_tactical = "Smoke"
        recommended_lethal = "Cluster Grenade"
        recommended_field_upgrade = "Assault Pack"
    elif flags["no_damage"]:
        recommended_tactical = "Smoke"
        recommended_lethal = "C4"
        recommended_field_upgrade = "Active Camo"
    elif flags["longshots"] or flags["optic_4x"]:
        recommended_tactical = "Pinpoint Grenade"
        recommended_lethal = "Needle Drone"
        recommended_field_upgrade = "Tactical Insertion"
    elif flags["hipfire"] or flags["sprint"] or flags["moving"] or flags["slide_dive"]:
        recommended_tactical = "Stim Shot"
        recommended_lethal = "Semtex"
        recommended_field_upgrade = "Mute Field"

    if wildcard_id == "overkill":
        playstyle_notes.append("Overkill is active, so the secondary slot may legally be another non-melee weapon.")
    elif wildcard_id == "gunfighter":
        playstyle_notes.append("Gunfighter is active, so the primary weapon can legally use 8 attachments.")
    elif wildcard_id == "perk_greed":
        playstyle_notes.append("Perk Greed is a general-purpose wildcard. Its extra perk does not count towards Combat Specialty.")
    elif wildcard_id == "tac_expert":
        playstyle_notes.append("Tac Expert supports tactical equipment challenge pressure with an extra tactical.")
    elif wildcard_id == "prepper":
        playstyle_notes.append("Prepper supports field-upgrade challenge pressure with two different Field Upgrades.")

    bonus = package.get("bonus", {})
    evidence = {
        "perk_package": package_name,
        "role": role,
        "perks": {
            "perk_1": package.get("perk_1", ""),
            "perk_2": package.get("perk_2", ""),
            "perk_3": package.get("perk_3", ""),
            "perk_4": package.get("perk_4", ""),
        },
        "modelled_bonus": bonus,
        "fit_score": perk_package_fit_score(
            package_name,
            build_goal=build_goal,
            fight_type=fight_type,
            challenge_requirements=challenge_requirements,
            tactical_goal=tactical_goal,
            map_size=map_size,
            playlist_style=playlist_style,
        ),
        "build_goal": build_goal,
        "fight_type": fight_type,
        "challenge_requirements": challenge_requirements,
        "tactical_goal": tactical_goal,
        "map_size": map_size,
        "playlist_style": playlist_style,
        "loadout_pairing": loadout_pairing,
        "wildcard_id": wildcard_id,
        "wildcard_name": wildcard_name,
        "recommended_tactical": recommended_tactical,
        "recommended_lethal": recommended_lethal,
        "recommended_field_upgrade": recommended_field_upgrade,
        "loadout_legality_notes": loadout_legality_notes,
        "reasons": reasons,
        "warnings": warnings,
        "equipment_priorities": equipment_priorities,
        "playstyle_notes": playstyle_notes,
    }

    specialty = str(package.get("specialty", "") or "").strip()
    specialty_text = f" Combat Specialty: {specialty}." if specialty else ""
    summary = (
        f"{package_name} selected as {role}. "
        f"Wildcard: {wildcard_name}. "
        f"Perks: {package.get('perk_1', '')}, {package.get('perk_2', '')}, "
        f"{package.get('perk_3', '')}." + specialty_text
    )

    return {
        "perk_recommendation_summary": summary,
        "perk_role": role,
        "perk_fit_score": evidence["fit_score"],
        "perk_score_bonus": perk_package_score_bonus(package_name),
        "perk_reasons": _perk_join(reasons),
        "perk_warnings": _perk_join(warnings),
        "equipment_priorities": _perk_join(equipment_priorities),
        "playstyle_notes": _perk_join(playstyle_notes),
        "wildcard_id": wildcard_id,
        "wildcard_name": wildcard_name,
        "recommended_tactical": recommended_tactical,
        "recommended_lethal": recommended_lethal,
        "recommended_field_upgrade": recommended_field_upgrade,
        "loadout_legality_notes": _perk_join(loadout_legality_notes),
        "perk_lab_evidence_json": json.dumps(evidence, indent=2),
    }


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
    "aiming_idle_sway_pct",
    "visual_recoil_pct",
    "slide_to_fire_pct",
    "dive_to_fire_pct",
    "hipfire_spread_pct",
    "jump_hipfire_spread_pct",
    "slide_hipfire_spread_pct",
    "dive_hipfire_spread_pct",
    "mags_add",
    "head_damage_pct",
    "head_damage_close_pct",
    "head_damage_mid_pct",
    "head_damage_long_pct",
    "head_damage_close_add",
    "head_damage_mid_add",
    "head_damage_long_add",
    "head_multiplier_pct",
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
    "aiming_idle_sway_pct",
    "visual_recoil_pct",
    "slide_to_fire_pct",
    "dive_to_fire_pct",
    "hipfire_spread_pct",
    "jump_hipfire_spread_pct",
    "slide_hipfire_spread_pct",
    "dive_hipfire_spread_pct",
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


def _clean_required_slots(required_slots=None) -> set[str]:
    if not required_slots:
        return set()

    return {
        normalise_slot_value(slot)
        for slot in required_slots
        if str(slot or "").strip()
    }


def generate_legal_attachment_combos(
    compatible_attachments,
    attachment_count,
    required_slots=None,
):
    """
    Exact legal build generator.

    Instead of trying every attachment combination and rejecting duplicate slots,
    this groups attachments by slot first, then only generates builds with one
    attachment per selected slot.

    Challenge locks can force required slots into every generated build while
    still allowing the Oracle to optimise the remaining slots normally.
    """

    if compatible_attachments.empty:
        return

    slot_groups = {}

    for slot, group in compatible_attachments.groupby("slot"):
        clean_slot = normalise_slot_value(slot)

        if not clean_slot:
            continue

        slot_groups[clean_slot] = [
            attachment
            for _, attachment in group.iterrows()
        ]

    slot_names = sorted(slot_groups.keys())
    required_slot_names = _clean_required_slots(required_slots)

    if len(slot_names) < attachment_count:
        return

    if len(required_slot_names) > attachment_count:
        return

    if any(slot not in slot_groups for slot in required_slot_names):
        return

    optional_slot_names = [
        slot
        for slot in slot_names
        if slot not in required_slot_names
    ]

    optional_count = attachment_count - len(required_slot_names)

    for optional_slots in combinations(optional_slot_names, optional_count):
        selected_slots = sorted([*required_slot_names, *optional_slots])
        grouped_options = [
            slot_groups[slot]
            for slot in selected_slots
        ]

        for combo in product(*grouped_options):
            yield combo


def estimate_legal_attachment_combo_count(
    slot_counts: dict[str, int],
    attachment_count: int,
    required_slots=None,
) -> int:
    """
    Count legal one-attachment-per-slot combinations without generating them.

    This powers the TTK page's workload warning so 8-attachment scans are visible
    before a deep brute-force pass starts.
    """
    normalised_slot_counts = {}

    for slot, count in slot_counts.items():
        clean_slot = normalise_slot_value(slot)
        if clean_slot and int(count or 0) > 0:
            normalised_slot_counts[clean_slot] = normalised_slot_counts.get(clean_slot, 0) + int(count or 0)

    slot_names = sorted(normalised_slot_counts.keys())
    required_slot_names = _clean_required_slots(required_slots)

    if len(slot_names) < attachment_count:
        return 0

    if len(required_slot_names) > attachment_count:
        return 0

    if any(slot not in slot_names for slot in required_slot_names):
        return 0

    optional_slot_names = [
        slot
        for slot in slot_names
        if slot not in required_slot_names
    ]

    optional_count = attachment_count - len(required_slot_names)

    total = 0

    for optional_slots in combinations(optional_slot_names, optional_count):
        selected_slots = sorted([*required_slot_names, *optional_slots])
        product_count = 1

        for slot in selected_slots:
            product_count *= int(normalised_slot_counts.get(slot, 0) or 0)

        total += product_count

    return int(total)


def _list_value(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = [value]

    return [
        str(item).strip()
        for item in values
        if str(item or "").strip()
    ]


def attachment_row_key(attachment) -> str:
    attachment_id = normalise_match_key(attachment.get("attachment_id", ""))

    if attachment_id:
        return f"id:{attachment_id}"

    return (
        "name:"
        + normalise_match_key(attachment.get("slot", ""))
        + "::"
        + normalise_match_key(attachment.get("attachment_name", ""))
    )


def attachment_matches_forced_rule(attachment, rule: dict) -> bool:
    slot = normalise_slot_value(rule.get("slot", ""))
    if slot and normalise_slot_value(attachment.get("slot", "")) != slot:
        return False

    attachment_id = str(rule.get("attachment_id", "") or "").strip()
    if attachment_id and normalise_match_key(attachment.get("attachment_id", "")) != normalise_match_key(attachment_id):
        return False

    attachment_name = str(rule.get("attachment_name", "") or "").strip()
    if attachment_name and normalise_match_key(attachment.get("attachment_name", "")) != normalise_match_key(attachment_name):
        return False

    name_text = normalise_match_value(attachment.get("attachment_name", ""))
    contains_any = _list_value(rule.get("name_contains_any", rule.get("name_contains", [])))

    if contains_any and not any(normalise_match_value(term) in name_text for term in contains_any):
        return False

    contains_all = _list_value(rule.get("name_contains_all", []))

    if contains_all and not all(normalise_match_value(term) in name_text for term in contains_all):
        return False

    # Some challenge requirements are better matched as a class of attachment
    # rather than a single display-name fragment. Example: underbarrel launchers
    # may be tagged in attachment_type, visible in the raw stat text, or written
    # directly in the attachment name.
    search_text = " ".join(
        normalise_match_value(attachment.get(field, ""))
        for field in [
            "attachment_name",
            "attachment_id",
            "attachment_type",
            "raw_stat_text",
        ]
    )

    text_contains_any = _list_value(rule.get("text_contains_any", []))
    if text_contains_any and not any(normalise_match_value(term) in search_text for term in text_contains_any):
        return False

    text_contains_all = _list_value(rule.get("text_contains_all", []))
    if text_contains_all and not all(normalise_match_value(term) in search_text for term in text_contains_all):
        return False

    attachment_type = normalise_schema_value(rule.get("attachment_type", ""))
    if attachment_type and normalise_schema_value(attachment.get("attachment_type", "")) != attachment_type:
        return False

    attachment_type_any = _list_value(rule.get("attachment_type_any", []))
    if attachment_type_any:
        allowed_types = {normalise_schema_value(item) for item in attachment_type_any}
        if normalise_schema_value(attachment.get("attachment_type", "")) not in allowed_types:
            return False

    min_optic_zoom = numeric_cell(rule.get("min_optic_zoom", 0), 0.0)
    exact_optic_zoom = numeric_cell(rule.get("optic_zoom", 0), 0.0)
    attachment_zoom = numeric_cell(attachment.get("optic_zoom", 0), 0.0)

    if min_optic_zoom > 0 and attachment_zoom < min_optic_zoom:
        return False

    if exact_optic_zoom > 0 and attachment_zoom != exact_optic_zoom:
        return False

    optic_type = normalise_schema_value(rule.get("optic_type", ""))
    if optic_type and normalise_schema_value(attachment.get("optic_type", "")) != optic_type:
        return False

    # A slot-only rule is valid, for example "any optic".
    return bool(
        slot
        or attachment_id
        or attachment_name
        or contains_any
        or contains_all
        or text_contains_any
        or text_contains_all
        or attachment_type
        or attachment_type_any
        or min_optic_zoom > 0
        or exact_optic_zoom > 0
        or optic_type
    )


def forced_rule_label(rule: dict) -> str:
    label = str(rule.get("label", "") or "").strip()

    if label:
        return label

    attachment_name = str(rule.get("attachment_name", "") or "").strip()
    if attachment_name:
        return attachment_name

    contains_any = _list_value(rule.get("name_contains_any", rule.get("name_contains", [])))
    if contains_any:
        return " or ".join(contains_any)

    slot = normalise_slot_value(rule.get("slot", ""))
    if slot:
        return f"any_{slot}"

    return "Challenge attachment"


def forced_attachment_rule_summary(forced_attachment_rules=None) -> str:
    rules = [
        rule
        for rule in (forced_attachment_rules or [])
        if isinstance(rule, dict)
    ]

    labels = [
        forced_rule_label(rule)
        for rule in rules
    ]

    return " | ".join(label for label in labels if label)


def prepare_challenge_attachment_pool(compatible_attachments: pd.DataFrame) -> pd.DataFrame:
    """
    Challenge locks may require a row that normal optimisation blocks.

    Example: underbarrel launchers are deliberately marked unmodelled because
    their projectile behaviour is outside normal gun TTK. They still need to be
    available when a camo explicitly requires an underbarrel launcher.

    Truly unsafe rows remain blocked, but unmodelled utility rows are allowed
    only inside this hard-lock pool.
    """
    if compatible_attachments.empty:
        return compatible_attachments.copy()

    updated = ensure_attachment_columns(compatible_attachments)
    updated = updated.copy()

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

    hard_block_statuses = {
        "exclude",
        "excluded",
        "invalid",
        "broken",
        "do_not_use",
    }

    status_mask = ~updated["verification_status"].apply(
        lambda value: normalise_match_value(value) in hard_block_statuses
    )
    updated = updated[status_mask].copy()

    if updated.empty:
        return updated.reset_index(drop=True)

    updated["_effect_summary"] = updated["_effect_summary"].apply(
        lambda value: value if str(value or "").strip() else "challenge-required unmodelled utility row"
    )

    return updated.reset_index(drop=True)


def apply_forced_attachment_rules_to_pool(
    *,
    modelled_pool: pd.DataFrame,
    full_compatible_attachments: pd.DataFrame,
    forced_attachment_rules=None,
) -> tuple[pd.DataFrame, set[str], list[str], list[str]]:
    """
    Apply challenge locks as hard constraints.

    For each required slot, matching rows are the only rows allowed in that
    slot. Other slots remain optimisable.
    """
    rules = [
        rule
        for rule in (forced_attachment_rules or [])
        if isinstance(rule, dict)
    ]

    if not rules:
        return modelled_pool.copy(), set(), [], []

    challenge_pool = prepare_challenge_attachment_pool(full_compatible_attachments)
    combined_pool = modelled_pool.copy()
    required_slots: set[str] = set()
    labels: list[str] = []
    missing_labels: list[str] = []
    allowed_keys_by_slot: dict[str, set[str]] = {}

    for rule in rules:
        label = forced_rule_label(rule)
        labels.append(label)

        matches = challenge_pool[
            challenge_pool.apply(
                lambda attachment: attachment_matches_forced_rule(attachment, rule),
                axis=1,
            )
        ].copy()

        if matches.empty:
            missing_labels.append(label)
            continue

        combined_pool = pd.concat([combined_pool, matches], ignore_index=True)

        for slot, group in matches.groupby("slot"):
            clean_slot = normalise_slot_value(slot)

            if not clean_slot:
                continue

            required_slots.add(clean_slot)
            keys = {
                attachment_row_key(row)
                for _, row in group.iterrows()
            }

            if clean_slot in allowed_keys_by_slot:
                allowed_keys_by_slot[clean_slot] = allowed_keys_by_slot[clean_slot].intersection(keys)
            else:
                allowed_keys_by_slot[clean_slot] = keys

    if missing_labels:
        return combined_pool.iloc[0:0].copy(), required_slots, labels, missing_labels

    if combined_pool.empty:
        return combined_pool, required_slots, labels, missing_labels

    combined_pool["_challenge_row_key"] = combined_pool.apply(
        attachment_row_key,
        axis=1,
    )

    keep_mask = []

    for _, row in combined_pool.iterrows():
        clean_slot = normalise_slot_value(row.get("slot", ""))

        if clean_slot in allowed_keys_by_slot:
            keep_mask.append(row.get("_challenge_row_key", "") in allowed_keys_by_slot[clean_slot])
        else:
            keep_mask.append(True)

    combined_pool = combined_pool[keep_mask].drop_duplicates(
        subset=["stats_profile", "attachment_id"],
        keep="last",
    )
    combined_pool = combined_pool.drop(columns=["_challenge_row_key"], errors="ignore")

    empty_slots = [
        slot
        for slot in required_slots
        if slot not in set(combined_pool["slot"].dropna().astype(str).str.strip())
    ]

    if empty_slots:
        missing_labels.extend(empty_slots)
        return combined_pool.iloc[0:0].copy(), required_slots, labels, missing_labels

    return combined_pool.reset_index(drop=True), required_slots, labels, missing_labels


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
    forced_attachment_rules=None,
) -> pd.DataFrame:
    """
    Estimate the build search space using the same slot rules and pool pruning
    as the optimiser. It does not score builds and does not generate combos.
    """
    if guns.empty or attachments.empty:
        return pd.DataFrame()

    filtered_guns = guns.copy()

    if weapon_class != "Any":
        requested_weapon_class = normalise_weapon_class_value(weapon_class)
        filtered_guns = filtered_guns[
            filtered_guns["weapon_class"].apply(normalise_weapon_class_value) == requested_weapon_class
        ]

    rows = []
    use_fast_mode = normalise_match_value(optimiser_mode) != "deep"

    for _, gun in filtered_guns.iterrows():
        full_compatible_attachments = get_compatible_attachments(
            gun=gun,
            attachments=attachments,
        )

        full_compatible_count = len(full_compatible_attachments)
        compatible_attachments = prepare_oracle_attachment_pool(full_compatible_attachments)
        modelled_compatible_count = len(compatible_attachments)
        ignored_count = max(0, full_compatible_count - modelled_compatible_count)

        compatible_attachments, required_slots, challenge_labels, missing_challenges = apply_forced_attachment_rules_to_pool(
            modelled_pool=compatible_attachments,
            full_compatible_attachments=full_compatible_attachments,
            forced_attachment_rules=forced_attachment_rules,
        )

        if compatible_attachments.empty or missing_challenges:
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
                    "challenge_requirements": " | ".join(challenge_labels),
                    "challenge_missing": " | ".join(missing_challenges),
                    "buildable": False,
                }
            )
            continue

        if len(required_slots) > attachment_count:
            rows.append(
                {
                    "gun_name": gun.get("gun_name", ""),
                    "weapon_class": gun.get("weapon_class", ""),
                    "attachment_count": attachment_count,
                    "optimiser_mode": "Fast" if use_fast_mode else "Deep",
                    "full_compatible_rows": full_compatible_count,
                    "modelled_rows": modelled_compatible_count,
                    "ignored_rows": ignored_count,
                    "usable_slots": int(compatible_attachments["slot"].dropna().nunique()),
                    "pool_rows_after_pruning": len(compatible_attachments),
                    "estimated_combinations": 0,
                    "slot_pool_summary": "",
                    "challenge_requirements": " | ".join(challenge_labels),
                    "challenge_missing": "Too many required slots for attachment budget",
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
                hard_limit_per_slot=2 if int(attachment_count or 0) >= 8 else 3,
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
            required_slots=required_slots,
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
                "challenge_requirements": " | ".join(challenge_labels),
                "challenge_required_slots": " | ".join(sorted(required_slots)),
                "challenge_missing": "",
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
    if is_headshot_build_goal(build_goal):
        head_damage_score = (
            numeric_cell(attachment.get("head_damage_pct", 0), 0.0)
            + numeric_cell(attachment.get("head_damage_close_pct", 0), 0.0)
            + numeric_cell(attachment.get("head_damage_mid_pct", 0), 0.0)
            + numeric_cell(attachment.get("head_damage_long_pct", 0), 0.0)
            + numeric_cell(attachment.get("head_damage_close_add", 0), 0.0)
            + numeric_cell(attachment.get("head_damage_mid_add", 0), 0.0)
            + numeric_cell(attachment.get("head_damage_long_add", 0), 0.0)
            + numeric_cell(attachment.get("head_multiplier_pct", 0), 0.0)
        )
        score += head_damage_score * 4.5

        head_multiplier = numeric_cell(attachment.get("head_multiplier", 0), 0.0)
        if 0 < head_multiplier <= 5:
            score += (head_multiplier - 1.0) * 45.0

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
    score += -numeric_cell(attachment.get("visual_recoil_pct", 0), 0.0) * recoil_weight * 0.35
    score += -numeric_cell(attachment.get("aiming_idle_sway_pct", 0), 0.0) * recoil_weight * 0.20
    score += -numeric_cell(attachment.get("first_shot_recoil_pct", 0), 0.0) * 0.20
    score += -numeric_cell(attachment.get("kick_reset_speed_pct", 0), 0.0) * 0.10

    score += numeric_cell(attachment.get("movement_pct", 0), 0.0) * 0.35
    score += numeric_cell(attachment.get("sprint_pct", 0), 0.0) * 0.25
    score += numeric_cell(attachment.get("crouch_movement_pct", 0), 0.0) * 0.15
    score += numeric_cell(attachment.get("ads_movement_pct", 0), 0.0) * 0.35

    close_comfort_weight = 0.45
    if "close" in fight_type_text or "aggressive" in build_goal_text:
        close_comfort_weight = 0.85

    score += -numeric_cell(attachment.get("slide_to_fire_pct", 0), 0.0) * close_comfort_weight
    score += -numeric_cell(attachment.get("dive_to_fire_pct", 0), 0.0) * close_comfort_weight * 0.75
    score += -numeric_cell(attachment.get("hipfire_spread_pct", 0), 0.0) * close_comfort_weight * 0.35
    score += -numeric_cell(attachment.get("jump_hipfire_spread_pct", 0), 0.0) * close_comfort_weight * 0.25
    score += -numeric_cell(attachment.get("slide_hipfire_spread_pct", 0), 0.0) * close_comfort_weight * 0.25
    score += -numeric_cell(attachment.get("dive_hipfire_spread_pct", 0), 0.0) * close_comfort_weight * 0.25
    score += numeric_cell(attachment.get("mags_add", 0), 0.0) * 0.25

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

        clean_slot = normalise_slot_value(slot)

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

        if is_headshot_build_goal(build_goal):
            force(best_index_by_numeric(group, "head_damage_pct", prefer_high=True))
            force(best_index_by_numeric(group, "head_damage_close_pct", prefer_high=True))
            force(best_index_by_numeric(group, "head_damage_mid_pct", prefer_high=True))
            force(best_index_by_numeric(group, "head_damage_long_pct", prefer_high=True))
            force(best_index_by_numeric(group, "head_multiplier_pct", prefer_high=True))

        if clean_slot == "magazine":
            force(best_index_by_numeric(group, "mag_size_add", prefer_high=True))
            force(best_index_by_numeric(group, "reload_pct", prefer_high=False))

        elif clean_slot == "fire_mod":
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

        elif clean_slot == "rear_grip":
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

        base_limit = max(1, int(candidate_limit_per_slot or 1))

        if hard_limit_per_slot and int(hard_limit_per_slot) > 0:
            base_limit = min(base_limit, int(hard_limit_per_slot))

        # Headshot and challenge-preservation rules can nominate several rows
        # from one slot. In FAST PASS we still enforce the hard cap after
        # scoring those nominees, otherwise 8-attachment builds explode.
        if hard_limit_per_slot and int(hard_limit_per_slot) > 0 and len(forced_indices) > int(hard_limit_per_slot):
            forced_indices = (
                group.loc[forced_indices]
                .sort_values("_fast_candidate_score", ascending=False)
                .head(int(hard_limit_per_slot))
                .index
                .tolist()
            )

        target_limit = base_limit
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
    forced_attachment_rules=None,
):
    if guns.empty or attachments.empty:
        return pd.DataFrame()

    filtered_guns = guns.copy()

    if weapon_class != "Any":
        requested_weapon_class = normalise_weapon_class_value(weapon_class)
        filtered_guns = filtered_guns[
            filtered_guns["weapon_class"].apply(normalise_weapon_class_value) == requested_weapon_class
        ]

    rows = []
    use_fast_mode = normalise_match_value(optimiser_mode) != "deep"

    for _, gun in filtered_guns.iterrows():
        full_compatible_attachments = get_compatible_attachments(
            gun=gun,
            attachments=attachments,
        )

        full_compatible_count = len(full_compatible_attachments)
        compatible_attachments = prepare_oracle_attachment_pool(full_compatible_attachments)
        unmodelled_attachments_ignored = max(0, full_compatible_count - len(compatible_attachments))

        compatible_attachments, required_slots, challenge_labels, missing_challenges = apply_forced_attachment_rules_to_pool(
            modelled_pool=compatible_attachments,
            full_compatible_attachments=full_compatible_attachments,
            forced_attachment_rules=forced_attachment_rules,
        )

        if missing_challenges or len(required_slots) > attachment_count:
            continue

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
                hard_limit_per_slot=2 if int(attachment_count or 0) >= 8 else 3,
            )
        else:
            compatible_attachments = prune_dominated_attachments(compatible_attachments)

        for combo in generate_legal_attachment_combos(
            compatible_attachments=compatible_attachments,
            attachment_count=attachment_count,
            required_slots=required_slots,
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

            challenge_summary = " | ".join(challenge_labels)
            challenge_required_slots = " | ".join(sorted(required_slots))
            explanation = explain_weapon_build(
                gun=gun,
                selected_attachments=selected_attachments,
                full_compatible_attachments=full_compatible_attachments,
                preview=preview,
                map_type=map_type,
                fight_type=fight_type,
                build_goal=build_goal,
                enemy_health=enemy_health,
                challenge_requirements=challenge_summary,
                challenge_required_slots=challenge_required_slots,
            )

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
                    "challenge_requirements": challenge_summary,
                    "challenge_required_slots": challenge_required_slots,
                    "optimiser_mode": "Fast" if use_fast_mode else "Deep",
                    "slot_candidate_limit": int(candidate_limit_per_slot) if use_fast_mode else "",
                    **preview,
                    **explanation,
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
    "slide to fire": "slide_to_fire_pct",
    "slide to fire speed": "slide_to_fire_pct",
    "dive to fire": "dive_to_fire_pct",
    "dive to fire speed": "dive_to_fire_pct",
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
    "hipfire spread": "hipfire_spread_pct",
    "jump hipfire spread": "jump_hipfire_spread_pct",
    "slide hipfire spread": "slide_hipfire_spread_pct",
    "dive hipfire spread": "dive_hipfire_spread_pct",
    "mags": "mags_add",
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
    forced_attachment_rules=None,
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
        forced_attachment_rules=forced_attachment_rules,
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
    pairing = str(loadout_pairing or "").strip()

    primary_class = None

    if pairing.startswith("AR +"):
        primary_class = "assault_rifle"
    elif pairing.startswith("SMG +"):
        primary_class = "smg"
    elif pairing.startswith("Shotgun +"):
        primary_class = "shotgun"
    elif pairing.startswith("LMG +"):
        primary_class = "lmg"
    elif pairing.startswith("Sniper +"):
        primary_class = "sniper_rifle"
    elif pairing.startswith("Marksman +"):
        primary_class = "marksman_rifle"

    if loadout_pairing_uses_standard_secondary(pairing):
        return primary_class, "standard_secondary"

    if "SMG" in pairing:
        return primary_class, "smg"

    return primary_class, "standard_secondary"


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
    required_class = normalise_weapon_class_value(required_weapon_class)

    if required_class == "standard_secondary":
        return filtered[
            filtered["weapon_class"].apply(normalise_weapon_class_value).isin(STANDARD_SECONDARY_WEAPON_CLASSES)
        ]

    if required_class:
        return filtered[filtered["weapon_class"].apply(normalise_weapon_class_value) == required_class]

    if role == "primary":
        return filtered[
            filtered["weapon_class"].apply(normalise_weapon_class_value).isin(PRIMARY_WEAPON_CLASSES)
        ]

    return filtered[
        filtered["weapon_class"].apply(normalise_weapon_class_value).isin(STANDARD_SECONDARY_WEAPON_CLASSES)
    ]


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
    build_goal: str = "",
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
        build_goal=build_goal,
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
        if normalise_weapon_class_value(weapon_class) in {"sniper_rifle", "marksman_rifle"}:
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
    primary_forced_attachment_rules=None,
    secondary_forced_attachment_rules=None,
    tactical_goal: str = "Auto from build goal / challenge",
    tactical_map_size: str = "Auto",
    playlist_style: str = "Auto",
    wildcard_id: str = "Oracle recommends",
):
    primary_class, secondary_class = weapon_classes_for_pairing(loadout_pairing)

    shared_challenge_requirements = " | ".join(
        item
        for item in [
            forced_attachment_rules_summary(primary_forced_attachment_rules),
            forced_attachment_rules_summary(secondary_forced_attachment_rules),
        ]
        if str(item or "").strip()
    )

    selected_wildcard_id = effective_wildcard_id(
        wildcard_id,
        loadout_pairing=loadout_pairing,
        attachment_count=attachment_count,
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=shared_challenge_requirements,
        tactical_goal=tactical_goal,
        playlist_style=playlist_style,
    )
    legality_notes = loadout_legality_warnings(
        loadout_pairing=loadout_pairing,
        wildcard_id=selected_wildcard_id,
        attachment_count=attachment_count,
    )

    if legality_notes:
        return pd.DataFrame()

    primary_attachment_count = int(attachment_count or 5)
    # BO7 wildcard legality matters: Gunfighter raises Primary to 8, not Secondary.
    # When the caller is testing a smaller lab count, keep both sides at that count.
    secondary_attachment_count = min(primary_attachment_count, 5)

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

    primary_guns = limit_guns_by_base_ttk(
        guns=primary_guns,
        attachments=attachments,
        enemy_health=enemy_health,
        fight_type=role_scenarios["primary_fight_type"],
        attachment_count=primary_attachment_count,
        build_goal=role_scenarios["primary_build_goal"],
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
        attachment_count=primary_attachment_count,
        top_n=candidate_pool,
        optimiser_mode=optimiser_mode,
        candidate_limit_per_slot=candidate_limit_per_slot,
        forced_attachment_rules=primary_forced_attachment_rules,
    )

    standard_secondary_placeholder = False

    if secondary_class == "standard_secondary":
        secondary_results = optimise_standard_secondaries_for_scenario(
            guns=secondary_guns,
            attachments=attachments,
            enemy_health=enemy_health,
            fight_type=role_scenarios["secondary_fight_type"],
            build_goal=role_scenarios["secondary_build_goal"],
            challenge_requirements=shared_challenge_requirements,
            tactical_goal=tactical_goal,
            map_size=tactical_map_size,
            playlist_style=playlist_style,
            top_n=candidate_pool,
        )
        if not secondary_results.empty:
            standard_secondary_placeholder = (
                str(secondary_results.iloc[0].get("secondary_slot_source", "") or "").strip()
                == "advisory_placeholder"
            )
    else:
        secondary_guns = limit_guns_by_base_ttk(
            guns=secondary_guns,
            attachments=attachments,
            enemy_health=enemy_health,
            fight_type=role_scenarios["secondary_fight_type"],
            attachment_count=secondary_attachment_count,
            build_goal=role_scenarios["secondary_build_goal"],
            limit=5,
        )

        secondary_results = optimise_loadouts_for_scenario(
            guns=secondary_guns,
            attachments=attachments,
            map_type=map_type,
            fight_type=role_scenarios["secondary_fight_type"],
            build_goal=role_scenarios["secondary_build_goal"],
            enemy_health=enemy_health,
            weapon_class="Any",
            attachment_count=secondary_attachment_count,
            top_n=candidate_pool,
            optimiser_mode=optimiser_mode,
            candidate_limit_per_slot=candidate_limit_per_slot,
            forced_attachment_rules=secondary_forced_attachment_rules,
        )

    if primary_results.empty or secondary_results.empty:
        return pd.DataFrame()

    if standard_secondary_placeholder:
        primary_weight = 1.0
        secondary_weight = 0.0
    else:
        primary_weight, secondary_weight = role_weights_for_scenario(
            map_type=map_type,
            fight_type=fight_type,
        )

    selected_perk_package = str(perk_package or "").strip()
    if normalise_match_value(selected_perk_package) in {"oracle recommends", "oracle_recommends", "auto", "best"}:
        selected_perk_package = recommend_perk_package(
            build_goal=build_goal,
            fight_type=fight_type,
            challenge_requirements=shared_challenge_requirements,
            tactical_goal=tactical_goal,
            map_size=tactical_map_size,
            playlist_style=playlist_style,
        )

    if selected_perk_package not in PERK_PACKAGES:
        selected_perk_package = "Balanced" if "Balanced" in PERK_PACKAGES else next(iter(PERK_PACKAGES))

    secondary_advisory_note = ""
    if standard_secondary_placeholder:
        secondary_advisory_note = (
            "Standard BO7 secondary slot is legal here. The Oracle has no pistol, launcher, or special weapon "
            "stats in guns.csv yet, so only the primary weapon is brute-forced."
        )

    perk_advice = build_perk_loadout_advice(
        perk_package=selected_perk_package,
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=shared_challenge_requirements,
        tactical_goal=tactical_goal,
        map_size=tactical_map_size,
        playlist_style=playlist_style,
        loadout_pairing=loadout_pairing,
        wildcard_id=selected_wildcard_id,
        loadout_legality_notes=[secondary_advisory_note] if secondary_advisory_note else [],
    )
    perk_bonus = perk_package_score_bonus(selected_perk_package) + perk_advice.get("perk_fit_score", 0.0)

    rows = []

    for _, primary in primary_results.iterrows():
        for _, secondary in secondary_results.iterrows():
            if not standard_secondary_placeholder and primary["gun_name"] == secondary["gun_name"]:
                continue

            primary_role_score = float(primary["oracle_score"])
            secondary_role_score = float(secondary["oracle_score"])

            if standard_secondary_placeholder:
                role_balance = 0.0
                secondary_role_label = "STANDARD SECONDARY"
                role_verdict = secondary_advisory_note
            else:
                role_balance = loadout_role_balance_score(
                    primary_role_score,
                    secondary_role_score,
                )
                secondary_role_label = loadout_role_label(
                    "secondary",
                    secondary.get("weapon_class", ""),
                    role_scenarios["secondary_fight_type"],
                    role_scenarios["secondary_build_goal"],
                )
                role_verdict = loadout_role_verdict(
                    primary_weapon=primary["gun_name"],
                    primary_class=primary["weapon_class"],
                    primary_role_label=loadout_role_label(
                        "primary",
                        primary.get("weapon_class", ""),
                        role_scenarios["primary_fight_type"],
                        role_scenarios["primary_build_goal"],
                    ),
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

            primary_role_label = loadout_role_label(
                "primary",
                primary.get("weapon_class", ""),
                role_scenarios["primary_fight_type"],
                role_scenarios["primary_build_goal"],
            )

            full_loadout_score = (
                primary_role_score * primary_weight
                + secondary_role_score * secondary_weight
                + perk_bonus
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
                    "wildcard_id": selected_wildcard_id,
                    "wildcard_name": wildcard_name_from_id(selected_wildcard_id),
                    "perk_package": selected_perk_package,
                    "perk_role": perk_advice.get("perk_role", ""),
                    "perk_fit_score": perk_advice.get("perk_fit_score", 0.0),
                    "perk_score_bonus": perk_advice.get("perk_score_bonus", 0.0),
                    "perk_recommendation_summary": perk_advice.get("perk_recommendation_summary", ""),
                    "perk_reasons": perk_advice.get("perk_reasons", ""),
                    "perk_warnings": perk_advice.get("perk_warnings", ""),
                    "equipment_priorities": perk_advice.get("equipment_priorities", ""),
                    "playstyle_notes": perk_advice.get("playstyle_notes", ""),
                    "recommended_tactical": perk_advice.get("recommended_tactical", ""),
                    "recommended_lethal": perk_advice.get("recommended_lethal", ""),
                    "recommended_field_upgrade": perk_advice.get("recommended_field_upgrade", ""),
                    "loadout_legality_notes": perk_advice.get("loadout_legality_notes", ""),
                    "perk_lab_evidence_json": perk_advice.get("perk_lab_evidence_json", ""),
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
                    "secondary_slot_source": secondary.get("secondary_slot_source", ""),
                    "secondary_slot_recommendation": secondary.get("secondary_slot_recommendation", ""),
                    "secondary_field_role": secondary.get("secondary_field_role", ""),
                    "secondary_advisor_summary": secondary.get("secondary_advisor_summary", ""),
                    "secondary_advisor_warnings": secondary.get("secondary_advisor_warnings", ""),
                    "secondary_advisor_evidence_json": secondary.get("secondary_advisor_evidence_json", ""),

                    "primary_weight": primary_weight,
                    "secondary_weight": secondary_weight,
                    "primary_challenge_requirements": primary.get("challenge_requirements", ""),
                    "secondary_challenge_requirements": secondary.get("challenge_requirements", ""),
                    "primary_build_reason_summary": primary.get("build_reason_summary", ""),
                    "primary_score_weight_summary": primary.get("score_weight_summary", ""),
                    "primary_optic_status": primary.get("optic_status", ""),
                    "primary_selected_attachment_notes": primary.get("selected_attachment_notes", ""),
                    "primary_rejected_breakpoint_notes": primary.get("rejected_breakpoint_notes", ""),
                    "primary_lab_evidence_json": primary.get("lab_evidence_json", ""),
                    "secondary_build_reason_summary": secondary.get("build_reason_summary", ""),
                    "secondary_score_weight_summary": secondary.get("score_weight_summary", ""),
                    "secondary_optic_status": secondary.get("optic_status", ""),
                    "secondary_selected_attachment_notes": secondary.get("selected_attachment_notes", ""),
                    "secondary_rejected_breakpoint_notes": secondary.get("rejected_breakpoint_notes", ""),
                    "secondary_lab_evidence_json": secondary.get("lab_evidence_json", ""),
                    "challenge_requirements": " | ".join(
                        item
                        for item in [
                            primary.get("challenge_requirements", ""),
                            secondary.get("challenge_requirements", ""),
                        ]
                        if str(item or "").strip()
                    ),
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


def optimise_two_weapon_loadouts_for_scenario(
    guns,
    attachments,
    map_type,
    fight_type,
    build_goal,
    loadout_pairing,
    enemy_health=300,
    attachment_count=5,
    top_n=10,
    candidate_pool=15,
    optimiser_mode: str = "Fast",
    candidate_limit_per_slot: int = 3,
    primary_forced_attachment_rules=None,
    secondary_forced_attachment_rules=None,
    wildcard_id: str = "Overkill",
):
    """
    Brute-force a two-weapon Warzone pairing without perk scoring.

    This keeps the weapons-only lab separate from the full-loadout optimiser.
    It reuses the full-loadout pairing logic, then removes the constant perk
    bonus so the displayed score reflects only the primary and secondary builds.
    """
    selected_wildcard_id = effective_wildcard_id(
        wildcard_id,
        loadout_pairing=loadout_pairing,
        attachment_count=attachment_count,
        build_goal=build_goal,
        fight_type=fight_type,
    )

    if selected_wildcard_id != "overkill" or int(attachment_count or 0) > 5:
        return pd.DataFrame()

    score_offset = perk_package_score_bonus("Balanced")

    results = optimise_full_loadouts_for_scenario(
        guns=guns,
        attachments=attachments,
        map_type=map_type,
        fight_type=fight_type,
        build_goal=build_goal,
        loadout_pairing=loadout_pairing,
        perk_package="Balanced",
        enemy_health=enemy_health,
        attachment_count=attachment_count,
        top_n=top_n,
        candidate_pool=candidate_pool,
        optimiser_mode=optimiser_mode,
        candidate_limit_per_slot=candidate_limit_per_slot,
        primary_forced_attachment_rules=primary_forced_attachment_rules,
        secondary_forced_attachment_rules=secondary_forced_attachment_rules,
        wildcard_id=selected_wildcard_id,
    )

    if results.empty:
        return results

    results = results.copy()
    results["perk_package"] = "Weapons only"

    if "full_loadout_score" in results.columns:
        results["full_loadout_score"] = results["full_loadout_score"].astype(float) - score_offset

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
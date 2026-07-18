from math import ceil
import json
import re
import pandas as pd
from itertools import combinations, product

from modules.warzone.attachment_import import (
    CODMUNITY_STAT_MAP,
    apply_codmunity_stat_to_attachment_row,
    normalise_codmunity_stat_label,
    parse_codmunity_attachment_html,
)

from modules.warzone.oracle_data import (
    ATTACHMENTS_PATH,
    ATTACHMENT_NUMERIC_COLUMNS,
    DEFAULT_STATS_PROFILE,
    EXTENDED_ATTACHMENT_COLUMNS,
    GUNS_PATH,
    LEGACY_STATS_PROFILE,
    OPTIONAL_ATTACHMENT_COLUMNS,
    REQUIRED_ATTACHMENT_COLUMNS,
    REQUIRED_GUN_COLUMNS,
    SUPPORTED_STATS_PROFILES,
    TTK_DATA_DIR,
    ensure_attachment_columns,
    ensure_profile_column,
    filter_ttk_data_by_profile,
    load_attachments,
    load_guns,
    load_ttk_data,
    normalise_list_cell,
    normalise_match_key,
    normalise_match_value,
    normalise_numeric_columns,
    normalise_schema_value,
    normalise_slot_value,
    normalise_stats_profile,
    normalise_ttk_attachments_dataframe,
    normalise_ttk_guns_dataframe,
    normalise_weapon_class_key,
    normalise_weapon_class_value,
    numeric_cell,
    slugify,
    split_list_cell,
    strip_html,
)

from modules.warzone.loadout_lab import (
    PERK_PACKAGES,
    PERK_SELECTION_OPTIONS,
    WILDCARD_SELECTION_OPTIONS,
    build_equipment_overclock_advice,
    build_perk_loadout_advice,
    build_scorestreak_package_advice,
    effective_wildcard_id,
    forced_attachment_rules_summary,
    load_loadout_catalogue,
    loadout_legality_warnings,
    loadout_pairing_requires_overkill,
    loadout_pairing_uses_standard_secondary,
    perk_package_fit_score,
    perk_package_score_bonus,
    recommend_perk_package,
    recommend_standard_secondary_slot,
    standard_secondary_class_fit_score,
    wildcard_id_from_selection,
    wildcard_name_from_id,
)

from modules.warzone.field_planner import (
    OPTIC_PREFERENCE_OPTIONS,
    TACTICAL_GOAL_OPTIONS,
    TACTICAL_MAP_SIZE_OPTIONS,
    TACTICAL_PLAYLIST_STYLE_OPTIONS,
    build_tactical_advice,
)




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
    "dragon's breath",
    "dragon breath",
    "launcher kit",
    "conversion",
    "dual wield",
    "titan wield",
    "argus lever",
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


def is_one_shot_build_goal(build_goal: str = "") -> bool:
    text = normalise_match_value(build_goal)
    return "one shot" in text or "one-shot" in text or "one_shot" in text


def is_long_range_build_goal(build_goal: str = "") -> bool:
    text = normalise_match_value(build_goal).replace("_", " ")
    return (
        "long range" in text
        or "long-range" in text
        or "longshot" in text
        or "long shot" in text
    )


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
        "shotgun_ads_practical_ttk_ms": "",
        "shotgun_hipfire_practical_ttk_ms": "",
        "shotgun_slide_practical_ttk_ms": "",
        "shotgun_best_close_ttk_ms": "",
        "shotgun_best_close_route": "",
        "shotgun_route_note": "",
        "shotgun_truth_note": "",
    }


def shotgun_truth_metrics(stats: dict, enemy_health: int = 300, fight_type: str = "Close range") -> dict:
    """
    Conservative shotgun trust model.

    Shotgun data is not only raw TTK. BO7 shotguns are decided by whether the
    selected build can land the first close-range kill reliably through ADS,
    hipfire, or slide/dive entry. This still cannot model pellet distribution,
    so the route result is a field-testable estimate rather than a guarantee.
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

    # Range coverage above 1.0 is useful, but capped so it cannot mask bad handling.
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
        note = "SHOTGUN TRUTH V2: score compares ADS, hipfire, and slide/dive routes, then still needs field proof for pellet reliability."

    base_metrics = {
        "is_shotgun": True,
        "shotgun_one_shot_potential": "YES" if one_shot_potential else "NO",
        "shotgun_two_shot_consistency": "YES" if two_shot_consistency else "NO",
        "shotgun_range_coverage": round(range_coverage, 3),
        "shotgun_handling_index": round(handling_index, 3),
        "shotgun_mag_safety": round(mag_safety, 3),
        "shotgun_truth_score": round(_clamp(truth_score, 0.0, 1.0), 3),
        "shotgun_truth_note": note,
    }

    route_metrics = shotgun_route_metrics(
        {
            **stats,
            **base_metrics,
            "enemy_health": health,
            "fight_type": fight_type,
        }
    )

    return {
        **base_metrics,
        **route_metrics,
    }


def _shotgun_pct_adjustment_ms(value, *, scale: float, low: float, high: float) -> float:
    """
    Convert percentage-style close-range shotgun modifiers into a millisecond
    adjustment. Negative in-game values are usually better, so they reduce the
    estimated route time. Positive values add friction.
    """
    pct = numeric_cell(value, 0.0)
    return max(low, min(high, pct * scale))


def shotgun_route_metrics(stats: dict) -> dict:
    """
    Estimate the practical close-range kill route for shotguns.

    ADS route: raw TTK plus ADS commitment.
    Hipfire route: raw TTK plus sprint-to-fire and spread reliability.
    Slide/dive route: raw TTK plus entry handling and slide/dive spread.

    This does not pretend to know pellet distribution. It gives the optimiser a
    better close-range objective than "ADS plus a generic penalty".
    """
    raw_ttk = numeric_cell(stats.get("raw_ttk_ms", 0), 0.0)
    ads_ms = numeric_cell(stats.get("ads_ms", 0), 0.0)
    sprint_to_fire_ms = numeric_cell(stats.get("sprint_to_fire_ms", 0), 0.0)
    shots_to_kill = max(1.0, numeric_cell(stats.get("shots_to_kill", 1), 1.0))
    truth_score = _clamp(numeric_cell(stats.get("shotgun_truth_score", 0), 0.0), 0.0, 1.0)
    range_coverage = _clamp(numeric_cell(stats.get("shotgun_range_coverage", 0), 0.0), 0.0, 1.25)

    hipfire_spread_pct = (
        numeric_cell(stats.get("hipfire_spread_pct", 0), 0.0)
        + numeric_cell(stats.get("jump_hipfire_spread_pct", 0), 0.0) * 0.35
    )
    slide_spread_pct = (
        numeric_cell(stats.get("slide_hipfire_spread_pct", 0), 0.0)
        + numeric_cell(stats.get("dive_hipfire_spread_pct", 0), 0.0) * 0.60
    )
    slide_entry_pct = (
        numeric_cell(stats.get("slide_to_fire_pct", 0), 0.0)
        + numeric_cell(stats.get("dive_to_fire_pct", 0), 0.0) * 0.60
    )

    extra_shot_penalty = max(0.0, shots_to_kill - 2.0) * 120.0
    range_penalty = max(0.0, 1.0 - min(range_coverage, 1.0)) * 160.0
    reliability_penalty = max(0.0, 1.0 - truth_score) * 190.0

    hipfire_spread_adjustment = _shotgun_pct_adjustment_ms(
        hipfire_spread_pct,
        scale=1.15,
        low=-90.0,
        high=130.0,
    )
    slide_spread_adjustment = _shotgun_pct_adjustment_ms(
        slide_spread_pct,
        scale=1.05,
        low=-80.0,
        high=120.0,
    )
    slide_entry_adjustment = _shotgun_pct_adjustment_ms(
        slide_entry_pct,
        scale=1.25,
        low=-100.0,
        high=130.0,
    )

    ads_route = (
        raw_ttk
        + ads_ms * 0.30
        + sprint_to_fire_ms * 0.05
        + range_penalty * 0.65
        + reliability_penalty
        + extra_shot_penalty
    )

    hipfire_route = (
        raw_ttk
        + sprint_to_fire_ms * 0.24
        + hipfire_spread_adjustment
        + range_penalty * 0.85
        + reliability_penalty * 0.90
        + extra_shot_penalty
    )

    slide_route = (
        raw_ttk
        + sprint_to_fire_ms * 0.18
        + slide_entry_adjustment
        + slide_spread_adjustment
        + range_penalty * 0.70
        + reliability_penalty * 0.92
        + extra_shot_penalty
    )

    routes = {
        "ADS": ads_route,
        "Hipfire": hipfire_route,
        "Slide/dive": slide_route,
    }
    best_route = min(routes, key=routes.get)
    best_value = round(max(0.0, routes[best_route]), 2)

    note = (
        f"Best close shotgun route: {best_route}. "
        "ADS, hipfire, and slide/dive are compared using raw TTK, handling, "
        "spread modifiers, range coverage, and shotgun truth reliability."
    )

    return {
        "shotgun_ads_practical_ttk_ms": round(max(0.0, ads_route), 2),
        "shotgun_hipfire_practical_ttk_ms": round(max(0.0, hipfire_route), 2),
        "shotgun_slide_practical_ttk_ms": round(max(0.0, slide_route), 2),
        "shotgun_best_close_ttk_ms": best_value,
        "shotgun_best_close_route": best_route,
        "shotgun_route_note": note,
    }


def calculate_shotgun_practical_ttk_ms(stats: dict) -> float:
    fight_type = str(stats.get("fight_type", "") or "").strip().lower()
    build_goal = str(stats.get("build_goal", "") or "").strip().lower()

    # Close-range shotgun work should use the fastest reliable route, not a
    # fixed ADS-centred formula.
    if (
        "close" in fight_type
        or "point blank" in build_goal
        or "aggressive" in build_goal
        or "hipfire" in build_goal
    ):
        route_value = numeric_cell(stats.get("shotgun_best_close_ttk_ms", 0), 0.0)
        if route_value > 0:
            return round(route_value, 2)

        return round(shotgun_route_metrics(stats)["shotgun_best_close_ttk_ms"], 2)

    raw_ttk = numeric_cell(stats.get("raw_ttk_ms", 0), 0.0)
    ads_ms = numeric_cell(stats.get("ads_ms", 0), 0.0)
    sprint_to_fire_ms = numeric_cell(stats.get("sprint_to_fire_ms", 0), 0.0)
    shots_to_kill = numeric_cell(stats.get("shots_to_kill", 1), 1.0)
    truth_score = _clamp(numeric_cell(stats.get("shotgun_truth_score", 0), 0.0), 0.0, 1.0)
    range_coverage = numeric_cell(stats.get("shotgun_range_coverage", 0), 0.0)

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
        updated_weights["shotgun_truth_score"] = updated_weights.get("shotgun_truth_score", 0.0) + 0.16
        updated_weights["shotgun_best_close_ttk_ms"] = updated_weights.get("shotgun_best_close_ttk_ms", 0.0) + 0.18
        updated_weights["practical_ttk_ms"] = updated_weights.get("practical_ttk_ms", 0.0) + 0.06

        total = sum(updated_weights.values())
        if total > 0:
            updated_weights = {
                metric: weight / total
                for metric, weight in updated_weights.items()
            }

        return scored, updated_weights

    return scored, weights



def apply_one_shot_viability_gate(
    results: pd.DataFrame,
    *,
    build_goal: str,
    enemy_health: int,
) -> pd.DataFrame:
    """
    For one-shot challenges, never let handling-only builds outrank a legal
    build that actually reaches the one-shot damage threshold.

    Up-to-budget optimisation is still valid, but a One-shot consistency route
    must first answer the core challenge question: can this build kill in one
    shot at the selected fight profile?
    """
    if results.empty or not is_one_shot_build_goal(build_goal):
        return results

    gated = results.copy()
    health = max(1.0, float(enemy_health or 1))

    damage = pd.to_numeric(gated.get("damage", pd.Series([0.0] * len(gated))), errors="coerce").fillna(0.0)
    shots = pd.to_numeric(gated.get("shots_to_kill", pd.Series([99.0] * len(gated))), errors="coerce").fillna(99.0)

    if "one_shot_margin" in gated.columns:
        margin = pd.to_numeric(gated["one_shot_margin"], errors="coerce").fillna(damage - health)
    else:
        margin = damage - health
        gated["one_shot_margin"] = margin

    one_shot_mask = (shots <= 1) | (margin >= 0)

    if one_shot_mask.any():
        gated = gated[one_shot_mask].copy()
        gated["one_shot_gate_status"] = "PASSED"
        gated["one_shot_gate_note"] = (
            "One-shot gate active: lower-damage builds were removed because at least "
            "one legal build reaches the one-shot threshold for this health profile."
        )
        return gated.reset_index(drop=True)

    gated["one_shot_gate_status"] = "FAILED"
    gated["one_shot_gate_note"] = (
        "One-shot gate active: no legal build reaches the one-shot threshold for this health profile, "
        "so the Oracle is showing the highest-margin fallback."
    )
    return gated.reset_index(drop=True)


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
    final_stats["fight_type"] = fight_type
    final_stats["build_goal"] = build_goal
    final_stats["enemy_health"] = int(enemy_health or 300)
    final_stats["range_m"] = effective_range_for_fight_type(final_stats, fight_type)

    final_stats["shots_to_kill"] = ceil(enemy_health / final_stats["damage"])
    final_stats["one_shot_margin"] = numeric_cell(final_stats.get("damage", 0), 0.0) - float(enemy_health or 0)
    final_stats["one_shot_ratio"] = (
        numeric_cell(final_stats.get("damage", 0), 0.0) / max(float(enemy_health or 1), 1.0)
    )

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


def exact_ttk_primary_stage_sort_key(preview: dict, build_goal: str, fight_type: str) -> tuple:
    """
    First stage for BEST TTK.

    This key chooses lethality only. Comfort support is added afterwards, so this
    must not include practical TTK, ADS, recoil or route handling. Otherwise a
    good support attachment changes the key and gets rejected as if it broke the
    raw-TTK breakpoint.
    """
    raw_ttk = numeric_cell(preview.get("raw_ttk_ms", 999999), 999999)
    damage = numeric_cell(preview.get("damage", 0), 0)
    shots_to_kill = numeric_cell(preview.get("shots_to_kill", 99), 99)
    one_shot_margin = numeric_cell(preview.get("one_shot_margin", -999999), -999999)

    if is_one_shot_build_goal(build_goal):
        return (
            shots_to_kill,
            -one_shot_margin,
            raw_ttk,
        )

    return (
        raw_ttk,
        shots_to_kill,
        -damage,
    )


def _attachment_id_set(combo) -> set[str]:
    return {
        normalise_match_key(attachment.get("attachment_id", ""))
        for attachment in combo
        if normalise_match_key(attachment.get("attachment_id", ""))
    }


def _attachment_slot_set(combo) -> set[str]:
    return {
        normalise_slot_value(attachment.get("slot", ""))
        for attachment in combo
        if normalise_slot_value(attachment.get("slot", ""))
    }


def _filter_attachments_for_remaining_slots(
    attachments: pd.DataFrame,
    *,
    used_slots: set[str],
    used_ids: set[str],
) -> pd.DataFrame:
    if attachments.empty:
        return attachments.copy()

    filtered = attachments.copy()
    filtered["_slot_key"] = filtered["slot"].apply(normalise_slot_value)
    filtered["_attachment_key"] = filtered["attachment_id"].apply(normalise_match_key)

    filtered = filtered[
        ~filtered["_slot_key"].isin(used_slots)
        & ~filtered["_attachment_key"].isin(used_ids)
    ].copy()

    return filtered.drop(columns=["_slot_key", "_attachment_key"], errors="ignore").reset_index(drop=True)


def _top_exact_candidates(candidates: list[tuple], limit: int) -> list[tuple]:
    if not candidates:
        return []

    return sorted(candidates, key=lambda item: item[0])[:max(1, int(limit or 1))]


def _exact_support_state_dominates(candidate_key: tuple, other_key: tuple) -> bool:
    """
    Pareto dominance for exact support states.

    A state can only dominate another when every exact sort metric is at least
    as good and at least one metric is better. This keeps real trade-offs alive
    while removing builds that cannot win later.
    """
    max_len = max(len(candidate_key), len(other_key))

    candidate_values = list(candidate_key) + [0.0] * (max_len - len(candidate_key))
    other_values = list(other_key) + [0.0] * (max_len - len(other_key))

    at_least_as_good = True
    strictly_better = False

    for candidate_value, other_value in zip(candidate_values, other_values):
        candidate_number = numeric_cell(candidate_value, 0.0)
        other_number = numeric_cell(other_value, 0.0)

        if candidate_number > other_number:
            at_least_as_good = False
            break

        if candidate_number < other_number:
            strictly_better = True

    return at_least_as_good and strictly_better


def _dedupe_exact_support_states(states: list[tuple]) -> list[tuple]:
    deduped: dict[tuple, tuple] = {}

    for key, combo, preview in states:
        identity = tuple(sorted(attachment_row_key(attachment) for attachment in combo))
        existing = deduped.get(identity)

        if existing is None or key < existing[0]:
            deduped[identity] = (key, combo, preview)

    return list(deduped.values())


def _pareto_prune_exact_support_states(
    states: list[tuple],
    *,
    state_limit: int = 768,
) -> tuple[list[tuple], int, bool]:
    """
    Keep the exact support frontier instead of brute-forcing every comfort combo.

    The frontier keeps all non-dominated trade-offs. A large safety cap prevents
    pathological data from hanging Streamlit; normal weapon pools should not hit
    it after slot-by-slot Pareto pruning.
    """
    if not states:
        return [], 0, False

    candidates = sorted(_dedupe_exact_support_states(states), key=lambda item: item[0])
    kept: list[tuple] = []
    pruned_count = 0

    for state in candidates:
        key = state[0]

        if any(_exact_support_state_dominates(existing[0], key) for existing in kept):
            pruned_count += 1
            continue

        kept = [
            existing
            for existing in kept
            if not _exact_support_state_dominates(key, existing[0])
        ]
        kept.append(state)

    kept = sorted(kept, key=lambda item: item[0])
    capped = False

    if state_limit and len(kept) > int(state_limit):
        kept = kept[:int(state_limit)]
        capped = True

    return kept, pruned_count, capped


def _exact_support_slot_groups(
    attachments: pd.DataFrame,
    *,
    used_slots: set[str],
    used_ids: set[str],
) -> list[tuple[str, list]]:
    remaining = _filter_attachments_for_remaining_slots(
        attachments,
        used_slots=used_slots,
        used_ids=used_ids,
    )

    if remaining.empty:
        return []

    slot_groups: list[tuple[str, list]] = []

    for slot, group in remaining.groupby("slot", sort=True):
        clean_slot = normalise_slot_value(slot)

        if not clean_slot or clean_slot in used_slots:
            continue

        rows = [row for _, row in group.iterrows()]
        if rows:
            slot_groups.append((clean_slot, rows))

    return slot_groups


def _select_exact_pareto_support_states(
    *,
    gun,
    core_combo: tuple,
    core_preview: dict,
    comfort_pool: pd.DataFrame,
    best_primary_key: tuple,
    build_goal: str,
    fight_type: str,
    enemy_health: int,
    max_count: int,
    minimum: int,
    support_front_limit: int = 768,
) -> tuple[list[tuple], int, int, bool]:
    """
    Fill support slots without generating the full product space.

    Each slot is evaluated, then the state list is Pareto-pruned. This still
    checks every attachment option as it enters the build, but it does not keep
    dominated partial builds that can no longer beat an existing state.
    """
    core_slots = _attachment_slot_set(core_combo)
    core_ids = _attachment_id_set(core_combo)

    slot_groups = _exact_support_slot_groups(
        comfort_pool,
        used_slots=core_slots,
        used_ids=core_ids,
    )

    initial_key = exact_ttk_sort_key(
        core_preview,
        build_goal=build_goal,
        fight_type=fight_type,
    )
    states: list[tuple] = [(initial_key, core_combo, core_preview)]
    scanned_support_states = 0
    pruned_support_states = 0
    front_was_capped = False

    for _, slot_attachments in slot_groups:
        next_states = list(states)

        for _, combo, _ in states:
            if len(combo) >= max_count:
                continue

            for attachment in slot_attachments:
                combined_combo = tuple([*combo, attachment])

                if len(combined_combo) > max_count:
                    continue

                if combo_has_attachment_conflicts(combined_combo):
                    continue

                scanned_support_states += 1

                preview = build_loadout_preview_from_combo(
                    gun=gun,
                    combo=combined_combo,
                    enemy_health=enemy_health,
                    fight_type=fight_type,
                    build_goal=build_goal,
                )

                # Support fill is only allowed around the winning raw breakpoint.
                # If a row somehow changes the primary key, keep the strict TTK
                # contract and drop it.
                if exact_ttk_primary_stage_sort_key(
                    preview,
                    build_goal=build_goal,
                    fight_type=fight_type,
                ) != best_primary_key:
                    continue

                sort_key = exact_ttk_sort_key(
                    preview,
                    build_goal=build_goal,
                    fight_type=fight_type,
                )
                next_states.append((sort_key, combined_combo, preview))

        before_prune = len(next_states)
        states, pruned_count, capped = _pareto_prune_exact_support_states(
            next_states,
            state_limit=support_front_limit,
        )
        pruned_support_states += pruned_count + max(0, before_prune - len(states) - pruned_count)
        front_was_capped = front_was_capped or capped

    final_states = [
        state
        for state in states
        if minimum <= len(state[1]) <= max_count
    ]

    if not final_states and minimum <= len(core_combo) <= max_count:
        final_states = states[:1]

    final_states = sorted(final_states, key=lambda item: item[0])
    return final_states, scanned_support_states, pruned_support_states, front_was_capped


def optimise_exact_ttk_two_stage_for_gun(
    *,
    gun,
    compatible_attachments: pd.DataFrame,
    full_compatible_attachments: pd.DataFrame,
    map_type: str,
    fight_type: str,
    build_goal: str,
    enemy_health: int,
    attachment_count: int,
    top_n: int,
    required_slots,
    min_attachment_count: int,
    attachment_count_mode: str,
    challenge_labels,
    unmodelled_attachments_ignored: int,
) -> list[dict]:
    """
    Exact BEST TTK without the million-build trap.

    Stage 1 checks every legal lethality-changing combo and finds the fastest raw
    breakpoint. Stage 2 keeps that breakpoint, then fills support slots with a
    Pareto frontier instead of brute-forcing every comfort product.
    """
    if compatible_attachments.empty:
        return []

    working = compatible_attachments.copy()
    working["_raw_ttk_effect_count"] = working.apply(
        lambda row: attachment_raw_ttk_effect_count(row, build_goal),
        axis=1,
    )

    core_pool = working[working["_raw_ttk_effect_count"] > 0].reset_index(drop=True)
    comfort_pool = working[working["_raw_ttk_effect_count"] <= 0].reset_index(drop=True)

    max_count = max(0, int(attachment_count or 0))
    minimum = max(0, int(min_attachment_count or 0))
    keep_limit = max(1, int(top_n or 10)) * 4
    core_keep_limit = max(16, int(top_n or 10) * 4)
    support_front_limit = 768

    core_candidates: list[tuple] = []
    scanned_core_count = 0

    if core_pool.empty:
        core_iterable = [tuple()]
    else:
        core_iterable = generate_legal_attachment_combos(
            compatible_attachments=core_pool,
            attachment_count=max_count,
            required_slots=required_slots,
            min_attachment_count=0,
            attachment_count_mode="up_to",
        )

    for core_combo in core_iterable:
        if len(core_combo) > max_count:
            continue

        if combo_has_attachment_conflicts(core_combo):
            continue

        scanned_core_count += 1

        preview = build_loadout_preview_from_combo(
            gun=gun,
            combo=core_combo,
            enemy_health=enemy_health,
            fight_type=fight_type,
            build_goal=build_goal,
        )
        primary_key = exact_ttk_primary_stage_sort_key(
            preview,
            build_goal=build_goal,
            fight_type=fight_type,
        )
        core_candidates.append((primary_key, core_combo, preview))

        if len(core_candidates) > core_keep_limit * 4:
            core_candidates = _top_exact_candidates(core_candidates, core_keep_limit)

    core_candidates = _top_exact_candidates(core_candidates, core_keep_limit)

    if not core_candidates:
        return []

    best_primary_key = core_candidates[0][0]
    best_core_candidates = [
        item
        for item in core_candidates
        if item[0] == best_primary_key
    ][:core_keep_limit]

    # Keep a small number of near-best cores only as an escape hatch for odd
    # data. They are not allowed to outrank the winning raw breakpoint because
    # Stage 2 filters against best_primary_key.
    if len(best_core_candidates) < min(core_keep_limit, len(core_candidates)):
        best_core_identities = {
            tuple(sorted(attachment_row_key(attachment) for attachment in item[1]))
            for item in best_core_candidates
        }

        for item in core_candidates:
            identity = tuple(sorted(attachment_row_key(attachment) for attachment in item[1]))
            if identity in best_core_identities:
                continue
            best_core_candidates.append(item)
            best_core_identities.add(identity)
            if len(best_core_candidates) >= min(core_keep_limit, max(int(top_n or 10) * 2, 12)):
                break

    best_candidates: list[tuple] = []
    scanned_support_count = 0
    pruned_support_count = 0
    support_front_capped = False

    for _, core_combo, core_preview in best_core_candidates:
        support_states, scanned_count, pruned_count, capped = _select_exact_pareto_support_states(
            gun=gun,
            core_combo=core_combo,
            core_preview=core_preview,
            comfort_pool=comfort_pool,
            best_primary_key=best_primary_key,
            build_goal=build_goal,
            fight_type=fight_type,
            enemy_health=enemy_health,
            max_count=max_count,
            minimum=minimum,
            support_front_limit=support_front_limit,
        )

        scanned_support_count += scanned_count
        pruned_support_count += pruned_count
        support_front_capped = support_front_capped or capped
        best_candidates.extend(support_states)

        if len(best_candidates) > keep_limit * 4:
            best_candidates = _top_exact_candidates(best_candidates, keep_limit)

    best_candidates = _top_exact_candidates(best_candidates, keep_limit)

    challenge_summary = " | ".join(challenge_labels)
    challenge_required_slots = " | ".join(sorted(required_slots))
    rows: list[dict] = []

    for rank, (sort_key, combo, preview) in enumerate(best_candidates, start=1):
        selected_attachments = pd.DataFrame(combo)
        selected_attachment_names = combo_attachment_names(combo)
        selected_attachment_slots = combo_attachment_slots(combo)
        selected_attachment_count = len(selected_attachment_slots)

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

        cap_note = (
            f" Support frontier safety cap {support_front_limit} was reached; validate with field testing."
            if support_front_capped
            else ""
        )

        rows.append(
            {
                "gun_name": gun["gun_name"],
                "weapon_class": gun["weapon_class"],
                "attachments": " | ".join(selected_attachment_names) if selected_attachment_names else "Base weapon only",
                "slots": " | ".join(selected_attachment_slots),
                "selected_attachment_count": selected_attachment_count,
                "attachment_budget": f"up to {attachment_count}" if attachment_count_mode == "up_to" else f"exactly {attachment_count}",
                "attachment_count_mode": attachment_count_mode,
                "min_attachment_count": min_attachment_count,
                "modelled_attachment_count": int(
                    selected_attachments.get("_modelled_effect_count", pd.Series(dtype=float)).fillna(0).astype(float).gt(0).sum()
                ) if "_modelled_effect_count" in selected_attachments.columns else len(selected_attachments),
                "unmodelled_attachments_ignored": unmodelled_attachments_ignored,
                "attachment_effects": combo_attachment_effects(combo),
                "attachment_trust_note": (
                    f"Exact BEST TTK checked {scanned_core_count:,} lethality combo(s), "
                    f"examined {scanned_support_count:,} support state(s), and Pareto-pruned "
                    f"{pruned_support_count:,} dominated state(s). It kept the fastest raw-TTK "
                    f"breakpoint, then chose the best legal support build around it."
                    f"{cap_note} Ignored {unmodelled_attachments_ignored} zero-effect or unmodelled conversion row(s)."
                ),
                "challenge_requirements": challenge_summary,
                "challenge_required_slots": challenge_required_slots,
                "optimiser_mode": "Exact TTK",
                "slot_candidate_limit": "",
                "exact_ttk_rank": rank,
                "exact_ttk_sort_key": str(sort_key),
                "exact_ttk_core_checked": scanned_core_count,
                "exact_ttk_support_states_checked": scanned_support_count,
                "exact_ttk_support_states_pruned": pruned_support_count,
                "exact_ttk_support_front_capped": support_front_capped,
                "oracle_score": round(1 / (1 + rank), 6),
                **exact_ttk_sort_columns_from_key(sort_key),
                **preview,
                **explanation,
            }
        )

    return rows




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
    "One-shot consistency",
    "Long-range consistency",
]


LOWER_IS_BETTER = {
    "raw_ttk_ms",
    "practical_ttk_ms",
    "ads_ms",
    "sprint_to_fire_ms",
    "recoil",
    "shots_to_kill",
    "shotgun_best_close_ttk_ms",
    "shotgun_ads_practical_ttk_ms",
    "shotgun_hipfire_practical_ttk_ms",
    "shotgun_slide_practical_ttk_ms",
}

HIGHER_IS_BETTER = {
    "damage",
    "one_shot_margin",
    "one_shot_ratio",
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
    "shotgun_ads_practical_ttk_ms",
    "shotgun_hipfire_practical_ttk_ms",
    "shotgun_slide_practical_ttk_ms",
    "shotgun_best_close_ttk_ms",
    "shotgun_best_close_route",
    "shotgun_route_note",
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
    goal_key = normalise_match_value(build_goal)

    if goal_key == "military camo headshots":
        weights = {
            "recoil": 0.42,
            "ads_ms": 0.16,
            "sprint_to_fire_ms": 0.10,
            "bullet_velocity": 0.12,
            "range_m": 0.10,
            "practical_ttk_ms": 0.07,
            "damage_per_mag": 0.03,
        }

    elif goal_key == "special camo ttk":
        weights = {
            "raw_ttk_ms": 0.55,
            "practical_ttk_ms": 0.25,
            "ads_ms": 0.08,
            "sprint_to_fire_ms": 0.06,
            "damage_per_mag": 0.06,
        }

    elif goal_key == "fastest ttk":
        weights = {
            "raw_ttk_ms": 0.70,
            "practical_ttk_ms": 0.20,
            "damage_per_mag": 0.10,
        }

    elif goal_key == "low recoil beam":
        weights = {
            "recoil": 0.40,
            "practical_ttk_ms": 0.20,
            "bullet_velocity": 0.20,
            "range_m": 0.15,
            "damage_per_mag": 0.05,
        }

    elif goal_key == "aggressive mobility":
        weights = {
            "practical_ttk_ms": 0.25,
            "ads_ms": 0.25,
            "sprint_to_fire_ms": 0.25,
            "recoil": 0.10,
            "damage_per_mag": 0.10,
            "range_m": 0.05,
        }

    elif is_one_shot_build_goal(build_goal):
        weights = {
            # One-shot challenges are about the damage breakpoint first.
            # Raw TTK alone is not enough because every true one-shot build has
            # 0 ms raw TTK. Damage margin keeps useful damage attachments alive.
            "shots_to_kill": 0.28,
            "one_shot_margin": 0.24,
            "damage": 0.14,
            "raw_ttk_ms": 0.10,
            "range_m": 0.10,
            "bullet_velocity": 0.08,
            "ads_ms": 0.04,
            "recoil": 0.02,
        }

    elif is_long_range_build_goal(build_goal):
        weights = {
            # Longshot challenges are about making the weapon stable and lethal
            # at the selected long-range damage profile, not just chasing raw TTK.
            "range_m": 0.26,
            "bullet_velocity": 0.22,
            "recoil": 0.18,
            "practical_ttk_ms": 0.12,
            "raw_ttk_ms": 0.08,
            "ads_ms": 0.06,
            "damage": 0.04,
            "damage_per_mag": 0.04,
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
        weights["shotgun_best_close_ttk_ms"] = weights.get("shotgun_best_close_ttk_ms", 0) + 0.08

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

    if is_one_shot_build_goal(build_goal):
        margin = numeric_cell(preview.get("one_shot_margin", 0), 0.0)
        margin_text = f"+{format_metric_value(margin)}" if margin > 0 else format_metric_value(margin)
        return (
            f"{build_goal} favours reaching the fewest shots-to-kill first, then damage margin above {enemy_health} HP, "
            f"range, velocity and handling. This build models {format_metric_value(damage)} damage, "
            f"{shots} shot(s), and a one-shot margin of {margin_text}."
        )

    if is_long_range_build_goal(build_goal):
        return (
            f"{build_goal} favours long-range damage, range coverage, bullet velocity, recoil stability and practical TTK. "
            f"At {enemy_health} HP this build models {format_metric_value(damage)} damage and needs {shots} shot(s) in the selected {fight_type.lower()} profile."
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



RAW_TTK_BODY_EFFECT_COLUMNS = [
    "damage_pct",
    "fire_rate_pct",
]

RAW_TTK_HEAD_EFFECT_COLUMNS = [
    "damage_pct",
    "fire_rate_pct",
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


def attachment_raw_ttk_effect_count(attachment, build_goal: str = "") -> int:
    """
    Count only effects that can change raw TTK for the current objective.

    This lets the BEST TTK route check every attachment row, then safely remove
    attachments that cannot alter the primary TTK calculation.
    """
    columns = RAW_TTK_HEAD_EFFECT_COLUMNS if (
        is_headshot_build_goal(build_goal) or is_one_shot_build_goal(build_goal)
    ) else RAW_TTK_BODY_EFFECT_COLUMNS

    return sum(
        1
        for column in columns
        if abs(numeric_cell(attachment.get(column, 0), 0.0)) > 0
    )


def exact_ttk_can_use_raw_ttk_only_pool(
    *,
    build_goal: str,
    challenge_labels=None,
    min_attachment_count: int = 0,
    required_slots=None,
) -> bool:
    """
    Strict BEST TTK path.

    For "No challenge / Best TTK", recoil, optics, magazines, handling and
    movement cannot improve raw TTK. They should not create millions of fake
    candidate builds or make the Oracle choose filler attachments.
    """
    if normalise_match_value(build_goal) != "fastest ttk":
        return False

    if challenge_labels:
        return False

    if required_slots:
        return False

    try:
        if int(min_attachment_count or 0) > 0:
            return False
    except (TypeError, ValueError):
        return False

    return True


def reduce_attachment_pool_for_strict_raw_ttk(
    compatible_attachments: pd.DataFrame,
    *,
    build_goal: str,
) -> pd.DataFrame:
    """
    Keep only attachments that can change raw TTK.

    This is not a speed heuristic. For the strict BEST TTK objective, attachments
    with no damage/fire-rate/head-damage effect cannot beat or improve a raw TTK
    result. They are still checked and deliberately excluded from the primary
    TTK search.
    """
    if compatible_attachments.empty:
        return compatible_attachments.copy()

    updated = compatible_attachments.copy()
    updated["_raw_ttk_effect_count"] = updated.apply(
        lambda row: attachment_raw_ttk_effect_count(row, build_goal),
        axis=1,
    )

    return updated[updated["_raw_ttk_effect_count"] > 0].reset_index(drop=True)


def _row_text_for_conflicts(attachment) -> str:
    return " ".join(
        str(attachment.get(column, "") or "")
        for column in [
            "attachment_id",
            "attachment_name",
            "attachment_type",
            "raw_stat_text",
            "verification_notes",
        ]
    ).lower().replace("_", " ")


def attachment_conflict_slots(attachment) -> set[str]:
    """
    Optional generic conflict support for attachments that block another slot.

    CSV columns supported:
    - conflicts_with_slots
    - conflict_slots
    - incompatible_slots

    Built-in known rule:
    - Parallel Foregrip cannot be combined with an optic.
    """
    conflict_values = []

    for column in [
        "conflicts_with_slots",
        "conflict_slots",
        "incompatible_slots",
    ]:
        conflict_values.extend(split_list_cell(attachment.get(column, "")))

    conflicts = {
        normalise_slot_value(value)
        for value in conflict_values
        if str(value or "").strip()
    }

    row_text = _row_text_for_conflicts(attachment)
    if "parallel foregrip" in row_text:
        conflicts.add("optic")

    own_slot = normalise_slot_value(attachment.get("slot", ""))
    conflicts.discard(own_slot)

    return {slot for slot in conflicts if slot}


def attachment_conflict_ids(attachment) -> set[str]:
    values = []
    for column in [
        "conflicts_with_attachment_ids",
        "conflict_attachment_ids",
        "incompatible_attachment_ids",
    ]:
        values.extend(split_list_cell(attachment.get(column, "")))

    return {
        normalise_match_key(value)
        for value in values
        if str(value or "").strip()
    }


def attachment_conflict_name_terms(attachment) -> set[str]:
    values = []
    for column in [
        "conflicts_with_attachment_names",
        "conflict_attachment_names",
        "incompatible_attachment_names",
    ]:
        values.extend(split_list_cell(attachment.get(column, "")))

    return {
        normalise_match_value(value)
        for value in values
        if str(value or "").strip()
    }


def combo_has_attachment_conflicts(combo) -> bool:
    selected_slots = {
        normalise_slot_value(attachment.get("slot", ""))
        for attachment in combo
        if normalise_slot_value(attachment.get("slot", ""))
    }
    selected_ids = {
        normalise_match_key(attachment.get("attachment_id", ""))
        for attachment in combo
        if normalise_match_key(attachment.get("attachment_id", ""))
    }
    selected_names = [
        normalise_match_value(attachment.get("attachment_name", ""))
        for attachment in combo
        if normalise_match_value(attachment.get("attachment_name", ""))
    ]

    for attachment in combo:
        slot_conflicts = attachment_conflict_slots(attachment)
        if slot_conflicts.intersection(selected_slots):
            return True

        id_conflicts = attachment_conflict_ids(attachment)
        own_id = normalise_match_key(attachment.get("attachment_id", ""))
        other_ids = selected_ids - {own_id}
        if id_conflicts.intersection(other_ids):
            return True

        name_terms = attachment_conflict_name_terms(attachment)
        own_name = normalise_match_value(attachment.get("attachment_name", ""))
        other_names = [name for name in selected_names if name != own_name]
        if name_terms and any(
            term and term in name
            for term in name_terms
            for name in other_names
        ):
            return True

    return False

def attachment_dominates(a, b) -> bool:
    """
    Returns True if attachment `a` is strictly at least as good as `b`
    on every stat, and strictly better on at least one.

    Only considers stats that actually affect scoring.
    A dominated attachment can never appear in the optimal build.

    Conflict safety: an attachment with extra slot/attachment conflicts cannot
    dominate a less restrictive attachment.
    """
    if attachment_conflict_slots(a) - attachment_conflict_slots(b):
        return False

    if attachment_conflict_ids(a) - attachment_conflict_ids(b):
        return False

    if attachment_conflict_name_terms(a) - attachment_conflict_name_terms(b):
        return False

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


def normalise_attachment_count_mode(value: str = "exact") -> str:
    text = normalise_schema_value(value)

    if text in {"up_to", "upto", "budget", "best_within_budget", "variable", "auto"}:
        return "up_to"

    return "exact"


def attachment_count_values(
    *,
    attachment_count: int,
    required_slots=None,
    min_attachment_count: int | None = None,
    attachment_count_mode: str = "exact",
    available_slot_count: int | None = None,
) -> list[int]:
    """
    Return legal attachment counts for the current budget model.

    ``exact`` preserves the old behaviour: a 5-build means exactly five slots.
    ``up_to`` treats attachment_count as a budget: the Oracle may use fewer slots
    when fewer attachments score better for the requested goal.
    """
    try:
        max_count = max(0, int(attachment_count or 0))
    except (TypeError, ValueError):
        max_count = 0

    try:
        minimum = max(0, int(min_attachment_count or 0))
    except (TypeError, ValueError):
        minimum = 0

    required_slot_names = _clean_required_slots(required_slots)
    required_count = len(required_slot_names)
    mode = normalise_attachment_count_mode(attachment_count_mode)

    if mode == "exact":
        minimum = max_count
    else:
        minimum = max(minimum, required_count)

    maximum = max_count
    if available_slot_count is not None:
        try:
            maximum = min(maximum, max(0, int(available_slot_count or 0)))
        except (TypeError, ValueError):
            maximum = max_count

    if required_count > maximum:
        return []

    if minimum > maximum:
        return []

    return list(range(minimum, maximum + 1))


def generate_legal_attachment_combos(
    compatible_attachments,
    attachment_count,
    required_slots=None,
    min_attachment_count: int | None = None,
    attachment_count_mode: str = "exact",
):
    """
    Legal build generator.

    Instead of trying every attachment combination and rejecting duplicate slots,
    this groups attachments by slot first, then only generates builds with one
    attachment per selected slot.

    Challenge locks can force required slots into every generated build while
    still allowing the Oracle to optimise the remaining slots normally.
    """

    if compatible_attachments.empty:
        legal_counts = attachment_count_values(
            attachment_count=attachment_count,
            required_slots=required_slots,
            min_attachment_count=min_attachment_count,
            attachment_count_mode=attachment_count_mode,
            available_slot_count=0,
        )
        if 0 in legal_counts:
            yield tuple()
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

    if any(slot not in slot_groups for slot in required_slot_names):
        return

    optional_slot_names = [
        slot
        for slot in slot_names
        if slot not in required_slot_names
    ]

    for count in attachment_count_values(
        attachment_count=attachment_count,
        required_slots=required_slot_names,
        min_attachment_count=min_attachment_count,
        attachment_count_mode=attachment_count_mode,
        available_slot_count=len(slot_names),
    ):
        optional_count = count - len(required_slot_names)

        if optional_count < 0:
            continue

        for optional_slots in combinations(optional_slot_names, optional_count):
            selected_slots = sorted([*required_slot_names, *optional_slots])
            grouped_options = [
                slot_groups[slot]
                for slot in selected_slots
            ]

            for combo in product(*grouped_options):
                if combo_has_attachment_conflicts(combo):
                    continue
                yield combo


def estimate_legal_attachment_combo_count(
    slot_counts: dict[str, int],
    attachment_count: int,
    required_slots=None,
    min_attachment_count: int | None = None,
    attachment_count_mode: str = "exact",
) -> int:
    """
    Count legal one-attachment-per-slot combinations without generating them.

    This powers the TTK page's workload warning so heavy scans are visible before
    a deep brute-force pass starts.
    """
    normalised_slot_counts = {}

    for slot, count in slot_counts.items():
        clean_slot = normalise_slot_value(slot)
        if clean_slot and int(count or 0) > 0:
            normalised_slot_counts[clean_slot] = normalised_slot_counts.get(clean_slot, 0) + int(count or 0)

    slot_names = sorted(normalised_slot_counts.keys())
    required_slot_names = _clean_required_slots(required_slots)

    if any(slot not in slot_names for slot in required_slot_names):
        return 0

    optional_slot_names = [
        slot
        for slot in slot_names
        if slot not in required_slot_names
    ]

    total = 0

    for count in attachment_count_values(
        attachment_count=attachment_count,
        required_slots=required_slot_names,
        min_attachment_count=min_attachment_count,
        attachment_count_mode=attachment_count_mode,
        available_slot_count=len(slot_names),
    ):
        optional_count = count - len(required_slot_names)

        if optional_count < 0:
            continue

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
    min_attachment_count: int | None = None,
    attachment_count_mode: str = "exact",
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
    optimiser_mode_key = normalise_match_value(optimiser_mode)
    use_exact_ttk_mode = optimiser_mode_key in {
        "exact ttk",
        "exact_ttk",
        "exact best ttk",
        "best ttk exact",
        "streaming exact ttk",
    }
    use_fast_mode = optimiser_mode_key != "deep" and not use_exact_ttk_mode
    attachment_count_mode = normalise_attachment_count_mode(attachment_count_mode)

    try:
        min_attachment_count = max(0, int(min_attachment_count or 0))
    except (TypeError, ValueError):
        min_attachment_count = 0

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

        if use_exact_ttk_mode and exact_ttk_can_use_raw_ttk_only_pool(
            build_goal=build_goal,
            challenge_labels=challenge_labels,
            min_attachment_count=min_attachment_count,
            required_slots=required_slots,
        ):
            # Workload estimate shows the small lethality stage. The actual
            # Exact TTK run then fills the best raw-TTK breakpoint with comfort
            # attachments, which is far cheaper than the old one-million-build
            # full Cartesian scan.
            compatible_attachments = reduce_attachment_pool_for_strict_raw_ttk(
                compatible_attachments,
                build_goal=build_goal,
            )

        if compatible_attachments.empty and not missing_challenges:
            legal_counts = attachment_count_values(
                attachment_count=attachment_count,
                required_slots=required_slots,
                min_attachment_count=min_attachment_count,
                attachment_count_mode=attachment_count_mode,
                available_slot_count=0,
            )
            if 0 in legal_counts:
                rows.append(
                    {
                        "gun_name": gun.get("gun_name", ""),
                        "weapon_class": gun.get("weapon_class", ""),
                        "attachment_count": attachment_count,
                        "attachment_count_mode": attachment_count_mode,
                        "min_attachment_count": min_attachment_count,
                        "optimiser_mode": "Exact TTK" if use_exact_ttk_mode else ("Fast" if use_fast_mode else "Deep"),
                        "full_compatible_rows": full_compatible_count,
                        "modelled_rows": modelled_compatible_count,
                        "ignored_rows": ignored_count,
                        "usable_slots": 0,
                        "pool_rows_after_pruning": 0,
                        "estimated_combinations": 1,
                        "slot_pool_summary": "base weapon only",
                        "challenge_requirements": " | ".join(challenge_labels),
                        "challenge_missing": "",
                        "buildable": True,
                    }
                )
                continue

        if compatible_attachments.empty or missing_challenges:
            rows.append(
                {
                    "gun_name": gun.get("gun_name", ""),
                    "weapon_class": gun.get("weapon_class", ""),
                    "attachment_count": attachment_count,
                    "optimiser_mode": "Exact TTK" if use_exact_ttk_mode else ("Fast" if use_fast_mode else "Deep"),
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

        pre_prune_slot_count = int(compatible_attachments["slot"].dropna().nunique())
        pre_prune_legal_counts = attachment_count_values(
            attachment_count=attachment_count,
            required_slots=required_slots,
            min_attachment_count=min_attachment_count,
            attachment_count_mode=attachment_count_mode,
            available_slot_count=pre_prune_slot_count,
        )

        if not pre_prune_legal_counts:
            rows.append(
                {
                    "gun_name": gun.get("gun_name", ""),
                    "weapon_class": gun.get("weapon_class", ""),
                    "attachment_count": attachment_count,
                    "attachment_count_mode": attachment_count_mode,
                    "min_attachment_count": min_attachment_count,
                    "optimiser_mode": "Exact TTK" if use_exact_ttk_mode else ("Fast" if use_fast_mode else "Deep"),
                    "full_compatible_rows": full_compatible_count,
                    "modelled_rows": modelled_compatible_count,
                    "ignored_rows": ignored_count,
                    "usable_slots": pre_prune_slot_count,
                    "pool_rows_after_pruning": len(compatible_attachments),
                    "estimated_combinations": 0,
                    "slot_pool_summary": "",
                    "challenge_requirements": " | ".join(challenge_labels),
                    "challenge_missing": "Required slots do not fit attachment budget",
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
            min_attachment_count=min_attachment_count,
            attachment_count_mode=attachment_count_mode,
        )

        rows.append(
            {
                "gun_name": gun.get("gun_name", ""),
                "weapon_class": gun.get("weapon_class", ""),
                "attachment_count": attachment_count,
                "attachment_count_mode": attachment_count_mode,
                "min_attachment_count": min_attachment_count,
                "optimiser_mode": "Exact TTK" if use_exact_ttk_mode else ("Fast" if use_fast_mode else "Deep"),
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

    one_shot_goal = "one shot" in build_goal_text or "one-shot" in build_goal_text or "one_shot" in build_goal_text
    long_range_goal = (
        "long range" in build_goal_text
        or "long-range" in build_goal_text
        or "longshot" in build_goal_text
        or "long shot" in build_goal_text
    )

    if "headshot" in build_goal_text or "military camo" in build_goal_text:
        recoil_weight += 1.8
        ads_weight += 0.3
        sprint_to_fire_weight += 0.2
        range_weight += 0.5
        bullet_velocity_weight += 0.4

    if one_shot_goal:
        range_weight += 1.0
        bullet_velocity_weight += 0.8
        ads_weight += 0.25
        recoil_weight += 0.35

    if long_range_goal:
        range_weight += 1.2
        bullet_velocity_weight += 1.0
        recoil_weight += 0.8
        ads_weight += 0.15

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

    damage_weight = 8.0 if one_shot_goal else 4.0
    score += numeric_cell(attachment.get("damage_pct", 0), 0.0) * damage_weight
    if is_headshot_build_goal(build_goal) or one_shot_goal:
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

        if is_headshot_build_goal(build_goal) or is_one_shot_build_goal(build_goal):
            force(best_index_by_numeric(group, "damage_pct", prefer_high=True))
            force(best_index_by_numeric(group, "head_damage_pct", prefer_high=True))
            force(best_index_by_numeric(group, "head_damage_close_pct", prefer_high=True))
            force(best_index_by_numeric(group, "head_damage_mid_pct", prefer_high=True))
            force(best_index_by_numeric(group, "head_damage_long_pct", prefer_high=True))
            force(best_index_by_numeric(group, "head_damage_close_add", prefer_high=True))
            force(best_index_by_numeric(group, "head_damage_mid_add", prefer_high=True))
            force(best_index_by_numeric(group, "head_damage_long_add", prefer_high=True))
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


def exact_ttk_sort_key(preview: dict, build_goal: str, fight_type: str) -> tuple:
    """
    Exhaustive BEST TTK objective.

    This is deliberately not the general Oracle score. The simplified BEST TTK
    button should answer the fastest-build question first, while still keeping
    challenge-specific tie breakers.
    """
    raw_ttk = numeric_cell(preview.get("raw_ttk_ms", 999999), 999999)
    practical_ttk = numeric_cell(preview.get("practical_ttk_ms", 999999), 999999)
    recoil = numeric_cell(preview.get("recoil", 999999), 999999)
    ads_ms = numeric_cell(preview.get("ads_ms", 999999), 999999)
    sprint_to_fire_ms = numeric_cell(preview.get("sprint_to_fire_ms", 999999), 999999)
    damage = numeric_cell(preview.get("damage", 0), 0)
    shots_to_kill = numeric_cell(preview.get("shots_to_kill", 99), 99)
    one_shot_margin = numeric_cell(preview.get("one_shot_margin", -999999), -999999)

    if is_one_shot_build_goal(build_goal):
        return (
            shots_to_kill,
            -one_shot_margin,
            practical_ttk,
            ads_ms,
            recoil,
        )

    if is_shotgun_weapon_class(preview.get("weapon_class", "")) and (
        str(fight_type or "").strip().lower() == "close range"
        or "point blank" in normalise_match_value(build_goal)
        or "hipfire" in normalise_match_value(build_goal)
        or "aggressive" in normalise_match_value(build_goal)
    ):
        shotgun_ttk = numeric_cell(
            preview.get("shotgun_best_close_ttk_ms", practical_ttk),
            practical_ttk,
        )
        return (
            shotgun_ttk,
            shots_to_kill,
            -damage,
            sprint_to_fire_ms,
            ads_ms,
        )

    if is_long_range_build_goal(build_goal):
        return (
            practical_ttk,
            recoil,
            -numeric_cell(preview.get("range_m", 0), 0),
            -numeric_cell(preview.get("bullet_velocity", 0), 0),
            raw_ttk,
        )

    if is_headshot_build_goal(build_goal):
        return (
            practical_ttk,
            recoil,
            raw_ttk,
            ads_ms,
        )

    return (
        raw_ttk,
        practical_ttk,
        shots_to_kill,
        ads_ms,
        recoil,
    )


def exact_ttk_sort_columns_from_key(sort_key: tuple) -> dict:
    padded = list(sort_key)[:8]
    while len(padded) < 8:
        padded.append(0.0)

    return {
        f"exact_ttk_sort_{index}": numeric_cell(value, 0.0)
        for index, value in enumerate(padded)
    }


def combo_attachment_names(combo) -> list[str]:
    return [
        str(attachment.get("attachment_name", "") or "").strip()
        for attachment in combo
        if str(attachment.get("attachment_name", "") or "").strip()
    ]


def combo_attachment_slots(combo) -> list[str]:
    return [
        str(attachment.get("slot", "") or "").strip()
        for attachment in combo
        if str(attachment.get("slot", "") or "").strip()
    ]


def combo_attachment_effects(combo) -> str:
    parts = []

    for attachment in combo:
        name = str(attachment.get("attachment_name", "") or "").strip()
        effect = str(attachment.get("_effect_summary", "") or "").strip()
        if name or effect:
            parts.append(f"{name}: {effect}".strip(": "))

    return " || ".join(parts)


def build_loadout_preview_from_combo(
    gun,
    combo,
    *,
    enemy_health: int,
    fight_type: str,
    build_goal: str,
) -> dict:
    """
    Same output as build_loadout_preview(), but avoids creating a pandas
    DataFrame for every candidate. This is the key speed-up for exhaustive
    single-weapon BEST TTK scans.
    """
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

    for attachment in combo:
        final_stats = apply_attachment_to_stats(final_stats, attachment)

    damage_column = damage_column_for_fight_type(fight_type, build_goal)

    if damage_column not in final_stats:
        damage_column = damage_column_for_fight_type(fight_type)

    final_stats["damage"] = final_stats[damage_column]
    final_stats["damage_model"] = "headshot" if is_headshot_build_goal(build_goal) else "body"
    final_stats["fight_type"] = fight_type
    final_stats["build_goal"] = build_goal
    final_stats["enemy_health"] = int(enemy_health or 300)
    final_stats["range_m"] = effective_range_for_fight_type(final_stats, fight_type)
    final_stats["shots_to_kill"] = ceil(enemy_health / final_stats["damage"])
    final_stats["one_shot_margin"] = numeric_cell(final_stats.get("damage", 0), 0.0) - float(enemy_health or 0)
    final_stats["one_shot_ratio"] = (
        numeric_cell(final_stats.get("damage", 0), 0.0) / max(float(enemy_health or 1), 1.0)
    )

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

    final_stats["damage_per_mag"] = (
        float(final_stats["damage"]) * float(final_stats["mag_size"])
    )
    final_stats["practical_ttk_ms"] = calculate_practical_ttk_ms(final_stats)

    return final_stats

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
    min_attachment_count: int | None = None,
    attachment_count_mode: str = "exact",
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
    optimiser_mode_key = normalise_match_value(optimiser_mode)
    use_exact_ttk_mode = optimiser_mode_key in {
        "exact ttk",
        "exact_ttk",
        "exact best ttk",
        "best ttk exact",
        "streaming exact ttk",
    }
    use_fast_mode = optimiser_mode_key != "deep" and not use_exact_ttk_mode
    attachment_count_mode = normalise_attachment_count_mode(attachment_count_mode)

    try:
        min_attachment_count = max(0, int(min_attachment_count or 0))
    except (TypeError, ValueError):
        min_attachment_count = 0

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

        unique_slot_count = compatible_attachments["slot"].dropna().nunique()
        legal_attachment_counts = attachment_count_values(
            attachment_count=attachment_count,
            required_slots=required_slots,
            min_attachment_count=min_attachment_count,
            attachment_count_mode=attachment_count_mode,
            available_slot_count=unique_slot_count,
        )

        if missing_challenges or not legal_attachment_counts:
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

        if use_exact_ttk_mode and exact_ttk_can_use_raw_ttk_only_pool(
            build_goal=build_goal,
            challenge_labels=challenge_labels,
            min_attachment_count=min_attachment_count,
            required_slots=required_slots,
        ):
            rows.extend(
                optimise_exact_ttk_two_stage_for_gun(
                    gun=gun,
                    compatible_attachments=compatible_attachments,
                    full_compatible_attachments=full_compatible_attachments,
                    map_type=map_type,
                    fight_type=fight_type,
                    build_goal=build_goal,
                    enemy_health=enemy_health,
                    attachment_count=attachment_count,
                    top_n=top_n,
                    required_slots=required_slots,
                    min_attachment_count=min_attachment_count,
                    attachment_count_mode=attachment_count_mode,
                    challenge_labels=challenge_labels,
                    unmodelled_attachments_ignored=unmodelled_attachments_ignored,
                )
            )
            continue

        if use_exact_ttk_mode:
            scanned_count = 0
            best_candidates: list[tuple[tuple, tuple, dict]] = []
            keep_limit = max(1, int(top_n or 10)) * 4

            for combo in generate_legal_attachment_combos(
                compatible_attachments=compatible_attachments,
                attachment_count=attachment_count,
                required_slots=required_slots,
                min_attachment_count=min_attachment_count,
                attachment_count_mode=attachment_count_mode,
            ):
                scanned_count += 1

                preview = build_loadout_preview_from_combo(
                    gun=gun,
                    combo=combo,
                    enemy_health=enemy_health,
                    fight_type=fight_type,
                    build_goal=build_goal,
                )

                sort_key = exact_ttk_sort_key(
                    preview,
                    build_goal=build_goal,
                    fight_type=fight_type,
                )

                best_candidates.append((sort_key, combo, preview))

                # Keep memory bounded while still scanning every legal build.
                if len(best_candidates) > keep_limit * 3:
                    best_candidates = sorted(
                        best_candidates,
                        key=lambda item: item[0],
                    )[:keep_limit]

            best_candidates = sorted(
                best_candidates,
                key=lambda item: item[0],
            )[:keep_limit]

            challenge_summary = " | ".join(challenge_labels)
            challenge_required_slots = " | ".join(sorted(required_slots))

            for rank, (sort_key, combo, preview) in enumerate(best_candidates, start=1):
                selected_attachments = pd.DataFrame(combo)
                selected_attachment_names = combo_attachment_names(combo)
                selected_attachment_slots = combo_attachment_slots(combo)
                selected_attachment_count = len(selected_attachment_slots)

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
                        "attachments": " | ".join(selected_attachment_names) if selected_attachment_names else "Base weapon only",
                        "slots": " | ".join(selected_attachment_slots),
                        "selected_attachment_count": selected_attachment_count,
                        "attachment_budget": f"up to {attachment_count}" if attachment_count_mode == "up_to" else f"exactly {attachment_count}",
                        "attachment_count_mode": attachment_count_mode,
                        "min_attachment_count": min_attachment_count,
                        "modelled_attachment_count": int(
                            selected_attachments.get("_modelled_effect_count", pd.Series(dtype=float)).fillna(0).astype(float).gt(0).sum()
                        ) if "_modelled_effect_count" in selected_attachments.columns else len(selected_attachments),
                        "unmodelled_attachments_ignored": unmodelled_attachments_ignored,
                        "attachment_effects": combo_attachment_effects(combo),
                        "attachment_trust_note": (
                            f"Exact BEST TTK checked {scanned_count:,} legal build(s). "
                            f"Ignored {unmodelled_attachments_ignored} zero-effect or unmodelled conversion row(s)."
                        ),
                        "challenge_requirements": challenge_summary,
                        "challenge_required_slots": challenge_required_slots,
                        "optimiser_mode": "Exact TTK",
                        "slot_candidate_limit": "",
                        "exact_ttk_rank": rank,
                        "exact_ttk_sort_key": str(sort_key),
                        "oracle_score": round(1 / (1 + rank), 6),
                        **exact_ttk_sort_columns_from_key(sort_key),
                        **preview,
                        **explanation,
                    }
                )

            continue

        for combo in generate_legal_attachment_combos(
            compatible_attachments=compatible_attachments,
            attachment_count=attachment_count,
            required_slots=required_slots,
            min_attachment_count=min_attachment_count,
            attachment_count_mode=attachment_count_mode,
        ):
            selected_attachments = pd.DataFrame(combo)
            selected_attachment_names = (
                selected_attachments["attachment_name"].tolist()
                if not selected_attachments.empty and "attachment_name" in selected_attachments.columns
                else []
            )
            selected_attachment_slots = (
                selected_attachments["slot"].tolist()
                if not selected_attachments.empty and "slot" in selected_attachments.columns
                else []
            )
            selected_attachment_count = len(selected_attachment_slots)

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
                    "attachments": " | ".join(selected_attachment_names) if selected_attachment_names else "Base weapon only",
                    "slots": " | ".join(selected_attachment_slots),
                    "selected_attachment_count": selected_attachment_count,
                    "attachment_budget": f"up to {attachment_count}" if attachment_count_mode == "up_to" else f"exactly {attachment_count}",
                    "attachment_count_mode": attachment_count_mode,
                    "min_attachment_count": min_attachment_count,
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
                    "optimiser_mode": "Exact TTK" if use_exact_ttk_mode else ("Fast" if use_fast_mode else "Deep"),
                    "slot_candidate_limit": int(candidate_limit_per_slot) if use_fast_mode else "",
                    **preview,
                    **explanation,
                }
            )

    if not rows:
        return pd.DataFrame()

    results = pd.DataFrame(rows)

    results = apply_one_shot_viability_gate(
        results,
        build_goal=build_goal,
        enemy_health=enemy_health,
    )

    if use_exact_ttk_mode:
        sort_columns = [
            column
            for column in [f"exact_ttk_sort_{index}" for index in range(8)]
            if column in results.columns
        ]

        if sort_columns:
            for column in sort_columns:
                results[column] = pd.to_numeric(results[column], errors="coerce").fillna(0.0)

            results = (
                results
                .sort_values(sort_columns, ascending=True)
                .head(top_n)
                .reset_index(drop=True)
            )
        else:
            results = results.head(top_n).reset_index(drop=True)

        results["exact_ttk_rank"] = range(1, len(results) + 1)
        results["oracle_score"] = [
            round(1 / (rank + 1), 6)
            for rank in range(1, len(results) + 1)
        ]

        return results

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
    min_attachment_count: int | None = None,
    attachment_count_mode: str = "exact",
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
    attachment_count_mode = normalise_attachment_count_mode(attachment_count_mode)

    try:
        minimum = max(0, int(min_attachment_count or 0))
    except (TypeError, ValueError):
        minimum = 0

    if attachment_count_mode == "exact":
        required_trusted_slots = int(attachment_count or 0)
    else:
        required_trusted_slots = minimum

    buildable = (
        trusted_slots >= required_trusted_slots
        if required_trusted_slots > 0
        else trusted_slots > 0
    )

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
            f"{', '.join(trusted_slots_list)}. Needs {required_trusted_slots} for this run. "
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
    min_attachment_count: int | None = None,
    attachment_count_mode: str = "up_to",
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
        min_attachment_count=min_attachment_count,
        attachment_count_mode=attachment_count_mode,
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
        min_attachment_count=min_attachment_count,
        attachment_count_mode=attachment_count_mode,
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
                    "recommended_tactical_overclock": perk_advice.get("recommended_tactical_overclock", ""),
                    "recommended_tactical_overclock_description": perk_advice.get("recommended_tactical_overclock_description", ""),
                    "recommended_lethal_overclock": perk_advice.get("recommended_lethal_overclock", ""),
                    "recommended_lethal_overclock_description": perk_advice.get("recommended_lethal_overclock_description", ""),
                    "recommended_field_upgrade_overclock": perk_advice.get("recommended_field_upgrade_overclock", ""),
                    "recommended_field_upgrade_overclock_description": perk_advice.get("recommended_field_upgrade_overclock_description", ""),
                    "equipment_overclock_summary": perk_advice.get("equipment_overclock_summary", ""),
                    "equipment_overclock_warnings": perk_advice.get("equipment_overclock_warnings", ""),
                    "equipment_overclock_lab_evidence_json": perk_advice.get("equipment_overclock_lab_evidence_json", ""),
                    "scorestreak_recommendation_summary": perk_advice.get("scorestreak_recommendation_summary", ""),
                    "recommended_scorestreaks": perk_advice.get("recommended_scorestreaks", ""),
                    "scorestreak_warnings": perk_advice.get("scorestreak_warnings", ""),
                    "scorestreak_lab_evidence_json": perk_advice.get("scorestreak_lab_evidence_json", ""),
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

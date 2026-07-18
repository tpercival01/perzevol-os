"""Loadout Lab.

Owns BO7 loadout legality, perk packages, equipment, overclocks, scorestreaks,
and standard-secondary recommendations. Weapon attachment optimisation remains
in ``ttk_oracle_engine`` during the compatibility migration.
"""

from pathlib import Path
import json
import re
from html import unescape

import pandas as pd


def numeric_cell(value, fallback: float = 0.0) -> float:
    if pd.isna(value):
        return fallback
    text = str(value).strip().replace("%", "").replace(",", "")
    if not text:
        return fallback
    try:
        number = float(text)
    except (TypeError, ValueError):
        return fallback
    if pd.isna(number) or number in {float("inf"), float("-inf")}:
        return fallback
    return number


def normalise_schema_value(value: str) -> str:
    text = unescape(str(value or "").strip()).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def normalise_match_value(value) -> str:
    return str(value or "").strip().lower()


def normalise_match_key(value) -> str:
    """Return a punctuation-insensitive key for catalogue and compatibility matching."""
    return re.sub(r"[^a-z0-9]+", "", normalise_match_value(value))


def slugify(value: str) -> str:
    """Return the shared lower-snake-case identifier format used by Oracle CSVs."""
    value = unescape(str(value or "").strip()).lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def normalise_tactical_text(value: str) -> str:
    """Return normalised tactical text for phrase matching."""
    return normalise_schema_value(value).replace("_", " ")


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


def normalise_weapon_class_value(value) -> str:
    key = re.sub(r"[^a-z0-9]+", "", normalise_match_value(value))
    return WEAPON_CLASS_ALIASES.get(key, normalise_schema_value(value))


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
        "tags": ["mobility", "fast_respawn", "sprint", "moving", "hipfire", "point_blank", "close_range", "melee", "pressure"],
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
        "tags": ["stealth", "no_damage", "flanking", "headshots", "melee", "point_blank", "thermal_counter"],
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
        "tags": ["longshots", "optic_4x", "one_shot", "headshots", "range", "stability", "stealth"],
        "strengths": [
            "Best fit for long lanes, magnified optics, and recoil-stability challenges.",
            "Uses Recon-style survival and visibility tools rather than pure entry speed.",
        ],
        "risks": [
            "Can feel too passive on tiny maps or close-range sprint challenges.",
        ],
    },
}


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
        "overclocks": load_csv_if_exists(OVERCLOCKS_PATH),
        "specialties": load_csv_if_exists(SPECIALTIES_PATH),
        "specialty_rules": load_csv_if_exists(SPECIALTY_RULES_PATH),
        "loadout_rules": load_csv_if_exists(LOADOUT_RULES_PATH),
        "loadout_slots": load_csv_if_exists(LOADOUT_SLOTS_PATH),
        "loadout_templates": load_csv_if_exists(LOADOUT_TEMPLATES_PATH),
        "scorestreaks": load_csv_if_exists(SCORESTREAKS_PATH),
        "scorestreak_overclocks": load_csv_if_exists(SCORESTREAK_OVERCLOCKS_PATH),
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

    if any(term in combined for term in ["melee", "point blank", "point-blank", "smoke", "stun"]):
        return "tac_expert"

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

    if "melee" in context or "knife" in context:
        scores["special"] += 0.28
        scores["pistol"] += 0.12
        scores["launcher"] -= 0.08

    if "point blank" in context or "point-blank" in context:
        scores["pistol"] += 0.22
        scores["special"] += 0.08
        scores["launcher"] -= 0.06

    if "close range kill" in context or "close-range kill" in context or "close kills" in context:
        scores["pistol"] += 0.16
        scores["special"] += 0.05

    if "one shot" in context or "one-shot" in context:
        scores["pistol"] += 0.08
        scores["launcher"] += 0.05

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

    if chosen_class == "special" and any(term in context for term in ["melee", "knife"]):
        warnings.append("Special secondary is selected for utility pressure. Melee progress still depends on route discipline and tactical entry tools.")

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


def _tactical_strings(*values) -> str:
    return " ".join(str(value or "").strip().lower() for value in values if str(value or "").strip())


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
        "point_blank": "point blank" in text or "point-blank" in text,
        "one_shot": "one shot" in text or "one-shot" in text or "one shot kill" in text or "one-shot kill" in text,
        "close_range": "close range kill" in text or "close-range kill" in text or "close kills" in text or "close quarter" in text,
        "melee": "melee" in text or "knife" in text or "combat axe" in text,
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
        if flags["hipfire"] or flags["moving"] or flags["sprint"] or flags["slide_dive"] or flags["point_blank"] or flags["close_range"] or flags["melee"]:
            score += 0.060
        if flags["point_blank"] or flags["melee"]:
            score += 0.030
        if flags["objective"] or flags["fast_respawn"]:
            score += 0.030
        if flags["headshots"]:
            score += 0.015
        if flags["no_damage"] or flags["longshots"] or flags["optic_4x"] or flags["one_shot"]:
            score -= 0.010

    elif package == "Balanced":
        score += 0.015
        if flags["headshots"] or flags["suppressor"] or flags["close_range"]:
            score += 0.035
        if flags["objective"] or flags["weapon_levelling"]:
            score += 0.025
        if flags["one_shot"]:
            score += 0.020
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
        if flags["melee"]:
            score += 0.055
        if flags["point_blank"]:
            score += 0.030
        if flags["headshots"]:
            score += 0.040
        if flags["suppressor"]:
            score += 0.030
        if flags["small_map"] and (flags["hipfire"] or flags["sprint"] or flags["slide_dive"]) and not flags["melee"]:
            score -= 0.010

    elif package == "Long-range":
        if flags["longshots"] or flags["optic_4x"] or flags["one_shot"] or str(fight_type).strip() == "Long range":
            score += 0.060
        if flags["one_shot"]:
            score += 0.030
        if flags["headshots"]:
            score += 0.035
        if flags["large_map"]:
            score += 0.025
        if flags["small_map"] and not flags["longshots"] and not flags["one_shot"]:
            score -= 0.015
        if flags["sprint"] or flags["slide_dive"] or flags["hipfire"] or flags["point_blank"] or flags["melee"]:
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


def loadout_item_text_blob(item) -> str:
    return _tactical_strings(
        item.get("raw_description", ""),
        item.get("effect_tags", ""),
        item.get("recommendation_tags", ""),
        item.get("mastery_action", ""),
        item.get("notes", ""),
    )


def _normalised_item_type(value: str) -> str:
    text = normalise_schema_value(value)
    if text in {"tactical_equipment", "tactical"}:
        return "tactical"
    if text in {"lethal_equipment", "lethal"}:
        return "lethal"
    if text in {"field_upgrade", "field_upgrades"}:
        return "field_upgrade"
    return text


def _normalised_item_id(value: str) -> str:
    return slugify(value)


def find_loadout_catalogue_item(
    catalogue: dict,
    *,
    item_type: str,
    item_name: str,
):
    item_type = _normalised_item_type(item_type)
    item_name = str(item_name or "").strip()

    if not item_name:
        return None

    if item_type in {"tactical", "lethal"}:
        data = catalogue.get("equipment", pd.DataFrame())
        id_column = "equipment_id"
        name_column = "equipment_name"
    elif item_type == "field_upgrade":
        data = catalogue.get("field_upgrades", pd.DataFrame())
        id_column = "field_upgrade_id"
        name_column = "field_upgrade_name"
    else:
        return None

    if data.empty or id_column not in data.columns or name_column not in data.columns:
        return None

    target_name = normalise_match_key(item_name)
    target_id = _normalised_item_id(item_name)

    matches = data[
        data[name_column].fillna("").astype(str).apply(normalise_match_key).eq(target_name)
        | data[id_column].fillna("").astype(str).apply(_normalised_item_id).eq(target_id)
    ]

    if matches.empty:
        return None

    return matches.iloc[0]


def loadout_item_overclock_fit_score(overclock, *, item=None, context: str = "") -> float:
    text = _tactical_strings(
        overclock.get("raw_description", ""),
        overclock.get("in_game_description", ""),
        overclock.get("effect_tags", ""),
        overclock.get("notes", ""),
    )
    item_text = loadout_item_text_blob(item if item is not None else {})
    context = str(context or "").lower()

    score = 0.0

    # Prefer the overclock the user visibly had active when the source data was captured,
    # but keep it small so the tactical context can still win.
    if normalise_match_value(overclock.get("active_at_capture", "")) == "true":
        score += 0.04

    status = normalise_schema_value(overclock.get("verification_status", ""))
    if status in {"verified", "verified_in_game_and_secondary", "in_game_verified"}:
        score += 0.04
    elif status in {"secondary_source", "needs_review", "needs_verification"}:
        score += 0.01

    # Headshot and no-damage grinds reward information, first-shot advantage, and control.
    if any(term in context for term in ["headshot", "military camo", "no damage", "longshot", "4.0x", "one shot", "one-shot"]):
        if any(term in text for term in [
            "detection_radius", "lifetime_increase", "duration_increase",
            "team_wall_visibility", "team_minimap", "enemy_reveal", "minimap",
            "target", "through_wall", "stealth", "charge_time_reduction",
            "faster_charge", "proximity_flash", "enemy_stun",
        ]):
            score += 0.18

    # Objective and launcher grinds reward area control, uptime, and clustered pressure.
    if any(term in context for term in ["objective", "hardpoint", "domination", "underbarrel", "launcher", "cluster"]):
        if any(term in text for term in [
            "area_of_effect", "radius", "mini_grenade", "effect_duration",
            "duration", "gas_damage", "stun", "equipment_resupply",
            "ammo_resupply", "projectile", "interception", "area_defence",
            "hologram", "objective_capture", "deployment",
        ]):
            score += 0.20

    # Movement and small-map challenges want fast deployment and repeatable entry tools.
    if any(term in context for term in ["small map", "fast respawn", "hipfire", "point blank", "point-blank", "close range", "melee", "knife", "sprint", "sliding", "diving", "wall-jumping", "moving"]):
        if any(term in text for term in [
            "raise_speed", "detonation_speed", "throw_distance", "throw_velocity",
            "cookable", "full_flash_angle", "look_away", "movement_slow",
            "faster_charge", "charge_time_reduction",
        ]):
            score += 0.14

    # Anti-scorestreak and utility contexts want electronics disruption and through-wall utility.
    if any(term in context for term in ["scorestreak", "destroy", "aerial", "vehicle", "equipment", "field upgrade", "launcher"]):
        if any(term in text for term in [
            "electronics", "hack", "through_wall", "disruption", "emp",
            "scorestreak", "equipment", "vehicle", "projectile",
        ]):
            score += 0.20

    # For pure lethal picks, lethality is usually safer than fancy behaviour.
    if any(term in item_text for term in ["explosive", "damage", "lethal", "anti_personnel", "objective_clear"]):
        if any(term in text for term in [
            "lethality_increase", "damage", "mini_grenade", "fire_damage",
            "rate_of_fire", "detonation_speed", "manual_flight_boost",
        ]):
            score += 0.12

    # Generic uptime is useful for most grinds.
    if any(term in text for term in ["duration", "charge_time_reduction", "radius", "area_of_effect"]):
        score += 0.04

    return round(score, 4)


def recommended_loadout_item_overclock(
    item_name: str,
    *,
    item_type: str,
    catalogue: dict,
    context: str,
) -> dict:
    overclocks = catalogue.get("overclocks", pd.DataFrame())
    if overclocks.empty or "parent_id" not in overclocks.columns or "parent_type" not in overclocks.columns:
        return {}

    item = find_loadout_catalogue_item(
        catalogue,
        item_type=item_type,
        item_name=item_name,
    )
    if item is None:
        return {}

    item_type = _normalised_item_type(item_type)

    if item_type in {"tactical", "lethal"}:
        parent_id = _normalised_item_id(item.get("equipment_id", ""))
        item_display_name = str(item.get("equipment_name", "") or "").strip()
    else:
        parent_id = _normalised_item_id(item.get("field_upgrade_id", ""))
        item_display_name = str(item.get("field_upgrade_name", "") or "").strip()

    matching = overclocks[
        overclocks["parent_type"].fillna("").astype(str).apply(_normalised_item_type).eq(item_type)
        & overclocks["parent_id"].fillna("").astype(str).apply(_normalised_item_id).eq(parent_id)
    ].copy()

    if matching.empty:
        return {}

    matching["_fit_score"] = matching.apply(
        lambda row: loadout_item_overclock_fit_score(row, item=item, context=context),
        axis=1,
    )
    best = matching.sort_values("_fit_score", ascending=False).iloc[0]

    return {
        "parent_type": item_type,
        "parent_id": parent_id,
        "item_name": item_display_name or item_name,
        "overclock_id": str(best.get("overclock_id", "") or "").strip(),
        "option_number": str(best.get("option_number", "") or "").strip(),
        "option_label": str(best.get("option_label", "") or "").strip(),
        "captured_in_game_name": str(best.get("captured_in_game_name", "") or "").strip(),
        "raw_description": str(best.get("raw_description", "") or "").strip(),
        "in_game_description": str(best.get("in_game_description", "") or "").strip(),
        "effect_tags": str(best.get("effect_tags", "") or "").strip(),
        "verification_status": str(best.get("verification_status", "") or "").strip(),
        "active_at_capture": str(best.get("active_at_capture", "") or "").strip(),
        "fit_score": numeric_cell(best.get("_fit_score", 0), 0.0),
    }


def overclock_display_name(overclock: dict) -> str:
    if not overclock:
        return ""

    captured_name = str(overclock.get("captured_in_game_name", "") or "").strip()
    option_label = str(overclock.get("option_label", "") or "").strip()
    option_number = str(overclock.get("option_number", "") or "").strip()

    if captured_name:
        return captured_name

    if option_label:
        return option_label

    if option_number:
        return f"Overclock {option_number}"

    return ""


def build_equipment_overclock_advice(
    *,
    recommended_tactical: str,
    recommended_lethal: str,
    recommended_field_upgrade: str,
    build_goal: str,
    fight_type: str,
    challenge_requirements: str = "",
    tactical_goal: str = "Auto from build goal / challenge",
    map_size: str = "Auto",
    playlist_style: str = "Auto",
    wildcard_id: str = "none",
) -> dict:
    catalogue = load_loadout_catalogue()
    context = _tactical_strings(
        build_goal,
        fight_type,
        challenge_requirements,
        tactical_goal,
        map_size,
        playlist_style,
        wildcard_id,
    )

    picks = {
        "tactical": recommended_loadout_item_overclock(
            recommended_tactical,
            item_type="tactical",
            catalogue=catalogue,
            context=context,
        ),
        "lethal": recommended_loadout_item_overclock(
            recommended_lethal,
            item_type="lethal",
            catalogue=catalogue,
            context=context,
        ),
        "field_upgrade": recommended_loadout_item_overclock(
            recommended_field_upgrade,
            item_type="field_upgrade",
            catalogue=catalogue,
            context=context,
        ),
    }

    warnings = []
    missing = [
        label.replace("_", " ")
        for label, pick in picks.items()
        if not pick
    ]

    if missing:
        warnings.append(
            "No overclock data found for: "
            + ", ".join(missing)
            + ". The base item recommendation still stands."
        )

    if wildcard_id_from_selection(wildcard_id) == "prepper":
        warnings.append("Prepper can equip two different Field Upgrades. This panel recommends the overclock for the primary Field Upgrade only.")

    lines = []
    for label, pick in picks.items():
        if not pick:
            continue
        display = overclock_display_name(pick)
        item_name = pick.get("item_name", "")
        description = pick.get("in_game_description") or pick.get("raw_description", "")
        if display:
            lines.append(f"{item_name}: {display} - {description}")
        else:
            lines.append(f"{item_name}: {description}")

    summary = "Equipment overclocks: " + " | ".join(lines) if lines else "Equipment overclock data unavailable for the current recommendations."

    evidence = {
        "advisor": "equipment_overclocks",
        "available": any(bool(pick) for pick in picks.values()),
        "build_goal": build_goal,
        "fight_type": fight_type,
        "challenge_requirements": challenge_requirements,
        "tactical_goal": tactical_goal,
        "map_size": map_size,
        "playlist_style": playlist_style,
        "wildcard_id": wildcard_id_from_selection(wildcard_id),
        "selected": picks,
        "warnings": warnings,
    }

    return {
        "equipment_overclock_summary": summary,
        "equipment_overclock_warnings": _perk_join(warnings),
        "recommended_tactical_overclock": overclock_display_name(picks["tactical"]),
        "recommended_tactical_overclock_description": picks["tactical"].get("in_game_description") or picks["tactical"].get("raw_description", "") if picks["tactical"] else "",
        "recommended_lethal_overclock": overclock_display_name(picks["lethal"]),
        "recommended_lethal_overclock_description": picks["lethal"].get("in_game_description") or picks["lethal"].get("raw_description", "") if picks["lethal"] else "",
        "recommended_field_upgrade_overclock": overclock_display_name(picks["field_upgrade"]),
        "recommended_field_upgrade_overclock_description": picks["field_upgrade"].get("in_game_description") or picks["field_upgrade"].get("raw_description", "") if picks["field_upgrade"] else "",
        "equipment_overclock_lab_evidence_json": json.dumps(evidence, indent=2),
    }


def scorestreak_cost_value(scorestreak) -> float:
    return numeric_cell(scorestreak.get("score_cost", 0), 0.0)


def scorestreak_text_blob(scorestreak) -> str:
    return _tactical_strings(
        scorestreak.get("scorestreak_name", ""),
        scorestreak.get("raw_description", ""),
        scorestreak.get("effect_tags", ""),
        scorestreak.get("recommendation_tags", ""),
        scorestreak.get("notes", ""),
    )


def scorestreak_fit_score(
    scorestreak,
    *,
    build_goal: str,
    fight_type: str,
    challenge_requirements: str = "",
    tactical_goal: str = "Auto from build goal / challenge",
    map_size: str = "Auto",
    playlist_style: str = "Auto",
    wildcard_id: str = "none",
) -> float:
    """Rank scorestreaks for a grind loadout.

    This is deliberately tactical, not TTK. Low-cost information streaks are
    often better for camo work than expensive highlight streaks because they
    create more repeatable gunfight attempts.
    """
    flags = _perk_text_flags(
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=tactical_goal,
        map_size=map_size,
        playlist_style=playlist_style,
    )
    context = _tactical_strings(build_goal, fight_type, challenge_requirements, tactical_goal, map_size, playlist_style)
    text = scorestreak_text_blob(scorestreak)
    cost = scorestreak_cost_value(scorestreak)

    # Cost is not everything, but for mastery grinding it matters a lot. A
    # streak you never earn is dead weight.
    score = 0.0
    if cost > 0:
        score += max(0.0, min(0.32, (1550.0 - cost) / 1550.0 * 0.32))

    if "low_cost" in text:
        score += 0.12
    if "scorestreak_grinding" in text:
        score += 0.14
    if "team_support" in text:
        score += 0.06

    if flags["headshots"]:
        if any(term in text for term in ["recon", "radar", "minimap", "enemy_location_reveal", "nearby_enemy_reveal", "advanced_recon"]):
            score += 0.22
        if "precision_elimination" in text:
            score += 0.04
        if "manual_control" in text and cost >= 800:
            score -= 0.04

    if flags["objective"] or flags["underbarrel_launcher"]:
        if any(term in text for term in ["objective_clear", "objective_defence", "area_control", "area_denial", "anti_personnel"]):
            score += 0.18
        if any(term in text for term in ["deployable", "automated", "passive_kills"]):
            score += 0.06

    if flags["longshots"] or flags["optic_4x"] or flags["one_shot"] or str(fight_type).strip() == "Long range":
        if any(term in text for term in ["recon", "advanced_recon", "precision_elimination", "target_reveal", "enemy_location_reveal"]):
            score += 0.16
        if "objective_clear" in text and cost >= 700:
            score -= 0.02

    if flags["no_damage"]:
        if any(term in text for term in ["recon", "radar", "minimap", "support", "counter_recon"]):
            score += 0.16
        if any(term in text for term in ["manual_control", "remote_controlled"]):
            score -= 0.04

    if flags["hipfire"] or flags["sprint"] or flags["moving"] or flags["slide_dive"] or flags["point_blank"] or flags["close_range"] or flags["melee"]:
        if any(term in text for term in ["low_cost", "small_maps", "anti_personnel", "objective_clear", "recon", "radar", "minimap"]):
            score += 0.13
        if cost >= 1000:
            score -= 0.06

    if any(term in context for term in ["scorestreak", "destroy", "destruction", "aerial", "vehicle", "launcher"]):
        if any(term in text for term in ["anti_scorestreak", "counter_equipment", "equipment_destruction", "vehicle_destruction", "air_superiority"]):
            score += 0.18
        if any(term in text for term in ["recon", "team_support", "score_gain"]):
            score += 0.08

    if "small map" in normalise_tactical_text(map_size):
        if "small_maps" in text:
            score += 0.11
        if cost >= 1000:
            score -= 0.08

    if "fast respawn" in normalise_tactical_text(playlist_style):
        if cost <= 600:
            score += 0.08
        if cost >= 1000:
            score -= 0.05

    if wildcard_id_from_selection(wildcard_id) == "high_roller":
        # High Roller allows a fourth slot. Slightly relax the low-cost bias so
        # one higher-impact streak can be included behind the cheap engine.
        if "high_tier" in text:
            score += 0.04
        if cost >= 1000:
            score += 0.03

    return round(score, 4)


def scorestreak_overclock_fit_score(overclock, *, scorestreak, context: str) -> float:
    text = _tactical_strings(
        overclock.get("raw_description", ""),
        overclock.get("effect_tags", ""),
        overclock.get("notes", ""),
    )
    scorestreak_text = scorestreak_text_blob(scorestreak)

    score = 0.0

    if "score_cost_reduction" in text or "lower score cost" in text:
        score += 0.35
        if any(term in context for term in ["headshot", "military camo", "mastery", "fast respawn", "small map"]):
            score += 0.10

    if any(term in context for term in ["scorestreak", "destroy", "launcher", "aerial", "vehicle"]):
        if any(term in text for term in ["anti_scorestreak", "lock_on", "vehicle", "equipment_destruction", "scorestreak"]):
            score += 0.25

    if any(term in context for term in ["headshot", "longshot", "one shot", "one-shot", "no damage", "objective", "melee", "point blank"]):
        if any(term in text for term in ["directional_enemy_indicators", "target_reveal", "enemy_ping", "radar", "minimap"]):
            score += 0.18

    if "anti_personnel" in scorestreak_text and any(term in text for term in ["additional", "cluster", "duration", "ammo", "explosive"]):
        score += 0.08

    return round(score, 4)


def recommended_scorestreak_overclock(scorestreak, overclocks: pd.DataFrame, *, context: str) -> dict:
    if overclocks.empty or "scorestreak_id" not in overclocks.columns:
        return {}

    scorestreak_id = str(scorestreak.get("scorestreak_id", "") or "").strip()
    matching = overclocks[
        overclocks["scorestreak_id"].fillna("").astype(str).str.strip().eq(scorestreak_id)
    ].copy()

    if matching.empty:
        return {}

    matching["_fit_score"] = matching.apply(
        lambda row: scorestreak_overclock_fit_score(row, scorestreak=scorestreak, context=context),
        axis=1,
    )
    best = matching.sort_values("_fit_score", ascending=False).iloc[0]

    return {
        "option_number": str(best.get("option_number", "") or "").strip(),
        "option_label": str(best.get("option_label", "") or "").strip(),
        "raw_description": str(best.get("raw_description", "") or "").strip(),
        "effect_tags": str(best.get("effect_tags", "") or "").strip(),
        "fit_score": numeric_cell(best.get("_fit_score", 0), 0.0),
    }


def build_scorestreak_package_advice(
    *,
    build_goal: str,
    fight_type: str,
    challenge_requirements: str = "",
    tactical_goal: str = "Auto from build goal / challenge",
    map_size: str = "Auto",
    playlist_style: str = "Auto",
    wildcard_id: str = "none",
    top_n: int | None = None,
) -> dict:
    catalogue = load_loadout_catalogue()
    scorestreaks = catalogue.get("scorestreaks", pd.DataFrame())
    overclocks = catalogue.get("scorestreak_overclocks", pd.DataFrame())

    slot_count = 4 if wildcard_id_from_selection(wildcard_id) == "high_roller" else 3
    if top_n:
        slot_count = int(top_n)

    if scorestreaks.empty:
        summary = "Scorestreak catalogue not found. Add data/bo7_loadouts/scorestreaks.csv to enable scorestreak recommendations."
        return {
            "scorestreak_recommendation_summary": summary,
            "recommended_scorestreaks": "",
            "scorestreak_warnings": "Scorestreak recommendations are unavailable until scorestreaks.csv exists.",
            "scorestreak_lab_evidence_json": json.dumps(
                {
                    "advisor": "scorestreak_package",
                    "available": False,
                    "expected_path": str(SCORESTREAKS_PATH),
                },
                indent=2,
            ),
        }

    ranked = scorestreaks.copy()
    ranked["_fit_score"] = ranked.apply(
        lambda row: scorestreak_fit_score(
            row,
            build_goal=build_goal,
            fight_type=fight_type,
            challenge_requirements=challenge_requirements,
            tactical_goal=tactical_goal,
            map_size=map_size,
            playlist_style=playlist_style,
            wildcard_id=wildcard_id,
        ),
        axis=1,
    )
    ranked["_score_cost"] = ranked.apply(scorestreak_cost_value, axis=1)
    ranked = ranked.sort_values(
        ["_fit_score", "_score_cost"],
        ascending=[False, True],
    ).reset_index(drop=True)

    selected = ranked.head(slot_count).copy()
    context = _tactical_strings(build_goal, fight_type, challenge_requirements, tactical_goal, map_size, playlist_style)

    picks = []
    for _, streak in selected.iterrows():
        overclock = recommended_scorestreak_overclock(streak, overclocks, context=context)
        picks.append(
            {
                "scorestreak_id": str(streak.get("scorestreak_id", "") or "").strip(),
                "scorestreak_name": str(streak.get("scorestreak_name", "") or "").strip(),
                "score_cost": scorestreak_cost_value(streak),
                "fit_score": numeric_cell(streak.get("_fit_score", 0), 0.0),
                "effect_tags": str(streak.get("effect_tags", "") or "").strip(),
                "recommendation_tags": str(streak.get("recommendation_tags", "") or "").strip(),
                "recommended_overclock": overclock,
            }
        )

    names = [item["scorestreak_name"] for item in picks if item.get("scorestreak_name")]
    warnings = []

    if wildcard_id_from_selection(wildcard_id) != "high_roller":
        warnings.append("High Roller is not active, so the advisor keeps this to 3 scorestreaks.")
    else:
        warnings.append("High Roller is active, so the advisor uses a fourth scorestreak slot.")

    if any(item.get("score_cost", 0) >= 1000 for item in picks):
        warnings.append("At least one high-cost streak is present. Field test whether you earn it often enough during the grind.")

    if any(term in context for term in ["launcher", "destroy", "scorestreak", "aerial", "vehicle"]):
        warnings.append("Launcher or destruction context detected: scorestreaks support the field plan, but enemy streak removal still belongs to launcher/equipment choices.")

    if not names:
        summary = "No scorestreak recommendation could be built from the current catalogue."
    else:
        summary = f"Scorestreak package: {', '.join(names)}."

    evidence = {
        "advisor": "scorestreak_package",
        "available": True,
        "slot_count": slot_count,
        "wildcard_id": wildcard_id_from_selection(wildcard_id),
        "build_goal": build_goal,
        "fight_type": fight_type,
        "challenge_requirements": challenge_requirements,
        "tactical_goal": tactical_goal,
        "map_size": map_size,
        "playlist_style": playlist_style,
        "selected_scorestreaks": picks,
        "top_ranked": ranked.head(8)[
            [
                "scorestreak_id",
                "scorestreak_name",
                "score_cost",
                "effect_tags",
                "recommendation_tags",
                "_fit_score",
            ]
        ].to_dict("records"),
    }

    return {
        "scorestreak_recommendation_summary": summary,
        "recommended_scorestreaks": " || ".join(names),
        "scorestreak_warnings": _perk_join(warnings),
        "scorestreak_lab_evidence_json": json.dumps(evidence, indent=2),
    }


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

    if flags["point_blank"]:
        reasons.append("Point blank kills need controlled entry tools and the confidence to force fights inside shotgun distance.")
        equipment_priorities.append("Prioritise stun, smoke, or speed tools that let you cross the last few metres safely.")
        playstyle_notes.append("Break lines of sight, enter through doors and corners, and refuse mid-lane duels.")

    if flags["close_range"]:
        reasons.append("Close-range kills need repeatable contact and quick reset tools more than passive lane holding.")
        equipment_priorities.append("Prioritise fast-entry tactical equipment and simple lethal pressure for room clears.")
        playstyle_notes.append("Play tight routes around objectives and interiors rather than rotating across open lanes.")

    if flags["one_shot"]:
        reasons.append("One-shot challenges reward first-shot advantage, flinch control, and holding the correct range.")
        equipment_priorities.append("Prioritise information or lane-control tools that help you take the first clean shot.")
        playstyle_notes.append("Do not sprint into panic fights. Pre-aim traffic and reset after every miss.")

    if flags["melee"]:
        reasons.append("Melee kills are mostly a route, stealth, and utility problem. Weapon maths is secondary.")
        equipment_priorities.append("Prioritise smoke, stun, stealth, and survivability tools that close distance safely.")
        playstyle_notes.append("Use chaos around objectives, flank routes, and covered gaps. Do not ego-cross open lanes.")

    if not reasons:
        reasons.append("No specialised perk pressure detected. Use the package as a general grind shell and field test lobby flow.")

    warnings.extend(risks)

    if package_name == "Aggressive" and (flags["no_damage"] or flags["longshots"]):
        warnings.append("Aggressive is attempt-rich but can fight the challenge if it makes you over-push.")
    if package_name == "Long-range" and (flags["small_map"] or flags["hipfire"] or flags["slide_dive"]):
        warnings.append("Long-range is stable, but may feel too passive for small-map movement challenges.")
    if flags["underbarrel_launcher"]:
        warnings.append("The Oracle cannot model blast radius, direct-hit consistency, or launcher ammo economy yet.")
    if flags["melee"]:
        warnings.append("Melee recommendations are tactical only. The Oracle cannot model melee lunge, swing speed, or hit registration yet.")
    if flags["one_shot"]:
        warnings.append("One-shot reliability depends on the entered damage model. Field test the actual one-shot range before trusting it.")

    warnings.extend(loadout_legality_notes)

    recommended_tactical = "Pinpoint Grenade" if flags["headshots"] else "Stim Shot"
    recommended_lethal = "Molotov" if flags["objective"] else "Frag"
    recommended_field_upgrade = "Trophy System" if flags["objective"] else "Assault Pack"

    if flags["underbarrel_launcher"]:
        recommended_tactical = "Smoke"
        recommended_lethal = "Cluster Grenade"
        recommended_field_upgrade = "Assault Pack"
    elif flags["melee"]:
        recommended_tactical = "Smoke"
        recommended_lethal = "Combat Axe"
        recommended_field_upgrade = "Active Camo"
    elif flags["point_blank"]:
        recommended_tactical = "Stun Grenade"
        recommended_lethal = "Semtex"
        recommended_field_upgrade = "Mute Field"
    elif flags["close_range"]:
        recommended_tactical = "Stim Shot"
        recommended_lethal = "Semtex"
        recommended_field_upgrade = "Mute Field"
    elif flags["no_damage"]:
        recommended_tactical = "Smoke"
        recommended_lethal = "C4"
        recommended_field_upgrade = "Active Camo"
    elif flags["one_shot"]:
        recommended_tactical = "Pinpoint Grenade"
        recommended_lethal = "Frag"
        recommended_field_upgrade = "Tactical Insertion"
    elif flags["longshots"] or flags["optic_4x"]:
        recommended_tactical = "Pinpoint Grenade"
        recommended_lethal = "Needle Drone"
        recommended_field_upgrade = "Tactical Insertion"
    elif flags["hipfire"] or flags["sprint"] or flags["moving"] or flags["slide_dive"]:
        recommended_tactical = "Stim Shot"
        recommended_lethal = "Semtex"
        recommended_field_upgrade = "Mute Field"

    equipment_overclock_advice = build_equipment_overclock_advice(
        recommended_tactical=recommended_tactical,
        recommended_lethal=recommended_lethal,
        recommended_field_upgrade=recommended_field_upgrade,
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=tactical_goal,
        map_size=map_size,
        playlist_style=playlist_style,
        wildcard_id=wildcard_id,
    )

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

    scorestreak_advice = build_scorestreak_package_advice(
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=tactical_goal,
        map_size=map_size,
        playlist_style=playlist_style,
        wildcard_id=wildcard_id,
    )

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
        "equipment_overclock_advice": json.loads(equipment_overclock_advice.get("equipment_overclock_lab_evidence_json", "{}") or "{}"),
        "scorestreak_advice": json.loads(scorestreak_advice.get("scorestreak_lab_evidence_json", "{}") or "{}"),
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
        "recommended_tactical_overclock": equipment_overclock_advice.get("recommended_tactical_overclock", ""),
        "recommended_tactical_overclock_description": equipment_overclock_advice.get("recommended_tactical_overclock_description", ""),
        "recommended_lethal_overclock": equipment_overclock_advice.get("recommended_lethal_overclock", ""),
        "recommended_lethal_overclock_description": equipment_overclock_advice.get("recommended_lethal_overclock_description", ""),
        "recommended_field_upgrade_overclock": equipment_overclock_advice.get("recommended_field_upgrade_overclock", ""),
        "recommended_field_upgrade_overclock_description": equipment_overclock_advice.get("recommended_field_upgrade_overclock_description", ""),
        "equipment_overclock_summary": equipment_overclock_advice.get("equipment_overclock_summary", ""),
        "equipment_overclock_warnings": equipment_overclock_advice.get("equipment_overclock_warnings", ""),
        "equipment_overclock_lab_evidence_json": equipment_overclock_advice.get("equipment_overclock_lab_evidence_json", ""),
        "scorestreak_recommendation_summary": scorestreak_advice.get("scorestreak_recommendation_summary", ""),
        "recommended_scorestreaks": scorestreak_advice.get("recommended_scorestreaks", ""),
        "scorestreak_warnings": scorestreak_advice.get("scorestreak_warnings", ""),
        "scorestreak_lab_evidence_json": scorestreak_advice.get("scorestreak_lab_evidence_json", ""),
        "loadout_legality_notes": _perk_join(loadout_legality_notes),
        "perk_lab_evidence_json": json.dumps(evidence, indent=2),
    }


def perk_package_score_bonus(perk_package):
    package = PERK_PACKAGES.get(perk_package, {})
    bonus = package.get("bonus", {})

    score_bonus = 0.0

    score_bonus += max(0, -float(bonus.get("ads_ms", 0))) * 0.001
    score_bonus += max(0, -float(bonus.get("sprint_to_fire_ms", 0))) * 0.001
    score_bonus += max(0, -float(bonus.get("reload_ms", 0))) * 0.0002
    score_bonus += max(0, -float(bonus.get("recoil", 0))) * 0.005

    return score_bonus

def optimise_full_loadouts_for_scenario(*args, **kwargs):
    """Compatibility wrapper for the weapon engine's current full-loadout pass."""
    from modules.warzone.ttk_oracle_engine import optimise_full_loadouts_for_scenario as _optimise
    return _optimise(*args, **kwargs)


__all__ = [
    "LOADOUT_PAIRINGS",
    "PERK_PACKAGES",
    "PERK_SELECTION_OPTIONS",
    "WILDCARD_SELECTION_OPTIONS",
    "build_equipment_overclock_advice",
    "build_perk_loadout_advice",
    "build_scorestreak_package_advice",
    "effective_wildcard_id",
    "load_loadout_catalogue",
    "loadout_legality_warnings",
    "loadout_pairing_requires_overkill",
    "optimise_full_loadouts_for_scenario",
    "perk_package_fit_score",
    "perk_package_score_bonus",
    "recommend_perk_package",
    "recommend_standard_secondary_slot",
    "wildcard_id_from_selection",
    "wildcard_name_from_id",
]

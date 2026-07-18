"""Deterministic challenge knowledge for Completion Commander.

This module contains tactical opinions, not weapon maths. It translates a
challenge description into a stable mission profile that Commander, Loadout Lab
and Field Planner can share.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class MissionKnowledge:
    key: str
    label: str
    build_goal: str
    fight_type: str
    tactical_goal: str
    map_size: str
    map_type: str
    playlist_style: str
    optic_preference: str
    preferred_modes: tuple[str, ...] = ()
    avoid_modes: tuple[str, ...] = ()
    playstyle: tuple[str, ...] = ()
    attachment_priorities: tuple[str, ...] = ()
    loadout_bias: dict[str, str] = field(default_factory=dict)
    confidence: str = "high"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MISSION_KNOWLEDGE = {
    "headshots": MissionKnowledge(
        key="headshots",
        label="Headshot grinding",
        build_goal="Military Camo Headshots",
        fight_type="Mixed fights",
        tactical_goal="Headshot grinding",
        map_size="Small",
        map_type="Small map / Resurgence",
        playlist_style="Fast respawn objective",
        optic_preference="Non-thermal preferred",
        preferred_modes=("Domination", "Hardpoint", "Control"),
        avoid_modes=("Search and Destroy", "Team Deathmatch"),
        playstyle=(
            "Hold predictable objective lanes.",
            "Aim upper chest and let recoil climb into the head.",
            "Prioritise repeatable engagements over flanks.",
        ),
        attachment_priorities=(
            "headshot breakpoint",
            "vertical recoil",
            "visual recoil",
            "ads speed",
        ),
        loadout_bias={
            "secondary": "launcher",
            "scorestreak_style": "low_cost_information",
        },
    ),
    "longshots": MissionKnowledge(
        key="longshots",
        label="Longshot grinding",
        build_goal="Long-range consistency",
        fight_type="Long range",
        tactical_goal="Longshots",
        map_size="Large",
        map_type="Large map / Battle Royale",
        playlist_style="Long-range lanes",
        optic_preference="Any optic",
        preferred_modes=("Domination", "Hardpoint", "Control"),
        avoid_modes=("Face Off", "Small-map moshpit"),
        playstyle=(
            "Hold long sightlines with predictable traffic.",
            "Avoid unnecessary close-range rotations.",
            "Prioritise velocity, range and recoil consistency.",
        ),
        attachment_priorities=(
            "bullet velocity",
            "damage range",
            "horizontal recoil",
            "aiming idle sway",
        ),
    ),
    "hipfire": MissionKnowledge(
        key="hipfire",
        label="Hipfire grinding",
        build_goal="Close-range aggression",
        fight_type="Close range",
        tactical_goal="Hipfire kills",
        map_size="Small",
        map_type="Small map / Resurgence",
        playlist_style="Fast respawn objective",
        optic_preference="Use my own optic",
        preferred_modes=("Hardpoint", "Domination", "Face Off"),
        avoid_modes=("Search and Destroy",),
        playstyle=(
            "Collapse onto objectives and doorways.",
            "Pre-aim from the hip before entering close fights.",
            "Avoid wasting attachment budget on long-range optics.",
        ),
        attachment_priorities=(
            "hipfire spread",
            "sprint to fire",
            "movement speed",
            "magazine safety",
        ),
    ),
    "point_blank": MissionKnowledge(
        key="point_blank",
        label="Point blank kills",
        build_goal="Aggressive mobility",
        fight_type="Close range",
        tactical_goal="Point blank kills",
        map_size="Small",
        map_type="Small map / Resurgence",
        playlist_style="Fast respawn objective",
        optic_preference="Use my own optic",
        preferred_modes=("Hardpoint", "Domination", "Face Off"),
        avoid_modes=("Search and Destroy", "Large-map lanes"),
        playstyle=(
            "Force fights inside rooms, stairwells and objective entrances.",
            "Use cover breaks to close the final few metres before shooting.",
            "Do not hold lanes unless they feed directly into point-blank traffic.",
        ),
        attachment_priorities=(
            "sprint to fire",
            "hipfire spread",
            "slide to fire",
            "movement speed",
            "magazine safety",
            "close damage",
        ),
        loadout_bias={
            "perk_style": "mobility_survival",
            "tactical": "stun_or_smoke",
            "field_upgrade": "close_distance",
        },
    ),
    "one_shot": MissionKnowledge(
        key="one_shot",
        label="One-shot kills",
        build_goal="One-shot consistency",
        fight_type="Long range",
        tactical_goal="One-shot kills",
        map_size="Medium",
        map_type="Large map / Battle Royale",
        playlist_style="Long-range lanes",
        optic_preference="Any optic",
        preferred_modes=("Domination", "Control", "Hardpoint"),
        avoid_modes=("Face Off", "Small-map moshpit"),
        playstyle=(
            "Take first-shot engagements from cover.",
            "Reset after every shot instead of ego-challenging weak follow-ups.",
            "Prioritise lanes where upper-body or headshot one-shot zones are repeatable.",
        ),
        attachment_priorities=(
            "one-shot breakpoint",
            "ads speed",
            "flinch resistance",
            "bullet velocity",
            "aiming idle sway",
            "damage range",
        ),
        loadout_bias={
            "perk_style": "survival_information",
            "secondary": "launcher",
        },
    ),
    "close_range": MissionKnowledge(
        key="close_range",
        label="Close-range kills",
        build_goal="Aggressive mobility",
        fight_type="Close range",
        tactical_goal="Close-range kills",
        map_size="Small",
        map_type="Small map / Resurgence",
        playlist_style="Fast respawn objective",
        optic_preference="Reflex / holo preferred",
        preferred_modes=("Hardpoint", "Domination", "Face Off"),
        avoid_modes=("Search and Destroy", "Long-range lanes"),
        playstyle=(
            "Route through buildings, short cuts and objective entrances.",
            "Take repeatable close fights instead of chasing long sightlines.",
            "Keep the gun ready before crossing doorways and hill breaks.",
        ),
        attachment_priorities=(
            "practical ttk",
            "sprint to fire",
            "ads speed",
            "movement speed",
            "magazine safety",
            "reload speed",
        ),
        loadout_bias={
            "perk_style": "aggressive",
            "secondary": "launcher",
        },
    ),
    "melee": MissionKnowledge(
        key="melee",
        label="Melee kills",
        build_goal="Aggressive mobility",
        fight_type="Close range",
        tactical_goal="Melee kills",
        map_size="Small",
        map_type="Small map / Resurgence",
        playlist_style="Fast respawn objective",
        optic_preference="No optic pressure",
        preferred_modes=("Hardpoint", "Domination", "Face Off"),
        avoid_modes=("Search and Destroy", "Large-map lanes", "Team Deathmatch"),
        playstyle=(
            "Use smoke, stuns and flank routes to cross open space.",
            "Play around objective chaos where enemies are already distracted.",
            "Do not ego-run long lanes; reset and take a covered route.",
        ),
        attachment_priorities=(
            "movement speed",
            "sprint speed",
            "survivability",
            "stealth",
            "equipment support",
        ),
        loadout_bias={
            "perk_style": "mobility_stealth",
            "tactical": "smoke_or_stun",
            "field_upgrade": "close_distance",
            "secondary": "melee",
        },
    ),
    "underbarrel_launcher": MissionKnowledge(
        key="underbarrel_launcher",
        label="Underbarrel launcher kills",
        build_goal="Objective pressure",
        fight_type="Close range",
        tactical_goal="Underbarrel launcher kills",
        map_size="Small",
        map_type="Small map / Resurgence",
        playlist_style="Objective anchor",
        optic_preference="Use my own optic",
        preferred_modes=("Hardpoint", "Domination", "Control"),
        avoid_modes=("Search and Destroy", "Team Deathmatch"),
        playstyle=(
            "Target grouped enemies around objectives.",
            "Use chokepoints and objective entrances.",
            "Carry ammunition support where possible.",
        ),
        attachment_priorities=(
            "underbarrel launcher lock",
            "handling",
            "movement",
            "magazine safety",
        ),
        loadout_bias={
            "field_upgrade": "ammo_support",
            "secondary": "launcher",
        },
    ),
    "suppressor": MissionKnowledge(
        key="suppressor",
        label="Suppressor kills",
        build_goal="Balanced practical TTK",
        fight_type="Mixed fights",
        tactical_goal="Suppressor kills",
        map_size="Small",
        map_type="Small map / Resurgence",
        playlist_style="Fast respawn objective",
        optic_preference="Use my own optic",
        preferred_modes=("Domination", "Hardpoint", "Control"),
        avoid_modes=("Search and Destroy",),
        playstyle=(
            "Keep the suppressor locked and optimise the remaining slots.",
            "Use repeatable objective routes rather than isolated flanks.",
        ),
        attachment_priorities=(
            "suppressor lock",
            "practical ttk",
            "recoil",
            "ads speed",
        ),
    ),
    "optic_4x": MissionKnowledge(
        key="optic_4x",
        label="4.0x optic kills",
        build_goal="Long-range consistency",
        fight_type="Long range",
        tactical_goal="4.0x+ optic kills",
        map_size="Large",
        map_type="Large map / Battle Royale",
        playlist_style="Long-range lanes",
        optic_preference="Force current Oracle optic",
        preferred_modes=("Domination", "Hardpoint", "Control"),
        avoid_modes=("Face Off", "Small-map moshpit"),
        playstyle=(
            "Use medium and long sightlines.",
            "Avoid forcing the magnified optic into constant point-blank fights.",
        ),
        attachment_priorities=(
            "4.0x optic lock",
            "visual recoil",
            "aiming idle sway",
            "bullet velocity",
        ),
    ),
    "objective": MissionKnowledge(
        key="objective",
        label="Objective kills",
        build_goal="Objective pressure",
        fight_type="Mixed fights",
        tactical_goal="Objective kills",
        map_size="Small",
        map_type="Small map / Resurgence",
        playlist_style="Objective anchor",
        optic_preference="Any optic",
        preferred_modes=("Hardpoint", "Domination", "Control"),
        avoid_modes=("Team Deathmatch", "Search and Destroy"),
        playstyle=(
            "Fight on or immediately beside the objective.",
            "Use utility to create repeatable close and mid-range fights.",
        ),
        attachment_priorities=(
            "practical ttk",
            "sprint to fire",
            "magazine safety",
            "recoil",
        ),
    ),
    "movement": MissionKnowledge(
        key="movement",
        label="Movement kills",
        build_goal="Close-range aggression",
        fight_type="Close range",
        tactical_goal="Kills while moving",
        map_size="Small",
        map_type="Small map / Resurgence",
        playlist_style="Fast respawn objective",
        optic_preference="Reflex / holo preferred",
        preferred_modes=("Hardpoint", "Domination", "Face Off"),
        avoid_modes=("Search and Destroy",),
        playstyle=(
            "Keep moving through short objective routes.",
            "Prioritise sprint-to-fire, movement and ADS movement.",
        ),
        attachment_priorities=(
            "sprint to fire",
            "movement speed",
            "ads movement",
            "hipfire spread",
        ),
    ),
    "no_damage": MissionKnowledge(
        key="no_damage",
        label="No-damage kills",
        build_goal="Long-range consistency",
        fight_type="Long range",
        tactical_goal="No-damage kills",
        map_size="Medium",
        map_type="Large map / Battle Royale",
        playlist_style="Passive survival",
        optic_preference="Any optic",
        preferred_modes=("Domination", "Control"),
        avoid_modes=("Face Off", "Small-map moshpit", "Hardpoint"),
        playstyle=(
            "Hold cover and take first-shot engagements.",
            "Do not chase weakened enemies into exposed routes.",
        ),
        attachment_priorities=(
            "first-shot recoil",
            "range",
            "bullet velocity",
            "flinch resistance",
        ),
    ),
    "default": MissionKnowledge(
        key="default",
        label="General weapon progression",
        build_goal="Balanced practical TTK",
        fight_type="Mixed fights",
        tactical_goal="Auto from build goal / challenge",
        map_size="Auto",
        map_type="Small map / Resurgence",
        playlist_style="Auto",
        optic_preference="Any optic",
        preferred_modes=("Domination", "Hardpoint", "Control"),
        avoid_modes=("Search and Destroy",),
        playstyle=("Use the highest-engagement respawn playlist available.",),
        attachment_priorities=("practical ttk", "recoil", "ads speed"),
        confidence="medium",
    ),
}


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def mission_knowledge_key(text: str) -> str:
    value = str(text or "").lower()

    ordered_rules = [
        ("underbarrel_launcher", ("underbarrel launcher", "launcher attachment")),
        ("optic_4x", ("4.0x", "4x scope", "4.0x+ magnification")),
        ("suppressor", ("suppressor", "supressor")),
        ("headshots", ("headshot", "military camo")),
        ("point_blank", ("point blank", "point-blank")),
        ("one_shot", ("one shot", "one-shot", "one hit", "one-hit", "one shot kill")),
        ("longshots", ("longshot", "long shot")),
        ("hipfire", ("hipfire", "hip fire")),
        (
            "close_range",
            (
                "close range",
                "close-range",
                "close kills",
                "close quarters",
                "short range",
                "short-range",
            ),
        ),
        ("melee", ("melee", "knife", "combat knife", "bat", "baseball bat")),
        ("no_damage", ("without taking any damage", "no damage")),
        (
            "movement",
            (
                "while moving",
                "sprint",
                "sliding",
                "diving",
                "wall-jumping",
                "wall jumping",
            ),
        ),
        ("objective", ("objective kill", "objective")),
    ]

    for key, terms in ordered_rules:
        if _contains_any(value, terms):
            return key

    return "default"


def resolve_mission_knowledge(
    text: str,
    preferences: Mapping[str, Any] | None = None,
) -> MissionKnowledge:
    base = MISSION_KNOWLEDGE[mission_knowledge_key(text)]
    preferences = dict(preferences or {})

    overrides = {
        "build_goal": str(preferences.get("build_goal", "") or "").strip(),
        "fight_type": str(preferences.get("fight_type", "") or "").strip(),
        "map_size": str(preferences.get("map_size", "") or "").strip(),
        "map_type": str(preferences.get("map_type", "") or "").strip(),
        "playlist_style": str(preferences.get("playlist_style", "") or "").strip(),
        "optic_preference": str(preferences.get("optic_preference", "") or "").strip(),
    }

    if not any(overrides.values()):
        return base

    values = base.to_dict()
    for key, value in overrides.items():
        if value:
            values[key] = value

    values["preferred_modes"] = tuple(values.get("preferred_modes", ()))
    values["avoid_modes"] = tuple(values.get("avoid_modes", ()))
    values["playstyle"] = tuple(values.get("playstyle", ()))
    values["attachment_priorities"] = tuple(values.get("attachment_priorities", ()))

    return MissionKnowledge(**values)


__all__ = [
    "MISSION_KNOWLEDGE",
    "MissionKnowledge",
    "mission_knowledge_key",
    "resolve_mission_knowledge",
]

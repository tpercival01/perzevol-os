"""Deterministic Field Planner.

This module owns playlist, map-size, playstyle and optic-context advice.
It deliberately does not calculate weapon stats or optimise attachments.
"""

from __future__ import annotations

import json
import math
import re
from html import unescape
from typing import Any, Mapping


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


def _normalise_schema_value(value: Any) -> str:
    text = unescape(str(value or "").strip()).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _normalise_slot_value(value: Any) -> str:
    key = _normalise_schema_value(value)
    aliases = {
        "under_barrel": "underbarrel",
        "optics": "optic",
        "sight": "optic",
        "scope": "optic",
    }
    return aliases.get(key, key)


def _numeric_cell(value: Any, fallback: float = 0.0) -> float:
    if value is None:
        return fallback
    try:
        number = float(str(value).strip().replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return fallback
    return fallback if not math.isfinite(number) else number


def _normalise_tactical_text(value: Any) -> str:
    return _normalise_schema_value(value).replace("_", " ")


def _tactical_strings(*values: Any) -> str:
    return " ".join(
        str(value or "").strip().lower()
        for value in values
        if str(value or "").strip()
    )


def _append_unique(items: list[str], additions: list[str]) -> None:
    for item in additions:
        if item and item not in items:
            items.append(item)


def selected_optic_from_evidence(row: Mapping[str, Any] | None = None, prefix: str = "") -> dict:
    if row is None:
        return {}

    evidence_text = str(row.get(f"{prefix}lab_evidence_json", "") or "").strip()
    if not evidence_text:
        evidence_text = str(row.get("lab_evidence_json", "") or "").strip()
    if not evidence_text:
        return {}

    try:
        packet = json.loads(evidence_text)
    except (TypeError, json.JSONDecodeError):
        return {}

    for attachment in packet.get("selected_attachments", []) or []:
        if _normalise_slot_value(attachment.get("slot", "")) == "optic":
            return dict(attachment)

    return {}


def _goal_flags(
    *,
    build_goal: str,
    fight_type: str,
    challenge_requirements: str,
    tactical_goal: str,
    playlist_style: str,
) -> dict[str, bool]:
    text = _tactical_strings(
        build_goal,
        fight_type,
        challenge_requirements,
        tactical_goal,
        playlist_style,
    )
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
    row: Mapping[str, Any] | None = None,
    prefix: str = "",
    selected_attachments=None,
) -> dict:
    """Return deterministic tactical recommendations for an Oracle result."""
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
        _append_unique(recommended_modes, [
            "Domination",
            "Hardpoint with anchor play",
            "Slower respawn playlists only if you can control angles",
        ])
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
        warnings.append(
            "Underbarrel launcher kills are challenge-specific. Weapon TTK does not model blast reliability, ammo economy, or direct-hit consistency."
        )

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

    map_key = _normalise_tactical_text(map_size)
    if "small map" in map_key:
        if flags["headshots"]:
            warnings.append(
                "Small maps create more headshot attempts, but optic clutter and thermal overlays can become a real comfort risk."
            )
        if flags["optic_4x"]:
            warnings.append(
                "4.0x+ optics are challenge-compliant on small maps, but not automatically comfortable. Treat the optic as FIELD TEST REQUIRED."
            )
    elif "large map" in map_key:
        _append_unique(priorities, [
            "Large maps increase value for bullet velocity, range, recoil stability, and clean optics."
        ])

    playlist_key = _normalise_tactical_text(playlist_style)
    if "fast respawn" in playlist_key:
        _append_unique(recommended_modes, ["Small-map objective respawn"])
        _append_unique(priorities, [
            "Maximise attempts per minute. Do not waste time in low-engagement playlists."
        ])
    elif "objective anchor" in playlist_key:
        _append_unique(recommended_modes, ["Domination", "Hardpoint"])
        _append_unique(priorities, [
            "Anchor a repeatable lane near the objective rather than sprinting through the whole map."
        ])
    elif "long range" in playlist_key:
        _append_unique(recommended_modes, ["Domination on medium/large maps"])
        _append_unique(priorities, [
            "Avoid short sightline maps even if the build's raw TTK looks strong."
        ])
    elif "passive survival" in playlist_key:
        _append_unique(priorities, [
            "Slow the pace, take first-shot advantage, and reset after each engagement."
        ])

    optic = selected_optic_from_evidence(row, prefix=prefix)
    if not optic and selected_attachments:
        for attachment in selected_attachments:
            if _normalise_slot_value(attachment.get("slot", "")) == "optic":
                optic = dict(attachment)
                break

    optic_note = ""
    if optic:
        optic_name = str(optic.get("name", optic.get("attachment_name", "")) or "").strip()
        optic_type = _normalise_schema_value(optic.get("optic_type", ""))
        optic_zoom = _numeric_cell(optic.get("optic_zoom", 0), 0.0)
        verification_status = _normalise_schema_value(optic.get("verification_status", ""))

        optic_parts = [f"Selected optic: {optic_name}"]
        if optic_type:
            optic_parts.append(f"type={optic_type}")
        if optic_zoom:
            optic_parts.append(f"zoom={optic_zoom:g}x")
        optic_note = " | ".join(optic_parts)

        if optic_type == "thermal":
            warnings.append(
                "THERMAL SIGHT PICTURE UNMODELLED: the optic may score well on recoil/stability while still feeling poor for small-map headshot grinding."
            )
        if verification_status in {"needs_review", "partial"}:
            warnings.append(
                f"Optic data is {verification_status}. Trust the modelled numbers, but field test the sight picture."
            )

        preference_key = _normalise_tactical_text(optic_preference)
        if "non thermal" in preference_key and optic_type == "thermal":
            warnings.append(
                "Optic preference conflict: the Oracle selected a thermal optic while non-thermal is preferred."
            )
        if "reflex" in preference_key and optic_type not in {"reflex", "holo"}:
            warnings.append(
                "Optic preference conflict: this is not a reflex/holo optic. Keep the build shell and swap to your preferred reticle if needed."
            )
        if "use my own optic" in preference_key:
            warnings.append(
                "You selected 'Use my own optic'. Treat the optic recommendation as replaceable and keep the non-optic build shell."
            )
    elif "optic" in _tactical_strings(challenge_requirements, tactical_goal):
        warnings.append(
            "The tactical context expects an optic, but no optic was detected in the winning build evidence."
        )

    summary_bits = []
    if flags["headshots"]:
        summary_bits.append(
            "Headshot grind: favour predictable objective traffic, recoil stability, and clean sight picture."
        )
    elif flags["objective"]:
        summary_bits.append(
            "Objective grind: optimise for repeated contact around flags or hills."
        )
    elif flags["underbarrel_launcher"]:
        summary_bits.append(
            "Launcher grind: use the weapon as a challenge carrier and farm clustered objective traffic."
        )
    else:
        summary_bits.append(
            "General grind: use fast respawn modes and field test the candidate before trusting it."
        )

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

def apply_mission_knowledge_to_advice(advice: Mapping[str, Any],mission_knowledge: Mapping[str, Any] | None,) -> dict:
    enriched = dict(advice or {})
    knowledge = dict(mission_knowledge or {})

    if not knowledge:
        return enriched

    recommended_modes = list(enriched.get("recommended_modes", []) or [])
    avoid_modes = list(enriched.get("avoid_modes", []) or [])
    priorities = list(enriched.get("priorities", []) or [])
    warnings = list(enriched.get("warnings", []) or [])

    _append_unique(recommended_modes, list(knowledge.get("preferred_modes", []) or []))
    _append_unique(avoid_modes, list(knowledge.get("avoid_modes", []) or []))

    playstyle = list(knowledge.get("playstyle", []) or [])
    attachment_priorities = list(knowledge.get("attachment_priorities", []) or [])

    if playstyle:
        _append_unique(priorities, [f"Playstyle: {item}" for item in playstyle])

    if attachment_priorities:
        _append_unique(
            priorities,
            [f"Attachment priority: {str(item).title()}" for item in attachment_priorities],
        )

    confidence = str(knowledge.get("confidence", "") or "").strip()
    if confidence and confidence.lower() != "high":
        warnings.append(f"Mission Knowledge confidence is {confidence}.")

    enriched["recommended_modes"] = recommended_modes
    enriched["avoid_modes"] = avoid_modes
    enriched["priorities"] = priorities
    enriched["warnings"] = warnings
    enriched["mission_knowledge"] = knowledge

    return enriched


__all__ = [
    "OPTIC_PREFERENCE_OPTIONS",
    "TACTICAL_GOAL_OPTIONS",
    "TACTICAL_MAP_SIZE_OPTIONS",
    "TACTICAL_PLAYLIST_STYLE_OPTIONS",
    "apply_mission_knowledge_to_advice",
    "build_tactical_advice",
    "selected_optic_from_evidence",
]

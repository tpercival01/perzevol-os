"""Commander mission translation for the Oracle pipeline.

This module converts a Commander-owned MissionProfile into the small set of
deterministic inputs required by Weapon Lab, Loadout Lab and Field Planner.
It does not run an optimiser and has no Streamlit dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Mapping

from modules.warzone.challenge_rules import (
    ChallengeConstraints,
    build_challenge_constraints,
)
from modules.warzone.oracle_data import (
    DEFAULT_STATS_PROFILE,
    normalise_schema_value,
    normalise_stats_profile,
)
from modules.warzone.oracle_models import MissionProfile
from modules.warzone.mission_knowledge import resolve_mission_knowledge


@dataclass(slots=True)
class OracleMissionInputs:
    mission: MissionProfile
    stats_profile: str
    build_goal: str
    fight_type: str
    tactical_goal: str
    map_size: str
    map_type: str
    playlist_style: str
    optic_preference: str
    enemy_health: int
    attachment_count: int
    challenge: ChallengeConstraints = field(default_factory=ChallengeConstraints)
    mission_knowledge: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def tactical_context(self) -> dict[str, Any]:
        return {
            "build_goal": self.build_goal,
            "fight_type": self.fight_type,
            "challenge_requirements": self.challenge.summary if self.challenge.active else "",
            "tactical_goal": self.tactical_goal,
            "map_size": self.map_size,
            "map_type": self.map_type,
            "playlist_style": self.playlist_style,
            "optic_preference": self.optic_preference,
            "mission_knowledge_key": self.mission_knowledge.get("key", ""),
            "preferred_modes": self.mission_knowledge.get("preferred_modes", []),
            "avoid_modes": self.mission_knowledge.get("avoid_modes", []),
            "playstyle": self.mission_knowledge.get("playstyle", []),
            "attachment_priorities": self.mission_knowledge.get("attachment_priorities", []),
        }

    def optimiser_kwargs(self) -> dict[str, Any]:
        return {
            "enemy_health": self.enemy_health,
            "map_type": self.map_type,
            "fight_type": self.fight_type,
            "build_goal": self.build_goal,
            "attachment_count": self.attachment_count,
            "forced_attachment_rules": list(self.challenge.rules),
        }

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["tactical_context"] = self.tactical_context()
        value["optimiser_kwargs"] = self.optimiser_kwargs()
        return value


def _text_blob(profile: MissionProfile) -> str:
    values = [
        profile.challenge_type,
        profile.challenge_name,
        profile.target,
        profile.metadata.get("challenge_description", ""),
        profile.metadata.get("task_name", ""),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _challenge_requirement(text: str) -> str:
    if _contains_any(text, ["underbarrel launcher", "launcher attachment"]):
        return "Underbarrel launcher"

    if _contains_any(text, ["suppressor", "supressor"]):
        return "Any suppressor"

    if _contains_any(text, ["4.0x", "4x scope", "4.0x+ magnification"]):
        return "4.0x+ optic"

    if _contains_any(text, ["8 attachments", "gunfighter"]):
        return "8 attachments"

    if _contains_any(text, ["5 or more attachments", "5+ attachments"]):
        return "5+ attachments"

    return ""


def _build_goal(text: str, profile: MissionProfile) -> str:
    if _contains_any(text, ["headshot", "military camo"]):
        return "Military Camo Headshots"

    if _contains_any(text, ["longshot", "long shot"]):
        return "Long-range consistency"

    if _contains_any(text, ["hipfire", "hip fire"]):
        return "Close-range aggression"

    if _contains_any(text, ["objective kill", "objective"]):
        return "Objective pressure"

    if _contains_any(text, ["one shot", "point blank"]):
        return "Close-range TTK"

    preference = str(profile.preferences.get("build_goal", "") or "").strip()
    return preference or "Balanced practical TTK"


def _fight_type(text: str, profile: MissionProfile) -> str:
    explicit = str(profile.preferences.get("fight_type", "") or "").strip()
    if explicit:
        return explicit

    if _contains_any(text, ["longshot", "long shot", "4.0x", "4x scope"]):
        return "Long range"

    if _contains_any(
        text,
        [
            "hipfire",
            "point blank",
            "sprint",
            "sliding",
            "diving",
            "wall-jumping",
            "switching weapons",
        ],
    ):
        return "Close range"

    return "Mixed fights"


def _tactical_goal(text: str) -> str:
    mappings = [
        (["headshot", "military camo"], "Headshot grinding"),
        (["objective kill"], "Objective kills"),
        (["hipfire", "hip fire"], "Hipfire kills"),
        (["while moving"], "Kills while moving"),
        (["sprint"], "Sprint kills"),
        (["sliding", "diving", "wall-jumping"], "Slide / dive / wall-jump kills"),
        (["without taking any damage"], "No-damage kills"),
        (["longshot", "long shot"], "Longshots"),
        (["underbarrel launcher", "launcher attachment"], "Underbarrel launcher kills"),
        (["suppressor", "supressor"], "Suppressor kills"),
        (["4.0x", "4x scope"], "4.0x+ optic kills"),
        (["scorestreak", "aerial", "vehicle", "destroy"], "Scorestreak destruction"),
    ]

    for terms, label in mappings:
        if _contains_any(text, terms):
            return label

    return "Auto from build goal / challenge"


def _map_size(text: str, profile: MissionProfile) -> str:
    explicit = str(profile.preferences.get("map_size", "") or "").strip()
    if explicit:
        return explicit

    if _contains_any(text, ["longshot", "long shot", "4.0x", "4x scope"]):
        return "Large"

    if _contains_any(
        text,
        [
            "headshot",
            "hipfire",
            "point blank",
            "sprint",
            "sliding",
            "diving",
            "wall-jumping",
        ],
    ):
        return "Small"

    return "Auto"



def _map_type(map_size: str, profile: MissionProfile) -> str:
    explicit = str(profile.preferences.get("map_type", "") or "").strip()
    if explicit:
        return explicit

    if map_size == "Large":
        return "Large map / Battle Royale"

    return "Small map / Resurgence"

def _playlist_style(text: str, profile: MissionProfile) -> str:
    explicit = str(profile.preferences.get("playlist_style", "") or "").strip()
    if explicit:
        return explicit

    if _contains_any(text, ["objective", "underbarrel launcher", "affected by your tactical"]):
        return "Objective anchor"

    if _contains_any(
        text,
        ["headshot", "hipfire", "sprint", "while moving", "sliding", "diving"],
    ):
        return "Fast respawn objective"

    if _contains_any(text, ["longshot", "without taking any damage"]):
        return "Controlled lanes"

    return "Auto"


def _optic_preference(text: str, profile: MissionProfile) -> str:
    explicit = str(profile.preferences.get("optic_preference", "") or "").strip()
    if explicit:
        return explicit

    if _contains_any(text, ["4.0x", "4x scope"]):
        return "Any"

    if _contains_any(text, ["headshot", "small map"]):
        return "Non-thermal preferred"

    return "Any"


def mission_profile_to_oracle_inputs(
    mission: MissionProfile | Mapping[str, Any],
) -> OracleMissionInputs:
    profile = mission if isinstance(mission, MissionProfile) else MissionProfile.from_mapping(mission)
    text = _text_blob(profile)

    requirement = _challenge_requirement(text)
    custom_text = str(profile.constraints.get("attachment_name_contains", "") or "")
    role_scope = str(profile.constraints.get("challenge_role_scope", "Primary weapon") or "Primary weapon")

    if profile.constraints.get("challenge_requirement"):
        requirement = str(profile.constraints["challenge_requirement"])

    challenge = build_challenge_constraints(
        requirement=requirement,
        custom_text=custom_text,
        role_scope=role_scope,
    )

    stats_profile = normalise_stats_profile(
        profile.stats_profile or profile.mode,
        DEFAULT_STATS_PROFILE,
    )
    enemy_health = int(profile.constraints.get("enemy_health", 100) or 100)
    attachment_count = int(profile.constraints.get("attachment_count", 5) or 5)
    attachment_count = max(attachment_count, challenge.required_attachment_count)

    warnings = []
    if not profile.weapon_id:
        warnings.append("Mission profile has no weapon_id.")
    if requirement and not challenge.active:
        warnings.append(f"Challenge requirement could not be translated: {requirement}")

    knowledge = resolve_mission_knowledge(
        text,
        preferences=profile.preferences,
    )

    return OracleMissionInputs(
        mission=profile,
        stats_profile=stats_profile,
        build_goal=knowledge.build_goal,
        fight_type=knowledge.fight_type,
        tactical_goal=knowledge.tactical_goal,
        map_size=knowledge.map_size,
        map_type=knowledge.map_type,
        playlist_style=knowledge.playlist_style,
        optic_preference=knowledge.optic_preference,
        enemy_health=enemy_health,
        attachment_count=attachment_count,
        challenge=challenge,
        mission_knowledge=knowledge.to_dict(),
        warnings=warnings,
    )


__all__ = [
    "OracleMissionInputs",
    "mission_profile_to_oracle_inputs",
]

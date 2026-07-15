from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

import pandas as pd

from modules.warzone.field_planner import build_tactical_advice
try:
    from modules.warzone.field_planner import apply_mission_knowledge_to_advice
except ImportError:  # Backwards-compatible while older Field Planner files are replaced.
    def apply_mission_knowledge_to_advice(advice: Mapping[str, Any], mission_knowledge: Mapping[str, Any] | None) -> dict:
        return dict(advice or {})

from modules.warzone.loadout_lab import (
    build_perk_loadout_advice,
    effective_wildcard_id,
    loadout_legality_warnings,
    recommend_perk_package,
    recommend_standard_secondary_slot,
    wildcard_name_from_id,
)
from modules.warzone.oracle_data import load_ttk_data
from modules.warzone.weapon_session import build_weapon_session
from modules.warzone.mission_adapter import OracleMissionInputs, mission_profile_to_oracle_inputs
from modules.warzone.oracle_models import (
    FieldPlan,
    LoadoutBuild,
    MissionProfile,
    SessionBrief,
    WeaponBuild,
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _split_double_pipe(value: Any) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    return [item.strip() for item in text.split("||") if item.strip()]


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    try:
        parsed = json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}

    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        text = _clean(value)
        if text and text not in target:
            target.append(text)


def _mission_preference(profile: MissionProfile, *keys: str, default: str = "") -> str:
    for key in keys:
        value = _clean(profile.preferences.get(key, ""))
        if value:
            return value
    return default


def _mission_knowledge_loadout_bias(inferred: OracleMissionInputs) -> dict[str, Any]:
    knowledge = inferred.mission_knowledge or {}
    bias = knowledge.get("loadout_bias", {})
    return dict(bias) if isinstance(bias, Mapping) else {}


def _perks_from_advice(advice: Mapping[str, Any]) -> list[str]:
    evidence = _json_mapping(advice.get("perk_lab_evidence_json", ""))
    perks = evidence.get("perks", {}) if isinstance(evidence, Mapping) else {}

    if not isinstance(perks, Mapping):
        return []

    return [
        _clean(perks.get(key))
        for key in ("perk_1", "perk_2", "perk_3", "perk_4")
        if _clean(perks.get(key))
    ]


def _overclocks_from_advice(advice: Mapping[str, Any]) -> dict[str, str]:
    overclocks = {
        "tactical": _clean(advice.get("recommended_tactical_overclock")),
        "lethal": _clean(advice.get("recommended_lethal_overclock")),
        "field_upgrade": _clean(advice.get("recommended_field_upgrade_overclock")),
    }
    return {key: value for key, value in overclocks.items() if value}


def _scorestreaks_from_advice(advice: Mapping[str, Any]) -> list[str]:
    return _split_double_pipe(advice.get("recommended_scorestreaks", ""))


def build_loadout_for_session(
    *,
    mission: MissionProfile,
    inferred: OracleMissionInputs,
    primary: WeaponBuild,
) -> LoadoutBuild:
    """Build the deterministic Loadout Lab recommendation for a SessionBrief.

    This deliberately ranks class components instead of brute-forcing full
    loadout combinations. Oracle owns the primary weapon build; Loadout Lab owns
    the legal class shell around it.
    """
    challenge_requirements = inferred.challenge.summary if inferred.challenge.active else ""
    loadout_bias = _mission_knowledge_loadout_bias(inferred)

    loadout_pairing = _mission_preference(
        mission,
        "loadout_pairing",
        "pairing",
        default="Any primary + standard secondary",
    )

    selected_wildcard = _mission_preference(
        mission,
        "wildcard",
        "selected_wildcard",
        default="Oracle recommends",
    )
    wildcard_id = effective_wildcard_id(
        selected_wildcard,
        loadout_pairing=loadout_pairing,
        attachment_count=inferred.attachment_count,
        build_goal=inferred.build_goal,
        fight_type=inferred.fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=inferred.tactical_goal,
        playlist_style=inferred.playlist_style,
    )
    wildcard_name = wildcard_name_from_id(wildcard_id)

    legality_notes = loadout_legality_warnings(
        loadout_pairing=loadout_pairing,
        wildcard_id=wildcard_id,
        attachment_count=inferred.attachment_count,
    )

    selected_perk_package = _mission_preference(
        mission,
        "perk_package",
        "perks",
        default="Oracle recommends",
    )
    if selected_perk_package.lower() in {"oracle recommends", "auto", "best", ""}:
        perk_package = recommend_perk_package(
            build_goal=inferred.build_goal,
            fight_type=inferred.fight_type,
            challenge_requirements=challenge_requirements,
            tactical_goal=inferred.tactical_goal,
            map_size=inferred.map_size,
            playlist_style=inferred.playlist_style,
        )
    else:
        perk_package = selected_perk_package

    perk_advice = build_perk_loadout_advice(
        perk_package=perk_package,
        build_goal=inferred.build_goal,
        fight_type=inferred.fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=inferred.tactical_goal,
        map_size=inferred.map_size,
        playlist_style=inferred.playlist_style,
        loadout_pairing=loadout_pairing,
        wildcard_id=wildcard_id,
        loadout_legality_notes=legality_notes,
    )

    secondary_advice = recommend_standard_secondary_slot(
        build_goal=inferred.build_goal,
        fight_type=inferred.fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=inferred.tactical_goal,
        map_size=inferred.map_size,
        playlist_style=inferred.playlist_style,
    )

    # Mission Knowledge can bias the legal secondary class without opening the
    # Overkill/two-primary path. Thomas usually prefers launchers for streak
    # destruction, but mastery context still gets to override through profiles.
    preferred_secondary = _clean(loadout_bias.get("secondary")).lower()
    if preferred_secondary in {"launcher", "pistol", "special"}:
        secondary_class = preferred_secondary
        secondary_label = {
            "launcher": "Launcher support",
            "pistol": "Emergency sidearm",
            "special": "Special utility",
        }[secondary_class]
        secondary_reason = f"Mission Knowledge biased the standard secondary slot to {secondary_class}."
        secondary_scores = dict(secondary_advice.get("secondary_class_scores", {}) or {})
    else:
        secondary_class = _clean(secondary_advice.get("recommended_secondary_class")) or "launcher"
        secondary_label = _clean(secondary_advice.get("secondary_slot_recommendation")) or "Standard secondary"
        secondary_reason = _clean(secondary_advice.get("secondary_advisor_summary"))
        secondary_scores = dict(secondary_advice.get("secondary_class_scores", {}) or {})

    secondary = WeaponBuild(
        weapon_id=secondary_class,
        weapon_name=secondary_label,
        weapon_class=secondary_class,
        reasoning=[secondary_reason] if secondary_reason else [],
        warnings=_split_double_pipe(secondary_advice.get("secondary_advisor_warnings", "")),
        evidence={
            "advisor": "standard_secondary_slot",
            "recommended_secondary_class": secondary_class,
            "secondary_class_scores": secondary_scores,
            "mission_knowledge_bias": loadout_bias,
            "raw_advice": dict(secondary_advice),
        },
    )

    reasoning: list[str] = []
    warnings: list[str] = []

    _append_unique(reasoning, [
        perk_advice.get("perk_recommendation_summary", ""),
        secondary_reason,
        perk_advice.get("equipment_overclock_summary", ""),
        perk_advice.get("scorestreak_recommendation_summary", ""),
        perk_advice.get("playstyle_notes", ""),
    ])
    _append_unique(warnings, legality_notes)
    _append_unique(warnings, _split_double_pipe(perk_advice.get("perk_warnings", "")))
    _append_unique(warnings, _split_double_pipe(perk_advice.get("equipment_overclock_warnings", "")))
    _append_unique(warnings, _split_double_pipe(perk_advice.get("scorestreak_warnings", "")))
    _append_unique(warnings, secondary.warnings)

    confidence = {
        "source": "loadout_lab_deterministic",
        "primary_source": "ttk_oracle_weapon_session",
        "class_source": "loadout_lab_ranked_advisors",
        "within_current_unlocks": True,
    }

    evidence = {
        "source": "loadout_lab",
        "loadout_pairing": loadout_pairing,
        "wildcard_id": wildcard_id,
        "wildcard_name": wildcard_name,
        "perk_package": perk_package,
        "perk_advice": dict(perk_advice),
        "secondary_advice": dict(secondary_advice),
        "mission_knowledge_bias": loadout_bias,
        "challenge_requirements": challenge_requirements,
    }

    return LoadoutBuild(
        primary=primary,
        secondary=secondary,
        wildcard=wildcard_name,
        perks=_perks_from_advice(perk_advice),
        tactical=_clean(perk_advice.get("recommended_tactical")),
        lethal=_clean(perk_advice.get("recommended_lethal")),
        field_upgrade=_clean(perk_advice.get("recommended_field_upgrade")),
        scorestreaks=_scorestreaks_from_advice(perk_advice),
        overclocks=_overclocks_from_advice(perk_advice),
        confidence=confidence,
        reasoning=reasoning,
        warnings=warnings,
        evidence=evidence,
    )


def build_session_brief(
    mission: MissionProfile | Mapping[str, Any],
    *,
    weapon_result: Mapping[str, Any],
    loadout: LoadoutBuild | None = None,
    tactical_context: Mapping[str, Any] | None = None,
) -> SessionBrief:
    """Build the shared SessionBrief consumed by Commander, Oracle and OBS."""
    profile = mission if isinstance(mission, MissionProfile) else MissionProfile.from_mapping(mission)
    weapon_build = WeaponBuild.from_result_mapping(weapon_result)
    inferred = mission_profile_to_oracle_inputs(profile)
    context = inferred.tactical_context()
    context.update(dict(tactical_context or {}))

    if loadout is None:
        loadout = build_loadout_for_session(
            mission=profile,
            inferred=inferred,
            primary=weapon_build,
        )

    advice = build_tactical_advice(
        build_goal=str(context.get("build_goal", inferred.build_goal)),
        fight_type=str(context.get("fight_type", inferred.fight_type)),
        challenge_requirements=str(context.get("challenge_requirements", inferred.challenge.summary)),
        tactical_goal=str(context.get("tactical_goal", inferred.tactical_goal)),
        map_size=str(context.get("map_size", inferred.map_size)),
        playlist_style=str(context.get("playlist_style", inferred.playlist_style)),
        optic_preference=str(context.get("optic_preference", inferred.optic_preference)),
        selected_attachments=weapon_result.get("selected_attachments", []),
    )
    advice = apply_mission_knowledge_to_advice(
        advice,
        inferred.mission_knowledge,
    )
    field_plan = FieldPlan.from_advice_mapping(advice)

    warnings = list(weapon_build.warnings)
    warnings.extend(item for item in loadout.warnings if item not in warnings)
    warnings.extend(item for item in field_plan.warnings if item not in warnings)

    return SessionBrief(
        mission=profile,
        weapon_build=weapon_build,
        loadout=loadout,
        field_plan=field_plan,
        warnings=warnings,
        evidence={
            "architecture_version": "mission_profile_v2",
            "source": "existing_oracle_result",
            "mission_inputs": inferred.to_dict(),
            "mission_knowledge": dict(inferred.mission_knowledge),
            "loadout_lab": dict(loadout.evidence),
        },
    )


def prepare_session_from_mission(
    mission: MissionProfile | Mapping[str, Any],
    *,
    guns: pd.DataFrame | None = None,
    attachments: pd.DataFrame | None = None,
    optimiser_mode: str = "Fast",
    candidate_limit_per_slot: int = 3,
    top_n: int = 1,
) -> SessionBrief:
    """Run the Commander-assigned weapon through Oracle and Loadout Lab.

    Commander mission -> inferred Oracle inputs -> exact weapon build ->
    deterministic Loadout Lab class -> tactical field plan -> SessionBrief.
    """
    profile = mission if isinstance(mission, MissionProfile) else MissionProfile.from_mapping(mission)
    inferred = mission_profile_to_oracle_inputs(profile)

    if guns is None or attachments is None:
        loaded_guns, loaded_attachments = load_ttk_data()
        guns = loaded_guns if guns is None else guns
        attachments = loaded_attachments if attachments is None else attachments

    weapon_session = build_weapon_session(
        guns=guns,
        attachments=attachments,
        weapon_name=profile.weapon_id,
        stats_profile=inferred.stats_profile,
        map_type=inferred.map_type,
        fight_type=inferred.fight_type,
        build_goal=inferred.build_goal,
        enemy_health=inferred.enemy_health,
        attachment_count=inferred.attachment_count,
        top_n=max(1, int(top_n or 1)),
        optimiser_mode=optimiser_mode,
        candidate_limit_per_slot=max(1, int(candidate_limit_per_slot or 1)),
        forced_attachment_rules=list(inferred.challenge.rules),
        attachment_unlock_mode=str(
            profile.constraints.get("attachment_unlock_mode", "current_level")
            or "current_level"
        ),
        target_weapon_level=profile.constraints.get("target_weapon_level"),
    )
    weapon_name = weapon_session.weapon_name
    results = weapon_session.results
    availability = weapon_session.availability

    if results.empty:
        challenge_text = (
            f" Challenge: {inferred.challenge.summary}."
            if inferred.challenge.active
            else ""
        )
        raise ValueError(
            f"No legal build was found for {weapon_name} with "
            f"{inferred.attachment_count} attachment(s).{challenge_text}"
        )

    best = results.iloc[0].to_dict()
    primary_build = WeaponBuild.from_result_mapping(best)
    loadout = build_loadout_for_session(
        mission=profile,
        inferred=inferred,
        primary=primary_build,
    )

    brief = build_session_brief(
        profile,
        weapon_result=best,
        loadout=loadout,
        tactical_context=inferred.tactical_context(),
    )
    brief.evidence["source"] = "mission_exact_weapon_optimiser"
    brief.evidence["optimiser_mode"] = optimiser_mode
    brief.evidence["candidate_limit_per_slot"] = int(candidate_limit_per_slot)
    brief.evidence["candidate_count_returned"] = int(len(results))
    brief.evidence["attachment_availability"] = availability.to_dict()
    brief.evidence["mission_knowledge"] = dict(inferred.mission_knowledge)
    brief.evidence["loadout_lab"] = dict(loadout.evidence)

    for warning in availability.warnings:
        if warning not in brief.warnings:
            brief.warnings.append(warning)

    return brief


__all__ = [
    "build_loadout_for_session",
    "build_session_brief",
    "prepare_session_from_mission",
]

"""Shared exact-weapon optimisation pipeline for Commander and TTK Oracle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from modules.warzone.attachment_availability import (
    AttachmentAvailability,
    filter_attachments_by_unlocks,
)
from modules.warzone.oracle_data import (
    filter_ttk_data_by_profile,
    normalise_match_key,
)
from modules.warzone.weapon_lab import (
    get_compatible_attachments,
    optimise_single_weapon_build,
)


@dataclass(slots=True)
class WeaponSessionResult:
    weapon_name: str
    results: pd.DataFrame
    availability: AttachmentAvailability
    warnings: list[str] = field(default_factory=list)

    @property
    def best(self) -> dict[str, Any]:
        return {} if self.results.empty else self.results.iloc[0].to_dict()

    def evidence(self) -> dict[str, Any]:
        return {
            "weapon_name": self.weapon_name,
            "attachment_availability": self.availability.to_dict(),
            "warnings": list(self.warnings),
            "candidate_count": int(len(self.results)),
        }


def _resolve_weapon_name(guns: pd.DataFrame, requested_weapon: str) -> str:
    key = normalise_match_key(requested_weapon)
    matches = guns[
        guns.apply(
            lambda row: key in {
                normalise_match_key(row.get("gun_id", "")),
                normalise_match_key(row.get("gun_name", "")),
            },
            axis=1,
        )
    ]
    if matches.empty:
        raise ValueError(f"Weapon '{requested_weapon}' was not found in the selected stats profile.")
    return str(matches.iloc[0].get("gun_name", requested_weapon) or requested_weapon)


def _resolve_weapon_row(guns: pd.DataFrame, resolved_weapon_name: str) -> pd.Series:
    key = normalise_match_key(resolved_weapon_name)
    matches = guns[
        guns.apply(
            lambda row: key in {
                normalise_match_key(row.get("gun_id", "")),
                normalise_match_key(row.get("gun_name", "")),
            },
            axis=1,
        )
    ]

    if matches.empty:
        raise ValueError(f"Weapon '{resolved_weapon_name}' was not found after name resolution.")

    return matches.iloc[0]


def _normalised_context_text(*values: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ") for value in values)


def challenge_adjusted_oracle_context(
    *,
    build_goal: str,
    fight_type: str,
    challenge_requirements: str = "",
    weapon_class: str = "",
) -> dict[str, Any]:
    """
    Let explicit camo requirements choose the scoring profile.

    Manual UI choices still matter for ordinary builds, but challenge text wins
    when it says the kill condition is one-shot, longshot, point blank, close
    range, hipfire, or melee. This prevents a one-shot mission accidentally
    being scored as raw "Fastest TTK", where every true one-shot becomes 0 ms.
    """
    original_build_goal = str(build_goal or "").strip() or "Balanced meta build"
    original_fight_type = str(fight_type or "").strip() or "Mixed fights"
    adjusted_build_goal = original_build_goal
    adjusted_fight_type = original_fight_type
    reasons: list[str] = []

    text = _normalised_context_text(challenge_requirements, build_goal, fight_type)
    weapon_class_text = _normalised_context_text(weapon_class)

    is_longshot = "longshot" in text or "long shot" in text
    is_one_shot = "one shot" in text or "one-shot" in text or "one hit" in text
    is_point_blank = "point blank" in text
    is_close = "close range" in text or "close kill" in text or "close-range" in text
    is_hipfire = "hipfire" in text or "hip fire" in text
    is_melee = "melee" in text

    if is_longshot:
        adjusted_build_goal = "Long-range consistency"
        adjusted_fight_type = "Long range"
        reasons.append("Longshot requirement forced Long-range consistency and Long range scoring.")

    elif is_one_shot:
        adjusted_build_goal = "One-shot consistency"
        # One Shot Kills is not automatically a longshot challenge.
        # Preserve the user's chosen fight range so a normal one-shot sniper task
        # does not accidentally test the weapon's max-falloff body damage.
        # Longshots are handled by the explicit longshot branch above.
        reasons.append("One Shot Kills forced One-shot consistency scoring while preserving the selected fight range.")

    elif is_point_blank or is_close or is_hipfire or is_melee:
        adjusted_build_goal = "Aggressive mobility"
        adjusted_fight_type = "Close range"
        reasons.append("Close-range challenge forced close-range aggressive scoring.")

    return {
        "build_goal": adjusted_build_goal,
        "fight_type": adjusted_fight_type,
        "changed": adjusted_build_goal != original_build_goal or adjusted_fight_type != original_fight_type,
        "reasons": reasons,
        "original_build_goal": original_build_goal,
        "original_fight_type": original_fight_type,
    }


def build_weapon_session(
    *,
    guns: pd.DataFrame,
    attachments: pd.DataFrame,
    weapon_name: str,
    stats_profile: str,
    map_type: str,
    fight_type: str,
    build_goal: str,
    enemy_health: int,
    attachment_count: int,
    top_n: int = 1,
    optimiser_mode: str = "Fast",
    candidate_limit_per_slot: int = 3,
    forced_attachment_rules: list[dict] | None = None,
    challenge_requirements: str = "",
    min_attachment_count: int | None = None,
    attachment_count_mode: str = "up_to",
    attachment_unlock_mode: str = "current_level",
    target_weapon_level: int | None = None,
    weapon_levels: pd.DataFrame | None = None,
) -> WeaponSessionResult:
    profile_guns, profile_attachments = filter_ttk_data_by_profile(
        guns=guns,
        attachments=attachments,
        stats_profile=stats_profile,
    )
    resolved_weapon_name = _resolve_weapon_name(profile_guns, weapon_name)
    resolved_weapon = _resolve_weapon_row(profile_guns, resolved_weapon_name)
    compatible_attachments = get_compatible_attachments(
        resolved_weapon,
        profile_attachments,
    )

    oracle_context = challenge_adjusted_oracle_context(
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=challenge_requirements,
        weapon_class=str(resolved_weapon.get("weapon_class", "") or ""),
    )
    effective_build_goal = str(oracle_context.get("build_goal", build_goal) or build_goal)
    effective_fight_type = str(oracle_context.get("fight_type", fight_type) or fight_type)

    eligible_attachments, availability = filter_attachments_by_unlocks(
        attachments=compatible_attachments,
        weapon_name=resolved_weapon_name,
        mode=attachment_unlock_mode,
        target_level=target_weapon_level,
        weapon_levels=weapon_levels,
    )
    results = optimise_single_weapon_build(
        guns=profile_guns,
        attachments=eligible_attachments,
        weapon_name=resolved_weapon_name,
        map_type=map_type,
        fight_type=effective_fight_type,
        build_goal=effective_build_goal,
        enemy_health=int(enemy_health),
        attachment_count=int(attachment_count),
        top_n=max(1, int(top_n or 1)),
        optimiser_mode=optimiser_mode,
        candidate_limit_per_slot=max(1, int(candidate_limit_per_slot or 1)),
        forced_attachment_rules=list(forced_attachment_rules or []),
        min_attachment_count=min_attachment_count,
        attachment_count_mode=attachment_count_mode,
    )
    warnings = list(availability.warnings)
    if oracle_context.get("changed"):
        warnings.extend(str(item) for item in oracle_context.get("reasons", []) if str(item or "").strip())

    if results.empty:
        mode_label = "up-to-budget" if str(attachment_count_mode or "").strip().lower() in {"up_to", "upto", "budget", "best_within_budget", "variable", "auto"} else "exact-count"
        minimum = int(min_attachment_count or 0)
        minimum_text = f" with at least {minimum} attachment(s)" if minimum > 0 else ""
        warnings.append(
            f"No legal {mode_label} build was found for {resolved_weapon_name} using a budget of {attachment_count} attachment(s){minimum_text}."
        )
    return WeaponSessionResult(
        weapon_name=resolved_weapon_name,
        results=results,
        availability=availability,
        warnings=warnings,
    )


__all__ = ["WeaponSessionResult", "build_weapon_session", "challenge_adjusted_oracle_context"]

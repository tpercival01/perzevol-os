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
        fight_type=fight_type,
        build_goal=build_goal,
        enemy_health=int(enemy_health),
        attachment_count=int(attachment_count),
        top_n=max(1, int(top_n or 1)),
        optimiser_mode=optimiser_mode,
        candidate_limit_per_slot=max(1, int(candidate_limit_per_slot or 1)),
        forced_attachment_rules=list(forced_attachment_rules or []),
    )
    warnings = list(availability.warnings)
    if results.empty:
        warnings.append(
            f"No legal {attachment_count}-attachment build was found for {resolved_weapon_name}."
        )
    return WeaponSessionResult(
        weapon_name=resolved_weapon_name,
        results=results,
        availability=availability,
        warnings=warnings,
    )


__all__ = ["WeaponSessionResult", "build_weapon_session"]

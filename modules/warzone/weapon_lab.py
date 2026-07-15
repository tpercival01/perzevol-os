"""Weapon Lab public API.

The implementation remains in ttk_oracle_engine during the compatibility
migration. Callers should import through this module from now on.
"""

from modules.warzone.ttk_oracle_engine import (
    BUILD_GOALS,
    FIGHT_TYPES,
    MAP_TYPES,
    build_base_weapon_rankings,
    get_compatible_attachments,
    describe_weapon_build_data,
    build_ttk_data_warnings,
    build_attachment_verification_rows,
    build_loadout_preview,
    estimate_optimizer_combo_count,
    optimise_single_weapon_build,
    optimise_two_weapon_loadouts_for_scenario,
)

__all__ = [
    "BUILD_GOALS",
    "FIGHT_TYPES",
    "MAP_TYPES",
    "build_base_weapon_rankings",
    "get_compatible_attachments",
    "describe_weapon_build_data",
    "build_ttk_data_warnings",
    "build_attachment_verification_rows",
    "build_loadout_preview",
    "estimate_optimizer_combo_count",
    "optimise_single_weapon_build",
    "optimise_two_weapon_loadouts_for_scenario",
]

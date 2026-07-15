"""Attachment unlock availability for TTK Oracle.

Weapon levels come from ``data/bo7_clean/weapon_prestige.csv``.
Attachment unlock metadata comes from ``attachments.csv``.

Blank unlock metadata is treated as unknown, not locked. This preserves current
behaviour while the unlock dataset is being populated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from modules.warzone.oracle_data import normalise_match_key, numeric_cell


WEAPON_PRESTIGE_PATH = Path("data/bo7_clean/weapon_prestige.csv")

UNLOCK_MODES = {
    "current_level",
    "max_level",
    "target_level",
}


@dataclass(slots=True)
class AttachmentAvailability:
    weapon_name: str
    mode: str
    current_level: int | None
    max_level: int | None
    effective_level: int | None
    eligible_count: int
    locked_count: int
    unknown_count: int
    total_count: int
    level_data_found: bool
    unlock_data_populated: bool
    locked_attachments: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_unlock_columns(attachments: pd.DataFrame) -> pd.DataFrame:
    updated = attachments.copy()

    defaults = {
        "unlock_weapon": "",
        "unlock_level": 0.0,
        "unlock_method": "",
    }

    for column, default in defaults.items():
        if column not in updated.columns:
            updated[column] = default

    updated["unlock_weapon"] = updated["unlock_weapon"].fillna("").astype(str)
    updated["unlock_method"] = updated["unlock_method"].fillna("").astype(str)
    updated["unlock_level"] = updated["unlock_level"].apply(
        lambda value: numeric_cell(value, 0.0)
    )
    return updated


def load_weapon_levels(path: Path = WEAPON_PRESTIGE_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(
            columns=["weapon_class", "weapon", "max_level", "current_level"]
        )

    data = pd.read_csv(path, dtype=str).fillna("")

    for column in ["weapon", "max_level", "current_level"]:
        if column not in data.columns:
            data[column] = ""

    data["_weapon_key"] = data["weapon"].apply(normalise_match_key)
    data["_max_level"] = data["max_level"].apply(
        lambda value: int(numeric_cell(value, 0.0))
    )
    data["_current_level"] = data["current_level"].apply(
        lambda value: int(numeric_cell(value, 0.0))
    )
    return data


def weapon_level_record(
    weapon_name: str,
    weapon_levels: pd.DataFrame,
) -> dict[str, Any] | None:
    if weapon_levels.empty:
        return None

    key = normalise_match_key(weapon_name)
    matches = weapon_levels[weapon_levels["_weapon_key"] == key]

    if matches.empty:
        return None

    row = matches.iloc[0]
    current = int(row.get("_current_level", 0) or 0)
    maximum = int(row.get("_max_level", 0) or 0)

    # Prestige levels can exceed the original Gunsmith unlock cap.
    effective_current = min(current, maximum) if maximum > 0 else current

    return {
        "weapon": str(row.get("weapon", weapon_name) or weapon_name),
        "current_level": current,
        "max_level": maximum,
        "effective_current_level": effective_current,
    }


def _effective_level_for_source(
    *,
    source_weapon: str,
    selected_weapon: str,
    mode: str,
    target_level: int | None,
    weapon_levels: pd.DataFrame,
) -> int | None:
    source = source_weapon or selected_weapon
    record = weapon_level_record(source, weapon_levels)

    if record is None:
        return None

    maximum = int(record.get("max_level", 0) or 0)
    current = int(record.get("effective_current_level", 0) or 0)

    if mode == "max_level":
        return maximum or current

    if (
        mode == "target_level"
        and normalise_match_key(source) == normalise_match_key(selected_weapon)
        and target_level is not None
    ):
        requested = max(0, int(target_level))
        return min(requested, maximum) if maximum > 0 else requested

    return current


def filter_attachments_by_unlocks(
    *,
    attachments: pd.DataFrame,
    weapon_name: str,
    mode: str = "current_level",
    target_level: int | None = None,
    weapon_levels: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, AttachmentAvailability]:
    mode = str(mode or "current_level").strip().lower()
    if mode not in UNLOCK_MODES:
        mode = "current_level"

    data = ensure_unlock_columns(attachments)
    levels = load_weapon_levels() if weapon_levels is None else weapon_levels.copy()

    selected_record = weapon_level_record(weapon_name, levels)
    current_level = (
        int(selected_record["current_level"])
        if selected_record is not None
        else None
    )
    max_level = (
        int(selected_record["max_level"])
        if selected_record is not None
        else None
    )
    selected_effective = _effective_level_for_source(
        source_weapon=weapon_name,
        selected_weapon=weapon_name,
        mode=mode,
        target_level=target_level,
        weapon_levels=levels,
    )

    unlock_data_populated = bool(
        (data["unlock_level"] > 0).any()
        or data["unlock_weapon"].str.strip().ne("").any()
        or data["unlock_method"].str.strip().ne("").any()
    )

    eligible_indices = []
    locked_rows = []
    unknown_count = 0

    non_level_methods = {
        "default",
        "shared",
        "armory",
        "event",
        "challenge",
        "prestige",
        "always_available",
    }

    for index, row in data.iterrows():
        unlock_level = int(numeric_cell(row.get("unlock_level", 0), 0.0))
        unlock_method = str(row.get("unlock_method", "") or "").strip().lower()
        unlock_weapon = str(row.get("unlock_weapon", "") or "").strip()

        if unlock_level <= 0:
            eligible_indices.append(index)
            if not unlock_method and not unlock_weapon:
                unknown_count += 1
            continue

        if unlock_method in non_level_methods and unlock_method != "prestige":
            eligible_indices.append(index)
            continue

        source_level = _effective_level_for_source(
            source_weapon=unlock_weapon or weapon_name,
            selected_weapon=weapon_name,
            mode=mode,
            target_level=target_level,
            weapon_levels=levels,
        )

        if source_level is None:
            # Unknown source levels must not silently remove usable attachments.
            eligible_indices.append(index)
            unknown_count += 1
            continue

        if source_level >= unlock_level:
            eligible_indices.append(index)
            continue

        locked_rows.append(
            {
                "attachment_id": str(row.get("attachment_id", "") or ""),
                "attachment_name": str(row.get("attachment_name", "") or ""),
                "slot": str(row.get("slot", "") or ""),
                "unlock_weapon": unlock_weapon or weapon_name,
                "unlock_level": unlock_level,
                "available_level": source_level,
            }
        )

    filtered = data.loc[eligible_indices].reset_index(drop=True)

    warnings = []
    if selected_record is None:
        warnings.append(
            f"No weapon level record was found for {weapon_name}; unknown unlocks were retained."
        )

    if not unlock_data_populated:
        warnings.append(
            "Attachment unlock metadata is not populated yet. Oracle currently assumes every attachment is available."
        )

    availability = AttachmentAvailability(
        weapon_name=weapon_name,
        mode=mode,
        current_level=current_level,
        max_level=max_level,
        effective_level=selected_effective,
        eligible_count=len(filtered),
        locked_count=len(locked_rows),
        unknown_count=unknown_count,
        total_count=len(data),
        level_data_found=selected_record is not None,
        unlock_data_populated=unlock_data_populated,
        locked_attachments=locked_rows,
        warnings=warnings,
    )

    return filtered, availability


__all__ = [
    "AttachmentAvailability",
    "UNLOCK_MODES",
    "WEAPON_PRESTIGE_PATH",
    "ensure_unlock_columns",
    "filter_attachments_by_unlocks",
    "load_weapon_levels",
    "weapon_level_record",
]

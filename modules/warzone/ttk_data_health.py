"""Lightweight data-health checks for BO7 TTK Oracle CSVs.

This module is deliberately read-only. It does not repair CSV files and it does
not run the optimiser. The page layer can use it to warn when the current
season data is unsafe for exact-build validation.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import pandas as pd

from modules.warzone.oracle_data import (
    ATTACHMENTS_PATH,
    GUNS_PATH,
    normalise_match_key,
    normalise_stats_profile,
    numeric_cell,
)


CONFLICT_COLUMNS = [
    "conflicts_with_slots",
    "conflicts_with_attachment_ids",
    "conflicts_with_name_contains",
]

BLOCKED_ORACLE_STATUSES = {
    "exclude",
    "excluded",
    "invalid",
    "broken",
    "do_not_use",
    "unmodelled",
    "conversion_unmodelled",
}

CONVERSION_NAME_HINTS = {
    "akimbo",
    "slug",
    "dragon's breath",
    "dragons breath",
    "conversion",
    "sweeper rig",
    "titan wield",
    "belt fed",
    "12-gauge masti",
    "12 gauge masti",
    "argus lever",
}

CONVERSION_NOTE_HINTS = {
    "not modelled",
    "unmodelled",
    "conversion",
    "changes damage",
    "changes the damage",
    "pellet",
    "dual wield",
    "separate weapon profile",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalised_text(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean(value).lower())


def _read_csv_shape(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    if not path.exists():
        return [], []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.reader(file))

    if not rows:
        return [], []

    header = rows[0]
    shaped_rows = []

    for line_number, row in enumerate(rows[1:], start=2):
        shaped_rows.append(
            {
                "line_number": line_number,
                "actual_columns": len(row),
                "expected_columns": len(header),
                "row": row,
            }
        )

    return header, shaped_rows


def _read_csv_dataframe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path, dtype=str, keep_default_na=False).fillna("")


def _split_list_cell(value: Any) -> list[str]:
    text = _clean(value)
    if not text:
        return []

    return [
        item.strip()
        for item in re.split(r"[|;]", text)
        if item.strip()
    ]


def _row_matches_weapon(row: pd.Series, gun: pd.Series) -> bool:
    gun_keys = {
        normalise_match_key(gun.get("gun_id", "")),
        normalise_match_key(gun.get("gun_name", "")),
    }
    gun_keys.discard("")

    compatible_guns = _split_list_cell(row.get("compatible_guns", ""))
    compatible_gun_keys = {
        normalise_match_key(item)
        for item in compatible_guns
        if normalise_match_key(item)
    }

    if compatible_gun_keys:
        return bool(gun_keys & compatible_gun_keys)

    gun_class = normalise_match_key(gun.get("weapon_class", ""))
    compatible_classes = {
        normalise_match_key(item)
        for item in _split_list_cell(row.get("compatible_weapon_classes", ""))
        if normalise_match_key(item)
    }

    return bool(gun_class and gun_class in compatible_classes)


def _unlock_is_populated(row: pd.Series) -> bool:
    method = _normalised_text(row.get("unlock_method", "")).replace(" ", "_")
    level = numeric_cell(row.get("unlock_level", 0), 0.0)
    source_weapon = _clean(row.get("unlock_weapon", ""))

    if not method:
        return False

    if method == "weapon_level":
        return bool(source_weapon and level > 0)

    return method in {
        "default",
        "shared",
        "armory",
        "event",
        "challenge",
        "prestige",
    }


def _conversion_risk_reason(row: pd.Series) -> str:
    name = _normalised_text(row.get("attachment_name", ""))
    status = _normalised_text(row.get("verification_status", "")).replace(" ", "_")

    if status in BLOCKED_ORACLE_STATUSES:
        return ""

    name_hits = sorted(hint for hint in CONVERSION_NAME_HINTS if hint in name)

    notes_blob = " ".join(
        _normalised_text(row.get(column, ""))
        for column in [
            "raw_stat_text",
            "verification_notes",
            "damage_profile_notes",
            "attachment_type",
        ]
        if column in row.index
    )
    note_hits = sorted(hint for hint in CONVERSION_NOTE_HINTS if hint in notes_blob)

    if name_hits or note_hits:
        parts = []
        if name_hits:
            parts.append("name hint: " + ", ".join(name_hits))
        if note_hits:
            parts.append("note hint: " + ", ".join(note_hits))
        return " | ".join(parts)

    return ""


def _profile_filter(df: pd.DataFrame, active_stats_profile: str) -> pd.DataFrame:
    if df.empty or "stats_profile" not in df.columns:
        return df.copy()

    target = normalise_stats_profile(active_stats_profile)
    return df[
        df["stats_profile"].apply(lambda value: normalise_stats_profile(value) == target)
    ].copy()


def build_ttk_data_health_report(
    *,
    active_stats_profile: str = "multiplayer",
    guns_path: Path = GUNS_PATH,
    attachments_path: Path = ATTACHMENTS_PATH,
) -> dict[str, Any]:
    """Return read-only CSV health tables for the TTK Oracle page."""
    attachment_header, raw_attachment_rows = _read_csv_shape(attachments_path)
    gun_header, raw_gun_rows = _read_csv_shape(guns_path)

    malformed_rows = []
    for item in raw_attachment_rows:
        if item["actual_columns"] == item["expected_columns"]:
            continue

        row = item["row"]
        name_index = attachment_header.index("attachment_name") if "attachment_name" in attachment_header else -1
        guns_index = attachment_header.index("compatible_guns") if "compatible_guns" in attachment_header else -1

        malformed_rows.append(
            {
                "line_number": item["line_number"],
                "attachment_name": row[name_index] if 0 <= name_index < len(row) else "",
                "compatible_guns": row[guns_index] if 0 <= guns_index < len(row) else "",
                "actual_columns": item["actual_columns"],
                "expected_columns": item["expected_columns"],
            }
        )

    malformed_gun_rows = []
    for item in raw_gun_rows:
        if item["actual_columns"] == item["expected_columns"]:
            continue

        row = item["row"]
        name_index = gun_header.index("gun_name") if "gun_name" in gun_header else -1

        malformed_gun_rows.append(
            {
                "line_number": item["line_number"],
                "gun_name": row[name_index] if 0 <= name_index < len(row) else "",
                "actual_columns": item["actual_columns"],
                "expected_columns": item["expected_columns"],
            }
        )

    guns = _read_csv_dataframe(guns_path)
    attachments = _read_csv_dataframe(attachments_path)

    profile_guns = _profile_filter(guns, active_stats_profile)
    profile_attachments = _profile_filter(attachments, active_stats_profile)

    missing_conflict_columns = [
        column for column in CONFLICT_COLUMNS
        if column not in attachments.columns
    ]

    conversion_risks = []
    if not profile_attachments.empty:
        for _, row in profile_attachments.iterrows():
            reason = _conversion_risk_reason(row)
            if not reason:
                continue

            conversion_risks.append(
                {
                    "attachment_id": _clean(row.get("attachment_id", "")),
                    "attachment_name": _clean(row.get("attachment_name", "")),
                    "compatible_guns": _clean(row.get("compatible_guns", "")),
                    "slot": _clean(row.get("slot", "")),
                    "verification_status": _clean(row.get("verification_status", "")),
                    "reason": reason,
                }
            )

    unlock_coverage = []
    if not profile_guns.empty and not profile_attachments.empty:
        for _, gun in profile_guns.iterrows():
            gun_rows = profile_attachments[
                profile_attachments.apply(lambda row: _row_matches_weapon(row, gun), axis=1)
            ]

            total = int(len(gun_rows))
            if total <= 0:
                unlock_coverage.append(
                    {
                        "gun_name": _clean(gun.get("gun_name", "")),
                        "weapon_class": _clean(gun.get("weapon_class", "")),
                        "attachments": 0,
                        "unlock_populated": 0,
                        "unlock_unknown": 0,
                        "unlock_populated_pct": 0.0,
                        "current_level_reliable": "NO DATA",
                    }
                )
                continue

            populated = int(gun_rows.apply(_unlock_is_populated, axis=1).sum())
            unknown = total - populated
            pct = round((populated / total) * 100, 1)

            unlock_coverage.append(
                {
                    "gun_name": _clean(gun.get("gun_name", "")),
                    "weapon_class": _clean(gun.get("weapon_class", "")),
                    "attachments": total,
                    "unlock_populated": populated,
                    "unlock_unknown": unknown,
                    "unlock_populated_pct": pct,
                    "current_level_reliable": "YES" if pct >= 90 else "PARTIAL" if pct >= 50 else "NO",
                }
            )

    malformed_names = {
        normalise_match_key(row.get("compatible_guns", ""))
        for row in malformed_rows
        if _clean(row.get("compatible_guns", ""))
    }

    unsafe_weapons = []
    if not profile_guns.empty:
        for _, gun in profile_guns.iterrows():
            gun_key = normalise_match_key(gun.get("gun_id", "")) or normalise_match_key(gun.get("gun_name", ""))
            gun_name_key = normalise_match_key(gun.get("gun_name", ""))
            if gun_key in malformed_names or gun_name_key in malformed_names:
                unsafe_weapons.append(_clean(gun.get("gun_name", "")))

    summary = {
        "active_stats_profile": active_stats_profile,
        "gun_rows": len(guns),
        "attachment_rows": len(attachments),
        "malformed_attachment_rows": len(malformed_rows),
        "malformed_gun_rows": len(malformed_gun_rows),
        "conversion_risk_rows": len(conversion_risks),
        "missing_conflict_columns": len(missing_conflict_columns),
        "unsafe_weapons": ", ".join(sorted(set(unsafe_weapons))),
    }

    return {
        "summary": summary,
        "malformed_attachment_rows": pd.DataFrame(malformed_rows),
        "malformed_gun_rows": pd.DataFrame(malformed_gun_rows),
        "conversion_risks": pd.DataFrame(conversion_risks),
        "unlock_coverage": pd.DataFrame(unlock_coverage),
        "missing_conflict_columns": missing_conflict_columns,
    }

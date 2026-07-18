"""Safe CSV repair helpers for BO7 TTK Oracle data.

This module is deliberately conservative. It never guesses missing stats.
It can produce a cleaned attachment CSV by:

- dropping structurally malformed rows
- adding conflict columns when the schema does not have them yet
- marking conversion-style rows as ``conversion_unmodelled``
- adding known cross-slot conflicts such as Parallel Foregrip blocking optics

Use it as a repair/export helper, not as an optimiser.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


CONFLICT_COLUMNS = [
    "conflicts_with_slots",
    "conflicts_with_attachment_ids",
    "conflicts_with_attachment_names",
]

KNOWN_SLOT_CONFLICTS_BY_ATTACHMENT_NAME = {
    "parallel foregrip": "optic",
}

CONVERSION_NAME_HINTS = [
    "dual fire kit",
    "javelin assembly",
    "sweeper rig",
    "wildfire conversion kit",
    "titan wield",
    "12-gauge masti",
    "12 gauge masti",
]

CONVERSION_NOTE_HINTS = [
    "conversion behaviour",
    "conversion-style behaviour",
    "conversion-kit behaviour",
    "changes the weapon damage model",
    "projectile behaviour",
    "projectile behavior",
    "dual-wield",
    "dual wield",
    "belt-fed behavior",
    "belt-fed behaviour",
    "belt fed behavior",
    "belt fed behaviour",
    "alternate-fire",
    "alternate fire",
]


@dataclass(slots=True)
class AttachmentCsvRepairReport:
    source_path: str
    output_path: str
    expected_columns: int
    input_rows: int
    output_rows: int
    dropped_malformed_rows: list[dict[str, Any]] = field(default_factory=list)
    blocked_conversion_rows: list[str] = field(default_factory=list)
    added_conflict_rows: list[str] = field(default_factory=list)
    added_columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "output_path": self.output_path,
            "expected_columns": self.expected_columns,
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "dropped_malformed_rows": self.dropped_malformed_rows,
            "blocked_conversion_rows": self.blocked_conversion_rows,
            "added_conflict_rows": self.added_conflict_rows,
            "added_columns": self.added_columns,
        }


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean(value).lower()).strip()


def _append_unique_pipe(existing: Any, addition: str) -> str:
    addition = _clean(addition)
    if not addition:
        return _clean(existing)

    parts = [
        item.strip()
        for item in re.split(r"[|,;]", _clean(existing))
        if item.strip()
    ]

    if addition not in parts:
        parts.append(addition)

    return " | ".join(parts)


def row_should_be_blocked_as_conversion(row: dict[str, Any]) -> bool:
    name = _key(row.get("attachment_name", ""))
    notes = _key(row.get("verification_notes", ""))
    status = _key(row.get("verification_status", ""))

    if status in {"conversion unmodelled", "unmodelled", "exclude", "excluded"}:
        return False

    if any(hint in name for hint in CONVERSION_NAME_HINTS):
        return True

    return any(hint in notes for hint in CONVERSION_NOTE_HINTS)


def repair_attachment_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, AttachmentCsvRepairReport]:
    repaired = df.copy().fillna("")
    added_columns: list[str] = []

    for column in CONFLICT_COLUMNS:
        if column not in repaired.columns:
            repaired[column] = ""
            added_columns.append(column)

    blocked_conversion_rows: list[str] = []
    added_conflict_rows: list[str] = []

    for index, row in repaired.iterrows():
        row_dict = row.to_dict()
        attachment_name = _clean(row_dict.get("attachment_name", ""))

        if row_should_be_blocked_as_conversion(row_dict):
            repaired.at[index, "verification_status"] = "conversion_unmodelled"
            note = _clean(repaired.at[index, "verification_notes"])
            guard_note = "Blocked by CSV repair: conversion or alternate-fire behaviour is not safely modelled."
            repaired.at[index, "verification_notes"] = (
                note if guard_note in note else f"{note} {guard_note}".strip()
            )
            blocked_conversion_rows.append(attachment_name)

        conflict_slots = KNOWN_SLOT_CONFLICTS_BY_ATTACHMENT_NAME.get(_key(attachment_name), "")
        if conflict_slots:
            repaired.at[index, "conflicts_with_slots"] = _append_unique_pipe(
                repaired.at[index, "conflicts_with_slots"],
                conflict_slots,
            )
            added_conflict_rows.append(attachment_name)

    report = AttachmentCsvRepairReport(
        source_path="",
        output_path="",
        expected_columns=len(df.columns),
        input_rows=len(df),
        output_rows=len(repaired),
        added_columns=added_columns,
        blocked_conversion_rows=blocked_conversion_rows,
        added_conflict_rows=added_conflict_rows,
    )

    return repaired, report


def load_well_formed_attachment_rows(path: Path | str) -> tuple[pd.DataFrame, list[dict[str, Any]], int, int]:
    source_path = Path(path)

    with source_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        rows = list(reader)

    if not rows:
        return pd.DataFrame(), [], 0, 0

    header = rows[0]
    expected_columns = len(header)
    good_rows = []
    malformed_rows: list[dict[str, Any]] = []

    for line_number, row in enumerate(rows[1:], start=2):
        if len(row) == expected_columns:
            good_rows.append(row)
            continue

        malformed_rows.append(
            {
                "line_number": line_number,
                "actual_columns": len(row),
                "expected_columns": expected_columns,
                "attachment_id": row[0] if len(row) > 0 else "",
                "attachment_name": row[1] if len(row) > 1 else "",
            }
        )

    return (
        pd.DataFrame(good_rows, columns=header).fillna(""),
        malformed_rows,
        expected_columns,
        len(rows) - 1,
    )


def build_clean_attachment_dataframe(path: Path | str) -> tuple[pd.DataFrame, AttachmentCsvRepairReport]:
    source_path = Path(path)
    df, malformed_rows, expected_columns, input_rows = load_well_formed_attachment_rows(source_path)
    repaired, report = repair_attachment_dataframe(df)

    report.source_path = str(source_path)
    report.expected_columns = expected_columns
    report.input_rows = input_rows
    report.output_rows = len(repaired)
    report.dropped_malformed_rows = malformed_rows

    return repaired, report


def write_clean_attachments_csv(
    source_path: Path | str,
    output_path: Path | str,
) -> AttachmentCsvRepairReport:
    repaired, report = build_clean_attachment_dataframe(source_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    repaired.to_csv(output, index=False)
    report.output_path = str(output)
    return report

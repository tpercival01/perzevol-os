"""Attachment import and Codmunity HTML parsing for TTK Oracle.

This module performs schema translation only. It does not score builds or
calculate weapon performance.
"""

from __future__ import annotations

import re

import pandas as pd

from modules.warzone.oracle_data import (
    ATTACHMENT_NUMERIC_COLUMNS,
    DEFAULT_STATS_PROFILE,
    EXTENDED_ATTACHMENT_COLUMNS,
    ensure_attachment_columns,
    normalise_stats_profile,
    numeric_cell,
    slugify,
    strip_html,
)


CODMUNITY_STAT_MAP = {
    "ads speed": "ads_pct",
    "sprint to fire": "sprint_to_fire_pct",
    "sprint to fire speed": "sprint_to_fire_pct",
    "reload speed": "reload_pct",
    "jump ads": "jump_ads_pct",
    "jump sprint to fire speed": "jump_sprint_to_fire_pct",
    "slide to fire": "slide_to_fire_pct",
    "slide to fire speed": "slide_to_fire_pct",
    "dive to fire": "dive_to_fire_pct",
    "dive to fire speed": "dive_to_fire_pct",
    "bullet velocity": "bullet_velocity_pct",
    "horizontal recoil": "horizontal_recoil_pct",
    "vertical recoil": "vertical_recoil_pct",
    "gun kick": "gun_kick_pct",
    "first shot recoil scale": "first_shot_recoil_pct",
    "kick reset speed": "kick_reset_speed_pct",
    "magazine size": "mag_size_add",
    "range": "range_pct",
    "damage": "damage_pct",
    "fire rate": "fire_rate_pct",
    "rpm": "fire_rate_pct",
    "movement": "movement_pct",
    "sprint": "sprint_pct",
    "crouch movement": "crouch_movement_pct",
    "ads movement": "ads_movement_pct",
    "flinch resistance": "flinch_resistance_pct",
    "hipfire spread": "hipfire_spread_pct",
    "jump hipfire spread": "jump_hipfire_spread_pct",
    "slide hipfire spread": "slide_hipfire_spread_pct",
    "dive hipfire spread": "dive_hipfire_spread_pct",
    "mags": "mags_add",
}

def normalise_codmunity_stat_label(label: str) -> str:
    label = strip_html(label).lower()
    label = re.sub(r"\s+", " ", label)
    return label.strip()

def apply_codmunity_stat_to_attachment_row(row: dict, value: str, label: str):
    clean_label = normalise_codmunity_stat_label(label)
    column = CODMUNITY_STAT_MAP.get(clean_label)

    if not column:
        return

    row[column] = numeric_cell(value, 0.0)

def parse_codmunity_attachment_html(
    html_text: str,
    compatible_weapon_classes: str = "",
    compatible_guns: str = "",
    source: str = "codmunity.gg",
    source_date: str = "",
    stats_profile: str = DEFAULT_STATS_PROFILE,
) -> pd.DataFrame:
    """
    Parses copied Codmunity attachment-table HTML into Oracle attachment rows.

    This is designed for data entry, not blind trust. Parsed rows should be
    spot-checked against one or two in-game expanded-stat screenshots before
    they are appended to the master CSV.
    """
    rows = []
    html_text = str(html_text or "")
    stats_profile = normalise_stats_profile(stats_profile, DEFAULT_STATS_PROFILE)

    for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html_text, flags=re.I | re.S):
        name_match = re.search(
            r'class="[^"]*attachment-name[^"]*"[^>]*>(.*?)</span>',
            row_html,
            flags=re.I | re.S,
        )
        slot_match = re.search(
            r'class="[^"]*slot[^"]*"[^>]*>(.*?)</span>',
            row_html,
            flags=re.I | re.S,
        )

        if not name_match or not slot_match:
            continue

        attachment_name = strip_html(name_match.group(1))
        slot = strip_html(slot_match.group(1))

        label_match = re.search(
            r'class="[^"]*label[^"]*"[^>]*>(.*?)</span>',
            row_html,
            flags=re.I | re.S,
        )
        unlock_match = re.search(
            r'class="[^"]*unlock[^"]*"[^>]*>(.*?)</span>',
            row_html,
            flags=re.I | re.S,
        )

        label = strip_html(label_match.group(1)) if label_match else ""
        unlock = strip_html(unlock_match.group(1)) if unlock_match else ""

        attachment_row = {
            column: 0.0 if column in ATTACHMENT_NUMERIC_COLUMNS else ""
            for column in EXTENDED_ATTACHMENT_COLUMNS
        }

        attachment_row.update({
            "attachment_id": slugify(f"{normalise_stats_profile(stats_profile, DEFAULT_STATS_PROFILE)}_{compatible_guns or compatible_weapon_classes}_{attachment_name}"),
            "attachment_name": attachment_name,
            "slot": slot,
            "stats_profile": normalise_stats_profile(stats_profile, DEFAULT_STATS_PROFILE),
            "compatible_weapon_classes": compatible_weapon_classes,
            "compatible_guns": compatible_guns,
            "source": source,
            "source_date": source_date,
            "verification_status": "needs_verification",
            "verification_notes": f"Label: {label}. Unlock: {unlock}.".strip(),
        })

        raw_stat_parts = []

        stat_items = re.findall(
            r'class="[^"]*attachment-stats-item[^"]*"[^>]*>(.*?)</div>',
            row_html,
            flags=re.I | re.S,
        )

        for stat_html in stat_items:
            highlight_match = re.search(
                r'class="[^"]*highlight[^"]*"[^>]*>(.*?)</span>',
                stat_html,
                flags=re.I | re.S,
            )

            if not highlight_match:
                continue

            value = strip_html(highlight_match.group(1))
            label_html = re.sub(
                r'<span[^>]*class="[^"]*highlight[^"]*"[^>]*>.*?</span>',
                " ",
                stat_html,
                flags=re.I | re.S,
            )
            stat_label = strip_html(label_html)

            if value and stat_label:
                raw_stat_parts.append(f"{value} {stat_label}")
                apply_codmunity_stat_to_attachment_row(
                    attachment_row,
                    value=value,
                    label=stat_label,
                )

        attachment_row["raw_stat_text"] = " | ".join(raw_stat_parts)

        rows.append(attachment_row)

    if not rows:
        return pd.DataFrame(columns=EXTENDED_ATTACHMENT_COLUMNS)

    dataframe = pd.DataFrame(rows)

    return ensure_attachment_columns(dataframe)[EXTENDED_ATTACHMENT_COLUMNS]

__all__ = [
    "CODMUNITY_STAT_MAP",
    "apply_codmunity_stat_to_attachment_row",
    "normalise_codmunity_stat_label",
    "parse_codmunity_attachment_html",
]

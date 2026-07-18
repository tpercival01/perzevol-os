"""Meta baseline loadouts for BO7 TTK Oracle.

Stores manually entered community/meta builds so the Oracle can compare its
modelled optimum against known season builds. This module does not optimise
attachments. It only owns CSV persistence and matching.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

import pandas as pd


TTK_DATA_DIR = Path("data/bo7_ttk")
META_LOADOUTS_PATH = TTK_DATA_DIR / "meta_loadouts.csv"

ATTACHMENT_FIELD_COUNT = 8

META_LOADOUT_COLUMNS = [
    "meta_loadout_id",
    "loadout_name",
    "source",
    "stats_profile",
    "weapon_id",
    "weapon_name",
    "challenge_tag",
    "enemy_health",
    "attachment_1",
    "attachment_2",
    "attachment_3",
    "attachment_4",
    "attachment_5",
    "attachment_6",
    "attachment_7",
    "attachment_8",
    "notes",
    "created_at",
    "updated_at",
    "verification_status",
]


def clean(value: Any) -> str:
    return str(value or "").strip()


def slugify(value: Any) -> str:
    text = clean(value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def attachment_fields() -> list[str]:
    return [f"attachment_{index}" for index in range(1, ATTACHMENT_FIELD_COUNT + 1)]


def normalise_meta_challenge_tag(value: Any) -> str:
    text = clean(value)

    if not text or text.lower() in {"no challenge", "no challenge / best ttk", "best ttk"}:
        return "best_ttk"

    return slugify(text)


def ensure_meta_loadout_columns(data: pd.DataFrame) -> pd.DataFrame:
    updated = data.copy()

    for column in META_LOADOUT_COLUMNS:
        if column not in updated.columns:
            updated[column] = ""

    updated = updated[META_LOADOUT_COLUMNS].copy()

    for column in META_LOADOUT_COLUMNS:
        updated[column] = updated[column].fillna("").astype(str)

    updated["challenge_tag"] = updated["challenge_tag"].apply(normalise_meta_challenge_tag)
    updated["stats_profile"] = updated["stats_profile"].apply(slugify)
    updated["weapon_id"] = updated["weapon_id"].apply(slugify)

    return updated


def load_meta_loadouts(path: Path = META_LOADOUTS_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=META_LOADOUT_COLUMNS)

    try:
        data = pd.read_csv(path, dtype=str).fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=META_LOADOUT_COLUMNS)

    return ensure_meta_loadout_columns(data)


def save_meta_loadouts(data: pd.DataFrame, path: Path = META_LOADOUTS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_meta_loadout_columns(data).to_csv(path, index=False)


def build_meta_loadout_id(
    *,
    stats_profile: Any,
    weapon_id: Any,
    weapon_name: Any,
    challenge_tag: Any,
    enemy_health: Any,
    loadout_name: Any,
) -> str:
    weapon_key = slugify(weapon_id) or slugify(weapon_name)
    health_key = clean(enemy_health) or "health_unknown"
    return slugify(
        "_".join(
            [
                "meta",
                slugify(stats_profile) or "profile",
                weapon_key or "weapon",
                normalise_meta_challenge_tag(challenge_tag),
                health_key,
                slugify(loadout_name) or "loadout",
            ]
        )
    )


def upsert_meta_loadout(loadout: dict[str, Any], path: Path = META_LOADOUTS_PATH) -> pd.DataFrame:
    data = load_meta_loadouts(path)
    now = datetime.now().isoformat(timespec="seconds")

    row = {column: clean(loadout.get(column, "")) for column in META_LOADOUT_COLUMNS}
    row["stats_profile"] = slugify(row.get("stats_profile", ""))
    row["weapon_id"] = slugify(row.get("weapon_id", ""))
    row["challenge_tag"] = normalise_meta_challenge_tag(row.get("challenge_tag", ""))
    row["updated_at"] = now

    if not row.get("created_at"):
        row["created_at"] = now

    if not row.get("verification_status"):
        row["verification_status"] = "manual"

    if not row.get("meta_loadout_id"):
        row["meta_loadout_id"] = build_meta_loadout_id(
            stats_profile=row.get("stats_profile", ""),
            weapon_id=row.get("weapon_id", ""),
            weapon_name=row.get("weapon_name", ""),
            challenge_tag=row.get("challenge_tag", ""),
            enemy_health=row.get("enemy_health", ""),
            loadout_name=row.get("loadout_name", ""),
        )

    if data.empty:
        updated = pd.DataFrame([row], columns=META_LOADOUT_COLUMNS)
    else:
        mask = data["meta_loadout_id"].astype(str).eq(row["meta_loadout_id"])
        if mask.any():
            data.loc[mask, META_LOADOUT_COLUMNS] = [row[column] for column in META_LOADOUT_COLUMNS]
            updated = data
        else:
            updated = pd.concat(
                [data, pd.DataFrame([row], columns=META_LOADOUT_COLUMNS)],
                ignore_index=True,
            )

    save_meta_loadouts(updated, path)
    return updated


def loadout_attachment_values(row: Any) -> list[str]:
    if isinstance(row, pd.Series):
        getter = row.get
    elif isinstance(row, dict):
        getter = row.get
    else:
        getter = lambda key, default="": ""

    values = []

    for field in attachment_fields():
        value = clean(getter(field, ""))
        if value:
            values.append(value)

    return values


def matching_meta_loadouts(
    data: pd.DataFrame,
    *,
    stats_profile: Any,
    weapon_id: Any = "",
    weapon_name: Any = "",
    challenge_tag: Any = "",
    enemy_health: Any = "",
) -> pd.DataFrame:
    if data.empty:
        return data.copy()

    working = ensure_meta_loadout_columns(data)
    profile_key = slugify(stats_profile)
    weapon_id_key = slugify(weapon_id)
    weapon_name_key = slugify(weapon_name)
    challenge_key = normalise_meta_challenge_tag(challenge_tag)
    health_key = clean(enemy_health)

    mask = working["stats_profile"].eq(profile_key)

    if weapon_id_key:
        mask &= working["weapon_id"].eq(weapon_id_key)
    elif weapon_name_key:
        mask &= working["weapon_name"].apply(slugify).eq(weapon_name_key)

    if challenge_key:
        mask &= working["challenge_tag"].isin({challenge_key, "any", ""})

    if health_key:
        mask &= working["enemy_health"].astype(str).isin({health_key, ""})

    return working[mask].reset_index(drop=True)

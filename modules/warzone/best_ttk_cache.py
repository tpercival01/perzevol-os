"""Persistent BEST TTK cache for the Warzone TTK Oracle.

This module is intentionally small and data-only. It keeps the Streamlit page
from owning cache serialisation, cache keys and cached session wrappers.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from modules.warzone.oracle_data import ATTACHMENTS_PATH, GUNS_PATH


STATE_DIR = Path("data/bo7_state")
BEST_TTK_CACHE_DIR = STATE_DIR / "best_ttk_cache"
BEST_TTK_CACHE_VERSION = "best_ttk_exact_pareto_v3"


class CachedAvailability:
    def __init__(self, data: dict | None = None):
        self._data = dict(data or {})

    def to_dict(self) -> dict:
        return dict(self._data)

    def __getattr__(self, name: str):
        return self._data.get(name, "")


class CachedWeaponSession:
    def __init__(
        self,
        *,
        weapon_name: str,
        results: pd.DataFrame,
        availability: dict | CachedAvailability | None = None,
        warnings: list[str] | None = None,
        cache_status: str = "",
        cache_key: str = "",
    ):
        self.weapon_name = weapon_name
        self.results = results
        if isinstance(availability, CachedAvailability):
            self.availability = availability
        else:
            self.availability = CachedAvailability(availability)
        self.warnings = list(warnings or [])
        self.cache_status = cache_status
        self.cache_key = cache_key


def _path_stamp(path: Path) -> dict:
    try:
        stat = path.stat()
        return {
            "path": str(path),
            "mtime_ns": int(stat.st_mtime_ns),
            "size": int(stat.st_size),
        }
    except FileNotFoundError:
        return {
            "path": str(path),
            "missing": True,
        }


def _json_safe(value: Any):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, pd.Series):
        return value.to_dict()
    return str(value)


def best_ttk_cache_key(
    *,
    selected_weapon: str,
    build_goal: str,
    fight_type: str,
    map_type: str,
    challenge_summary: str,
    challenge_rules: list[dict],
    min_attachment_count: int,
    attachment_unlock_mode: str,
    stats_profile: str,
    enemy_health: int,
    guns_path: Path = GUNS_PATH,
    attachments_path: Path = ATTACHMENTS_PATH,
    attachment_count: int = 8,
    attachment_count_mode: str = "up_to",
) -> str:
    payload = {
        "version": BEST_TTK_CACHE_VERSION,
        "stats_profile": stats_profile,
        "weapon": selected_weapon,
        "build_goal": build_goal,
        "fight_type": fight_type,
        "map_type": map_type,
        "enemy_health": int(enemy_health or 0),
        "attachment_count": int(attachment_count or 0),
        "attachment_count_mode": attachment_count_mode,
        "min_attachment_count": int(min_attachment_count or 0),
        "attachment_unlock_mode": attachment_unlock_mode,
        "challenge_summary": challenge_summary,
        "challenge_rules": challenge_rules or [],
        "guns_stamp": _path_stamp(guns_path),
        "attachments_stamp": _path_stamp(attachments_path),
    }
    raw = json.dumps(payload, sort_keys=True, default=_json_safe)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_best_ttk_cache(cache_key: str) -> CachedWeaponSession | None:
    path = BEST_TTK_CACHE_DIR / f"{cache_key}.json"

    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        results = pd.DataFrame(payload.get("results", []))
        if results.empty:
            return None

        return CachedWeaponSession(
            weapon_name=payload.get("weapon_name", ""),
            results=results,
            availability=payload.get("availability", {}),
            warnings=payload.get("warnings", []),
            cache_status="HIT",
            cache_key=cache_key,
        )
    except Exception:
        return None


def save_best_ttk_cache(cache_key: str, session) -> None:
    results = getattr(session, "results", pd.DataFrame())

    if results is None or results.empty:
        return

    availability = {}
    if getattr(session, "availability", None) is not None:
        try:
            availability = session.availability.to_dict()
        except Exception:
            availability = {}

    payload = {
        "cache_key": cache_key,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "weapon_name": getattr(session, "weapon_name", ""),
        "availability": availability,
        "warnings": list(getattr(session, "warnings", []) or []),
        "results": json.loads(results.to_json(orient="records")),
    }

    BEST_TTK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (BEST_TTK_CACHE_DIR / f"{cache_key}.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def wrap_best_ttk_session(session, *, cache_status: str, cache_key: str) -> CachedWeaponSession:
    availability = {}
    if getattr(session, "availability", None) is not None:
        try:
            availability = session.availability.to_dict()
        except Exception:
            availability = {}

    return CachedWeaponSession(
        weapon_name=getattr(session, "weapon_name", ""),
        results=getattr(session, "results", pd.DataFrame()),
        availability=availability,
        warnings=list(getattr(session, "warnings", []) or []),
        cache_status=cache_status,
        cache_key=cache_key,
    )


def clear_best_ttk_cache() -> int:
    if not BEST_TTK_CACHE_DIR.exists():
        return 0

    removed = 0
    for cache_file in BEST_TTK_CACHE_DIR.glob("*.json"):
        cache_file.unlink()
        removed += 1

    return removed

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(slots=True)
class MissionProfile:
    """Commander-owned description of the current gameplay mission."""

    mode: str
    weapon_id: str
    target: str = ""
    challenge_type: str = ""
    challenge_name: str = ""
    remaining: int | None = None
    stats_profile: str = "multiplayer"
    session_id: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    preferences: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MissionProfile":
        return cls(
            mode=str(value.get("mode", "multiplayer") or "multiplayer"),
            weapon_id=str(value.get("weapon_id", value.get("weapon", "")) or ""),
            target=str(value.get("target", "") or ""),
            challenge_type=str(value.get("challenge_type", value.get("challenge", "")) or ""),
            challenge_name=str(value.get("challenge_name", "") or ""),
            remaining=_optional_int(value.get("remaining")),
            stats_profile=str(value.get("stats_profile", value.get("mode", "multiplayer")) or "multiplayer"),
            session_id=str(value.get("session_id", "") or ""),
            constraints=dict(value.get("constraints", {}) or {}),
            preferences=dict(value.get("preferences", {}) or {}),
            metadata=dict(value.get("metadata", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WeaponBuild:
    weapon_id: str
    weapon_name: str
    weapon_class: str = ""
    attachments: list[str] = field(default_factory=list)
    slots: list[str] = field(default_factory=list)
    raw_ttk_ms: float | None = None
    practical_ttk_ms: float | None = None
    oracle_score: float | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, Any] = field(default_factory=dict)
    reasoning: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result_mapping(cls, value: Mapping[str, Any]) -> "WeaponBuild":
        return cls(
            weapon_id=str(value.get("gun_id", value.get("weapon_id", "")) or ""),
            weapon_name=str(value.get("gun_name", value.get("weapon_name", "")) or ""),
            weapon_class=str(value.get("weapon_class", "") or ""),
            attachments=_split_pipe(value.get("attachments", "")),
            slots=_split_pipe(value.get("slots", "")),
            raw_ttk_ms=_optional_float(value.get("raw_ttk_ms")),
            practical_ttk_ms=_optional_float(value.get("practical_ttk_ms")),
            oracle_score=_optional_float(value.get("oracle_score")),
            stats=dict(value),
            reasoning=_split_double_pipe(value.get("selected_attachment_notes", "")),
            warnings=_split_double_pipe(value.get("warnings", "")),
            evidence=_json_mapping(value.get("lab_evidence_json", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LoadoutBuild:
    primary: WeaponBuild
    secondary: WeaponBuild | None = None
    wildcard: str = ""
    perks: list[str] = field(default_factory=list)
    tactical: str = ""
    lethal: str = ""
    field_upgrade: str = ""
    scorestreaks: list[str] = field(default_factory=list)
    overclocks: dict[str, str] = field(default_factory=dict)
    confidence: dict[str, Any] = field(default_factory=dict)
    reasoning: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FieldPlan:
    recommended_modes: list[str] = field(default_factory=list)
    avoid_modes: list[str] = field(default_factory=list)
    map_size: str = ""
    playstyle: str = ""
    engagement_range: str = ""
    priorities: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    estimated_minutes: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_advice_mapping(cls, value: Mapping[str, Any]) -> "FieldPlan":
        return cls(
            recommended_modes=list(value.get("recommended_modes", []) or []),
            avoid_modes=list(value.get("avoid_modes", []) or []),
            map_size=str(value.get("map_size", "") or ""),
            playstyle=str(value.get("playstyle", "") or ""),
            engagement_range=str(value.get("engagement_range", "") or ""),
            priorities=list(value.get("priorities", []) or []),
            notes=_split_double_pipe(value.get("notes", "")),
            warnings=list(value.get("warnings", []) or []),
            estimated_minutes=_optional_int(value.get("estimated_minutes")),
            evidence=dict(value.get("evidence", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SessionBrief:
    mission: MissionProfile
    weapon_build: WeaponBuild
    loadout: LoadoutBuild | None = None
    field_plan: FieldPlan | None = None
    confidence: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _split_pipe(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.split("|") if item.strip()]


def _split_double_pipe(value: Any) -> list[str]:
    text = str(value or "").strip()
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


import json

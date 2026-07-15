"""Pure BO7 challenge constraints for TTK Oracle.

This module contains no Streamlit code and no optimiser maths. It translates a
camo requirement into hard attachment rules and attachment-count constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field


CHALLENGE_REQUIREMENT_OPTIONS = [
    "Any suppressor",
    "Underbarrel launcher",
    "4.0x+ optic",
    "Any optic / reticle",
    "Specific attachment name contains",
    "5+ attachments",
    "8 attachments",
]

CHALLENGE_ROLE_SCOPES = [
    "Primary weapon",
    "Secondary weapon",
    "Both weapons",
]


@dataclass(frozen=True)
class ChallengeConstraints:
    requirement: str = ""
    rules: list[dict] = field(default_factory=list)
    required_attachment_count: int = 0
    summary: str = ""
    role_scope: str = "Both weapons"

    @property
    def active(self) -> bool:
        return bool(self.rules or self.required_attachment_count)


def challenge_rules_from_selection(
    requirement: str,
    custom_text: str = "",
) -> list[dict]:
    requirement = str(requirement or "").strip()
    custom_text = str(custom_text or "").strip()

    if requirement == "Any suppressor":
        return [
            {
                "label": "Challenge lock: any suppressor",
                "slot": "muzzle",
                "name_contains_any": ["suppressor", "supressor"],
            }
        ]

    if requirement == "Underbarrel launcher":
        return [
            {
                "label": "Challenge lock: underbarrel launcher",
                "slot": "underbarrel",
                "attachment_type": "underbarrel_launcher",
            }
        ]

    if requirement == "4.0x+ optic":
        return [
            {
                "label": "Challenge lock: 4.0x+ optic",
                "slot": "optic",
                "min_optic_zoom": 4.0,
            }
        ]

    if requirement == "Any optic / reticle":
        return [
            {
                "label": "Challenge lock: any optic / reticle",
                "slot": "optic",
            }
        ]

    if requirement == "Specific attachment name contains" and custom_text:
        return [
            {
                "label": f"Challenge lock: {custom_text}",
                "name_contains_any": [custom_text],
            }
        ]

    return []


def challenge_required_attachment_count(requirement: str) -> int:
    requirement = str(requirement or "").strip()

    if requirement == "8 attachments":
        return 8

    if requirement == "5+ attachments":
        return 5

    return 0


def challenge_requires_eight_attachments(requirement: str) -> bool:
    return challenge_required_attachment_count(requirement) == 8


def challenge_summary(
    requirement: str,
    rules: list[dict] | None = None,
    required_attachment_count: int | None = None,
) -> str:
    rules = list(rules or challenge_rules_from_selection(requirement))
    required_count = (
        challenge_required_attachment_count(requirement)
        if required_attachment_count is None
        else int(required_attachment_count or 0)
    )

    if required_count == 8:
        return "Challenge lock: 8 attachments"

    if required_count > 0:
        return f"Challenge lock: {required_count}+ attachments"

    if rules:
        return " | ".join(
            str(rule.get("label", "Challenge lock"))
            for rule in rules
        )

    return "Challenge lock active, but no usable requirement has been entered."


def build_challenge_constraints(
    requirement: str,
    custom_text: str = "",
    role_scope: str = "Both weapons",
) -> ChallengeConstraints:
    rules = challenge_rules_from_selection(requirement, custom_text)
    required_count = challenge_required_attachment_count(requirement)

    return ChallengeConstraints(
        requirement=str(requirement or "").strip(),
        rules=rules,
        required_attachment_count=required_count,
        summary=challenge_summary(
            requirement,
            rules=rules,
            required_attachment_count=required_count,
        ),
        role_scope=str(role_scope or "Both weapons").strip() or "Both weapons",
    )


def split_challenge_rules_by_scope(
    rules: list[dict],
    role_scope: str,
) -> tuple[list[dict], list[dict]]:
    role_scope = str(role_scope or "").strip()

    if not rules:
        return [], []

    if role_scope == "Primary weapon":
        return list(rules), []

    if role_scope == "Secondary weapon":
        return [], list(rules)

    return list(rules), list(rules)


def apply_attachment_count_requirement(
    current_count: int,
    required_attachment_count: int,
) -> int:
    try:
        current = int(current_count or 0)
    except (TypeError, ValueError):
        current = 0

    try:
        required = int(required_attachment_count or 0)
    except (TypeError, ValueError):
        required = 0

    return max(current, required)


__all__ = [
    "CHALLENGE_REQUIREMENT_OPTIONS",
    "CHALLENGE_ROLE_SCOPES",
    "ChallengeConstraints",
    "apply_attachment_count_requirement",
    "build_challenge_constraints",
    "challenge_required_attachment_count",
    "challenge_requires_eight_attachments",
    "challenge_rules_from_selection",
    "challenge_summary",
    "split_challenge_rules_by_scope",
]

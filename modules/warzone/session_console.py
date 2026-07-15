"""Streamlit operations console for Commander-driven Oracle sessions."""

from __future__ import annotations

from typing import Any, Mapping

import streamlit as st

from modules.warzone.oracle_models import MissionProfile, SessionBrief


MISSION_CHALLENGE_PRESETS = {
    "Military headshots": "Get 80 total Headshots",
    "Underbarrel launcher kills": "Get 20 Kills with an Underbarrel Launcher Attachment equipped",
    "Suppressor kills": "With a Suppressor Attachment equipped: get 50 Eliminations",
    "4.0x+ optic kills": "With a 4.0x+ magnification scope equipped: get 50 Eliminations",
    "Gunfighter / 8 attachments": "With the Gunfighter Wildcard: get 50 Elims with 8 Attachments",
    "Objective kills": "Get 30 Objective Kills",
    "Hipfire kills": "Get 30 Hipfire Kills",
    "Longshots": "Get 15 Long Shot Medals",
    "Custom": "",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _mission_knowledge_from_brief(brief: SessionBrief) -> dict[str, Any]:
    evidence = brief.evidence if isinstance(brief.evidence, Mapping) else {}
    mission_knowledge = dict(evidence.get("mission_knowledge", {}) or {})
    if mission_knowledge:
        return mission_knowledge

    mission_inputs = evidence.get("mission_inputs", {}) or {}
    if isinstance(mission_inputs, Mapping):
        return dict(mission_inputs.get("mission_knowledge", {}) or {})

    return {}


def build_manual_mission_profile(
    *,
    weapon_id: str,
    target: str,
    challenge_name: str,
    remaining: int | None,
    stats_profile: str,
    enemy_health: int,
    attachment_count: int,
) -> MissionProfile:
    return MissionProfile(
        mode=stats_profile,
        stats_profile=stats_profile,
        weapon_id=weapon_id,
        target=target,
        challenge_name=challenge_name,
        remaining=remaining,
        constraints={
            "enemy_health": int(enemy_health),
            "attachment_count": int(attachment_count),
        },
        metadata={"source": "oracle_operations_console"},
    )


def render_session_brief(brief: SessionBrief) -> None:
    mission = brief.mission
    weapon = brief.weapon_build
    loadout = brief.loadout
    field_plan = brief.field_plan

    st.markdown("## SESSION BRIEF")
    st.caption("Commander mission translated into an exact weapon build, Loadout Lab class, and field plan.")

    mission_cols = st.columns(4)
    mission_cols[0].metric("Weapon", weapon.weapon_name or mission.weapon_id)
    mission_cols[1].metric("Target", mission.target or "Current challenge")
    mission_cols[2].metric("Remaining", mission.remaining if mission.remaining is not None else "Not set")
    mission_cols[3].metric(
        "Oracle score",
        f"{weapon.oracle_score:.3f}" if weapon.oracle_score is not None else "n/a",
    )

    st.markdown("### Mission")
    st.info(mission.challenge_name or mission.challenge_type or "Commander mission")

    mission_knowledge = _mission_knowledge_from_brief(brief)
    if mission_knowledge:
        st.markdown("### Mission Intelligence")
        st.caption(
            f"{mission_knowledge.get('label', 'Mission Knowledge')} · "
            f"confidence: {mission_knowledge.get('confidence', 'unknown')}"
        )

        intel_cols = st.columns(4)
        with intel_cols[0]:
            st.markdown("**Preferred modes**")
            for item in mission_knowledge.get("preferred_modes", []) or []:
                st.write(f"- {item}")

        with intel_cols[1]:
            st.markdown("**Avoid**")
            for item in mission_knowledge.get("avoid_modes", []) or []:
                st.write(f"- {item}")

        with intel_cols[2]:
            st.markdown("**Playstyle**")
            for item in mission_knowledge.get("playstyle", []) or []:
                st.write(f"- {item}")

        with intel_cols[3]:
            st.markdown("**Attachment priorities**")
            for item in mission_knowledge.get("attachment_priorities", []) or []:
                st.write(f"- {str(item).title()}")

    availability = (
        brief.evidence.get("attachment_availability", {})
        if isinstance(brief.evidence, dict)
        else {}
    )

    if availability:
        current_level = availability.get("current_level")
        max_level = availability.get("max_level")
        eligible_count = availability.get("eligible_count", 0)
        total_count = availability.get("total_count", 0)
        locked_count = availability.get("locked_count", 0)

        level_text = (
            f"Level {current_level}"
            if current_level is not None
            else "Level unknown"
        )
        if max_level:
            level_text += f" / unlock cap {max_level}"

        st.caption(
            f"BUILD CONSTRAINT · {level_text} · "
            f"{eligible_count}/{total_count} attachments available · "
            f"{locked_count} level-locked"
        )

    st.markdown("### Weapon Build")
    build_cols = st.columns(3)
    build_cols[0].metric(
        "Raw TTK",
        f"{weapon.raw_ttk_ms:.0f} ms" if weapon.raw_ttk_ms is not None else "n/a",
    )
    build_cols[1].metric(
        "Practical TTK",
        f"{weapon.practical_ttk_ms:.0f} ms" if weapon.practical_ttk_ms is not None else "n/a",
    )
    build_cols[2].metric("Attachments", len(weapon.attachments))

    for attachment, slot in zip(weapon.attachments, weapon.slots):
        st.write(f"**{slot or 'attachment'}:** {attachment}")

    if weapon.reasoning:
        with st.expander("Why this build", expanded=True):
            for item in weapon.reasoning:
                st.write(f"- {item}")

    if loadout is not None:
        st.markdown("### Loadout Lab")
        loadout_cols = st.columns(4)

        secondary_name = "Standard secondary"
        if loadout.secondary is not None:
            secondary_name = loadout.secondary.weapon_name or loadout.secondary.weapon_class or "Standard secondary"

        with loadout_cols[0]:
            st.markdown("**Secondary**")
            st.write(secondary_name)

        with loadout_cols[1]:
            st.markdown("**Wildcard**")
            st.write(loadout.wildcard or "None")

        with loadout_cols[2]:
            st.markdown("**Field upgrade**")
            st.write(loadout.field_upgrade or "Field choice")

        with loadout_cols[3]:
            st.markdown("**Scorestreaks**")
            st.write(", ".join(loadout.scorestreaks) if loadout.scorestreaks else "Not resolved")

        class_cols = st.columns(2)
        with class_cols[0]:
            st.markdown("**Perks**")
            if loadout.perks:
                for perk in loadout.perks:
                    st.write(f"- {perk}")
            else:
                st.write("Not resolved")

            st.markdown("**Equipment**")
            st.write(f"Tactical: {_clean(loadout.tactical) or 'Field choice'}")
            st.write(f"Lethal: {_clean(loadout.lethal) or 'Field choice'}")

        with class_cols[1]:
            st.markdown("**Overclocks**")
            if loadout.overclocks:
                for label, value in loadout.overclocks.items():
                    st.write(f"- {label.replace('_', ' ').title()}: {value}")
            else:
                st.write("No overclock data resolved")

            if loadout.reasoning:
                with st.expander("Why this class", expanded=True):
                    for item in loadout.reasoning:
                        st.write(f"- {item}")

    if field_plan is not None:
        st.markdown("### Field Plan")
        plan_cols = st.columns(3)

        with plan_cols[0]:
            st.markdown("**Recommended modes**")
            for item in field_plan.recommended_modes:
                st.write(f"- {item}")

        with plan_cols[1]:
            st.markdown("**Avoid / use carefully**")
            for item in field_plan.avoid_modes:
                st.write(f"- {item}")

        with plan_cols[2]:
            st.markdown("**Priorities**")
            for item in field_plan.priorities:
                st.write(f"- {item}")

        if field_plan.notes:
            with st.expander("Field notes", expanded=True):
                for item in field_plan.notes:
                    st.write(f"- {item}")

    if brief.warnings:
        with st.expander("Warnings", expanded=True):
            for item in brief.warnings:
                st.warning(item)

    with st.expander("Mission evidence", expanded=False):
        st.json(brief.to_dict())


__all__ = [
    "MISSION_CHALLENGE_PRESETS",
    "build_manual_mission_profile",
    "render_session_brief",
]

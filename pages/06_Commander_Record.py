import html
from datetime import datetime
from typing import Any, Mapping

import streamlit as st

from modules.ui.perzevol_theme import inject_perzevol_theme
from modules.warzone.commander_session import load_current_commander_session

st.set_page_config(
    page_title="Perzevol OS - OBS Record View",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def clean(value: Any) -> str:
    return str(value or "").strip()


def esc(value: Any) -> str:
    return html.escape(clean(value))


def compact_markup(markup: str) -> str:
    return "".join(
        line.strip()
        for line in str(markup or "").splitlines()
        if line.strip()
    )


def render_html(markup: str):
    st.markdown(compact_markup(markup), unsafe_allow_html=True)


def as_dict(value: Any) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def as_list(value: Any) -> list:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if "|" in text:
            return [part.strip() for part in text.split("|") if part.strip()]
        if "," in text:
            return [part.strip() for part in text.split(",") if part.strip()]
        return [text]

    return [value]


def first_text(*values: Any, fallback: str = "") -> str:
    for value in values:
        text = clean(value)
        if text:
            return text
    return fallback


def format_number(value: Any, suffix: str = "") -> str:
    if value in (None, ""):
        return "n/a"

    try:
        number = float(value)
    except (TypeError, ValueError):
        return esc(value)

    if number.is_integer():
        return f"{int(number)}{suffix}"

    return f"{number:.2f}{suffix}"


def css_list(items: list[Any], empty: str = "Not supplied") -> str:
    values = [clean(item) for item in items if clean(item)]

    if not values:
        return f"<p>{esc(empty)}</p>"

    return "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in values) + "</ul>"


def render_css(clean_mode: bool):
    inject_perzevol_theme(clean_mode=clean_mode, screen="obs_record")

    render_html(
        """
        <style>
        html,
        body,
        [data-testid="stApp"],
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"],
        .main,
        .main .block-container {
            height: auto !important;
            min-height: 100% !important;
            max-height: none !important;
        }

        [data-testid="stAppViewContainer"] {
            overflow-y: auto !important;
        }

        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"],
        .main .block-container {
            overflow: visible !important;
        }

        .main .block-container,
        [data-testid="stMainBlockContainer"] {
            max-width: 1420px !important;
            padding-top: 0.9rem !important;
            padding-bottom: 4rem !important;
        }

        .obs-shell {
            border: 1px solid rgba(136, 255, 186, 0.30);
            background:
                radial-gradient(circle at top right, rgba(48, 209, 88, 0.14), transparent 36%),
                linear-gradient(180deg, rgba(9, 20, 15, 0.97), rgba(5, 10, 8, 0.98));
            padding: 18px 20px;
            margin: 10px 0 18px;
        }

        .obs-topline {
            display: flex;
            justify-content: space-between;
            gap: 18px;
            align-items: flex-start;
            border-bottom: 1px solid rgba(255, 255, 255, 0.10);
            padding-bottom: 12px;
            margin-bottom: 12px;
        }

        .obs-kicker,
        .obs-panel-title,
        .obs-label {
            font-size: 0.70rem;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            font-weight: 850;
        }

        .obs-kicker,
        .obs-panel-title {
            color: #78f2a7;
        }

        .obs-label {
            color: rgba(255, 255, 255, 0.52);
            display: block;
            margin-bottom: 4px;
        }

        .obs-title {
            color: #ffffff;
            font-size: 1.9rem;
            line-height: 1.05;
            font-weight: 950;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            margin-top: 3px;
        }

        .obs-subtitle {
            color: rgba(255, 255, 255, 0.74);
            font-size: 0.94rem;
            margin-top: 5px;
        }

        .obs-metrics {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            justify-content: flex-end;
        }

        .obs-metrics div {
            min-width: 112px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: rgba(255, 255, 255, 0.035);
            padding: 8px 10px;
            text-align: right;
        }

        .obs-metrics strong {
            color: #ffffff;
            display: block;
            font-size: 1.05rem;
            line-height: 1.1;
        }

        .obs-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
            gap: 12px;
            margin-top: 12px;
        }

        .obs-grid-three {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 12px;
            margin-top: 12px;
        }

        .obs-panel {
            border: 1px solid rgba(255, 255, 255, 0.11);
            background: rgba(255, 255, 255, 0.028);
            padding: 12px 14px;
        }

        .obs-panel.warning {
            border-color: rgba(255, 196, 0, 0.32);
            background: rgba(255, 196, 0, 0.07);
        }

        .obs-copy {
            color: rgba(255, 255, 255, 0.88);
            font-size: 0.86rem;
            line-height: 1.45;
            margin-top: 8px;
        }

        .obs-copy ul {
            margin: 6px 0 0 18px;
            padding: 0;
        }

        .obs-copy li {
            margin-bottom: 4px;
        }

        .attachment-grid {
            display: grid;
            grid-template-columns: minmax(105px, 0.36fr) minmax(0, 1fr);
            gap: 5px 10px;
            margin-top: 8px;
            font-size: 0.84rem;
            line-height: 1.35;
        }

        .attachment-slot {
            color: rgba(255, 255, 255, 0.52);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-size: 0.70rem;
        }

        .attachment-name {
            color: rgba(255, 255, 255, 0.92);
        }

        .obs-rule {
            margin-top: 14px;
            border: 1px solid rgba(255, 75, 75, 0.36);
            background: rgba(255, 75, 75, 0.11);
            color: #ffffff;
            padding: 9px 11px;
            font-family: monospace;
            font-weight: 950;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        @media (max-width: 960px) {
            .obs-topline {
                flex-direction: column;
            }

            .obs-metrics {
                justify-content: flex-start;
            }

            .obs-metrics div {
                text-align: left;
            }

            .obs-grid,
            .obs-grid-three {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """
    )


def snapshot_session_brief(snapshot: Mapping[str, Any]) -> dict:
    brief = as_dict(snapshot.get("session_brief"))

    if brief:
        return brief

    # Defensive fallback for older persisted snapshots.
    for key in ("brief", "oracle_brief"):
        value = as_dict(snapshot.get(key))
        if value:
            return value

    return {}


def mission_knowledge_from_brief(brief: Mapping[str, Any]) -> dict:
    evidence = as_dict(brief.get("evidence"))

    knowledge = as_dict(evidence.get("mission_knowledge"))
    if knowledge:
        return knowledge

    mission_inputs = as_dict(evidence.get("mission_inputs"))
    return as_dict(mission_inputs.get("mission_knowledge"))


def render_empty_state():
    render_html(
        """
        <div class="obs-shell">
            <div class="obs-kicker">No Session Snapshot</div>
            <div class="obs-title">Generate And Start A Commander Session</div>
            <div class="obs-subtitle">
                OBS Record View only displays the active persisted SessionBrief.
                Open Commander Launch, prepare the first mission, then start the session.
            </div>
            <div class="obs-rule">OBS IS DISPLAY ONLY. COMMANDER AND ORACLE OWN THE LOGIC.</div>
        </div>
        """
    )


def render_attachment_grid(weapon: Mapping[str, Any]) -> str:
    attachments = as_list(weapon.get("attachments"))
    slots = as_list(weapon.get("slots"))

    if not attachments:
        return "<div class='obs-copy'>No attachment build available.</div>"

    lines = []
    for index, attachment in enumerate(attachments):
        slot = slots[index] if index < len(slots) else "attachment"
        slot_label = clean(slot).replace("_", " ").title() or "Attachment"
        lines.append(
            f"<span class='attachment-slot'>{esc(slot_label)}</span>"
            f"<span class='attachment-name'>{esc(attachment)}</span>"
        )

    return "<div class='attachment-grid'>" + "".join(lines) + "</div>"


def render_loadout_lines(loadout: Mapping[str, Any]) -> str:
    if not loadout:
        return "<p>Loadout Lab has not attached class data to this snapshot yet.</p>"

    secondary = loadout.get("secondary")
    if isinstance(secondary, Mapping):
        secondary_text = first_text(
            secondary.get("weapon_name"),
            secondary.get("name"),
            fallback="Standard secondary",
        )
    else:
        secondary_text = first_text(secondary, fallback="Standard secondary")

    perks = as_list(loadout.get("perks"))
    scorestreaks = as_list(loadout.get("scorestreaks"))

    lines = [
        f"<span class='obs-label'>Secondary</span>{esc(secondary_text)}",
        f"<span class='obs-label'>Wildcard</span>{esc(loadout.get('wildcard') or 'None')}",
        f"<span class='obs-label'>Perks</span>{esc(' | '.join(clean(item) for item in perks if clean(item)) or 'Not resolved')}",
        f"<span class='obs-label'>Tactical</span>{esc(loadout.get('tactical') or 'Field choice')}",
        f"<span class='obs-label'>Lethal</span>{esc(loadout.get('lethal') or 'Field choice')}",
        f"<span class='obs-label'>Field Upgrade</span>{esc(loadout.get('field_upgrade') or 'Field choice')}",
    ]

    if scorestreaks:
        lines.append(
            f"<span class='obs-label'>Scorestreaks</span>{esc(' | '.join(clean(item) for item in scorestreaks if clean(item)))}"
        )

    return "<br>".join(lines)


def render_snapshot(snapshot: Mapping[str, Any]):
    brief = snapshot_session_brief(snapshot)

    if not brief:
        render_empty_state()
        st.warning("A Commander session file exists, but it does not contain a SessionBrief payload.")
        return

    plan = as_dict(snapshot.get("plan"))
    stop = as_dict(snapshot.get("stop"))
    mission = as_dict(brief.get("mission"))
    weapon = as_dict(brief.get("weapon_build"))
    loadout = as_dict(brief.get("loadout"))
    field_plan = as_dict(brief.get("field_plan"))
    evidence = as_dict(brief.get("evidence"))
    mission_knowledge = mission_knowledge_from_brief(brief)
    availability = as_dict(evidence.get("attachment_availability"))

    weapon_name = first_text(
        weapon.get("weapon_name"),
        mission.get("weapon_id"),
        stop.get("weapon"),
        snapshot.get("weapon"),
        fallback="Active Weapon",
    )
    challenge = first_text(
        mission.get("challenge_name"),
        mission.get("challenge_type"),
        stop.get("challenge_text"),
        snapshot.get("challenge"),
        fallback="Current challenge",
    )
    target = first_text(
        mission.get("target"),
        stop.get("camo"),
        fallback="Assigned target",
    )
    mode = first_text(
        mission.get("mode"),
        stop.get("mode"),
        plan.get("mode"),
        fallback="Unknown mode",
    )
    stop_number = first_text(stop.get("stop_number"), fallback="?")
    total_stops = len(as_list(plan.get("stops")))

    level_line = ""
    if availability:
        level_line = (
            f"Level {esc(availability.get('current_level') if availability.get('current_level') is not None else 'unknown')}"
            f" · {esc(availability.get('eligible_count', 0))}/{esc(availability.get('total_count', 0))} attachments available"
            f" · {esc(availability.get('locked_count', 0))} locked"
        )
        if availability.get("max_level"):
            level_line += f" · cap {esc(availability.get('max_level'))}"

    preferred_modes = as_list(mission_knowledge.get("preferred_modes"))
    avoid_modes = as_list(mission_knowledge.get("avoid_modes"))
    playstyle = as_list(mission_knowledge.get("playstyle"))
    attachment_priorities = as_list(mission_knowledge.get("attachment_priorities"))

    field_modes = as_list(field_plan.get("recommended_modes"))
    field_avoid = as_list(field_plan.get("avoid_modes"))
    field_priorities = as_list(field_plan.get("priorities"))
    field_notes = as_list(field_plan.get("notes"))
    warnings = as_list(brief.get("warnings")) + as_list(field_plan.get("warnings"))

    render_html(
        f"""
        <div class="obs-shell">
            <div class="obs-topline">
                <div>
                    <div class="obs-kicker">MISSION RECEIVED</div>
                    <div class="obs-title">{esc(weapon_name)}</div>
                    <div class="obs-subtitle">{esc(target)} · {esc(mode)} · {esc(challenge)}</div>
                </div>
                <div class="obs-metrics">
                    <div><span class="obs-label">Raw TTK</span><strong>{format_number(weapon.get("raw_ttk_ms"), " ms")}</strong></div>
                    <div><span class="obs-label">Practical</span><strong>{format_number(weapon.get("practical_ttk_ms"), " ms")}</strong></div>
                    <div><span class="obs-label">Oracle</span><strong>{format_number(weapon.get("oracle_score"))}</strong></div>
                    <div><span class="obs-label">Stop</span><strong>{esc(stop_number)}{f" / {esc(total_stops)}" if total_stops else ""}</strong></div>
                </div>
            </div>

            <div class="obs-copy">{level_line or "Attachment availability evidence not supplied."}</div>

            <div class="obs-grid">
                <div class="obs-panel">
                    <div class="obs-panel-title">BUILD</div>
                    {render_attachment_grid(weapon)}
                </div>

                <div class="obs-panel">
                    <div class="obs-panel-title">LOADOUT</div>
                    <div class="obs-copy">{render_loadout_lines(loadout)}</div>
                </div>
            </div>

            <div class="obs-grid-three">
                <div class="obs-panel">
                    <div class="obs-panel-title">MISSION INTELLIGENCE</div>
                    <div class="obs-copy">
                        <span class="obs-label">Profile</span>
                        {esc(first_text(mission_knowledge.get("label"), mission_knowledge.get("key"), fallback="Not resolved"))}
                        <br><span class="obs-label">Preferred Modes</span>
                        {esc(" | ".join(clean(item) for item in preferred_modes if clean(item)) or "Not supplied")}
                        <br><span class="obs-label">Avoid</span>
                        {esc(" | ".join(clean(item) for item in avoid_modes if clean(item)) or "Not supplied")}
                    </div>
                </div>

                <div class="obs-panel">
                    <div class="obs-panel-title">PLAYSTYLE</div>
                    <div class="obs-copy">
                        {css_list(playstyle, "No challenge-specific playstyle supplied.")}
                    </div>
                </div>

                <div class="obs-panel">
                    <div class="obs-panel-title">ATTACHMENT PRIORITIES</div>
                    <div class="obs-copy">
                        {css_list([str(item).title() for item in attachment_priorities], "No priority list supplied.")}
                    </div>
                </div>
            </div>

            <div class="obs-grid">
                <div class="obs-panel">
                    <div class="obs-panel-title">FIELD PLAN</div>
                    <div class="obs-copy">
                        <span class="obs-label">Recommended Modes</span>
                        {esc(" | ".join(clean(item) for item in field_modes if clean(item)) or "Use the Mission Intelligence modes.")}
                        <br><span class="obs-label">Avoid / Use Carefully</span>
                        {esc(" | ".join(clean(item) for item in field_avoid if clean(item)) or "No avoid list supplied.")}
                        <br><span class="obs-label">Priorities</span>
                        {esc(" · ".join(clean(item) for item in field_priorities[:5] if clean(item)) or "No field priorities supplied.")}
                        <br><span class="obs-label">Notes</span>
                        {esc(" · ".join(clean(item) for item in field_notes[:3] if clean(item)) or "No notes supplied.")}
                    </div>
                </div>

                <div class="obs-panel warning">
                    <div class="obs-panel-title">WARNINGS</div>
                    <div class="obs-copy">
                        {css_list(warnings, "No warnings on the current snapshot.")}
                    </div>
                </div>
            </div>

            <div class="obs-rule">OBS IS DISPLAY ONLY. FOLLOW THE SESSION BRIEF. BANK PROGRESS IN MISSION CONTROL.</div>
        </div>
        """
    )


def main():
    with st.sidebar:
        clean_mode = st.toggle("OBS clean mode", value=True)
        show_raw_snapshot = st.toggle("Show raw snapshot", value=False)
        if st.button("Refresh", use_container_width=True):
            st.rerun()

    render_css(clean_mode)

    snapshot = load_current_commander_session()

    if not snapshot:
        render_empty_state()
        return

    render_snapshot(snapshot)

    if show_raw_snapshot:
        with st.expander("Raw persisted Commander session", expanded=False):
            st.json(snapshot)


if __name__ == "__main__":
    main()

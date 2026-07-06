import html
import json
from pathlib import Path
from typing import Any

import streamlit as st

from modules.warzone.killchain_engine import (
    load_tracker_tasks,
    summarise_tasks,
)
from modules.warzone.loadout_architect import (
    ENERGY_OPTIONS,
    MODE_OPTIONS,
    attach_loadouts_to_plan,
    build_generation_profile,
    clean,
    copyable_plan_text,
    generate_quick_plan,
    load_loadout_templates,
    recording_lines_for_plan,
)
from modules.warzone.series_director import attach_series_context_to_plan

st.set_page_config(
    page_title="Perzevol OS - Commander Launch",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

STATE_DIR = Path("data/bo7_state")
COMPLETION_STATE_PATH = STATE_DIR / "completion_state.json"
LATEST_LAUNCH_PLAN_PATH = STATE_DIR / "latest_commander_launch_plan.json"


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


def ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_completion_state() -> dict:
    ensure_state_dir()

    if not COMPLETION_STATE_PATH.exists():
        return {}

    try:
        with COMPLETION_STATE_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError:
        return {}


def load_latest_launch_plan() -> dict | None:
    ensure_state_dir()

    if not LATEST_LAUNCH_PLAN_PATH.exists():
        return None

    try:
        with LATEST_LAUNCH_PLAN_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict) and data.get("stops"):
            return data

    except (json.JSONDecodeError, OSError):
        return None

    return None


def save_latest_launch_plan(plan: dict):
    ensure_state_dir()

    with LATEST_LAUNCH_PLAN_PATH.open("w", encoding="utf-8") as file:
        json.dump(plan, file, indent=2)


def clear_latest_launch_plan():
    if LATEST_LAUNCH_PLAN_PATH.exists():
        LATEST_LAUNCH_PLAN_PATH.unlink()


def apply_completion_state(tasks: list[dict], completion_state: dict) -> list[dict]:
    for task in tasks:
        task_id = task.get("task_id")

        if task_id in completion_state:
            task["last_result"] = completion_state[task_id].get("result", "Camo completed")
            task["completed_on_session"] = completion_state[task_id].get("result") == "Camo completed"

    return tasks


def load_commander_tasks() -> tuple[list[dict], dict]:
    completion_state = load_completion_state()
    tasks = apply_completion_state(load_tracker_tasks(), completion_state)
    return tasks, completion_state


def render_css():
    render_html(
        """
        <style>
        .commander-title {
            font-size: 2.75rem;
            font-weight: 950;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            line-height: 1;
        }

        .commander-subtitle {
            color: #bbbbbb;
            font-family: monospace;
            margin-top: 0.35rem;
            margin-bottom: 1rem;
        }

        .matrix-wrap {
            border: 1px solid rgba(255,255,255,0.10);
            background: rgba(255,255,255,0.025);
            padding: 0.9rem 1rem;
            margin: 0.8rem 0 1rem 0;
        }

        .matrix-row-label {
            color: #ffffff;
            font-size: 1rem;
            font-weight: 950;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            padding-top: 0.55rem;
        }

        .mode-head {
            color: #ff4b4b;
            font-family: monospace;
            font-size: 0.72rem;
            font-weight: 950;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            text-align: center;
            margin-bottom: 0.3rem;
        }

        .plan-card {
            border: 1px solid rgba(48,209,88,0.34);
            border-left: 10px solid #30d158;
            background:
                radial-gradient(circle at top right, rgba(48,209,88,0.20), rgba(48,209,88,0.035) 36%, transparent 62%),
                linear-gradient(135deg, rgba(48,209,88,0.11), rgba(255,255,255,0.035));
            padding: 1rem 1.15rem;
            margin: 1rem 0;
        }

        .plan-title {
            color: #ffffff;
            font-size: 2rem;
            font-weight: 950;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            line-height: 1;
        }

        .plan-subtitle {
            color: #d4d4d4;
            margin-top: 0.4rem;
        }

        .mini-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.55rem;
            margin-top: 0.75rem;
        }

        .mini-grid div {
            background: rgba(0,0,0,0.25);
            border: 1px solid rgba(255,255,255,0.08);
            padding: 0.5rem 0.55rem;
        }

        .mini-grid span {
            display: block;
            color: #999999;
            font-family: monospace;
            font-size: 0.64rem;
            font-weight: 850;
            letter-spacing: 0.10em;
            text-transform: uppercase;
            margin-bottom: 0.18rem;
        }

        .mini-grid strong {
            color: #ffffff;
            font-size: 0.88rem;
            font-weight: 900;
        }

        .objective-card {
            border: 1px solid rgba(255,255,255,0.12);
            background: rgba(255,255,255,0.035);
            padding: 1rem 1.1rem;
            margin: 0.85rem 0;
        }

        .objective-label {
            color: #ff4b4b;
            font-family: monospace;
            font-size: 0.72rem;
            font-weight: 950;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }

        .objective-title {
            color: #ffffff;
            font-size: 1.45rem;
            font-weight: 950;
            text-transform: uppercase;
            line-height: 1.05;
        }

        .objective-subtitle {
            color: #cccccc;
            margin: 0.25rem 0 0.75rem 0;
        }

        .detail-box {
            border: 1px solid rgba(0,194,255,0.24);
            background: rgba(0,194,255,0.05);
            padding: 0.75rem 0.85rem;
            margin-top: 0.75rem;
        }

        .detail-box span {
            display: block;
            color: #00c2ff;
            font-family: monospace;
            font-size: 0.68rem;
            font-weight: 950;
            letter-spacing: 0.13em;
            text-transform: uppercase;
            margin-bottom: 0.28rem;
        }

        .detail-box p {
            margin: 0;
            color: #eeeeee;
            line-height: 1.35;
        }

        .rule-strip {
            margin-top: 0.75rem;
            padding: 0.55rem 0.7rem;
            color: #ffffff;
            background: rgba(255,75,75,0.16);
            border: 1px solid rgba(255,75,75,0.30);
            font-family: monospace;
            font-weight: 900;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .series-card {
            border: 1px solid rgba(255,204,0,0.34);
            border-left: 10px solid #ffcc00;
            background:
                radial-gradient(circle at top right, rgba(255,204,0,0.18), rgba(255,204,0,0.035) 38%, transparent 64%),
                linear-gradient(135deg, rgba(255,204,0,0.08), rgba(255,255,255,0.035));
            padding: 1rem 1.15rem;
            margin: 1rem 0;
        }

        .series-kicker {
            color: #ffcc00;
            font-family: monospace;
            font-size: 0.72rem;
            font-weight: 950;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }

        .series-title {
            color: #ffffff;
            font-size: 1.75rem;
            font-weight: 950;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            line-height: 1.05;
        }

        .series-hook {
            color: #eeeeee;
            font-size: 1rem;
            line-height: 1.35;
            margin-top: 0.6rem;
        }

        .morale-banner {
            border: 1px solid rgba(255,75,75,0.42);
            background: rgba(255,75,75,0.10);
            padding: 0.75rem 0.85rem;
            margin: 0.75rem 0;
        }

        .morale-banner strong {
            display: block;
            color: #ffffff;
            font-size: 1.35rem;
            font-weight: 950;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            line-height: 1.05;
        }

        .morale-banner span {
            display: block;
            color: #f0f0f0;
            margin-top: 0.35rem;
        }

        </style>
        """
    )


def render_series_context_card(plan: dict):
    context = plan.get("series_context", {}) or {}

    if not context:
        return

    proof_points = context.get("proof_points", []) or []
    proof_preview = " · ".join(proof_points[:2]) if proof_points else "Show decision, gameplay proof, and debrief."
    morale = context.get("morale", {}) or {}

    render_html(
        f"""
        <div class="series-card">
            <div class="series-kicker">Series Director</div>
            <div class="morale-banner">
                <strong>{esc(morale.get("headline") or context.get("morale_headline") or "JUST ONE MORE CHALLENGE.")}</strong>
                <span>{esc(morale.get("line") or context.get("morale_line") or "Bank one visible piece of progress, then reassess.")}</span>
            </div>
            <div class="series-title">{esc(context.get("episode_title", "AI Chose My BO7 Grind"))}</div>
            <div class="series-hook">{esc(context.get("hook", ""))}</div>
            <div class="mini-grid">
                <div><span>Deadline</span><strong>{esc(context.get("days_remaining", "?"))} days</strong></div>
                <div><span>Pressure</span><strong>{esc(context.get("pressure", "Unknown"))}</strong></div>
                <div><span>Thumbnail</span><strong>{esc(context.get("thumbnail_text", "AI CHOSE"))}</strong></div>
                <div><span>Angle</span><strong>{esc(context.get("completion_angle", "Completion"))}</strong></div>
            </div>
            <div class="detail-box">
                <span>Why this episode matters</span>
                <p>{esc(context.get("route_promise", ""))}<br>{esc(context.get("pace_line", ""))}</p>
            </div>
            <div class="detail-box">
                <span>Minimum viable win</span>
                <p>{esc(morale.get("micro_action") or context.get("morale_micro_action") or "Play the first stop and look only for proof.")}<br>{esc(morale.get("rule") or context.get("morale_rule") or "A partial is still useful data.")}</p>
            </div>
            <div class="detail-box">
                <span>Proof to capture</span>
                <p>{esc(proof_preview)}</p>
            </div>
        </div>
        """
    )


def render_mode_candidates(plan: dict):
    candidates = plan.get("mode_candidates", []) or []

    if not candidates:
        return

    with st.expander("Mode comparison"):
        for candidate in candidates:
            st.write(
                f"{candidate.get('mode', 'Unknown')} | "
                f"score {candidate.get('score', 0)} | "
                f"{candidate.get('stops', 0)} stop(s) | "
                f"{candidate.get('estimated_minutes', 0)} min | "
                f"{candidate.get('primary_route', '')}"
            )


def render_plan(plan: dict, tasks: list[dict]):
    templates = load_loadout_templates()
    plan = attach_loadouts_to_plan(plan, tasks, templates)
    plan = attach_series_context_to_plan(plan, summarise_tasks(tasks), load_completion_state())
    st.session_state.bo7_quick_launch_plan = plan
    save_latest_launch_plan(plan)

    stops = plan.get("stops", [])
    profile = plan.get("quick_profile", {})

    render_html(
        f"""
        <div class="plan-card">
            <div class="plan-title">{esc(plan.get("quick_button_label", "Commander Plan"))}</div>
            <div class="plan-subtitle">{esc(plan.get("quick_description", "Generated route."))}</div>
            <div class="mini-grid">
                <div><span>Energy</span><strong>{esc(plan.get("quick_energy_label", "Unknown"))}</strong></div>
                <div><span>Mode</span><strong>{esc(plan.get("mode", "Unknown"))}</strong></div>
                <div><span>Stops</span><strong>{esc(len(stops))}</strong></div>
                <div><span>Rule</span><strong>No reroll</strong></div>
            </div>
            <div class="mini-grid">
                <div><span>Time</span><strong>{esc(plan.get("available_minutes", "?"))} min</strong></div>
                <div><span>Goal</span><strong>{esc(profile.get("session_goal", ""))}</strong></div>
                <div><span>Style</span><strong>{esc(plan.get("commander_mode", ""))}</strong></div>
                <div><span>Closeness</span><strong>{esc(plan.get("minimum_closeness", ""))}%</strong></div>
            </div>
        </div>
        """
    )

    render_series_context_card(plan)

    if plan.get("note"):
        st.warning(plan.get("note"))

    render_mode_candidates(plan)

    if not stops:
        st.warning("No stops returned for this combination. Try ANY MODE, TRACKER CLEANUP, or a lower energy route.")
        return

    copy_col, script_col = st.columns(2)

    with copy_col:
        with st.expander("Copyable plan text", expanded=False):
            st.text_area(
                "Copyable plan",
                value=copyable_plan_text(plan, tasks, templates),
                height=260,
                label_visibility="collapsed",
            )

    with script_col:
        with st.expander("Recording lines", expanded=False):
            st.text_area(
                "Recording lines",
                value=recording_lines_for_plan(plan),
                height=260,
                label_visibility="collapsed",
            )

    for stop in stops:
        loadout = stop.get("loadout") or {}
        companion_objectives = stop.get("companion_objectives", []) or []
        companion_text = " · ".join(companion_objectives[:4]) if companion_objectives else "None assigned"

        render_html(
            f"""
            <div class="objective-card">
                <div class="objective-label">STOP {esc(stop.get("stop_number", "?"))}</div>
                <div class="objective-title">{esc(stop.get("weapon", "Objective"))}</div>
                <div class="objective-subtitle">{esc(stop.get("camo", "Target"))}</div>

                <div class="mini-grid">
                    <div><span>Mode</span><strong>{esc(stop.get("mode", plan.get("mode", "Unknown")))}</strong></div>
                    <div><span>Type</span><strong>{esc(stop.get("task_type", "objective"))}</strong></div>
                    <div><span>Class</span><strong>{esc(stop.get("weapon_class", "N/A"))}</strong></div>
                    <div><span>Estimate</span><strong>{esc(stop.get("estimated_minutes", "?"))} min</strong></div>
                </div>

                <div class="detail-box">
                    <span>Objective</span>
                    <p>{esc(stop.get("challenge_text", "Complete the assigned objective."))}</p>
                </div>

                <div class="detail-box">
                    <span>Loadout</span>
                    <p>
                        <strong>Template:</strong> {esc(loadout.get("template_name"))}<br>
                        <strong>Primary:</strong> {esc(loadout.get("primary"))}<br>
                        <strong>Why this primary:</strong> {esc(loadout.get("primary_reason"))}<br>
                        <strong>Natural goal:</strong> {esc(loadout.get("natural_goal"))}<br>
                        <strong>Goal source:</strong> {esc(loadout.get("natural_goal_source"))}<br>
                        <strong>Attachments:</strong> {esc(loadout.get("primary_attachments"))}<br>
                        <strong>Attachment source:</strong> {esc(loadout.get("primary_attachment_source") or loadout.get("ttk_oracle_note") or "Unknown")}<br>
                        <strong>Secondary:</strong> {esc(loadout.get("secondary"))} · {esc(loadout.get("secondary_attachments"))}<br>
                        <strong>Wildcard:</strong> {esc(loadout.get("wildcard"))}<br>
                        <strong>Perks:</strong> {esc(loadout.get("perks"))}<br>
                        <strong>Tactical / Lethal / Field:</strong> {esc(loadout.get("tactical"))} / {esc(loadout.get("lethal"))} / {esc(loadout.get("field_upgrade"))}<br>
                        <strong>Scorestreaks:</strong> {esc(loadout.get("scorestreaks"))}
                    </p>
                </div>

                <div class="detail-box">
                    <span>Stack If Free</span>
                    <p>{esc(companion_text)}</p>
                </div>

                <div class="rule-strip">Complete this, bank it, move to the next stop.</div>
            </div>
            """
        )


def render_matrix(tasks: list[dict], task_summary: dict, completion_state: dict):
    render_html(
        """
        <div class="matrix-wrap">
            <div class="commander-subtitle">
                Pick one button. Rows are energy. Columns are mode. ANY MODE means the Commander chooses the mode.
            </div>
        </div>
        """
    )

    header_cols = st.columns([1.15] + [1 for _ in MODE_OPTIONS])

    with header_cols[0]:
        st.markdown("")

    for index, mode in enumerate(MODE_OPTIONS):
        with header_cols[index + 1]:
            render_html(f"<div class='mode-head'>{esc(mode['short'])}</div>")

    for energy in ENERGY_OPTIONS:
        row_cols = st.columns([1.15] + [1 for _ in MODE_OPTIONS])

        with row_cols[0]:
            render_html(f"<div class='matrix-row-label'>{esc(energy['short'])}</div>")
            st.caption(energy["label"])

        for mode_index, mode in enumerate(MODE_OPTIONS):
            profile = build_generation_profile(energy, mode)
            button_label = profile["button_label"]
            button_key = f"quick_{energy['key']}_{mode['key']}"

            with row_cols[mode_index + 1]:
                if st.button(button_label, key=button_key, use_container_width=True):
                    plan = generate_quick_plan(
                        energy=energy,
                        mode=mode,
                        tasks=tasks,
                        attach_loadouts=True,
                    )
                    plan = attach_series_context_to_plan(plan, task_summary, completion_state)
                    st.session_state.bo7_quick_launch_plan = plan
                    save_latest_launch_plan(plan)
                    st.rerun()


def main():
    render_css()

    st.markdown("<div class='commander-title'>Commander Launch</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='commander-subtitle'>Every energy and mode combination. One click gives objectives plus loadout.</div>",
        unsafe_allow_html=True,
    )

    tasks, completion_state = load_commander_tasks()
    task_summary = summarise_tasks(tasks)

    st.caption(
        f"Tasks loaded: {task_summary.get('total', 0)} · "
        f"Available: {task_summary.get('available', 0)} · "
        f"Locked: {task_summary.get('locked', 0)} · "
        f"App-completed: {len(completion_state)}"
    )

    if not st.session_state.get("bo7_quick_launch_plan"):
        restored_plan = load_latest_launch_plan()
        if restored_plan:
            st.session_state.bo7_quick_launch_plan = restored_plan
            st.caption("Recovered latest Commander Launch plan from disk.")

    st.divider()

    render_matrix(tasks, task_summary, completion_state)

    st.divider()

    plan = st.session_state.get("bo7_quick_launch_plan")

    if plan:
        render_plan(plan, tasks)

        st.divider()

        col_a, col_b, col_c = st.columns(3)

        with col_a:
            if st.button("CLEAR QUICK PLAN", use_container_width=True):
                st.session_state.bo7_quick_launch_plan = None
                clear_latest_launch_plan()
                st.rerun()

        with col_b:
            if st.button("OPEN OBS RECORD VIEW", use_container_width=True):
                try:
                    st.switch_page("pages/06_Commander_Record.py")
                except Exception:
                    st.info("Open BO7: OBS Record View from the sidebar.")

        with col_c:
            if st.button("SEND TO MISSION CONTROL", use_container_width=True, type="primary"):
                mission_plan = attach_loadouts_to_plan(plan, tasks)
                mission_plan = attach_series_context_to_plan(mission_plan, task_summary, completion_state)
                st.session_state.bo7_session_plan = mission_plan
                st.session_state.bo7_quick_launch_plan = mission_plan
                save_latest_launch_plan(mission_plan)
                st.session_state.bo7_completed_stop_ids = []
                st.session_state.bo7_stop_results = {}
                st.session_state.bo7_account_levels_gained = 0.0
                st.session_state.bo7_account_levels_debrief_adjustment = 0.0

                try:
                    st.switch_page("pages/03_Warzone.py")
                except Exception:
                    st.success("Plan sent to Mission Control. Open BO7: Completion Commander from the sidebar.")
    else:
        st.info("Choose any energy/mode combination above. The Commander will generate the route and loadouts here.")


if __name__ == "__main__":
    main()

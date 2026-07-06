import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from modules.warzone.loadout_architect import recording_lines_for_plan
from modules.warzone.series_director import attach_series_context_to_plan

st.set_page_config(
    page_title="Perzevol OS - OBS Record View",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

STATE_DIR = Path("data/bo7_state")
LATEST_LAUNCH_PLAN_PATH = STATE_DIR / "latest_commander_launch_plan.json"

RESOLVED_STATUSES = {"done", "partial", "skipped"}


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


def load_latest_launch_plan() -> dict | None:
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


def current_plan() -> tuple[dict | None, str]:
    active = st.session_state.get("bo7_session_plan")
    if isinstance(active, dict) and active.get("stops"):
        return attach_series_context_to_plan(active), "Mission Control active plan"

    quick = st.session_state.get("bo7_quick_launch_plan")
    if isinstance(quick, dict) and quick.get("stops"):
        return attach_series_context_to_plan(quick), "Commander Launch plan"

    latest = load_latest_launch_plan()
    if latest:
        return attach_series_context_to_plan(latest), "Recovered latest launch plan"

    return None, ""


def stop_results() -> dict:
    results = st.session_state.get("bo7_stop_results", {})
    return results if isinstance(results, dict) else {}


def stop_status(stop: dict) -> str:
    task_id = clean(stop.get("task_id"))
    result = stop_results().get(task_id, {})
    return clean(result.get("status")) or "pending"


def active_stop(plan: dict) -> dict:
    for stop in plan.get("stops", []) or []:
        if stop_status(stop) not in RESOLVED_STATUSES:
            return stop

    stops = plan.get("stops", []) or []
    return stops[-1] if stops else {}


def count_statuses(plan: dict) -> dict:
    counts = {"done": 0, "partial": 0, "skipped": 0, "pending": 0}

    for stop in plan.get("stops", []) or []:
        status = stop_status(stop)
        if status not in counts:
            status = "pending"
        counts[status] += 1

    return counts


def plan_progress_label(plan: dict) -> str:
    counts = count_statuses(plan)
    useful = counts["done"] + counts["partial"]
    total = sum(counts.values())

    if not total:
        return "0%"

    return f"{round((useful / total) * 100)}%"


def loadout_for_stop(stop: dict) -> dict:
    loadout = stop.get("loadout", {})
    return loadout if isinstance(loadout, dict) else {}


def render_css(clean_mode: bool):
    sidebar_css = ""
    if clean_mode:
        sidebar_css = """
        [data-testid="stSidebar"] {display: none;}
        [data-testid="collapsedControl"] {display: none;}
        header {visibility: hidden;}
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        """

    render_html(
        f"""
        <style>
        {sidebar_css}

        .stApp {{
            background:
                radial-gradient(circle at top left, rgba(255,75,75,0.18), transparent 30%),
                radial-gradient(circle at bottom right, rgba(0,194,255,0.12), transparent 28%),
                linear-gradient(135deg, #050608 0%, #090b10 48%, #030405 100%);
        }}

        .block-container {{
            max-width: 96vw;
            padding-top: 1.1rem;
            padding-bottom: 1.2rem;
            padding-left: 1.3rem;
            padding-right: 1.3rem;
        }}

        .record-shell {{
            border: 1px solid rgba(255,255,255,0.10);
            background: rgba(0,0,0,0.20);
            padding: 0.95rem 1.05rem;
            margin-bottom: 0.85rem;
        }}

        .record-title {{
            color: #ffffff;
            font-size: 3rem;
            font-weight: 950;
            line-height: 0.95;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}

        .record-subtitle {{
            color: #ff4b4b;
            font-family: monospace;
            font-size: 0.95rem;
            letter-spacing: 0.22em;
            text-transform: uppercase;
            margin-top: 0.45rem;
        }}

        .hero-card {{
            border: 1px solid rgba(255,75,75,0.42);
            border-left: 12px solid #ff4b4b;
            background:
                radial-gradient(circle at top right, rgba(255,75,75,0.28), rgba(255,75,75,0.05) 38%, transparent 64%),
                linear-gradient(135deg, rgba(255,75,75,0.15), rgba(255,255,255,0.035));
            padding: 1.15rem 1.35rem;
            margin: 0.85rem 0;
            box-shadow: 0 0 30px rgba(0,0,0,0.35);
        }}

        .blue-card {{
            border-color: rgba(0,194,255,0.38);
            border-left-color: #00c2ff;
            background:
                radial-gradient(circle at top right, rgba(0,194,255,0.20), rgba(0,194,255,0.04) 38%, transparent 64%),
                linear-gradient(135deg, rgba(0,194,255,0.11), rgba(255,255,255,0.035));
        }}

        .green-card {{
            border-color: rgba(48,209,88,0.38);
            border-left-color: #30d158;
            background:
                radial-gradient(circle at top right, rgba(48,209,88,0.20), rgba(48,209,88,0.04) 38%, transparent 64%),
                linear-gradient(135deg, rgba(48,209,88,0.11), rgba(255,255,255,0.035));
        }}

        .gold-card {{
            border-color: rgba(255,204,0,0.38);
            border-left-color: #ffcc00;
            background:
                radial-gradient(circle at top right, rgba(255,204,0,0.20), rgba(255,204,0,0.04) 38%, transparent 64%),
                linear-gradient(135deg, rgba(255,204,0,0.10), rgba(255,255,255,0.035));
        }}

        .eyebrow {{
            color: #ff4b4b;
            font-family: monospace;
            font-size: 0.76rem;
            font-weight: 950;
            letter-spacing: 0.22em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }}

        .blue-card .eyebrow {{ color: #00c2ff; }}
        .green-card .eyebrow {{ color: #30d158; }}
        .gold-card .eyebrow {{ color: #ffcc00; }}

        .card-title {{
            color: #ffffff;
            font-size: 2.35rem;
            font-weight: 950;
            line-height: 1.02;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }}

        .card-subtitle {{
            color: #d8d8d8;
            font-size: 1rem;
            font-weight: 780;
            margin-top: 0.35rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }}

        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.65rem;
            margin-top: 0.85rem;
        }}

        .stat-grid div {{
            background: rgba(0,0,0,0.28);
            border: 1px solid rgba(255,255,255,0.08);
            padding: 0.58rem 0.68rem;
        }}

        .stat-grid span {{
            display: block;
            color: #999999;
            font-family: monospace;
            font-size: 0.66rem;
            font-weight: 850;
            letter-spacing: 0.11em;
            text-transform: uppercase;
            margin-bottom: 0.22rem;
        }}

        .stat-grid strong {{
            color: #ffffff;
            font-size: 0.98rem;
            font-weight: 900;
        }}

        .detail {{
            margin-top: 0.85rem;
            padding: 0.8rem 0.9rem;
            background: rgba(0,0,0,0.24);
            border: 1px solid rgba(255,255,255,0.08);
        }}

        .detail span {{
            display: block;
            color: #999999;
            font-family: monospace;
            font-size: 0.68rem;
            font-weight: 900;
            letter-spacing: 0.13em;
            text-transform: uppercase;
            margin-bottom: 0.3rem;
        }}

        .detail p {{
            color: #eeeeee;
            font-size: 1rem;
            line-height: 1.35;
            margin: 0;
        }}

        .rule {{
            margin-top: 0.85rem;
            padding: 0.62rem 0.78rem;
            color: #ffffff;
            background: rgba(255,75,75,0.18);
            border: 1px solid rgba(255,75,75,0.32);
            font-family: monospace;
            font-weight: 950;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}

        .shot-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.65rem;
            margin-top: 0.8rem;
        }}

        .shot {{
            background: rgba(0,0,0,0.26);
            border: 1px solid rgba(255,255,255,0.08);
            padding: 0.7rem 0.78rem;
        }}

        .shot span {{
            display: block;
            color: #ffcc00;
            font-family: monospace;
            font-size: 0.67rem;
            font-weight: 950;
            letter-spacing: 0.13em;
            text-transform: uppercase;
            margin-bottom: 0.25rem;
        }}

        .shot p {{
            color: #eeeeee;
            font-size: 0.92rem;
            line-height: 1.3;
            margin: 0;
        }}

        .morale-banner {{
            border: 1px solid rgba(255,75,75,0.44);
            background: rgba(255,75,75,0.12);
            padding: 0.8rem 0.9rem;
            margin: 0.8rem 0;
        }}

        .morale-banner strong {{
            display: block;
            color: #ffffff;
            font-size: 1.6rem;
            font-weight: 950;
            letter-spacing: 0.07em;
            line-height: 1.03;
            text-transform: uppercase;
        }}

        .morale-banner span {{
            display: block;
            color: #eeeeee;
            margin-top: 0.35rem;
            line-height: 1.3;
        }}

        @media (max-width: 900px) {{
            .record-title {{ font-size: 2rem; }}
            .card-title {{ font-size: 1.65rem; }}
            .stat-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
            .shot-grid {{ grid-template-columns: 1fr; }}
        }}
        </style>
        """
    )


def render_header(plan: dict, source_label: str):
    context = plan.get("series_context", {}) or {}

    render_html(
        f"""
        <div class="record-shell">
            <div class="record-title">OBS Record View</div>
            <div class="record-subtitle">AI chose the grind · {esc(source_label)} · {esc(datetime.now().strftime("%H:%M"))}</div>
        </div>
        """
    )

    stops = plan.get("stops", []) or []
    render_html(
        f"""
        <div class="hero-card">
            <div class="eyebrow">Commander Decision Locked</div>
            <div class="card-title">{esc(context.get("episode_title", plan.get("quick_button_label", plan.get("quick_preset_label", "Commander Plan"))))}</div>
            <div class="card-subtitle">{esc(context.get("hook", plan.get("quick_description", "Follow the active Commander route.")))}</div>
            <div class="stat-grid">
                <div><span>Mode</span><strong>{esc(plan.get("mode", "Unknown"))}</strong></div>
                <div><span>Timebox</span><strong>{esc(plan.get("available_minutes", "?"))} min</strong></div>
                <div><span>Stops</span><strong>{esc(len(stops))}</strong></div>
                <div><span>Pressure</span><strong>{esc(context.get("pressure", "No reroll"))}</strong></div>
            </div>
            <div class="detail">
                <span>Series Stakes</span>
                <p>{esc(context.get("stakes", "The Commander chose the session. The player follows the plan."))}</p>
            </div>
            <div class="rule">The Commander chose the session. The player follows the plan.</div>
        </div>
        """
    )


def render_series_story(plan: dict):
    context = plan.get("series_context", {}) or {}

    if not context:
        return

    proof_points = context.get("proof_points", []) or []
    proof_items = "".join(
        f"<div class='shot'><span>Proof {index + 1}</span><p>{esc(point)}</p></div>"
        for index, point in enumerate(proof_points[:4])
    )
    morale = context.get("morale", {}) or {}

    render_html(
        f"""
        <div class="hero-card gold-card">
            <div class="eyebrow">Series Brain</div>
            <div class="morale-banner">
                <strong>{esc(morale.get("headline") or context.get("morale_headline") or "JUST ONE MORE CHALLENGE.")}</strong>
                <span>{esc(morale.get("line") or context.get("morale_line") or "Bank one visible piece of progress, then reassess.")}</span>
            </div>
            <div class="card-title">{esc(context.get("thumbnail_text", "AI CHOSE"))}</div>
            <div class="card-subtitle">{esc(context.get("completion_angle", "Completion route"))}</div>
            <div class="detail">
                <span>Route Promise</span>
                <p>{esc(context.get("route_promise", ""))}</p>
            </div>
            <div class="detail">
                <span>Minimum Viable Win</span>
                <p>{esc(morale.get("micro_action") or context.get("morale_micro_action") or "Play the first stop and look only for proof.")}<br>{esc(morale.get("rule") or context.get("morale_rule") or "A partial is still useful data.")}</p>
            </div>
            <div class="detail">
                <span>Pace Line</span>
                <p>{esc(context.get("pace_line", ""))}</p>
            </div>
            <div class="shot-grid">{proof_items}</div>
        </div>
        """
    )


def render_current_objective(plan: dict, stop: dict):
    loadout = loadout_for_stop(stop)
    render_html(
        f"""
        <div class="hero-card blue-card">
            <div class="eyebrow">Current Objective</div>
            <div class="card-title">{esc(stop.get("weapon", "Objective"))}</div>
            <div class="card-subtitle">{esc(stop.get("camo", "Target"))}</div>
            <div class="stat-grid">
                <div><span>Stop</span><strong>{esc(stop.get("stop_number", "?"))}</strong></div>
                <div><span>Status</span><strong>{esc(stop_status(stop).upper())}</strong></div>
                <div><span>Type</span><strong>{esc(stop.get("task_type", "objective"))}</strong></div>
                <div><span>Estimate</span><strong>{esc(stop.get("estimated_minutes", "?"))} min</strong></div>
            </div>
            <div class="detail">
                <span>Objective</span>
                <p>{esc(stop.get("challenge_text", "Complete the assigned objective."))}</p>
            </div>
            <div class="detail">
                <span>Why This Weapon</span>
                <p>{esc(loadout.get("primary_reason") or loadout.get("natural_goal") or "Use the assigned objective weapon.")}</p>
            </div>
            <div class="rule">Complete this, bank progress, then move to the next stop.</div>
        </div>
        """
    )


def render_loadout(stop: dict):
    loadout = loadout_for_stop(stop)
    render_html(
        f"""
        <div class="hero-card green-card">
            <div class="eyebrow">Loadout Commander</div>
            <div class="card-title">{esc(loadout.get("primary", "Use assigned weapon"))}</div>
            <div class="card-subtitle">{esc(loadout.get("template_name", "Template loadout"))}</div>
            <div class="detail">
                <span>Primary Attachments</span>
                <p>{esc(loadout.get("primary_attachments") or "No trusted Commander attachment build available.")}</p>
            </div>
            <div class="detail">
                <span>Attachment Source</span>
                <p>{esc(loadout.get("primary_attachment_source") or loadout.get("ttk_oracle_note") or "Unknown")}</p>
            </div>
            <div class="detail">
                <span>Natural Goal</span>
                <p>{esc(loadout.get("natural_goal", "No natural weapon goal found."))}</p>
            </div>
            <div class="stat-grid">
                <div><span>Source</span><strong>{esc(loadout.get("natural_goal_source", "N/A"))}</strong></div>
                <div><span>Secondary</span><strong>{esc(loadout.get("secondary", "N/A"))}</strong></div>
                <div><span>Wildcard</span><strong>{esc(loadout.get("wildcard", "N/A"))}</strong></div>
                <div><span>Field</span><strong>{esc(loadout.get("field_upgrade", "N/A"))}</strong></div>
            </div>
            <div class="detail">
                <span>Perks / Equipment</span>
                <p>
                    Perks: {esc(loadout.get("perks", "N/A"))}<br>
                    Tactical: {esc(loadout.get("tactical", "N/A"))} ·
                    Lethal: {esc(loadout.get("lethal", "N/A"))} ·
                    Scorestreaks: {esc(loadout.get("scorestreaks", "N/A"))}
                </p>
            </div>
        </div>
        """
    )


def render_shot_list(plan: dict, stop: dict):
    render_html(
        f"""
        <div class="hero-card gold-card">
            <div class="eyebrow">Recording Director</div>
            <div class="card-title">Shot List</div>
            <div class="card-subtitle">Capture decision, class, proof, and debrief</div>
            <div class="shot-grid">
                <div class="shot"><span>Clip 1</span><p>Hold on this OBS view long enough to read the Commander decision.</p></div>
                <div class="shot"><span>Clip 2</span><p>Show the loadout card, then cut to the exact class in-game.</p></div>
                <div class="shot"><span>Clip 3</span><p>Gameplay with the assigned weapon or objective. No rerolls.</p></div>
                <div class="shot"><span>Clip 4</span><p>Capture unlock, progress bar, camo pop, card tier, or match proof.</p></div>
                <div class="shot"><span>Clip 5</span><p>Go to Mission Control, bank levels/progress, then show the next route.</p></div>
                <div class="shot"><span>Clip 6</span><p>End on the debrief. The AI route either worked, partially worked, or failed.</p></div>
            </div>
            <div class="rule">Video story: AI chose my grind. I followed it. The tracker moved.</div>
        </div>
        """
    )

    with st.expander("Copyable recording lines", expanded=False):
        st.text_area(
            "Recording lines",
            value=recording_lines_for_plan(plan),
            height=170,
            label_visibility="collapsed",
        )


def render_debrief(plan: dict):
    counts = count_statuses(plan)
    total = sum(counts.values())
    progress = plan_progress_label(plan)

    if counts["done"] >= 3:
        headline = "Route Worked"
        verdict = "The Commander found a productive route. Keep this logic."
    elif counts["done"] >= 1 or counts["partial"] >= 1:
        headline = "Progress Banked"
        verdict = "The session moved the tracker. Not perfect, but useful."
    elif counts["skipped"] >= 1:
        headline = "Route Needs Reroute"
        verdict = "A blocker was exposed. Mission Control should reroute from the debrief."
    else:
        headline = "Session In Progress"
        verdict = "No result logged yet. Play the objective, then bank the proof."

    render_html(
        f"""
        <div class="hero-card green-card">
            <div class="eyebrow">Session Debrief Snapshot</div>
            <div class="card-title">{esc(headline)}</div>
            <div class="card-subtitle">{esc(verdict)}</div>
            <div class="stat-grid">
                <div><span>Done</span><strong>{esc(counts["done"])}</strong></div>
                <div><span>Partial</span><strong>{esc(counts["partial"])}</strong></div>
                <div><span>Skipped</span><strong>{esc(counts["skipped"])}</strong></div>
                <div><span>Useful</span><strong>{esc(progress)}</strong></div>
            </div>
            <div class="rule">{esc(total)} stop(s) in route memory. Debrief updates when Mission Control logs progress.</div>
        </div>
        """
    )


def main():
    control_cols = st.columns([1, 1, 3])
    with control_cols[0]:
        clean_mode = st.toggle("OBS clean mode", value=True)
    with control_cols[1]:
        if st.button("Refresh view", use_container_width=True):
            st.rerun()

    render_css(clean_mode)

    plan, source_label = current_plan()

    if not plan:
        render_html(
            """
            <div class="record-shell">
                <div class="record-title">No Plan Loaded</div>
                <div class="record-subtitle">Generate a route in Commander Launch, or send a plan to Mission Control.</div>
            </div>
            """
        )
        st.info("Open BO7: Commander Launch, generate a route, then return to OBS Record View.")
        return

    stop = active_stop(plan)

    if not stop:
        st.warning("The active plan has no stops.")
        return

    render_header(plan, source_label)

    col_left, col_right = st.columns([1.08, 0.92], gap="large")

    with col_left:
        render_current_objective(plan, stop)
        render_loadout(stop)

    with col_right:
        render_series_story(plan)
        render_shot_list(plan, stop)
        render_debrief(plan)


if __name__ == "__main__":
    main()

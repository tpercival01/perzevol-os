import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from modules.ui.perzevol_theme import inject_perzevol_theme
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
        return attach_series_context_to_plan(active), "MISSION CONTROL ACTIVE PLAN"

    quick = st.session_state.get("bo7_quick_launch_plan")
    if isinstance(quick, dict) and quick.get("stops"):
        return attach_series_context_to_plan(quick), "COMMANDER LAUNCH PLAN"

    latest = load_latest_launch_plan()
    if latest:
        return attach_series_context_to_plan(latest), "RECOVERED LATEST LAUNCH PLAN"

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
    inject_perzevol_theme(clean_mode=clean_mode, screen="obs_record")

    render_html(
        """
        <style>
        .obs-two-col {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            gap: 1rem;
            margin-top: 1rem;
        }

        .obs-morale-card .obs-headline {
            font-size: clamp(1.6rem, 3.4vw, 3.2rem);
            line-height: 0.95;
        }

        .obs-morale-card .obs-subhead {
            margin-top: 0.75rem;
            letter-spacing: 0.08em;
        }

        .obs-status-card .obs-mini-body,
        .obs-loadout-card .obs-mini-body {
            font-size: 0.98rem;
            line-height: 1.45;
        }

        .director-notes-wrap {
            margin-top: 0.75rem;
        }

        @media (max-width: 900px) {
            .obs-two-col {
                grid-template-columns: 1fr;
            }
        }
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
                <p>{esc(context.get("stakes", "AI CHOSE THE GRIND. NO REROLLS UNLESS IMPOSSIBLE."))}</p>
            </div>
            <div class="rule">AI CHOSE THE GRIND. NO REROLLS UNLESS IMPOSSIBLE.</div>
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
            <div class="eyebrow">Series Director</div>
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
            <div class="rule">BANK THE UGLY PROGRESS. PROOF OVER PERFECTION.</div>
        </div>
        """
    )


def render_loadout(stop: dict):
    loadout = loadout_for_stop(stop)
    render_html(
        f"""
        <div class="hero-card green-card">
            <div class="eyebrow">Assigned Class</div>
            <div class="card-title">{esc(loadout.get("primary", "Use assigned weapon"))}</div>
            <div class="card-subtitle">{esc(loadout.get("template_name", "Template loadout"))}</div>
            <div class="detail">
                <span>Primary Attachments</span>
                <p>{esc(loadout.get("primary_attachments") or "No trusted Commander attachment build available.")}</p>
            </div>
            <div class="detail">
                <span>Attachment Source</span>
                <p>{esc(loadout.get("primary_attachment_source") or "Commander/manual build")}</p>
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
                <div class="shot"><span>Clip 5</span><p>Bank the stop from this OBS view, then move to the next assigned objective.</p></div>
                <div class="shot"><span>Clip 6</span><p>End on the debrief. The AI route either worked, partially worked, or failed.</p></div>
            </div>
            <div class="rule">AI CHOSE THE GRIND. I FOLLOWED THE ROUTE. THE TRACKER MOVED.</div>
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



def plan_stops(plan: dict) -> list[dict]:
    stops = plan.get("stops", []) if isinstance(plan, dict) else []
    return stops if isinstance(stops, list) else []


def active_stop_index(plan: dict) -> int:
    stops = plan_stops(plan)

    for index, stop in enumerate(stops):
        if stop_status(stop) not in RESOLVED_STATUSES:
            return index

    return max(0, len(stops) - 1)


def ensure_record_stop_index(plan: dict):
    stops = plan_stops(plan)
    plan_id = clean(plan.get("plan_id") or plan.get("quick_button_label") or plan.get("quick_preset_label") or len(stops))

    if st.session_state.get("bo7_obs_plan_id") != plan_id:
        st.session_state.bo7_obs_plan_id = plan_id
        st.session_state.bo7_obs_stop_index = active_stop_index(plan)

    if "bo7_obs_stop_index" not in st.session_state:
        st.session_state.bo7_obs_stop_index = active_stop_index(plan)

    if stops:
        st.session_state.bo7_obs_stop_index = max(
            0,
            min(int(st.session_state.bo7_obs_stop_index), len(stops) - 1),
        )
    else:
        st.session_state.bo7_obs_stop_index = 0


def selected_record_stop(plan: dict) -> dict:
    stops = plan_stops(plan)
    if not stops:
        return {}

    ensure_record_stop_index(plan)
    return stops[int(st.session_state.get("bo7_obs_stop_index", 0))]


def move_record_stop(plan: dict, delta: int):
    stops = plan_stops(plan)
    if not stops:
        return

    ensure_record_stop_index(plan)
    current = int(st.session_state.get("bo7_obs_stop_index", 0))
    st.session_state.bo7_obs_stop_index = max(0, min(current + delta, len(stops) - 1))


def mark_record_stop(stop: dict, status: str):
    task_id = clean(stop.get("task_id"))
    if not task_id:
        return

    results = stop_results()
    results[task_id] = {
        "status": status,
        "result": "OBS quick mark",
        "blame": "Successful operation" if status == "done" else "",
        "notes": "Marked from OBS Record View.",
        "stop_number": stop.get("stop_number", ""),
        "weapon": stop.get("weapon", ""),
        "camo": stop.get("camo", ""),
        "mode": stop.get("mode", ""),
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
    }
    st.session_state.bo7_stop_results = results


def undo_record_stop(stop: dict):
    task_id = clean(stop.get("task_id"))
    if not task_id:
        return

    results = stop_results()
    if task_id in results:
        del results[task_id]
    st.session_state.bo7_stop_results = results


def render_obs_command_bar(plan: dict, stop: dict):
    stops = plan_stops(plan)
    ensure_record_stop_index(plan)
    index = int(st.session_state.get("bo7_obs_stop_index", 0))
    total = len(stops)
    cols = st.columns(6, gap="small")

    with cols[0]:
        if st.button("← PREV", use_container_width=True, disabled=index <= 0):
            move_record_stop(plan, -1)
            st.rerun()

    with cols[1]:
        if st.button("NEXT →", use_container_width=True, disabled=index >= total - 1):
            move_record_stop(plan, 1)
            st.rerun()

    with cols[2]:
        if st.button("DONE", use_container_width=True):
            mark_record_stop(stop, "done")
            st.rerun()

    with cols[3]:
        if st.button("PARTIAL", use_container_width=True):
            mark_record_stop(stop, "partial")
            st.rerun()

    with cols[4]:
        if st.button("SKIP", use_container_width=True):
            mark_record_stop(stop, "skipped")
            st.rerun()

    with cols[5]:
        if st.button("UNDO", use_container_width=True):
            undo_record_stop(stop)
            st.rerun()


def line_clamp_text(value: Any, fallback: str = "") -> str:
    text = clean(value) or fallback
    return esc(text)


def render_obs_viewport_frame(plan: dict, stop: dict, source_label: str):
    context = plan.get("series_context", {}) or {}
    loadout = loadout_for_stop(stop)
    morale = context.get("morale", {}) or {}
    counts = count_statuses(plan)

    if counts["done"] >= 3:
        verdict = "ROUTE WORKED"
        verdict_note = "The Commander found a productive route. Keep this logic."
    elif counts["done"] >= 1 or counts["partial"] >= 1:
        verdict = "PROGRESS BANKED"
        verdict_note = "The tracker moved. Not perfect, but worth it."
    elif counts["skipped"] >= 1:
        verdict = "REROUTE REQUIRED"
        verdict_note = "A blocker was exposed. Debrief it honestly."
    else:
        verdict = "SESSION LIVE"
        verdict_note = "No proof banked yet. Play the assigned objective."

    stops = plan.get("stops", []) or []
    stop_number = clean(stop.get("stop_number")) or str(st.session_state.get("bo7_obs_stop_index", 0) + 1)
    morale_headline = (
        morale.get("headline")
        or context.get("morale_headline")
        or "THE GAME WANTS YOU TO QUIT. DO NOT GIVE IT THAT WIN."
    )
    morale_line = f"AI chose {clean(plan.get('mode')) or 'the route'} • No reroll unless impossible"

    render_html(
        f"""
        <div class="obs-frame">
            <div class="obs-topline">
                <div>
                    <div class="obs-title">OBS RECORD VIEW</div>
                    <div class="obs-subtitle">AI chose the grind · {esc(source_label)} · {esc(datetime.now().strftime("%H:%M"))}</div>
                </div>
                <div class="obs-stat-grid">
                    <div class="obs-stat"><span class="obs-label">Mode</span><div class="obs-value">{esc(plan.get("mode", "Unknown"))}</div></div>
                    <div class="obs-stat"><span class="obs-label">Timebox</span><div class="obs-value">{esc(plan.get("available_minutes", "?"))} min</div></div>
                    <div class="obs-stat"><span class="obs-label">Stop</span><div class="obs-value">{esc(stop_number)} / {esc(len(stops))}</div></div>
                    <div class="obs-stat"><span class="obs-label">Status</span><div class="obs-value">{esc(stop_status(stop).upper())}</div></div>
                </div>
            </div>

            <div class="obs-two-col">
                <div class="obs-primary">
                    <div class="obs-kicker">Current Objective · Commander Decision Locked</div>
                    <div class="obs-headline">{esc(stop.get("weapon", "Objective"))}</div>
                    <div class="obs-subhead">{esc(stop.get("camo", "Assigned Target"))}</div>
                    <div class="obs-textbox">
                        <span class="obs-label">Objective</span>
                        <p>{line_clamp_text(stop.get("challenge_text"), "Complete the assigned objective.")}</p>
                    </div>
                    <div class="obs-rule">NO REROLLS UNLESS IMPOSSIBLE · BANK THE UGLY PROGRESS</div>
                </div>

                <div class="obs-director obs-morale-card">
                    <div class="obs-kicker">Commander Line</div>
                    <div class="obs-headline">{line_clamp_text(morale_headline, "THE GAME WANTS YOU TO QUIT. DO NOT GIVE IT THAT WIN.")}</div>
                    <div class="obs-subhead">{esc(morale_line)}</div>
                    <div class="obs-rule">PROOF OVER PERFECTION</div>
                </div>
            </div>

            <div class="obs-two-col">
                <div class="obs-mini-card green obs-loadout-card">
                    <div class="obs-kicker">Assigned Class</div>
                    <div class="obs-mini-title">{line_clamp_text(loadout.get("primary"), "Use assigned weapon")}</div>
                    <div class="obs-mini-body">
                        <span class="obs-label">Build Rule</span>
                        {line_clamp_text(loadout.get("primary_attachments"), "Use your verified in-game build. TTK Oracle is detached.")}
                    </div>
                </div>

                <div class="obs-mini-card red obs-status-card">
                    <div class="obs-kicker">Session Status / Debrief</div>
                    <div class="obs-mini-title">{esc(verdict)}</div>
                    <div class="obs-mini-body">
                        <span class="obs-label">Tracker State</span>
                        Done {esc(counts["done"])} · Partial {esc(counts["partial"])} · Skipped {esc(counts["skipped"])}<br>
                        {esc(verdict_note)}
                    </div>
                </div>
            </div>
        </div>
        """
    )


def render_director_notes(plan: dict, stop: dict):
    context = plan.get("series_context", {}) or {}
    proof_points = context.get("proof_points", []) or []

    if not proof_points:
        proof_points = [
            "Show the Commander decision before gameplay.",
            "Capture progress proof after the objective moves.",
            "End on the debrief or Finish Line page.",
        ]

    with st.expander("Director Notes", expanded=False):
        st.markdown("**Proof checklist**")
        for index, point in enumerate(proof_points[:6], start=1):
            st.write(f"{index}. {point}")

        st.text_area(
            "Copyable recording lines",
            value=recording_lines_for_plan(plan),
            height=170,
            key=f"bo7_director_notes_{stop.get('task_id', 'active')}",
        )


def main():
    with st.sidebar:
        clean_mode = st.toggle("OBS clean mode", value=True)
        show_director_notes = st.toggle("Show director notes", value=False)
        if st.button("Refresh", use_container_width=True):
            st.rerun()

    render_css(clean_mode)

    plan, source_label = current_plan()

    if not plan:
        render_html(
            """
            <div class="obs-frame">
                <div class="obs-primary">
                    <div class="obs-kicker">No Plan Loaded</div>
                    <div class="obs-headline">Generate A Route First</div>
                    <div class="obs-textbox"><p>Open Commander Launch, generate a route, then return to OBS Record View.</p></div>
                    <div class="obs-rule">AI CHOSE THE GRIND AFTER A PLAN EXISTS</div>
                </div>
            </div>
            """
        )
        return

    ensure_record_stop_index(plan)
    stop = selected_record_stop(plan)

    if not stop:
        st.warning("The active plan has no stops.")
        return

    render_obs_command_bar(plan, stop)
    render_obs_viewport_frame(plan, stop, source_label)

    if show_director_notes:
        render_director_notes(plan, stop)


if __name__ == "__main__":
    main()

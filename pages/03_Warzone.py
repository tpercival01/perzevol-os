import csv
import json
from pathlib import Path
import pandas as pd

import streamlit as st

from modules.warzone.killchain_engine import (
    BLAME_OPTIONS,
    ENERGY_LEVELS,
    MODES,
    MOTIVATION_LEVELS,
    RESULT_OPTIONS,
    SESSION_GOALS,
    apply_mission_result,
    generate_commander_reply,
    generate_mission,
    get_available_tasks,
    get_ranked_tasks,
    load_hub_progress,
    load_tracker_tasks,
    summarise_sessions,
    summarise_tasks,
)


STATE_DIR = Path("data/bo7_state")
COMPLETION_STATE_PATH = STATE_DIR / "completion_state.json"
SESSION_LOG_PATH = STATE_DIR / "session_log.csv"


def ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_completion_state():
    ensure_state_dir()
    if not COMPLETION_STATE_PATH.exists():
        return {}
    try:
        with COMPLETION_STATE_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError:
        return {}


def save_completion_state(completion_state):
    ensure_state_dir()
    with COMPLETION_STATE_PATH.open("w", encoding="utf-8") as file:
        json.dump(completion_state, file, indent=2)


def apply_completion_state(tasks, completion_state):
    for task in tasks:
        task_id = task.get("task_id")
        if task_id in completion_state:
            task["last_result"] = completion_state[task_id].get("result", "Camo completed")
            task["completed_on_session"] = completion_state[task_id].get("result") == "Camo completed"
    return tasks


def load_persisted_session_log():
    ensure_state_dir()
    if not SESSION_LOG_PATH.exists():
        return []
    with SESSION_LOG_PATH.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def append_session_log(row):
    ensure_state_dir()
    fieldnames = [
        "mission_id", "time", "mode", "target", "challenge",
        "recommended_mode", "command", "time_limit", "result", "blame", "notes",
    ]
    file_exists = SESSION_LOG_PATH.exists()
    with SESSION_LOG_PATH.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in fieldnames})


def mark_task_complete(task, reason="Manual completion"):
    completion_state = load_completion_state()
    completion_state[task["task_id"]] = {
        "result": "Camo completed",
        "mode": task["mode"],
        "weapon": task["weapon"],
        "camo": task["camo"],
        "reason": reason,
    }
    save_completion_state(completion_state)
    for current_task in st.session_state.bo7_tasks:
        if current_task["task_id"] == task["task_id"]:
            current_task["last_result"] = "Camo completed"
            current_task["completed_on_session"] = True
            break


def reset_persistent_state():
    ensure_state_dir()
    if COMPLETION_STATE_PATH.exists():
        COMPLETION_STATE_PATH.unlink()
    if SESSION_LOG_PATH.exists():
        SESSION_LOG_PATH.unlink()


def task_label(task):
    return f"{task['mode']} | {task['weapon']} — {task['camo']} | {task['challenge_text']}"


def initialise_state():
    if "bo7_completion_state" not in st.session_state:
        st.session_state.bo7_completion_state = load_completion_state()

    if "bo7_tasks" not in st.session_state:
        tasks = load_tracker_tasks()
        st.session_state.bo7_tasks = apply_completion_state(
            tasks, st.session_state.bo7_completion_state,
        )

    if "bo7_progress" not in st.session_state:
        st.session_state.bo7_progress = load_hub_progress()

    if "bo7_latest_mission" not in st.session_state:
        st.session_state.bo7_latest_mission = None

    if "bo7_session_log" not in st.session_state:
        st.session_state.bo7_session_log = load_persisted_session_log()

    if "bo7_chat" not in st.session_state:
        st.session_state.bo7_chat = [
            {
                "role": "assistant",
                "content": (
                    "Completion Commander online. Tracker loaded. "
                    "Persistent memory active. Human choice is deprecated."
                ),
            }
        ]

    # Persist form state across reruns
    if "bo7_form_minutes" not in st.session_state:
        st.session_state.bo7_form_minutes = 90
    if "bo7_form_energy" not in st.session_state:
        st.session_state.bo7_form_energy = ENERGY_LEVELS[0]
    if "bo7_form_motivation" not in st.session_state:
        st.session_state.bo7_form_motivation = MOTIVATION_LEVELS[1]
    if "bo7_form_preferred_mode" not in st.session_state:
        st.session_state.bo7_form_preferred_mode = MODES[0]
    if "bo7_form_avoided_mode" not in st.session_state:
        st.session_state.bo7_form_avoided_mode = MODES[2]
    if "bo7_form_session_goal" not in st.session_state:
        st.session_state.bo7_form_session_goal = SESSION_GOALS[0]


CLEAN_DATA_DIR = Path("data/bo7_clean")

QUICK_UPDATE_FILES = {
    # Camos
    "Apocalypse / Warzone camos": "apocalypse_status.csv",
    "Singularity / Multiplayer camos": "singularity_status.csv",
    "Infestation / Zombies camos": "infestation_status.csv",
    "Genesis / Co-Op camos": "genesis_status.csv",
    # Prestige & Badges
    "Weapon prestige": "weapon_prestige.csv",
    "Mastery badges — weapons": "mastery_badges_weapons.csv",
    "Mastery badges — equipment MP": "mastery_badges_equipment_mp.csv",
    "Mastery badges — equipment Zombies": "mastery_badges_equipment_zombies.csv",
    # Reticles
    "Reticles": "reticles.csv",
    # Misc Challenges
    "Misc challenges — MP": "misc_challenges_mp.csv",
    "Misc challenges — Zombies": "misc_challenges_zombies.csv",
    # Calling Cards
    "Calling cards — Co-Op / Endgame": "calling_cards_sp.csv",
    "Calling cards — Multiplayer": "calling_cards_mp.csv",
    "Calling cards — Zombies": "calling_cards_zm.csv",
    "Calling cards — Warzone": "calling_cards_wz.csv",
    # Titles
    "Titles": "titles.csv",
}
 
QUICK_UPDATE_ID_COLUMNS = {
    "apocalypse_status.csv": ["mode", "chain", "weapon_class", "weapon"],
    "singularity_status.csv": ["mode", "chain", "weapon_class", "weapon"],
    "infestation_status.csv": ["mode", "chain", "weapon_class", "weapon"],
    "genesis_status.csv": ["mode", "chain", "weapon_class", "weapon"],
    "weapon_prestige.csv": ["weapon_class", "weapon", "max_level"],
    "mastery_badges_weapons.csv": ["weapon_class", "weapon"],
    "mastery_badges_equipment_mp.csv": ["mode", "category", "item"],
    "mastery_badges_equipment_zombies.csv": ["mode", "category", "item"],
    "reticles.csv": ["mode", "classification", "reticle"],
    "misc_challenges_mp.csv": ["mode", "category", "sub_category", "challenge"],
    "misc_challenges_zombies.csv": ["mode", "category", "sub_category", "challenge"],
    "calling_cards_sp.csv": ["mode", "category", "sub_category", "challenge", "requirement",
                              "tier1_target", "tier2_target", "tier3_target", "tier4_target", "tier5_target"],
    "calling_cards_mp.csv": ["mode", "category", "sub_category", "challenge", "requirement",
                              "tier1_target", "tier2_target", "tier3_target", "tier4_target", "tier5_target"],
    "calling_cards_zm.csv": ["mode", "category", "sub_category", "challenge", "requirement",
                              "tier1_target", "tier2_target", "tier3_target", "tier4_target", "tier5_target"],
    "calling_cards_wz.csv": ["mode", "category", "sub_category", "challenge", "requirement",
                              "tier1_target", "tier2_target", "tier3_target", "tier4_target", "tier5_target"],
    "titles.csv": ["mode", "title", "criteria"],
}



def quick_update_path(filename):
    return CLEAN_DATA_DIR / filename


def load_quick_update_csv(filename):
    path = quick_update_path(filename)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def save_quick_update_csv(filename, dataframe):
    path = quick_update_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(path, index=False)


def is_true_cell(value):
    return str(value).strip().upper() in {"TRUE", "YES", "DONE", "COMPLETE", "COMPLETED", "✅"}


def bool_to_csv_value(value):
    return "TRUE" if bool(value) else "FALSE"


def quick_update_status_columns(filename, dataframe):
    id_columns = QUICK_UPDATE_ID_COLUMNS.get(filename, [])
    return [column for column in dataframe.columns if column not in id_columns]


def render_quick_completion_grid():
    st.caption(
        "Use this when you go further than the Commander ordered. "
        "Tick every camo/prestige milestone you actually completed, save, then reload orders."
    )

    selected_label = st.selectbox(
        "Data source",
        list(QUICK_UPDATE_FILES.keys()),
        key="quick_update_source",
    )

    filename = QUICK_UPDATE_FILES[selected_label]
    dataframe = load_quick_update_csv(filename)

    if dataframe.empty:
        st.warning(f"No file found for `{filename}`.")
        return

    id_columns = QUICK_UPDATE_ID_COLUMNS.get(filename, [])
    status_columns = quick_update_status_columns(filename, dataframe)

    if "weapon_class" in dataframe.columns:
        weapon_classes = ["All"] + sorted(
            value for value in dataframe["weapon_class"].dropna().unique().tolist() if value
        )
        selected_class = st.selectbox(
            "Weapon class", weapon_classes, key=f"quick_update_class_{filename}",
        )
    else:
        selected_class = "All"

    filtered_dataframe = dataframe.copy()

    if selected_class != "All" and "weapon_class" in filtered_dataframe.columns:
        filtered_dataframe = filtered_dataframe[
            filtered_dataframe["weapon_class"] == selected_class
        ]

    if "weapon" in filtered_dataframe.columns:
        weapon_options = ["All"] + sorted(
            value for value in filtered_dataframe["weapon"].dropna().unique().tolist() if value
        )
        selected_weapon = st.selectbox(
            "Weapon", weapon_options, key=f"quick_update_weapon_{filename}",
        )
        if selected_weapon != "All":
            filtered_dataframe = filtered_dataframe[
                filtered_dataframe["weapon"] == selected_weapon
            ]

    if filtered_dataframe.empty:
        st.warning("No rows match this filter.")
        return

    grid_dataframe = filtered_dataframe.copy()
    for column in status_columns:
        grid_dataframe[column] = grid_dataframe[column].apply(is_true_cell)

    column_config = {
        column: st.column_config.CheckboxColumn(column) for column in status_columns
    }

    edited_dataframe = st.data_editor(
        grid_dataframe,
        use_container_width=True,
        hide_index=False,
        disabled=id_columns,
        column_config=column_config,
        key=f"quick_update_grid_{filename}",
    )

    if st.button("SAVE QUICK UPDATE", use_container_width=True):
        updated_dataframe = dataframe.copy()
        for row_index, edited_row in edited_dataframe.iterrows():
            for column in status_columns:
                updated_dataframe.loc[row_index, column] = bool_to_csv_value(edited_row[column])

        save_quick_update_csv(filename, updated_dataframe)

        st.session_state.bo7_completion_state = load_completion_state()
        st.session_state.bo7_tasks = apply_completion_state(
            load_tracker_tasks(), st.session_state.bo7_completion_state,
        )
        st.session_state.bo7_progress = load_hub_progress()
        st.session_state.bo7_latest_mission = None

        st.success("Quick update saved. Orders reloaded from clean CSV data.")
        st.rerun()


initialise_state()

# ─── STYLES ───────────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    .main {
        background: radial-gradient(circle at top, #141821 0%, #07080a 55%, #020303 100%);
    }
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    .commander-title {
        font-size: 3.8rem;
        font-weight: 900;
        letter-spacing: 0.08em;
        margin-bottom: 0;
        color: #f2f2f2;
        text-transform: uppercase;
    }
    .commander-subtitle {
        color: #ff4b4b;
        font-size: 1.05rem;
        letter-spacing: 0.28em;
        text-transform: uppercase;
        margin-top: -0.3rem;
    }
    .commander-directive {
        border-left: 4px solid #ff4b4b;
        padding: 0.8rem 1rem;
        margin-top: 1.2rem;
        background: rgba(255, 75, 75, 0.08);
        color: #dddddd;
        font-family: monospace;
    }
    .order-weapon {
        font-size: 3.2rem;
        font-weight: 900;
        color: #ffffff;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        line-height: 1.1;
        margin-bottom: 0.2rem;
    }
    .order-camo {
        font-size: 1.6rem;
        font-weight: 700;
        color: #ff4b4b;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 1rem;
    }
    .order-mode {
        font-size: 0.95rem;
        color: #888888;
        letter-spacing: 0.2em;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }
    .order-challenge {
        font-size: 1.15rem;
        color: #dddddd;
        font-family: monospace;
        background: rgba(255,255,255,0.04);
        border-left: 3px solid #ff4b4b;
        padding: 0.8rem 1rem;
        margin-bottom: 1.5rem;
    }
    .order-commentary {
        font-size: 0.85rem;
        color: #666666;
        font-style: italic;
        margin-top: 1rem;
        font-family: monospace;
    }
    .order-strategy {
        font-size: 0.9rem;
        color: #aaaaaa;
        font-family: monospace;
        margin-bottom: 0.5rem;
    }
    @media (max-width: 900px) {
        .commander-title { font-size: 2.2rem; }
        .order-weapon { font-size: 2rem; }
        .order-camo { font-size: 1.2rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── HEADER ───────────────────────────────────────────────────────────────────

st.markdown("<div class='commander-title'>COMPLETION COMMANDER</div>", unsafe_allow_html=True)
st.markdown("<div class='commander-subtitle'>AI BO7 100% Tracker</div>", unsafe_allow_html=True)
st.markdown(
    """
    <div class="commander-directive">
        DIRECTIVE: 100% BLACK OPS 7 BEFORE MW4.<br>
        HUMAN OPERATOR: THOMAS<br>
        ACTIVE STRATEGY: EXACT ORDERS. FAST LOGGING. PERSISTENT MEMORY.<br>
        WARNING: HUMAN MOTIVATION CLASSIFIED AS UNRELIABLE
    </div>
    """,
    unsafe_allow_html=True,
)

st.divider()

# ─── TABS ─────────────────────────────────────────────────────────────────────

tab_mission, tab_quick_update, tab_tracker, tab_chat, tab_log, tab_protocol = st.tabs(
    ["Mission Control", "Quick Update", "Tracker", "AI Chat", "Session Log", "Protocol"]
)

# ─── MISSION CONTROL ──────────────────────────────────────────────────────────

with tab_mission:

    mission = st.session_state.bo7_latest_mission

    # ── STATE 2: ACTIVE MISSION ──
    if mission:
        st.markdown(f"<div class='order-mode'>☣ {mission['mode']} — ORDERS ACTIVE</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='order-weapon'>{mission['weapon'] if 'weapon' in mission else mission['target'].split('—')[0].strip()}</div>", unsafe_allow_html=True)

        camo_display = mission['target'].split('—')[-1].strip() if '—' in mission['target'] else mission['target']
        st.markdown(f"<div class='order-camo'>{camo_display}</div>", unsafe_allow_html=True)

        st.markdown(f"<div class='order-challenge'>{mission['challenge_text']}</div>", unsafe_allow_html=True)

        st.markdown(f"<div class='order-strategy'>▶ {mission['strategy']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='order-strategy'>✕ AVOID: {mission['avoid']}</div>", unsafe_allow_html=True)

        st.markdown(f"<div class='order-commentary'>{mission['ai_commentary']}</div>", unsafe_allow_html=True)

        st.divider()

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("✅  COMPLETED", type="primary", use_container_width=True):
                log_row = {
                    "mission_id": mission["mission_id"],
                    "time": mission["timestamp"],
                    "mode": mission["mode"],
                    "target": mission["target"],
                    "challenge": mission["challenge_text"],
                    "recommended_mode": mission["recommended_mode"],
                    "command": mission["command"],
                    "time_limit": mission["time_limit"],
                    "result": "Camo completed",
                    "blame": "Successful operation",
                    "notes": "",
                }
                st.session_state.bo7_session_log.append(log_row)
                append_session_log(log_row)

                st.session_state.bo7_tasks = apply_mission_result(
                    tasks=st.session_state.bo7_tasks,
                    mission=mission,
                    result="Camo completed",
                )

                if mission.get("task_id"):
                    completion_state = load_completion_state()
                    completion_state[mission["task_id"]] = {
                        "result": "Camo completed",
                        "mode": mission["mode"],
                        "target": mission["target"],
                        "reason": "Mission result logged",
                    }
                    save_completion_state(completion_state)
                    st.session_state.bo7_completion_state = completion_state

                st.session_state.bo7_latest_mission = None
                st.rerun()

        with col2:
            if st.button("⚠️  PARTIAL", use_container_width=True):
                log_row = {
                    "mission_id": mission["mission_id"],
                    "time": mission["timestamp"],
                    "mode": mission["mode"],
                    "target": mission["target"],
                    "challenge": mission["challenge_text"],
                    "recommended_mode": mission["recommended_mode"],
                    "command": mission["command"],
                    "time_limit": mission["time_limit"],
                    "result": "Partial progress",
                    "blame": "Human avoidance",
                    "notes": "",
                }
                st.session_state.bo7_session_log.append(log_row)
                append_session_log(log_row)

                st.session_state.bo7_tasks = apply_mission_result(
                    tasks=st.session_state.bo7_tasks,
                    mission=mission,
                    result="Partial progress",
                )
                st.session_state.bo7_latest_mission = None
                st.rerun()

        with col3:
            if st.button("❌  BLOCKED", use_container_width=True):
                log_row = {
                    "mission_id": mission["mission_id"],
                    "time": mission["timestamp"],
                    "mode": mission["mode"],
                    "target": mission["target"],
                    "challenge": mission["challenge_text"],
                    "recommended_mode": mission["recommended_mode"],
                    "command": mission["command"],
                    "time_limit": mission["time_limit"],
                    "result": "Blocked / wrong requirement",
                    "blame": "Bad AI assignment",
                    "notes": "",
                }
                st.session_state.bo7_session_log.append(log_row)
                append_session_log(log_row)

                st.session_state.bo7_tasks = apply_mission_result(
                    tasks=st.session_state.bo7_tasks,
                    mission=mission,
                    result="Blocked / wrong requirement",
                )
                st.session_state.bo7_latest_mission = None
                st.rerun()

    # ── STATE 1: NO ACTIVE MISSION ──
    else:
        task_summary = summarise_tasks(st.session_state.bo7_tasks)

        st.caption(
            f"Tasks loaded: {task_summary['total']} · "
            f"Available: {task_summary['available']} · "
            f"Locked: {task_summary['locked']} · "
            f"Done: {len(st.session_state.bo7_completion_state)}"
        )

        st.divider()

        available_minutes = st.slider(
            "Available time (minutes)",
            min_value=15, max_value=240,
            value=st.session_state.bo7_form_minutes,
            step=15,
            key="slider_minutes",
        )

        col1, col2 = st.columns(2)
        with col1:
            energy = st.selectbox(
                "Energy", ENERGY_LEVELS,
                index=ENERGY_LEVELS.index(st.session_state.bo7_form_energy),
                key="select_energy",
            )
            preferred_mode = st.selectbox(
                "Preferred mode", MODES,
                index=MODES.index(st.session_state.bo7_form_preferred_mode),
                key="select_preferred",
            )
            session_goal = st.selectbox(
                "Session goal", SESSION_GOALS,
                index=SESSION_GOALS.index(st.session_state.bo7_form_session_goal),
                key="select_goal",
            )

        with col2:
            motivation = st.selectbox(
                "Motivation", MOTIVATION_LEVELS,
                index=MOTIVATION_LEVELS.index(st.session_state.bo7_form_motivation),
                key="select_motivation",
            )
            avoided_mode = st.selectbox(
                "Avoid mode", MODES,
                index=MODES.index(st.session_state.bo7_form_avoided_mode),
                key="select_avoided",
            )

        st.divider()

        if st.button("GENERATE ORDERS", type="primary", use_container_width=True):
            # Persist form state
            st.session_state.bo7_form_minutes = available_minutes
            st.session_state.bo7_form_energy = energy
            st.session_state.bo7_form_motivation = motivation
            st.session_state.bo7_form_preferred_mode = preferred_mode
            st.session_state.bo7_form_avoided_mode = avoided_mode
            st.session_state.bo7_form_session_goal = session_goal

            st.session_state.bo7_latest_mission = generate_mission(
                tasks=st.session_state.bo7_tasks,
                available_minutes=available_minutes,
                energy=energy,
                motivation=motivation,
                preferred_mode=preferred_mode,
                avoided_mode=avoided_mode,
                session_goal=session_goal,
                operator_note="",
            )
            st.rerun()

# ─── QUICK UPDATE ─────────────────────────────────────────────────────────────

with tab_quick_update:
    st.subheader("Quick Update")
    st.markdown(
        "Use this when you complete more than the Commander ordered. "
        "Tick everything you actually completed, save, then generate the next order."
    )
    render_quick_completion_grid()

# ─── TRACKER ──────────────────────────────────────────────────────────────────

with tab_tracker:
    st.subheader("Current Tracker State")

    task_summary = summarise_tasks(st.session_state.bo7_tasks)
    session_summary = summarise_sessions(st.session_state.bo7_session_log)

    cols = st.columns(5)
    cols[0].metric("Loaded Tasks", task_summary["total"])
    cols[1].metric("Remaining", task_summary["available"])
    cols[2].metric("Locked", task_summary["locked"])
    cols[3].metric("Remembered Done", len(st.session_state.bo7_completion_state))
    cols[4].metric("Logged Missions", session_summary["total"])

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Reload tracker CSVs + saved state", use_container_width=True):
            st.session_state.bo7_completion_state = load_completion_state()
            tasks = load_tracker_tasks()
            st.session_state.bo7_tasks = apply_completion_state(
                tasks, st.session_state.bo7_completion_state,
            )
            st.session_state.bo7_progress = load_hub_progress()
            st.session_state.bo7_latest_mission = None
            st.session_state.bo7_session_log = load_persisted_session_log()
            st.success("Tracker CSVs and saved completion state reloaded.")
            st.rerun()

    with col2:
        if st.button("DANGER: Reset saved state", use_container_width=True):
            reset_persistent_state()
            st.session_state.bo7_completion_state = {}
            st.session_state.bo7_tasks = load_tracker_tasks()
            st.session_state.bo7_session_log = []
            st.session_state.bo7_latest_mission = None
            st.error("Saved state reset.")
            st.rerun()

    st.divider()

    st.markdown("### Remaining Camo Queue")

    available_tasks = get_available_tasks(st.session_state.bo7_tasks)

    if available_tasks:
        st.dataframe(
            [
                {
                    "Mode": task["mode"],
                    "Chain": task["chain"],
                    "Class": task["weapon_class"],
                    "Weapon": task["weapon"],
                    "Next Camo": task["camo"],
                    "Challenge": task["challenge_text"],
                    "Recommended Mode": task["recommended_mode"],
                    "Weapon Progress": f"{task['weapon_progress']:.2f}%",
                }
                for task in available_tasks
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("No remaining unlocked camo tasks detected.")

    st.divider()

    st.markdown("### Persisted completions")

    if st.session_state.bo7_completion_state:
        st.dataframe(
            [
                {
                    "Task ID": task_id,
                    "Result": data.get("result", ""),
                    "Mode": data.get("mode", ""),
                    "Target": data.get("target", data.get("weapon", "")),
                    "Reason": data.get("reason", ""),
                }
                for task_id, data in st.session_state.bo7_completion_state.items()
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No persisted completions yet.")

# ─── AI CHAT ──────────────────────────────────────────────────────────────────

with tab_chat:
    st.subheader("AI Chat")

    for message in st.session_state.bo7_chat:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_prompt = st.chat_input("Ask the Completion Commander what to do next...")

    if user_prompt:
        st.session_state.bo7_chat.append({"role": "user", "content": user_prompt})

        reply = generate_commander_reply(
            message=user_prompt,
            tasks=st.session_state.bo7_tasks,
            latest_mission=st.session_state.bo7_latest_mission,
            session_log=st.session_state.bo7_session_log,
        )

        st.session_state.bo7_chat.append({"role": "assistant", "content": reply})
        st.rerun()

# ─── SESSION LOG ──────────────────────────────────────────────────────────────

with tab_log:
    st.subheader("Session Log")

    summary = summarise_sessions(st.session_state.bo7_session_log)

    cols = st.columns(5)
    cols[0].metric("Sessions", summary["total"])
    cols[1].metric("Completed", summary["completed"])
    cols[2].metric("Partial", summary["partial"])
    cols[3].metric("Blocked", summary["blocked"])
    cols[4].metric("Failed", summary["failed"])

    st.caption(f"Persistent log path: `{SESSION_LOG_PATH}`")

    st.divider()

    if st.session_state.bo7_session_log:
        st.dataframe(
            st.session_state.bo7_session_log,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("No BO7 missions logged yet.")

# ─── PROTOCOL ─────────────────────────────────────────────────────────────────

with tab_protocol:
    st.subheader("Experiment Protocol")

    st.markdown(
        """
        ### Prime directive

        Reach as close to **100% Black Ops 7 completion** as possible before **MW4**.

        ### Persistence rule

        - Original tracker CSVs are never edited.
        - Completed camos are remembered in `data/bo7_state/completion_state.json`.
        - Every logged mission is appended to `data/bo7_state/session_log.csv`.

        ### The machine must output

        - exact weapon
        - exact camo
        - exact challenge
        - recommended mode
        - strategy
        - avoid warning
        - one-click result logging

        ### Operator rule

        If the AI issues a mission, the human must obey unless the mission is blocked, impossible, or based on inaccurate tracker data.
        """
    )
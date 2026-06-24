import csv
import json
from pathlib import Path
import pandas as pd
from datetime import datetime

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
    build_session_plan,
    rebuild_plan_after_progress,
    compute_full_tracker_summary,
    _pct
)


STATE_DIR = Path("data/bo7_state")
COMPLETION_STATE_PATH = STATE_DIR / "completion_state.json"
SESSION_LOG_PATH = STATE_DIR / "session_log.csv"
 
FINAL_CAMO_COLUMN = {
    "apocalypse_status.csv": "Apocalypse",
    "singularity_status.csv": "Singularity",
    "infestation_status.csv": "Infestation",
    "genesis_status.csv": "Genesis",
}
 
CHAIN_LABELS = {
    "apocalypse_status.csv": "Apocalypse (Warzone)",
    "singularity_status.csv": "Singularity (Multiplayer)",
    "infestation_status.csv": "Infestation (Zombies)",
    "genesis_status.csv": "Genesis (Co-Op / Endgame)",
}
 
 
def compute_weapon_completion_dashboard(clean_folder: Path) -> dict[str, any]:
    """
    Computes true weapon-level completion per camo chain, where "done"
    means the final per-weapon camo column is TRUE (Genesis, Singularity,
    Infestation, Apocalypse) — not the gate camos beneath them.
 
    Returns a dict keyed by chain label, each containing:
      - done / total weapons
      - per weapon_class breakdown of done / total
      - list of weapons still not done
    """
    dashboard: dict[str, any] = {}
 
    for filename, final_col in FINAL_CAMO_COLUMN.items():
        path = clean_folder / filename
        label = CHAIN_LABELS[filename]
 
        if not path.exists():
            dashboard[label] = {"done": 0, "total": 0, "by_class": {}, "not_done": []}
            continue
 
        df = pd.read_csv(path, dtype=str).fillna("")
 
        if final_col not in df.columns:
            dashboard[label] = {"done": 0, "total": 0, "by_class": {}, "not_done": []}
            continue
 
        # Exclude rows where this camo chain doesn't apply at all (e.g.
        # Wonder Weapons have no camo chain in any mode). N/A means
        # excluded from the denominator entirely, not "not done".
        applicable_mask = ~df[final_col].str.strip().str.upper().isin({"N/A", "NA", "NONE"})
        df = df[applicable_mask]
 
        total = len(df)
        is_done = df[final_col].str.strip().str.upper().isin({"TRUE", "YES", "DONE", "COMPLETE", "COMPLETED"})
        done = int(is_done.sum())
 
        by_class: dict[str, dict[str, int]] = {}
        not_done: list[str] = []
 
        for _, row in df.iterrows():
            weapon_class = row.get("weapon_class", "Unclassified")
            weapon = row.get("weapon", "Unknown")
            row_done = str(row.get(final_col, "")).strip().upper() in {"TRUE", "YES", "DONE", "COMPLETE", "COMPLETED"}
 
            if weapon_class not in by_class:
                by_class[weapon_class] = {"done": 0, "total": 0}
 
            by_class[weapon_class]["total"] += 1
            if row_done:
                by_class[weapon_class]["done"] += 1
            else:
                not_done.append(f"{weapon_class} — {weapon}")
 
        dashboard[label] = {
            "done": done,
            "total": total,
            "by_class": by_class,
            "not_done": not_done,
        }
 
    return dashboard
 
 
def compute_total_line_item_count(tasks: list[dict[str, any]], completion_state: dict[str, any]) -> dict[str, int]:
    """
    Count A — the true 100% atom count. Every active task object currently
    generated (already excludes anything TRUE in the source CSVs) plus
    everything recorded as done via the app's own completion state.
 
    This is the closest thing to "total line items remaining across
    the whole database" since load_tracker_tasks() only emits a task
    for the NEXT incomplete step per weapon/item, not every tier — so
    this is an undercount of true atomic items but an accurate count
    of "distinct next-steps remaining," which is the more actionable number.
    """
    return {
        "remaining_steps": len(tasks),
        "logged_this_app_session": len(completion_state),
    }


def ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


ACCOUNT_PARAMS_PATH = STATE_DIR / "account_params.json"
 
DOUBLE_XP_DURATIONS = [15, 30, 45, 60]
DOUBLE_XP_TYPES = ["weapon", "account"]
 
 
def default_token_bank() -> dict[str, int]:
    bank = {}
    for xp_type in DOUBLE_XP_TYPES:
        for duration in DOUBLE_XP_DURATIONS:
            bank[f"{xp_type}_{duration}"] = 0
    return bank
 
 
def load_account_params() -> dict[str, any]:
    ensure_state_dir()
    if not ACCOUNT_PARAMS_PATH.exists():
        return {"double_xp_tokens": default_token_bank()}
    try:
        with ACCOUNT_PARAMS_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
            if "double_xp_tokens" not in data:
                data["double_xp_tokens"] = default_token_bank()
            # Ensure all keys exist even if file predates a new duration/type
            for key in default_token_bank():
                data["double_xp_tokens"].setdefault(key, 0)
            return data
    except json.JSONDecodeError:
        return {"double_xp_tokens": default_token_bank()}
 
 
def save_account_params(params: dict[str, any]):
    ensure_state_dir()
    with ACCOUNT_PARAMS_PATH.open("w", encoding="utf-8") as file:
        json.dump(params, file, indent=2)
 
 
def spend_double_xp_token(xp_type: str, duration: int) -> bool:
    """
    Decrements one token of the given type/duration from the bank.
    Returns True if successful, False if none available.
    """
    params = load_account_params()
    key = f"{xp_type}_{duration}"
    current = params["double_xp_tokens"].get(key, 0)
 
    if current <= 0:
        return False
 
    params["double_xp_tokens"][key] = current - 1
    save_account_params(params)
    return True
 
 
def token_bank_summary(params: dict[str, any]) -> str:
    bank = params.get("double_xp_tokens", {})
    parts = []
    for xp_type in DOUBLE_XP_TYPES:
        counts = [f"{d}m:{bank.get(f'{xp_type}_{d}', 0)}" for d in DOUBLE_XP_DURATIONS]
        parts.append(f"{xp_type.title()} — " + ", ".join(counts))
    return " | ".join(parts)

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

    if "bo7_account_params" not in st.session_state:
        st.session_state.bo7_account_params = load_account_params()


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
    if "bo7_session_plan" not in st.session_state:
        st.session_state.bo7_session_plan = None
    if "bo7_completed_stop_ids" not in st.session_state:
        st.session_state.bo7_completed_stop_ids = []



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

tab_mission, tab_account, tab_quick_update, tab_tracker, tab_chat, tab_log, tab_protocol = st.tabs(
    ["Mission Control", "Account", "Quick Update", "Tracker", "AI Chat", "Session Log", "Protocol"]
)

# ─── MISSION CONTROL ──────────────────────────────────────────────────────────


with tab_mission:
 
    plan = st.session_state.bo7_session_plan
 
    # ── STATE 2: ACTIVE PLAN ──
    if plan and plan.get("stops"):
        st.markdown(f"<div class='order-mode'>☣ {plan['mode']} — SESSION PLAN ACTIVE</div>", unsafe_allow_html=True)
 
        if plan.get("cluster_summary"):
            cluster_text = " · ".join(
                f"{c['label']} ({c['close_count']} close)"
                for c in plan["cluster_summary"]
            )
            st.markdown(f"<div class='order-strategy'>Focus clusters: {cluster_text}</div>", unsafe_allow_html=True)
 
        st.divider()
 
        for stop in plan["stops"]:
            stop_number = stop["stop_number"]
            weapon = stop["weapon"]
            camo = stop["camo"]
            progress = stop["weapon_progress"]
            challenge = stop["challenge_text"]
            cluster_label = stop["cluster_label"]
 
            with st.container():
                st.markdown(
                    f"<div class='order-weapon' style='font-size:1.6rem;'>"
                    f"{stop_number}. {weapon}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div class='order-camo' style='font-size:1.1rem;'>{camo} · {cluster_label}</div>",
                    unsafe_allow_html=True,
                )

                st.markdown(f"<div class='order-challenge'>{challenge}</div>", unsafe_allow_html=True)
 
                
                with st.expander("Used a Double XP token on this?"):
                    used_token = st.checkbox(
                        "Yes, spend a token",
                        key=f"used_token_{stop['task_id']}",
                    )
                    token_type = None
                    token_duration = None
                    if used_token:
                        tc1, tc2 = st.columns(2)
                        with tc1:
                            token_type = st.selectbox(
                                "Type",
                                DOUBLE_XP_TYPES,
                                key=f"token_type_{stop['task_id']}",
                                format_func=lambda x: x.title(),
                            )
                        with tc2:
                            token_duration = st.selectbox(
                                "Duration",
                                DOUBLE_XP_DURATIONS,
                                key=f"token_duration_{stop['task_id']}",
                                format_func=lambda x: f"{x} min",
                            )
 
                col1, col2, col3 = st.columns(3)
 
                def _maybe_spend_token():
                    if used_token and token_type and token_duration:
                        success = spend_double_xp_token(token_type, token_duration)
                        st.session_state.bo7_account_params = load_account_params()
                        if not success:
                            st.warning(
                                f"No {token_duration}-minute {token_type} tokens left in the bank. "
                                "Logged anyway, but check Account Parameters."
                            )
 
                with col1:
                    if st.button("✅ Done", key=f"done_{stop['task_id']}", use_container_width=True):
                        _log_stop(stop["task_id"], "Camo completed", "Successful operation", stop)
                        _maybe_spend_token()
                        st.session_state.bo7_completed_stop_ids.append(stop["task_id"])
                        st.rerun()
 
                with col2:
                    if st.button("⚠️ Partial", key=f"partial_{stop['task_id']}", use_container_width=True):
                        _log_stop(stop["task_id"], "Partial progress", "Human avoidance", stop)
                        _maybe_spend_token()
                        st.session_state.bo7_completed_stop_ids.append(stop["task_id"])
                        st.rerun()
 
                with col3:
                    if st.button("⏭️ Skip", key=f"skip_{stop['task_id']}", use_container_width=True):
                        st.session_state.bo7_completed_stop_ids.append(stop["task_id"])
                        st.rerun()
 
                st.divider()
 
        st.markdown("**Time remaining in this session:**")
        remaining_minutes = st.number_input(
            "Minutes left",
            min_value=0,
            max_value=240,
            value=st.session_state.get("bo7_form_minutes", 60),
            step=5,
            key="plan_remaining_minutes",
        )
 
        col_a, col_b = st.columns(2)
 
        with col_a:
            if st.button("🔄 REBUILD PLAN WITH REMAINING TIME", type="primary", use_container_width=True):
                st.session_state.bo7_form_minutes = remaining_minutes
 
                new_plan = rebuild_plan_after_progress(
                    tasks=st.session_state.bo7_tasks,
                    preferred_mode=plan["mode"],
                    session_goal=st.session_state.bo7_form_session_goal,
                    motivation=st.session_state.bo7_form_motivation,
                    completed_task_ids=st.session_state.bo7_completed_stop_ids,
                    remaining_minutes=remaining_minutes,
                )
 
                st.session_state.bo7_session_plan = new_plan
                st.rerun()
 
        with col_b:
            if st.button("⏹️ END SESSION", use_container_width=True):
                st.session_state.bo7_session_plan = None
                st.session_state.bo7_completed_stop_ids = []
                st.rerun()
 
    # ── STATE 1: NO ACTIVE PLAN ──
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
 
        if st.button("GENERATE SESSION PLAN", type="primary", use_container_width=True):
            st.session_state.bo7_form_minutes = available_minutes
            st.session_state.bo7_form_energy = energy
            st.session_state.bo7_form_motivation = motivation
            st.session_state.bo7_form_preferred_mode = preferred_mode
            st.session_state.bo7_form_avoided_mode = avoided_mode
            st.session_state.bo7_form_session_goal = session_goal
            st.session_state.bo7_completed_stop_ids = []
 
            new_plan = build_session_plan(
                tasks=st.session_state.bo7_tasks,
                preferred_mode=preferred_mode,
                session_goal=session_goal,
                motivation=motivation,
                available_minutes=available_minutes,
            )
 
            st.session_state.bo7_session_plan = new_plan
            st.rerun()

# -- Account -- 

with tab_account:
    st.subheader("Account Parameters")
    st.caption("Settings that persist across sessions. Update when something changes — not every time you play.")
 
    st.markdown("### Double XP Token Banks")
    st.caption("COD gives these as separate banks per duration and per type. Enter what you currently have.")
 
    params = st.session_state.bo7_account_params
    bank = params["double_xp_tokens"]
 
    st.markdown("**Weapon XP tokens**")
    w_cols = st.columns(4)
    for i, duration in enumerate(DOUBLE_XP_DURATIONS):
        key = f"weapon_{duration}"
        with w_cols[i]:
            bank[key] = st.number_input(
                f"{duration} min",
                min_value=0,
                max_value=50,
                value=bank.get(key, 0),
                step=1,
                key=f"input_{key}",
            )
 
    st.markdown("**Account XP tokens**")
    a_cols = st.columns(4)
    for i, duration in enumerate(DOUBLE_XP_DURATIONS):
        key = f"account_{duration}"
        with a_cols[i]:
            bank[key] = st.number_input(
                f"{duration} min",
                min_value=0,
                max_value=50,
                value=bank.get(key, 0),
                step=1,
                key=f"input_{key}",
            )
 
    if st.button("SAVE ACCOUNT PARAMETERS", type="primary", use_container_width=True):
        params["double_xp_tokens"] = bank
        save_account_params(params)
        st.session_state.bo7_account_params = params
        st.success("Saved.")
        st.rerun()
 
    st.divider()
    st.caption(f"Current bank: {token_bank_summary(params)}")

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
    st.subheader("100% Tracker")
 
    summary = compute_full_tracker_summary(CLEAN_DATA_DIR)
 
    # ── LIVE SESSION QUEUE (kept from before, relabelled) ──
    task_summary = summarise_tasks(st.session_state.bo7_tasks)
    line_items = compute_total_line_item_count(
        st.session_state.bo7_tasks, st.session_state.bo7_completion_state,
    )
    cols = st.columns(5)
    cols[0].metric("Open Steps Loaded", task_summary["total"])
    cols[1].metric("Unlocked Steps", task_summary["available"])
    cols[2].metric("Locked Steps", task_summary["locked"])
    cols[3].metric("Logged Via App", line_items["logged_this_app_session"])
    cols[4].metric("Sessions Logged", summarise_sessions(st.session_state.bo7_session_log)["total"])
    st.caption("These describe the live task queue, not your full account progress — see below for that.")
 
    st.divider()
 
    # ── MASTERY BADGES SUMMARY ROW ──
    st.markdown("## Mastery Badges")
    mb = summary["mastery_badges"]
 
    weapon_mp_g, weapon_mp_g_total = mb.get("weapon_mp_gold", (0, 0))
    weapon_mp_d, weapon_mp_d_total = mb.get("weapon_mp_diamond", (0, 0))
    weapon_zm_g, weapon_zm_g_total = mb.get("weapon_zm_gold", (0, 0))
    weapon_zm_d, weapon_zm_d_total = mb.get("weapon_zm_diamond", (0, 0))
 
    all_done = weapon_mp_g + weapon_mp_d + weapon_zm_g + weapon_zm_d
    all_total = weapon_mp_g_total + weapon_mp_d_total + weapon_zm_g_total + weapon_zm_d_total
    mp_done = weapon_mp_g + weapon_mp_d
    mp_total = weapon_mp_g_total + weapon_mp_d_total
    zm_done = weapon_zm_g + weapon_zm_d
    zm_total = weapon_zm_g_total + weapon_zm_d_total
 
    badge_cols = st.columns(7)
    badge_cols[0].metric("All", f"{_pct(all_done, all_total):.1f}%", f"{all_done}/{all_total}")
    badge_cols[1].metric("MP", f"{_pct(mp_done, mp_total):.1f}%", f"{mp_done}/{mp_total}")
    badge_cols[2].metric("ZM", f"{_pct(zm_done, zm_total):.1f}%", f"{zm_done}/{zm_total}")
    badge_cols[3].metric("Gold MP", f"{weapon_mp_g}/{weapon_mp_g_total}")
    badge_cols[4].metric("Dia MP", f"{weapon_mp_d}/{weapon_mp_d_total}")
    badge_cols[5].metric("Gold ZM", f"{weapon_zm_g}/{weapon_zm_g_total}")
    badge_cols[6].metric("Dia ZM", f"{weapon_zm_d}/{weapon_zm_d_total}")
 
    st.divider()
 
    # ── WEAPON LEVEL / PRESTIGE ──
    st.markdown("## Weapon Prestige")
    prestige = summary["prestige"]
    st.metric("Weapon Prestige Master (WPM)", f"{_pct(prestige['wpm_done'], prestige['total']):.1f}%",
               f"{prestige['wpm_done']}/{prestige['total']} weapons")
 
    st.divider()
 
    # ── PER-MODE CAMO COMPLETION ──
    st.markdown("## Camo Completion by Mode")
    camos = summary["camos"]
 
    camo_order = [
        "Genesis (Co-Op / Endgame)", "Singularity (Multiplayer)",
        "Infestation (Zombies)", "Apocalypse (Warzone)",
    ]
    camo_cols = st.columns(4)
    for i, chain_label in enumerate(camo_order):
        data = camos.get(chain_label, {"base_done":0,"base_total":0,"mastery_done":0,"mastery_total":0})
        with camo_cols[i]:
            st.markdown(f"**{chain_label.split(' (')[0]}**")
            base_pct = _pct(data["base_done"], data["base_total"])
            mastery_pct = _pct(data["mastery_done"], data["mastery_total"])
            st.metric("Base Camo", f"{base_pct:.1f}%", f"{data['base_done']}/{data['base_total']}")
            st.metric("Mastery (final)", f"{mastery_pct:.1f}%", f"{data['mastery_done']}/{data['mastery_total']}")
 
    st.divider()
 
    # ── CALLING CARD COMPLETION BY MODE ──
    st.markdown("## Calling Card Completion by Mode")
    cc = summary["calling_cards"]
    cc_cols = st.columns(4)
    for i, mode in enumerate(["Co-Op / Endgame", "Multiplayer", "Zombies", "Warzone"]):
        done, total = cc.get(mode, (0, 0))
        with cc_cols[i]:
            st.metric(mode, f"{_pct(done, total):.1f}%", f"{done}/{total}")
 
    st.divider()
 
    # ── GLOBAL CAMO MASTERY TABLE ──
    st.markdown("## Global Camo Mastery")
    mastery_rows = []
    for chain_label in camo_order:
        data = camos.get(chain_label, {"mastery_done":0,"mastery_total":0})
        mastery_rows.append({
            "Chain": chain_label.split(" (")[0],
            "Mode": chain_label.split("(")[-1].rstrip(")"),
            "Done": data["mastery_done"],
            "Total": data["mastery_total"],
            "%": f"{_pct(data['mastery_done'], data['mastery_total']):.1f}%",
        })
    st.dataframe(mastery_rows, use_container_width=True, hide_index=True)
 
    st.divider()
 
    # ── RETICLE COMPLETION BY MODE ──
    st.markdown("## Reticle Completion (Stage 100) by Mode")
    ret = summary["reticles"]
    ret_cols = st.columns(4)
    for i, mode in enumerate(["Co-Op / Endgame", "Multiplayer", "Zombies", "Warzone"]):
        done, total = ret.get(mode, (0, 0))
        with ret_cols[i]:
            st.metric(mode, f"{_pct(done, total):.1f}%", f"{done}/{total}")
 
    st.divider()
 
    # ── TITLES BY MODE ──
    st.markdown("## Titles Earned by Mode")
    titles = summary["titles"]
    title_modes = list(titles.keys())
    title_cols = st.columns(len(title_modes)) if title_modes else []
    for i, mode in enumerate(title_modes):
        done, total = titles[mode]
        with title_cols[i]:
            st.metric(mode, f"{_pct(done, total):.1f}%", f"{done}/{total}")
 
    st.divider()
 
    # ── COLOURS ──
    st.markdown("## Colours Unlocked")
    colours_done, colours_total = summary["colours"]
    st.metric("Colours (account level gated)", f"{_pct(colours_done, colours_total):.1f}%",
               f"{colours_done}/{colours_total}")
 
    st.divider()
 
    # ── AUGMENTS (Zombies only) ──
    st.markdown("## Augments (Zombies)")
    aug_done, aug_total = summary["augments"]
    st.metric("Perk-A-Colas / Ammo Mods / Field Upgrades", f"{_pct(aug_done, aug_total):.1f}%",
               f"{aug_done}/{aug_total}")
 
    st.divider()
 
    # ── OVERCLOCKS (Multiplayer only) ──
    st.markdown("## Overclocks (Multiplayer)")
    oc_done, oc_total = summary["overclocks"]
    st.metric("Scorestreaks / Lethals / Tacticals / Field Upgrades", f"{_pct(oc_done, oc_total):.1f}%",
               f"{oc_done}/{oc_total}")
 
    st.divider()
 
    # ── INTEL BY MAP ──
    st.markdown("## Intel by Map")
    intel = summary["intel"]
    if intel:
        intel_cols = st.columns(min(len(intel), 4))
        for i, (map_name, (done, total)) in enumerate(intel.items()):
            with intel_cols[i % len(intel_cols)]:
                st.metric(map_name, f"{_pct(done, total):.1f}%", f"{done}/{total}")
    else:
        st.info("No intel data found.")
 
    st.divider()
 
    # ── REWARDS ──
    st.markdown("## Rewards")
    rewards = summary["rewards"]
 
    if "zombies_total" in rewards:
        z_done, z_total = rewards["zombies_total"]
        st.markdown(f"**Zombies Rewards (Main Quests, Relics, Survival, etc.) — {_pct(z_done, z_total):.1f}% ({z_done}/{z_total})**")
        with st.expander("Breakdown by map"):
            by_map = rewards.get("zombies_by_map", {})
            rows = [
                {"Map": map_name, "Done": done, "Total": total, "%": f"{_pct(done, total):.1f}%"}
                for map_name, (done, total) in by_map.items()
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)
 
    if "endgame_operations_total" in rewards:
        e_done, e_total = rewards["endgame_operations_total"]
        st.markdown(f"**Endgame Operations (Act I/II/III) — {_pct(e_done, e_total):.1f}% ({e_done}/{e_total})**")
        with st.expander("Breakdown by Operation"):
            by_act = rewards.get("endgame_operations_by_act", {})
            rows = [
                {"Operation": op, "Done": done, "Total": total, "%": f"{_pct(done, total):.1f}%"}
                for op, (done, total) in by_act.items()
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)
 
    if "zombies_total" not in rewards and "endgame_operations_total" not in rewards:
        st.info("No rewards data found.")
 
    st.divider()
 
    # ── RELOAD / RESET CONTROLS ──
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
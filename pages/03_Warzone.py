import csv
import html
import json
import re
from pathlib import Path
import pandas as pd
from datetime import datetime

import streamlit as st

from modules.ui.perzevol_theme import inject_perzevol_theme

st.set_page_config(
    page_title="Perzevol OS - BO7 Completion Commander",
    page_icon="☣",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_perzevol_theme(screen="mission_control")


from modules.warzone.killchain_engine import (
    BLAME_OPTIONS,
    ENERGY_LEVELS,
    MODES,
    MOTIVATION_LEVELS,
    RESULT_OPTIONS,
    SESSION_GOALS,
    COMMANDER_MODES,
    FOCUS_TARGETS,
    ANCHOR_COLLECTIONS,
    apply_mission_result,
    build_recovery_plan,
    build_recovery_suggestions,
    build_stop_explanation,
    generate_commander_reply,
    generate_mission,
    generate_plan_brief,
    get_available_tasks,
    get_ranked_tasks,
    load_hub_progress,
    load_tracker_tasks,
    summarise_sessions,
    summarise_tasks,
    build_session_plan,
    rebuild_plan_after_progress,
    compute_full_tracker_summary,
    _pct,
    safe_int,
)

# TTK Oracle is deliberately detached from Mission Control for recording stability.
TTK_ORACLE_AVAILABLE = False
load_ttk_data = None
optimise_single_weapon_build = None

from modules.warzone.loadout_architect import (
    attach_loadouts_to_plan,
    build_loadout_for_stop as architect_build_loadout_for_stop,
    load_loadout_templates as architect_load_loadout_templates,
)
from modules.warzone.series_director import attach_series_context_to_plan


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
        return {
            "double_xp_tokens": default_token_bank(),
            "account_level": 1.0,
        }
    try:
        with ACCOUNT_PARAMS_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
            if "double_xp_tokens" not in data:
                data["double_xp_tokens"] = default_token_bank()
            # Ensure all keys exist even if file predates a new duration/type
            for key in default_token_bank():
                data["double_xp_tokens"].setdefault(key, 0)
            data.setdefault("account_level", 1.0)
            return data
    except json.JSONDecodeError:
        return {
            "double_xp_tokens": default_token_bank(),
            "account_level": 1.0,
        }
 
def save_account_params(params: dict[str, any]):
    ensure_state_dir()
    with ACCOUNT_PARAMS_PATH.open("w", encoding="utf-8") as file:
        json.dump(params, file, indent=2)
 
def set_account_level(account_level: float):
    params = load_account_params()
    params["account_level"] = float(account_level)
    save_account_params(params)
    st.session_state.bo7_account_params = params


def add_account_levels(levels_gained: float):
    params = load_account_params()
    current_level = float(params.get("account_level", 1.0))
    params["account_level"] = current_level + float(levels_gained)
    save_account_params(params)
    st.session_state.bo7_account_params = params
 
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
        "mission_id",
        "time",
        "mode",
        "target",
        "challenge",
        "recommended_mode",
        "command",
        "time_limit",
        "result",
        "blame",
        "notes",
        "account_levels_gained",
        "actual_minutes_played",
    ]

    file_exists = SESSION_LOG_PATH.exists()

    if file_exists:
        with SESSION_LOG_PATH.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            existing_fieldnames = reader.fieldnames or []
            existing_rows = list(reader)

        if existing_fieldnames != fieldnames:
            with SESSION_LOG_PATH.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                for existing_row in existing_rows:
                    writer.writerow({key: existing_row.get(key, "") for key in fieldnames})

    with SESSION_LOG_PATH.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in fieldnames})

def log_account_level_gain(levels_gained: float, plan: dict, actual_minutes_played: int = 0):
    if levels_gained <= 0:
        return

    add_account_levels(levels_gained)

    append_session_log({
        "mission_id": f"AccountLevel:{datetime.now().isoformat(timespec='seconds')}",
        "time": datetime.now().isoformat(timespec="seconds"),
        "mode": plan.get("mode", "Global Cleanup") if plan else "Global Cleanup",
        "target": "Account Level",
        "challenge": "Session account level gain",
        "recommended_mode": plan.get("mode", "") if plan else "",
        "command": "Account level progress logged at session end.",
        "time_limit": plan.get("available_minutes", "") if plan else "",
        "result": "Account levels gained",
        "blame": "Successful operation",
        "notes": f"+{levels_gained:g} account levels",
        "account_levels_gained": levels_gained,
        "actual_minutes_played": actual_minutes_played,
    })

def log_objective_account_level_gain(
    stop: dict,
    plan: dict,
    levels_gained: float = 0.0,
):
    """
    Logs account XP at the moment it is earned, rather than waiting for End Session.

    This updates the persistent account level immediately and keeps a running
    session total for the debrief card.
    """
    try:
        levels_gained = float(levels_gained or 0.0)
    except (TypeError, ValueError):
        levels_gained = 0.0

    if levels_gained <= 0:
        return {"updated": False, "message": ""}

    add_account_levels(levels_gained)

    current_total = float(st.session_state.get("bo7_account_levels_gained", 0.0) or 0.0)
    st.session_state.bo7_account_levels_gained = current_total + levels_gained

    weapon = stop.get("weapon", "Objective")
    camo = stop.get("camo", "")
    mode = stop.get("mode") or plan.get("mode", "Global Cleanup") if plan else stop.get("mode", "Global Cleanup")

    append_session_log({
        "mission_id": f"AccountLevel:{datetime.now().isoformat(timespec='seconds')}",
        "time": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "target": "Account Level",
        "challenge": f"Account level gain during {weapon}",
        "recommended_mode": stop.get("recommended_mode", "") if stop else "",
        "command": "Account level progress logged during the active objective.",
        "time_limit": plan.get("available_minutes", "") if plan else "",
        "result": "Account levels gained",
        "blame": "Successful operation",
        "notes": f"+{levels_gained:g} account levels during {weapon} - {camo}",
        "account_levels_gained": levels_gained,
        "actual_minutes_played": 0,
    })

    message = (
        f"+{levels_gained:g} account levels logged now. "
        f"Session total: +{st.session_state.bo7_account_levels_gained:g}."
    )

    queue_celebration(
        "⚡ ACCOUNT LEVELS BANKED",
        message,
        "minor",
    )

    return {"updated": True, "message": message}

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

def sorted_task_values(tasks, field: str, mode: str = ""):
    values = set()

    for task in tasks:
        if mode and mode != "Global Cleanup" and task.get("mode") != mode:
            continue

        value = str(task.get(field, "")).strip()
        if value:
            values.add(value)

    return sorted(values)


def safe_select_index(options, selected):
    if selected in options:
        return options.index(selected)
    return 0


def stop_status(task_id):
    return st.session_state.bo7_stop_results.get(task_id, {}).get("status", "pending")


def stop_is_resolved(task_id):
    return stop_status(task_id) in {"done", "partial", "skipped"}


def resolved_stop_ids():
    return [
        task_id
        for task_id, result in st.session_state.bo7_stop_results.items()
        if result.get("status") in {"done", "partial", "skipped"}
    ]

def log_plan_stop(stop, result, blame):
    append_session_log({
        "mission_id": stop.get("task_id", ""),
        "time": datetime.now().isoformat(timespec="seconds"),
        "mode": stop.get("mode", ""),
        "target": stop.get("weapon", ""),
        "challenge": stop.get("challenge_text", ""),
        "recommended_mode": stop.get("recommended_mode", ""),
        "command": stop.get("camo", ""),
        "time_limit": "",
        "result": result,
        "blame": blame,
        "notes": f"Session objective {stop.get('stop_number', '')}",
    })

def record_stop_result(stop, status, result="", blame="", notes="", timing=None):
    task_id = stop["task_id"]
    timing = timing or {}

    st.session_state.bo7_stop_results[task_id] = {
        "status": status,
        "result": result,
        "blame": blame,
        "notes": notes,
        "stop_number": stop.get("stop_number", ""),
        "weapon": stop.get("weapon", ""),
        "camo": stop.get("camo", ""),
        "mode": stop.get("mode", ""),
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "started_at": timing.get("started_at", ""),
        "ended_at": timing.get("ended_at", ""),
        "elapsed_minutes": timing.get("elapsed_minutes", 0),
        "total_elapsed_minutes": timing.get("total_elapsed_minutes", 0),
        "remaining_minutes_after": timing.get("remaining_minutes_after", 0),
    }

    if task_id not in st.session_state.bo7_completed_stop_ids:
        st.session_state.bo7_completed_stop_ids.append(task_id)

def parse_timer_datetime(value: str):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def elapsed_minutes_between(started_at: str, ended_at: str = "") -> int:
    start = parse_timer_datetime(started_at)
    end = parse_timer_datetime(ended_at) or datetime.now()

    if not start:
        return 0

    seconds = max(0, (end - start).total_seconds())
    return int(round(seconds / 60))


def logged_stop_minutes() -> int:
    total = 0

    for result in st.session_state.get("bo7_stop_results", {}).values():
        try:
            total += int(float(result.get("elapsed_minutes", 0) or 0))
        except ValueError:
            continue

    return total


def plan_available_minutes(plan: dict) -> int:
    return int(
        plan.get("available_minutes", 0)
        or st.session_state.get("bo7_form_minutes", 0)
        or 0
    )


def active_stop_for_timing(plan: dict) -> dict:
    stops = plan.get("stops", []) if plan else []

    for stop in stops:
        if not stop_is_resolved(stop.get("task_id", "")):
            return stop

    return {}


def ensure_active_stop_timer(plan: dict):
    if not plan:
        return

    now = datetime.now().isoformat(timespec="seconds")
    active_stop = active_stop_for_timing(plan)
    active_stop_id = active_stop.get("task_id", "")

    if not st.session_state.get("bo7_session_started_at"):
        st.session_state.bo7_session_started_at = now

    if active_stop_id and st.session_state.get("bo7_active_stop_id") != active_stop_id:
        st.session_state.bo7_active_stop_id = active_stop_id
        st.session_state.bo7_active_stop_started_at = now


def current_stop_elapsed_minutes() -> int:
    return elapsed_minutes_between(
        st.session_state.get("bo7_active_stop_started_at", "")
    )


def current_time_remaining(plan: dict) -> int:
    available = plan_available_minutes(plan)
    spent = logged_stop_minutes()
    current = current_stop_elapsed_minutes()
    return max(0, available - spent - current)


def close_active_stop_timer(stop: dict, plan: dict) -> dict:
    ended_at = datetime.now().isoformat(timespec="seconds")
    started_at = st.session_state.get("bo7_active_stop_started_at") or ended_at

    elapsed = elapsed_minutes_between(started_at, ended_at)
    previous_elapsed = logged_stop_minutes()
    total_elapsed = previous_elapsed + elapsed
    remaining_after = max(0, plan_available_minutes(plan) - total_elapsed)

    timing = {
        "started_at": started_at,
        "ended_at": ended_at,
        "elapsed_minutes": elapsed,
        "total_elapsed_minutes": total_elapsed,
        "remaining_minutes_after": remaining_after,
    }

    st.session_state.bo7_active_stop_id = ""
    st.session_state.bo7_active_stop_started_at = ""

    return timing

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
    if "bo7_form_commander_mode" not in st.session_state:
        st.session_state.bo7_form_commander_mode = COMMANDER_MODES[0]
    if "bo7_form_focus_targets" not in st.session_state:
        st.session_state.bo7_form_focus_targets = []
    if "bo7_form_anchor_weapon" not in st.session_state:
        st.session_state.bo7_form_anchor_weapon = ""
    if "bo7_form_anchor_class" not in st.session_state:
        st.session_state.bo7_form_anchor_class = ""
    if "bo7_form_anchor_collection" not in st.session_state:
        st.session_state.bo7_form_anchor_collection = ANCHOR_COLLECTIONS[0]
    if "bo7_form_minimum_closeness" not in st.session_state:
        st.session_state.bo7_form_minimum_closeness = 80
    if "bo7_actual_minutes_played" not in st.session_state:
        st.session_state.bo7_actual_minutes_played = 0
    if "bo7_session_plan" not in st.session_state:
        st.session_state.bo7_session_plan = None
    if "bo7_completed_stop_ids" not in st.session_state:
        st.session_state.bo7_completed_stop_ids = []
    if "bo7_stop_results" not in st.session_state:
        st.session_state.bo7_stop_results = {}
    if "bo7_account_levels_gained" not in st.session_state:
        st.session_state.bo7_account_levels_gained = 0.0
    if "bo7_account_levels_debrief_adjustment" not in st.session_state:
        st.session_state.bo7_account_levels_debrief_adjustment = 0.0
    if "bo7_celebrations" not in st.session_state:
        st.session_state.bo7_celebrations = []
    if "bo7_last_debrief" not in st.session_state:
        st.session_state.bo7_last_debrief = None
    if "bo7_recording_mode" not in st.session_state:
        st.session_state.bo7_recording_mode = False
    if "bo7_session_started_at" not in st.session_state:
        st.session_state.bo7_session_started_at = ""
    if "bo7_active_stop_id" not in st.session_state:
        st.session_state.bo7_active_stop_id = ""
    if "bo7_active_stop_started_at" not in st.session_state:
        st.session_state.bo7_active_stop_started_at = ""

CLEAN_DATA_DIR = Path("data/bo7_clean")

LOADOUT_TEMPLATE_FILE = CLEAN_DATA_DIR / "loadout_templates.csv"

PLAYABLE_WEAPON_CLASSES = {
    "Assault Rifles",
    "Submachine Guns",
    "Shotguns",
    "LMGs",
    "Marksman Rifles",
    "Sniper Rifles",
    "Pistols",
    "Launchers",
    "Specials",
    "Melee",
    "Wonder Weapons",
}


def loadout_html(value) -> str:
    return html.escape(str(value or "").strip())


def loadout_clean(value) -> str:
    return str(value or "").strip()


def strip_goal_suffix_for_ttk(weapon_text: str) -> str:
    text = loadout_clean(weapon_text)
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
    text = re.sub(r"\s+if safe, otherwise.*$", "", text, flags=re.IGNORECASE).strip()
    return text


@st.cache_data(show_spinner=False)
def load_commander_ttk_data():
    """
    Loads TTK Oracle data for the Commander card.

    The Commander should keep working if the TTK module or CSVs are missing,
    so this returns an error string instead of raising into the UI.
    """
    if not TTK_ORACLE_AVAILABLE or load_ttk_data is None:
        return pd.DataFrame(), pd.DataFrame(), "TTK Oracle module is not available."

    try:
        guns, attachments = load_ttk_data()
        return guns, attachments, ""
    except Exception as error:
        return pd.DataFrame(), pd.DataFrame(), str(error)


def normalise_ttk_weapon_key(value) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
    )


def commander_ttk_match_weapon_name(guns: pd.DataFrame, weapon_name: str) -> str:
    if guns.empty or "gun_name" not in guns.columns:
        return ""

    raw_weapon = loadout_clean(weapon_name)

    candidates = [
        raw_weapon,
        raw_weapon.split("(", 1)[0].strip(),
    ]

    gun_names = [
        loadout_clean(name)
        for name in guns["gun_name"].dropna().astype(str).tolist()
        if loadout_clean(name)
    ]

    name_lookup = {
        normalise_ttk_weapon_key(name): name
        for name in gun_names
    }

    for candidate in candidates:
        matched = name_lookup.get(normalise_ttk_weapon_key(candidate))
        if matched:
            return matched

    return ""


def commander_ttk_defaults(stop: dict, plan: dict) -> dict:
    mode = loadout_clean(stop.get("mode") or (plan or {}).get("mode"))
    weapon_class = loadout_clean(stop.get("weapon_class"))

    if mode == "Warzone":
        return {
            "supported": True,
            "mode": mode,
            "enemy_health": 300,
            "map_type": "Large map / Battle Royale",
            "fight_type": "Long range" if weapon_class in {"Sniper Rifles", "Marksman Rifles"} else "Mixed fights",
            "build_goal": "Balanced meta build",
        }

    if mode == "Multiplayer":
        return {
            "supported": True,
            "mode": mode,
            "enemy_health": 100,
            "map_type": "Small map / Resurgence",
            "fight_type": "Mid range" if weapon_class in {"Sniper Rifles", "Marksman Rifles"} else "Close range",
            "build_goal": "Balanced meta build",
        }

    return {
        "supported": False,
        "mode": mode or "Unknown",
        "reason": "TTK Oracle auto-builds are currently enabled for Multiplayer and Warzone only.",
    }


def build_ttk_oracle_recommendation(primary_weapon: str, stop: dict, plan: dict) -> dict:
    weapon_name = strip_goal_suffix_for_ttk(primary_weapon)

    if not weapon_name:
        return {
            "status": "fallback",
            "reason": "No assigned weapon found for the active objective.",
        }

    defaults = commander_ttk_defaults(stop, plan)

    if not defaults.get("supported"):
        return {
            "status": "fallback",
            "reason": defaults.get("reason", "Mode is not supported by Commander auto-builds yet."),
            "mode": defaults.get("mode", ""),
        }

    guns, attachments, load_error = load_commander_ttk_data()

    if load_error:
        return {
            "status": "fallback",
            "reason": f"TTK data failed to load: {load_error}",
        }

    matched_weapon = commander_ttk_match_weapon_name(guns, weapon_name)

    if not matched_weapon:
        return {
            "status": "fallback",
            "reason": f"No TTK data found for {weapon_name}.",
        }

    if optimise_single_weapon_build is None:
        return {
            "status": "fallback",
            "reason": "TTK optimiser is unavailable.",
        }

    results = pd.DataFrame()
    used_attachment_count = 5

    try:
        for attachment_count in (5, 4, 3):
            candidate_results = optimise_single_weapon_build(
                guns=guns,
                attachments=attachments,
                weapon_name=matched_weapon,
                map_type=defaults["map_type"],
                fight_type=defaults["fight_type"],
                build_goal=defaults["build_goal"],
                enemy_health=int(defaults["enemy_health"]),
                attachment_count=attachment_count,
                top_n=1,
            )

            if candidate_results is not None and not candidate_results.empty:
                results = candidate_results
                used_attachment_count = attachment_count
                break
    except Exception as error:
        return {
            "status": "fallback",
            "weapon": matched_weapon,
            "reason": f"TTK Oracle failed for {matched_weapon}: {error}",
        }

    if results.empty:
        reason = f"TTK Oracle has data for {matched_weapon}, but not enough trusted/modelled attachment data for a build."
        try:
            from modules.warzone.ttk_oracle_engine import describe_weapon_build_data
            status = describe_weapon_build_data(
                guns=guns,
                attachments=attachments,
                weapon_name=matched_weapon,
                attachment_count=5,
            )
            reason = status.get("message", reason)
        except Exception:
            pass

        return {
            "status": "fallback",
            "weapon": matched_weapon,
            "reason": reason,
        }

    best = results.iloc[0]

    return {
        "status": "ok",
        "weapon": loadout_clean(best.get("gun_name", matched_weapon)),
        "weapon_class": loadout_clean(best.get("weapon_class", stop.get("weapon_class", ""))),
        "attachments": loadout_clean(best.get("attachments", "")),
        "slots": loadout_clean(best.get("slots", "")),
        "attachment_count": used_attachment_count,
        "attachment_trust_note": loadout_clean(best.get("attachment_trust_note", "")),
        "raw_ttk_ms": float(best.get("raw_ttk_ms", 0) or 0),
        "practical_ttk_ms": float(best.get("practical_ttk_ms", 0) or 0),
        "ads_ms": float(best.get("ads_ms", 0) or 0),
        "sprint_to_fire_ms": float(best.get("sprint_to_fire_ms", 0) or 0),
        "recoil": float(best.get("recoil", 0) or 0),
        "oracle_score": float(best.get("oracle_score", 0) or 0),
        "enemy_health": int(defaults["enemy_health"]),
        "map_type": defaults["map_type"],
        "fight_type": defaults["fight_type"],
        "build_goal": defaults["build_goal"],
        "mode": defaults["mode"],
    }


def best_unfinished_singularity_weapon(anchor_class: str = "") -> str:
    """
    Pick a real Multiplayer weapon to carry while the main objective is not
    itself a weapon task. This keeps no-thinking plans playable and still
    moves the 100% tracker instead of showing a vague placeholder.
    """
    path = CLEAN_DATA_DIR / "singularity_status.csv"

    if not path.exists():
        return ""

    dataframe = pd.read_csv(path, dtype=str).fillna("")
    required_columns = {"weapon_class", "weapon"}

    if not required_columns.issubset(set(dataframe.columns)):
        return ""

    id_columns = {"mode", "chain", "weapon_class", "weapon"}
    camo_columns = [column for column in dataframe.columns if column not in id_columns]

    if not camo_columns:
        return ""

    final_column = "Singularity" if "Singularity" in dataframe.columns else camo_columns[-1]
    anchor_class = loadout_clean(anchor_class)

    candidates = []

    for _, row in dataframe.iterrows():
        weapon = loadout_clean(row.get("weapon"))
        weapon_class = loadout_clean(row.get("weapon_class"))

        if not weapon:
            continue

        if anchor_class and anchor_class != "Any" and weapon_class != anchor_class:
            continue

        final_value = loadout_clean(row.get(final_column)).upper()

        if final_value in {"TRUE", "YES", "DONE", "COMPLETE", "COMPLETED", "✅"}:
            continue

        if final_value in {"N/A", "NA", "NONE", ""}:
            continue

        applicable = [
            column for column in camo_columns
            if loadout_clean(row.get(column)).upper() not in {"N/A", "NA", "NONE", ""}
        ]

        if not applicable:
            continue

        completed = sum(
            1 for column in applicable
            if loadout_clean(row.get(column)).upper() in {"TRUE", "YES", "DONE", "COMPLETE", "COMPLETED", "✅"}
        )

        progress = (completed / len(applicable)) * 100
        candidates.append((progress, weapon_class, weapon))

    if not candidates and anchor_class:
        return best_unfinished_singularity_weapon("")

    if not candidates:
        return ""

    progress, weapon_class, weapon = sorted(candidates, reverse=True)[0]
    return f"{weapon} ({weapon_class}, {progress:.0f}% Singularity)"


def render_recording_markup(markup: str):
    """
    Streamlit markdown treats indented raw HTML blocks as code in some cases.
    Compact the card markup before rendering so nested divs never leak as text.
    """
    compact_markup = "".join(
        line.strip()
        for line in str(markup or "").splitlines()
        if line.strip()
    )
    st.markdown(compact_markup, unsafe_allow_html=True)


def render_series_context_panel(plan: dict):
    context = plan.get("series_context", {}) or {}

    if not context:
        return

    proof_points = context.get("proof_points", []) or []
    proof_preview = " · ".join(proof_points[:2]) if proof_points else "Show Commander decision, gameplay proof, and debrief."
    morale = context.get("morale", {}) or {}

    render_recording_markup(
        f"""
        <div class="recording-card director-card">
            <div class="recording-eyebrow">SERIES DIRECTOR</div>
            <div class="recording-section">
                <span>MORALE OVERRIDE</span>
                <p><strong>{loadout_html(morale.get("headline") or context.get("morale_headline") or "JUST ONE MORE CHALLENGE.")}</strong><br>{loadout_html(morale.get("line") or context.get("morale_line") or "Bank one visible piece of progress, then reassess.")}</p>
            </div>
            <h2>{loadout_html(context.get("episode_title", "AI Chose My BO7 Grind"))}</h2>
            <p>{loadout_html(context.get("hook", ""))}</p>

            <div class="recording-grid">
                <div><span>Deadline</span><strong>{loadout_html(context.get("days_remaining", "?"))} days</strong></div>
                <div><span>Pressure</span><strong>{loadout_html(context.get("pressure", "Unknown"))}</strong></div>
                <div><span>Thumbnail</span><strong>{loadout_html(context.get("thumbnail_text", "AI CHOSE"))}</strong></div>
                <div><span>Angle</span><strong>{loadout_html(context.get("completion_angle", "Completion"))}</strong></div>
            </div>

            <div class="recording-section">
                <span>Why This Session Matters</span>
                <p>{loadout_html(context.get("route_promise", ""))}<br>{loadout_html(context.get("pace_line", ""))}</p>
            </div>

            <div class="recording-section">
                <span>Minimum Viable Win</span>
                <p>{loadout_html(morale.get("micro_action") or context.get("morale_micro_action") or "Play the first stop and look only for proof.")}<br>{loadout_html(morale.get("rule") or context.get("morale_rule") or "A partial is still useful data.")}</p>
            </div>

            <div class="recording-section">
                <span>Proof To Capture</span>
                <p>{loadout_html(proof_preview)}</p>
            </div>
        </div>
        """
    )

def load_loadout_templates() -> list[dict]:
    if not LOADOUT_TEMPLATE_FILE.exists():
        return []

    with LOADOUT_TEMPLATE_FILE.open("r", encoding="utf-8", newline="") as file:
        return [
            row for row in csv.DictReader(file)
            if loadout_clean(row.get("template_id"))
        ]


def current_recording_stop(plan: dict) -> dict:
    stops = plan.get("stops", []) if plan else []

    for stop in stops:
        if not stop_is_resolved(stop.get("task_id", "")):
            return stop

    return stops[0] if stops else {}


def stop_is_weapon_objective(stop: dict) -> bool:
    task_type = loadout_clean(stop.get("task_type"))
    weapon_class = loadout_clean(stop.get("weapon_class"))

    if weapon_class in PLAYABLE_WEAPON_CLASSES:
        return True

    return task_type in {
        "camo",
        "mastery_badge_weapon",
        "weapon_prestige",
        "overclock",
    }


def companion_weapon_anchor(stop: dict, plan: dict) -> str:
    weapon = loadout_clean(stop.get("weapon"))

    if stop_is_weapon_objective(stop) and weapon:
        return weapon

    anchor_weapon = loadout_clean(plan.get("anchor_weapon") if plan else "")
    if anchor_weapon:
        return anchor_weapon

    return ""


def assigned_primary_for_loadout(template: dict, stop: dict, plan: dict) -> str:
    primary_weapon = loadout_clean(template.get("primary_weapon"))
    primary_role = loadout_clean(template.get("primary_role"))
    route_type = loadout_clean(template.get("route_type"))
    assigned_weapon = companion_weapon_anchor(stop, plan)
    weapon_class = loadout_clean(stop.get("weapon_class"))

    if primary_role == "replace_with_assigned_weapon" and assigned_weapon:
        return assigned_weapon

    if (
        primary_role == "replace_with_assigned_weapon_if_sniper"
        and assigned_weapon
        and weapon_class == "Sniper Rifles"
    ):
        return assigned_weapon

    if (
        primary_role == "replace_with_assigned_genesis_weapon_if_safe"
        and assigned_weapon
        and loadout_clean(stop.get("mode")) == "Co-Op / Endgame"
        and loadout_clean(stop.get("task_type")) == "camo"
    ):
        return f"{assigned_weapon} if the clear stays safe; otherwise {primary_weapon}"

    if primary_role == "replace_with_best_unfinished_singularity_weapon":
        anchor_class = loadout_clean(plan.get("anchor_class") if plan else "")
        unfinished_weapon = best_unfinished_singularity_weapon(anchor_class)
        return unfinished_weapon or primary_weapon

    if route_type == "scorestreak" and not assigned_weapon:
        return primary_weapon

    return primary_weapon or assigned_weapon or "Use the assigned objective weapon"


def score_loadout_template(template: dict, stop: dict, plan: dict) -> int:
    score = safe_int(template.get("priority", 0), 0)

    mode = loadout_clean(stop.get("mode") or plan.get("mode"))
    template_mode = loadout_clean(template.get("mode"))
    task_type = loadout_clean(stop.get("task_type"))
    weapon_class = loadout_clean(stop.get("weapon_class"))
    route_type = loadout_clean(template.get("route_type"))
    template_class = loadout_clean(template.get("weapon_class"))

    if template_mode == mode:
        score += 100

    if template_mode and template_mode != mode:
        score -= 100

    if mode == "Co-Op / Endgame" and route_type == "operation":
        score += 80

    if task_type in {"endgame_operation", "endgame_unlock"} and route_type == "operation":
        score += 120

    if task_type == "mastery_badge_equipment" and "Scorestreak" in loadout_clean(stop.get("weapon_class")):
        if route_type == "scorestreak":
            score += 130

    if route_type == "scorestreak" and "Scorestreak" in loadout_clean(stop.get("category")):
        score += 100

    if weapon_class and template_class == weapon_class:
        score += 130

    if weapon_class == "Sniper Rifles" and template.get("template_id") == "mp_sniper":
        score += 180

    if task_type in {"camo", "mastery_badge_weapon", "weapon_prestige"} and route_type == "weapon_progress":
        score += 80

    if template_class == "Any" and route_type in {"scorestreak", "operation"}:
        score += 25

    return score


def build_loadout_recommendation(plan: dict) -> dict:
    templates = architect_load_loadout_templates()
    stop = current_recording_stop(plan)

    if not stop:
        return {
            "template": {},
            "stop": stop,
            "reason": "No active objective found for the current plan.",
        }

    precomputed = stop.get("loadout") or {}
    loadout = precomputed or architect_build_loadout_for_stop(
        stop=stop,
        plan=plan,
        tasks=st.session_state.get("bo7_tasks", []),
        templates=templates,
    )

    template = loadout.get("template", {}) or {}
    primary = loadout.get("primary", "")

    ttk_oracle = build_ttk_oracle_recommendation(primary, stop, plan)

    return {
        "template": template,
        "stop": stop,
        "primary": primary,
        "primary_attachments": loadout.get("primary_attachments", ""),
        "primary_attachment_source": loadout.get("primary_attachment_source", "") or loadout.get("ttk_oracle_note", ""),
        "secondary": loadout.get("secondary", ""),
        "secondary_attachments": loadout.get("secondary_attachments", ""),
        "wildcard": loadout.get("wildcard", ""),
        "perks": loadout.get("perks", ""),
        "tactical": loadout.get("tactical", ""),
        "lethal": loadout.get("lethal", ""),
        "field_upgrade": loadout.get("field_upgrade", ""),
        "scorestreaks": loadout.get("scorestreaks", ""),
        "skill_tracks": loadout.get("skill_tracks", ""),
        "template_name": loadout.get("template_name", ""),
        "primary_reason": loadout.get("primary_reason", ""),
        "natural_goal": loadout.get("natural_goal", ""),
        "natural_goal_source": loadout.get("natural_goal_source", ""),
        "score": loadout.get("score", 0),
        "reason": loadout.get("reason", ""),
        "ttk_oracle": ttk_oracle,
    }



def render_recording_order_card(plan: dict):
    stop = current_recording_stop(plan)

    if not stop:
        return

    weapon = loadout_clean(stop.get("weapon")) or "Assigned Objective"
    camo = loadout_clean(stop.get("camo")) or "Objective"
    mode = loadout_clean(stop.get("mode") or plan.get("mode")) or "Unknown Mode"
    task_type = loadout_clean(stop.get("task_type")) or "objective"
    challenge = loadout_clean(stop.get("challenge_text")) or "Complete the assigned objective."
    timebox = loadout_clean(plan.get("available_minutes", "?"))
    stop_number = loadout_clean(stop.get("stop_number")) or "1"
    total_stops = len(plan.get("stops", []) or [])

    optional_stacks = stop.get("companion_objectives", []) or []
    optional_stack_text = " · ".join(optional_stacks[:4]) if optional_stacks else "None assigned"

    diagnostics = plan.get("diagnostics", {}) if plan else {}
    confidence = loadout_clean(diagnostics.get("confidence", "Unknown"))
    confidence_score = loadout_clean(diagnostics.get("confidence_score", 0))

    why_bits = []
    rationale = diagnostics.get("rationale", [])
    if rationale:
        why_bits.append(str(rationale[0]))

    route_summary = plan.get("route_summary", {}) if plan else {}
    primary_route = loadout_clean(route_summary.get("primary_route"))
    if primary_route:
        why_bits.append(f"Route: {primary_route}")

    why_text = " ".join(why_bits) if why_bits else "Highest-value available route from the current tracker state."

    intro_line = f"The Commander picked {weapon}. I do not get a reroll."
    objective_line = f"The target is {camo}: {challenge}"
    rule_line = "No rerolls unless the objective is impossible. The debrief decides if the route worked."

    render_recording_markup(
        f"""
        <div class="recording-card decision-card">
            <div class="decision-strip">COMMANDER DECISION LOCKED</div>
            <div class="recording-eyebrow">AI CHOSE THE GRIND</div>
            <div class="recording-title">{loadout_html(weapon)}</div>
            <div class="recording-subtitle">{loadout_html(camo)}</div>

            <div class="decision-command">
                <span>Session Briefing</span>
                <p>
                    The Commander has selected {loadout_html(weapon)} for {loadout_html(mode)}.
                    The target is {loadout_html(camo)}. Follow the route, bank progress, then let the debrief judge the session.
                </p>
            </div>

            <div class="recording-grid">
                <div><span>Mode</span><strong>{loadout_html(mode)}</strong></div>
                <div><span>Timebox</span><strong>{loadout_html(timebox)} min</strong></div>
                <div><span>Stop</span><strong>{loadout_html(stop_number)} / {loadout_html(total_stops)}</strong></div>
            </div>

            <div class="recording-grid">
                <div><span>Type</span><strong>{loadout_html(task_type)}</strong></div>
                <div><span>Confidence</span><strong>{loadout_html(confidence)}</strong></div>
                <div><span>Score</span><strong>{loadout_html(confidence_score)} / 100</strong></div>
            </div>

            <div class="recording-section">
                <span>Main Objective</span>
                <p>{loadout_html(challenge)}</p>
            </div>

            <div class="recording-section">
                <span>Why This Was Picked</span>
                <p>{loadout_html(why_text)}</p>
            </div>

            <div class="recording-section">
                <span>Optional Stacks</span>
                <p>{loadout_html(optional_stack_text)}</p>
            </div>

            <div class="recording-section recording-lines">
                <span>Recording Lines</span>
                <p>
                    <strong>Intro:</strong> {loadout_html(intro_line)}<br>
                    <strong>Objective:</strong> {loadout_html(objective_line)}<br>
                    <strong>Rule:</strong> {loadout_html(rule_line)}
                </p>
            </div>

            <div class="recording-rule">RULE: NO REROLL UNLESS IMPOSSIBLE</div>
        </div>
        """
    )

def render_recording_loadout_card(plan: dict):
    recommendation = build_loadout_recommendation(plan)
    ttk_oracle = recommendation.get("ttk_oracle", {}) or {}
    oracle_ready = ttk_oracle.get("status") == "ok"

    if not recommendation.get("primary"):
        st.warning(recommendation.get("reason", "No loadout recommendation available."))
        return

    natural_goal_text = loadout_clean(recommendation.get("natural_goal"))
    natural_goal_source = loadout_clean(recommendation.get("natural_goal_source"))
    primary_reason = loadout_clean(recommendation.get("primary_reason"))
    streak_text = loadout_clean(recommendation.get("scorestreaks")) or "Scorestreaks not required"

    skill_tracks = loadout_clean(recommendation.get("skill_tracks"))
    if skill_tracks and skill_tracks != "N/A":
        streak_text += " | Skill Tracks: " + skill_tracks

    template_notes = loadout_clean(recommendation.get("reason"))

    if oracle_ready:
        card_title = "TTK Oracle Build"
        primary_subtitle = f"Primary: {ttk_oracle.get('weapon')}"
        primary_attachment_label = "TTK Oracle Attachments"
        primary_attachment_text = ttk_oracle.get("attachments") or "No attachment list returned."
        notes = (
            f"TTK Oracle locked the Commander-assigned weapon for {ttk_oracle.get('mode')} "
            f"at {ttk_oracle.get('enemy_health')} HP using {ttk_oracle.get('attachment_count', 5)} trusted attachment(s). {template_notes}"
        )
        oracle_section_html = f"""
            <div class="recording-section">
                <span>Oracle Readout</span>
                <p>
                    Raw TTK: {loadout_html(f"{ttk_oracle.get('raw_ttk_ms', 0):.0f} ms")} ·
                    Practical TTK: {loadout_html(f"{ttk_oracle.get('practical_ttk_ms', 0):.0f} ms")} ·
                    ADS: {loadout_html(f"{ttk_oracle.get('ads_ms', 0):.0f} ms")} ·
                    Sprint-to-fire: {loadout_html(f"{ttk_oracle.get('sprint_to_fire_ms', 0):.0f} ms")} ·
                    Recoil: {loadout_html(f"{ttk_oracle.get('recoil', 0):.1f}")}
                </p>
            </div>

            <div class="recording-section">
                <span>Oracle Scenario</span>
                <p>
                    {loadout_html(ttk_oracle.get("fight_type"))} ·
                    {loadout_html(ttk_oracle.get("build_goal"))} ·
                    Enemy health: {loadout_html(ttk_oracle.get("enemy_health"))} HP
                </p>
            </div>
        """
    else:
        card_title = loadout_clean(recommendation.get("template_name")) or "Loadout Template"
        primary_subtitle = f"Primary: {recommendation.get('primary')}"
        primary_attachment_label = "Primary Attachments"
        primary_attachment_text = recommendation.get("primary_attachments") or "No trusted Commander attachment build available."
        oracle_reason = loadout_clean(ttk_oracle.get("reason"))
        notes = template_notes
        if oracle_reason:
            notes = f"Template fallback. TTK Oracle: {oracle_reason} {template_notes}".strip()
        oracle_section_html = ""

    render_recording_markup(
        f"""
        <div class="recording-card loadout-card">
            <div class="recording-eyebrow">LOADOUT COMMANDER</div>
            <div class="recording-title">{loadout_html(card_title)}</div>
            <div class="recording-subtitle">{loadout_html(primary_subtitle)}</div>

            <div class="recording-grid">
                <div>
                    <span>Secondary</span>
                    <strong>{loadout_html(recommendation.get("secondary") or "N/A")}</strong>
                </div>
                <div>
                    <span>Wildcard</span>
                    <strong>{loadout_html(recommendation.get("wildcard") or "N/A")}</strong>
                </div>
                <div>
                    <span>Field Upgrade</span>
                    <strong>{loadout_html(recommendation.get("field_upgrade") or "N/A")}</strong>
                </div>
            </div>

            <div class="recording-section">
                <span>{loadout_html(primary_attachment_label)}</span>
                <p>{loadout_html(primary_attachment_text)}</p>
            </div>

            <div class="recording-section">
                <span>Attachment Source</span>
                <p>{loadout_html(recommendation.get("primary_attachment_source") or ttk_oracle.get("attachment_trust_note") or "Unknown")}</p>
            </div>

            <div class="recording-section">
                <span>Why This Primary</span>
                <p>{loadout_html(primary_reason or "Primary selected from the active objective and nearest natural weapon goal.")}</p>
            </div>

            <div class="recording-section">
                <span>Natural Weapon Goal</span>
                <p>{loadout_html(natural_goal_text or "No natural weapon goal found.")}<br><strong>Source:</strong> {loadout_html(natural_goal_source or "Unknown")}</p>
            </div>

            {oracle_section_html}

            <div class="recording-section">
                <span>Secondary Attachments</span>
                <p>{loadout_html(recommendation.get("secondary_attachments") or "N/A")}</p>
            </div>

            <div class="recording-section">
                <span>Equipment / Perks</span>
                <p>Tactical: {loadout_html(recommendation.get("tactical") or "N/A")} · Lethal: {loadout_html(recommendation.get("lethal") or "N/A")} · Perks: {loadout_html(recommendation.get("perks") or "N/A")}</p>
            </div>

            <div class="recording-section">
                <span>Streaks / Skill Tracks</span>
                <p>{loadout_html(streak_text)}</p>
            </div>

            <div class="recording-rule">{loadout_html(notes)}</div>
        </div>
        """
    )


def render_recording_director_card(plan: dict):
    stop = current_recording_stop(plan)

    if not stop:
        return

    weapon = loadout_clean(stop.get("weapon")) or "assigned objective"
    camo = loadout_clean(stop.get("camo")) or "objective"
    mode = loadout_clean(stop.get("mode") or plan.get("mode")) or "selected mode"
    challenge = loadout_clean(stop.get("challenge_text")) or "complete the assigned objective"
    task_type = loadout_clean(stop.get("task_type")) or "objective"

    optional_stacks = stop.get("companion_objectives", []) or []
    optional_stack_text = " · ".join(optional_stacks[:3]) if optional_stacks else "No optional stack needed."

    copy_bank = "\n".join([
        f"HOOK: I let the Commander choose my next BO7 grind. It picked {weapon}.",
        f"RULE: No rerolls unless the objective is impossible.",
        f"OBJECTIVE: {mode} - {weapon} - {camo}.",
        f"PROOF: The target is {challenge}.",
        f"MID-SESSION: I am not picking the easy option. The Commander already locked the route.",
        f"PROGRESS: If this lands, the tracker moves and the debrief decides whether the route worked.",
        f"ENDING: The AI chose the grind. I followed the plan. Now the debrief judges the session.",
    ])

    render_recording_markup(
        f"""
        <div class="recording-card director-card">
            <div class="recording-eyebrow">RECORDING DIRECTOR</div>
            <div class="recording-title">SHOT LIST LOCKED</div>
            <div class="recording-subtitle">{loadout_html(mode)} · {loadout_html(task_type)}</div>

            <div class="recording-section">
                <span>Video Hook</span>
                <p>I let the Commander choose my next BO7 grind. It picked <strong>{loadout_html(weapon)}</strong>.</p>
            </div>

            <div class="shot-list">
                <div class="shot-item">
                    <span>Clip 1</span>
                    <p>Show the Commander decision card. Hold long enough for the objective to be readable.</p>
                </div>
                <div class="shot-item">
                    <span>Clip 2</span>
                    <p>Show the Loadout Commander card. Capture the weapon/build proof before gameplay.</p>
                </div>
                <div class="shot-item">
                    <span>Clip 3</span>
                    <p>Cut to gameplay with the assigned weapon. Do not explain too much, just prove the route.</p>
                </div>
                <div class="shot-item">
                    <span>Clip 4</span>
                    <p>Capture the unlock, progress bar, camo pop, or post-match proof screen.</p>
                </div>
                <div class="shot-item">
                    <span>Clip 5</span>
                    <p>Return to the Progress Banked pop after logging the objective.</p>
                </div>
                <div class="shot-item">
                    <span>Clip 6</span>
                    <p>End on the Commander debrief. This is the proof that the AI-controlled session moved the tracker.</p>
                </div>
            </div>

            <div class="recording-section">
                <span>Optional Stack Callout</span>
                <p>{loadout_html(optional_stack_text)}</p>
            </div>

            <div class="recording-rule">CAPTURE THE DECISION, THE LOADOUT, THE PROOF, THE DEBRIEF.</div>
        </div>
        """
    )

    st.text_area(
        "Copyable recording lines",
        value=copy_bank,
        height=190,
        key=f"bo7_recording_copy_bank_{stop.get('task_id', 'active')}",
        help="Paste into notes, OBS scene notes, or your edit checklist.",
    )

def render_recording_debrief_card(plan: dict):
    if not plan:
        return

    debrief = build_session_debrief(
        plan=plan,
        stop_results=st.session_state.get("bo7_stop_results", {}),
        account_levels_gained=float(st.session_state.get("bo7_account_levels_gained", 0.0) or 0.0),
        actual_minutes_played=int(st.session_state.get("bo7_actual_minutes_played", 0) or 0),
    )

    counts = debrief.get("counts", {})
    done_count = int(counts.get("done", 0) or 0)
    partial_count = int(counts.get("partial", 0) or 0)
    skipped_count = int(counts.get("skipped", 0) or 0)
    pending_count = int(counts.get("pending", 0) or 0)

    total_stops = done_count + partial_count + skipped_count + pending_count
    resolved_count = done_count + partial_count + skipped_count
    useful_count = done_count + partial_count

    completion_rate = 0
    if total_stops > 0:
        completion_rate = int(round((useful_count / total_stops) * 100))

    account_levels = float(debrief.get("account_levels_gained", 0.0) or 0.0)
    actual_minutes = int(debrief.get("actual_minutes_played", 0) or 0)
    available_minutes = int(debrief.get("available_minutes", 0) or 0)

    completed_items = debrief.get("completed_items", []) or []
    skipped_items = debrief.get("skipped_items", []) or []

    completed_text = " · ".join(completed_items[:3]) if completed_items else "No full objective clears logged yet."
    skipped_text = " · ".join(skipped_items[:2]) if skipped_items else "No major blockers logged."

    if done_count >= 3:
        headline = "ROUTE WORKED"
        verdict_line = "The Commander picked a productive route. Keep this logic."
        ending_line = "The AI route moved the tracker. No reroll needed."
    elif done_count >= 1 or partial_count >= 2:
        headline = "PROGRESS BANKED"
        verdict_line = "The session moved forward. Not perfect, but the tracker is better than when it started."
        ending_line = "The Commander made the call. Progress still landed."
    elif partial_count >= 1:
        headline = "PARTIAL ROUTE"
        verdict_line = "The route was not clean, but some progress was still banked."
        ending_line = "Not a clean win, but the Commander still forced progress."
    else:
        headline = "ROUTE FAILED"
        verdict_line = "The objective did not land. Next session needs a cleaner route or lower friction target."
        ending_line = "The AI picked it. The session exposed the blocker."

    if skipped_count:
        blocker_line = f"{skipped_count} blocker logged. Use that as the next routing correction."
    else:
        blocker_line = "No blocker strong enough to break the no-reroll rule."

    time_line = f"{actual_minutes} min played" if actual_minutes else f"{available_minutes} min planned"

    render_recording_markup(
        f"""
        <div class="recording-card debrief-card">
            <div class="recording-eyebrow">SESSION DEBRIEF</div>
            <div class="recording-title">{loadout_html(headline)}</div>
            <div class="recording-subtitle">{loadout_html(debrief.get("primary_route", "Unknown route"))}</div>

            <div class="debrief-verdict-box">
                <span>Commander Verdict</span>
                <p>{loadout_html(verdict_line)}</p>
            </div>

            <div class="recording-grid">
                <div><span>Done</span><strong>{loadout_html(done_count)}</strong></div>
                <div><span>Partial</span><strong>{loadout_html(partial_count)}</strong></div>
                <div><span>Skipped</span><strong>{loadout_html(skipped_count)}</strong></div>
            </div>

            <div class="recording-grid">
                <div><span>Useful Rate</span><strong>{loadout_html(completion_rate)}%</strong></div>
                <div><span>Resolved</span><strong>{loadout_html(resolved_count)} / {loadout_html(total_stops)}</strong></div>
                <div><span>Time</span><strong>{loadout_html(time_line)}</strong></div>
            </div>

            <div class="recording-section">
                <span>Progress Banked</span>
                <p>{loadout_html(completed_text)}</p>
            </div>

            <div class="recording-section">
                <span>Blockers</span>
                <p>{loadout_html(skipped_text)} {loadout_html(blocker_line)}</p>
            </div>

            <div class="recording-section">
                <span>Account Progress</span>
                <p>Account levels gained: +{loadout_html(f"{account_levels:g}")}</p>
            </div>

            <div class="debrief-line-card">
                <div class="recording-section">
                    <span>Recording Lines</span>
                    <p>
                        <strong>End line:</strong> {loadout_html(ending_line)}<br>
                        <strong>Proof line:</strong> {loadout_html(done_count)} done, {loadout_html(partial_count)} partial, {loadout_html(skipped_count)} skipped.<br>
                        <strong>Next-session tease:</strong> The Commander will reroute from this debrief.
                    </p>
                </div>
            </div>

            <div class="recording-rule">SESSION CLOSED. ROUTE MEMORY UPDATED.</div>
        </div>
        """
    )

def render_live_objective_hud(plan: dict):
    """
    Shows the currently active objective as a play-now HUD.

    This is intentionally UI-only. It reads the same active stop and timer state
    already used by the session plan, without changing route logic or logging.
    """
    if not plan:
        return

    stop = active_stop_for_timing(plan)

    if not stop:
        return

    task_id = stop.get("task_id", "")
    weapon = loadout_clean(stop.get("weapon")) or "Assigned Objective"
    camo = loadout_clean(stop.get("camo")) or "Objective"
    mode = loadout_clean(stop.get("mode") or plan.get("mode")) or "Unknown Mode"
    task_type = loadout_clean(stop.get("task_type")) or "objective"
    challenge = loadout_clean(stop.get("challenge_text")) or "Complete the assigned objective."
    stop_number = loadout_clean(stop.get("stop_number")) or "1"
    total_stops = len(plan.get("stops", []) or [])

    elapsed = current_stop_elapsed_minutes()
    remaining = current_time_remaining(plan)
    logged = logged_stop_minutes()
    available = plan_available_minutes(plan)
    estimated = int(stop.get("estimated_minutes", 0) or 0)

    resolved_count = len(resolved_stop_ids())
    route_progress = 0
    if total_stops:
        route_progress = int(round((resolved_count / total_stops) * 100))

    status = stop_status(task_id).upper()

    if estimated and elapsed > estimated:
        pressure = "Over estimate"
    elif remaining <= 10:
        pressure = "Final push"
    elif elapsed <= 2:
        pressure = "Just started"
    else:
        pressure = "On route"

    optional_stacks = stop.get("companion_objectives", []) or []
    if optional_stacks:
        stack_text = "Stack if free: " + " · ".join(optional_stacks[:3])
    else:
        stack_text = "No optional stack required. Focus the assigned objective."

    render_recording_markup(
        f"""
        <div class="live-hud-card">
            <div class="live-hud-eyebrow">LIVE OBJECTIVE HUD</div>
            <div class="live-hud-title">{loadout_html(weapon)}</div>
            <div class="live-hud-subtitle">{loadout_html(camo)} · {loadout_html(mode)} · {loadout_html(task_type)}</div>

            <div class="live-hud-command">
                <span>Commander Order</span>
                <p>{loadout_html(challenge)}</p>
            </div>

            <div class="live-hud-grid">
                <div><span>Stop</span><strong>{loadout_html(stop_number)} / {loadout_html(total_stops)}</strong></div>
                <div><span>Status</span><strong>{loadout_html(status)}</strong></div>
                <div><span>Elapsed</span><strong>{loadout_html(elapsed)} min</strong></div>
                <div><span>Time Left</span><strong>{loadout_html(remaining)} min</strong></div>
            </div>

            <div class="live-hud-grid">
                <div><span>Route</span><strong>{loadout_html(route_progress)}%</strong></div>
                <div><span>Logged</span><strong>{loadout_html(logged)} / {loadout_html(available)} min</strong></div>
                <div><span>Estimate</span><strong>{loadout_html(estimated or "?")} min</strong></div>
                <div><span>Pressure</span><strong>{loadout_html(pressure)}</strong></div>
            </div>

            <div class="live-hud-command">
                <span>Stacking Note</span>
                <p>{loadout_html(stack_text)}</p>
            </div>

            <div class="recording-rule">PLAY THIS OBJECTIVE NOW. LOG PROGRESS BEFORE MOVING ON.</div>
        </div>
        """
    )

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

CAMO_CHAIN_FILES = {
    "Apocalypse": "apocalypse_status.csv",
    "Singularity": "singularity_status.csv",
    "Infestation": "infestation_status.csv",
    "Genesis": "genesis_status.csv",
}


def write_camo_completion_from_stop(stop) -> bool:
    """
    Writes a completed session-plan camo objective back into the source camo CSV.

    Supports task IDs shaped like:
    Camo:{mode}:{chain}:{weapon}:{camo_name}

    v1 updates the exact camo column named in the task_id.
    """
    task_id = str(stop.get("task_id", "")).strip()

    if not task_id.startswith("Camo:"):
        return False

    parts = task_id.split(":", 4)

    if len(parts) != 5:
        return False

    _prefix, mode, chain, weapon, camo_name = parts

    filename = CAMO_CHAIN_FILES.get(chain)

    if not filename:
        return False

    dataframe = load_quick_update_csv(filename)

    if dataframe.empty:
        return False

    required_columns = {"mode", "chain", "weapon"}

    if not required_columns.issubset(set(dataframe.columns)):
        return False

    if camo_name not in dataframe.columns:
        return False

    row_mask = (
        dataframe["mode"].fillna("").str.strip().eq(mode)
        & dataframe["chain"].fillna("").str.strip().eq(chain)
        & dataframe["weapon"].fillna("").str.strip().eq(weapon)
    )

    if not row_mask.any():
        return False

    dataframe.loc[row_mask, camo_name] = "TRUE"
    save_quick_update_csv(filename, dataframe)

    return True

def write_reticle_completion_from_stop(stop) -> bool:
    """
    Writes a completed session-plan reticle objective back into reticles.csv.

    Supports task IDs shaped like:
    Reticle:{mode}:{reticle}:{stage_percent}

    This is mode-specific. Completing Warzone VAS MicroFlex 100 does not touch
    Multiplayer, Zombies, or Co-Op / Endgame VAS MicroFlex rows.
    """
    task_id = str(stop.get("task_id", "")).strip()

    if not task_id.startswith("Reticle:"):
        return False

    parts = task_id.split(":", 3)

    if len(parts) != 4:
        return False

    _prefix, mode, reticle, stage_percent = parts

    stage_column = f"stage_{stage_percent}_complete"

    dataframe = load_quick_update_csv("reticles.csv")

    if dataframe.empty:
        return False

    required_columns = {"mode", "reticle"}

    if not required_columns.issubset(set(dataframe.columns)):
        return False

    if stage_column not in dataframe.columns:
        return False

    row_mask = (
        dataframe["mode"].fillna("").str.strip().eq(mode)
        & dataframe["reticle"].fillna("").str.strip().eq(reticle)
    )

    if not row_mask.any():
        return False

    dataframe.loc[row_mask, stage_column] = "TRUE"
    save_quick_update_csv("reticles.csv", dataframe)

    return True

def write_reticle_reached_from_stop(stop, reached_stage: str) -> bool:
    """
    Marks all reticle stages up to reached_stage as TRUE.

    Supports task IDs shaped like:
    Reticle:{mode}:{reticle}:{stage_percent}

    Mode-specific, so Warzone reticle progress does not touch MP/ZM/Co-Op rows.
    """
    if not reached_stage or reached_stage == "No extra update":
        return False

    task_id = str(stop.get("task_id", "")).strip()

    if not task_id.startswith("Reticle:"):
        return False

    parts = task_id.split(":", 3)

    if len(parts) != 4:
        return False

    _prefix, mode, reticle, _stage_percent = parts

    stage_order = ["20", "40", "60", "80", "100"]

    if reached_stage not in stage_order:
        return False

    dataframe = load_quick_update_csv("reticles.csv")

    if dataframe.empty:
        return False

    required_columns = {"mode", "reticle"}

    if not required_columns.issubset(set(dataframe.columns)):
        return False

    row_mask = (
        dataframe["mode"].fillna("").str.strip().eq(mode)
        & dataframe["reticle"].fillna("").str.strip().eq(reticle)
    )

    if not row_mask.any():
        return False

    reached_index = stage_order.index(reached_stage)

    for stage in stage_order[:reached_index + 1]:
        column = f"stage_{stage}_complete"
        if column in dataframe.columns:
            dataframe.loc[row_mask, column] = "TRUE"

    save_quick_update_csv("reticles.csv", dataframe)

    return True


def camo_reached_options_from_stop(stop) -> list[str]:
    task_id = str(stop.get("task_id", "")).strip()

    if not task_id.startswith("Camo:"):
        return ["No extra update"]

    parts = task_id.split(":", 4)

    if len(parts) != 5:
        return ["No extra update"]

    _prefix, mode, chain, weapon, camo_name = parts
    filename = CAMO_CHAIN_FILES.get(chain)

    if not filename:
        return ["No extra update"]

    dataframe = load_quick_update_csv(filename)

    if dataframe.empty:
        return ["No extra update"]

    row_mask = (
        dataframe["mode"].fillna("").str.strip().eq(mode)
        & dataframe["chain"].fillna("").str.strip().eq(chain)
        & dataframe["weapon"].fillna("").str.strip().eq(weapon)
    )

    if not row_mask.any():
        return ["No extra update"]

    id_columns = {"mode", "chain", "weapon_class", "weapon"}
    camo_columns = [
        column for column in dataframe.columns
        if column not in id_columns
        and str(dataframe.loc[row_mask, column].iloc[0]).strip().upper() not in {"N/A", "NA", "NONE", ""}
    ]

    if camo_name in camo_columns:
        camo_columns = camo_columns[camo_columns.index(camo_name):]

    return ["No extra update"] + camo_columns


def write_camo_reached_from_stop(stop, reached_camo: str) -> bool:
    """
    Marks all camo columns up to reached_camo as TRUE for the objective weapon.

    This handles real sessions where the Commander asked for Military 5-9,
    but you kept going and reached Golden Dragon, Doomsteel, etc.
    """
    if not reached_camo or reached_camo == "No extra update":
        return False

    task_id = str(stop.get("task_id", "")).strip()

    if not task_id.startswith("Camo:"):
        return False

    parts = task_id.split(":", 4)

    if len(parts) != 5:
        return False

    _prefix, mode, chain, weapon, _assigned_camo = parts
    filename = CAMO_CHAIN_FILES.get(chain)

    if not filename:
        return False

    dataframe = load_quick_update_csv(filename)

    if dataframe.empty:
        return False

    row_mask = (
        dataframe["mode"].fillna("").str.strip().eq(mode)
        & dataframe["chain"].fillna("").str.strip().eq(chain)
        & dataframe["weapon"].fillna("").str.strip().eq(weapon)
    )

    if not row_mask.any():
        return False

    id_columns = {"mode", "chain", "weapon_class", "weapon"}
    camo_columns = [
        column for column in dataframe.columns
        if column not in id_columns
        and str(dataframe.loc[row_mask, column].iloc[0]).strip().upper() not in {"N/A", "NA", "NONE", ""}
    ]

    if reached_camo not in camo_columns:
        return False

    reached_index = camo_columns.index(reached_camo)

    for column in camo_columns[:reached_index + 1]:
        dataframe.loc[row_mask, column] = "TRUE"

    save_quick_update_csv(filename, dataframe)

    return True

def weapon_level_snapshot_for_stop(stop: dict) -> dict:
    weapon = str(stop.get("weapon", "")).strip()

    if not weapon:
        return {
            "found": False,
            "message": "No weapon found for this objective.",
            "current_level": 0.0,
            "max_level": 0.0,
        }

    dataframe = load_quick_update_csv("weapon_prestige.csv")

    if dataframe.empty or "weapon" not in dataframe.columns:
        return {
            "found": False,
            "message": "weapon_prestige.csv unavailable.",
            "current_level": 0.0,
            "max_level": 0.0,
        }

    if "current_level" not in dataframe.columns:
        dataframe["current_level"] = "0"

    row_mask = dataframe["weapon"].fillna("").str.strip().eq(weapon)

    if not row_mask.any():
        return {
            "found": False,
            "message": f"{weapon} not found in weapon_prestige.csv.",
            "current_level": 0.0,
            "max_level": 0.0,
        }

    row = dataframe.loc[row_mask].iloc[0]

    try:
        current_level = float(str(row.get("current_level", "0")).strip() or 0)
    except ValueError:
        current_level = 0.0

    try:
        max_level = float(str(row.get("max_level", "0")).strip() or 0)
    except ValueError:
        max_level = 0.0

    if max_level > 0:
        message = f"Current weapon level before this objective: {current_level:g}/{max_level:g}"
    else:
        message = f"Current weapon level before this objective: {current_level:g}"

    return {
        "found": True,
        "message": message,
        "current_level": current_level,
        "max_level": max_level,
    }


def write_weapon_level_progress_from_stop(
    stop,
    levels_gained: float = 0.0,
    prestiged_reset: bool = False,
) -> dict:
    """
    Updates current weapon level in weapon_prestige.csv.

    v1 behaviour:
    - Adds levels_gained to current_level.
    - Creates current_level column if missing.
    - Caps visible current_level at max_level before prestige reset.
    - If prestiged_reset is True:
        - marks p1_complete if not already done
        - else marks p2_complete if not already done
        - resets current_level to 0
    """
    weapon = str(stop.get("weapon", "")).strip()

    if not weapon:
        return {"updated": False, "message": "No weapon found on objective."}

    dataframe = load_quick_update_csv("weapon_prestige.csv")

    if dataframe.empty:
        return {"updated": False, "message": "weapon_prestige.csv not found."}

    if "weapon" not in dataframe.columns:
        return {"updated": False, "message": "weapon_prestige.csv missing weapon column."}

    if "current_level" not in dataframe.columns:
        dataframe["current_level"] = "0"

    row_mask = dataframe["weapon"].fillna("").str.strip().eq(weapon)

    if not row_mask.any():
        return {"updated": False, "message": f"{weapon} not found in weapon_prestige.csv."}

    row_index = dataframe.index[row_mask][0]
    row = dataframe.loc[row_index]

    try:
        current_level = float(str(row.get("current_level", "0")).strip() or 0)
    except ValueError:
        current_level = 0.0

    try:
        max_level = float(str(row.get("max_level", "0")).strip() or 0)
    except ValueError:
        max_level = 0.0

    levels_gained = max(0.0, float(levels_gained or 0.0))
    new_level = current_level + levels_gained

    if max_level > 0:
        new_level = min(new_level, max_level)

    prestige_marked = ""

    if prestiged_reset:
        if "p1_complete" in dataframe.columns and not is_true_cell(row.get("p1_complete", "")):
            dataframe.loc[row_index, "p1_complete"] = "TRUE"
            prestige_marked = "Prestige 1"
        elif "p2_complete" in dataframe.columns and not is_true_cell(row.get("p2_complete", "")):
            dataframe.loc[row_index, "p2_complete"] = "TRUE"
            prestige_marked = "Prestige 2"

        dataframe.loc[row_index, "current_level"] = "0"
    else:
        dataframe.loc[row_index, "current_level"] = f"{new_level:g}"

    save_quick_update_csv("weapon_prestige.csv", dataframe)

    if prestiged_reset and prestige_marked:
        return {
            "updated": True,
            "message": f"{weapon}: {prestige_marked} marked complete. Level reset to 0.",
            "hit_cap": False,
            "prestige_marked": prestige_marked,
        }

    hit_cap = max_level > 0 and new_level >= max_level

    return {
        "updated": True,
        "message": f"{weapon}: +{levels_gained:g} levels. Current level {new_level:g}/{max_level:g}.",
        "hit_cap": hit_cap,
        "prestige_marked": "",
    }


def queue_weapon_level_celebration(stop: dict, level_result: dict):
    if not level_result.get("updated"):
        return

    weapon = stop.get("weapon", "Weapon")
    message = level_result.get("message", "")

    if level_result.get("prestige_marked"):
        queue_celebration(
            "⚙️ WEAPON PRESTIGE RESET",
            message,
            "major",
        )
        return

    if level_result.get("hit_cap"):
        queue_celebration(
            "🔺 WEAPON LEVEL CAP REACHED",
            f"{weapon} hit its current level cap. Prestige/reset is available.",
            "major",
        )
        return

    queue_celebration(
        "📈 WEAPON LEVELS LOGGED",
        message,
        "minor",
    )


def render_objective_progress_pulse(
    stop: dict,
    task_id: str,
    weapon_level_key: str,
    weapon_reset_key: str,
    account_level_key: str,
    camo_reached_key: str,
    reticle_reached_key: str,
):
    """Compact in-objective progress capture so updates happen as they are earned."""
    st.markdown("#### ⚡ Progress Pulse")
    st.caption(
        "Bank progress here before pressing Objective Done or Partial Progress. "
        "This keeps the debrief as a check, not a memory test."
    )

    pulse_cols = st.columns(3)

    with pulse_cols[0]:
        st.markdown("**Weapon XP**")
        level_snapshot = weapon_level_snapshot_for_stop(stop)

        if level_snapshot.get("found"):
            st.info(level_snapshot["message"])
            input_label = (
                f"Levels gained from "
                f"{level_snapshot.get('current_level', 0):g}"
            )
        else:
            st.warning(level_snapshot["message"])
            input_label = "Weapon levels gained"

        st.number_input(
            input_label,
            min_value=0.0,
            max_value=250.0,
            value=0.0,
            step=0.5,
            key=weapon_level_key,
        )

        st.checkbox(
            "Prestiged/reset after this objective",
            key=weapon_reset_key,
        )

    with pulse_cols[1]:
        st.markdown("**Account XP**")
        current_account_level = float(
            st.session_state.get("bo7_account_params", {}).get("account_level", 1.0)
            or 1.0
        )
        st.metric("Current account level", f"{current_account_level:g}")
        st.number_input(
            "Account levels gained",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=0.5,
            key=account_level_key,
            help="Logged immediately when this objective is marked Done or Partial.",
        )
        session_account_levels = float(
            st.session_state.get("bo7_account_levels_gained", 0.0)
            or 0.0
        )
        if session_account_levels:
            st.caption(f"Already banked this session: +{session_account_levels:g}")

    with pulse_cols[2]:
        st.markdown("**Completion Sync**")

        if stop.get("task_type") == "camo":
            st.selectbox(
                "Highest camo reached",
                camo_reached_options_from_stop(stop),
                key=camo_reached_key,
            )
            st.caption("Marks every camo up to the selected camo as complete.")
        elif stop.get("task_type") == "reticle":
            st.selectbox(
                "Highest reticle stage reached",
                ["No extra update", "20", "40", "60", "80", "100"],
                key=reticle_reached_key,
            )
            st.caption("Marks every stage up to the selected stage as complete.")
        else:
            st.info("Use Session Catch-Up above for accidental badges, cards, reticles, or scorestreak progress.")

    st.caption(
        "Then press Objective Done or Partial Progress. The Commander will log the objective, "
        "update CSV progress where possible, and refresh the route."
    )


def reload_commander_from_csv():
    st.session_state.bo7_completion_state = load_completion_state()
    st.session_state.bo7_tasks = apply_completion_state(
        load_tracker_tasks(),
        st.session_state.bo7_completion_state,
    )
    st.session_state.bo7_progress = load_hub_progress()
    st.session_state.bo7_latest_mission = None

def queue_celebration(
    title: str,
    message: str,
    tier: str = "minor",
    label: str = "Progress Banked",
    stat: str = "Logged",
    footer: str = "Commander route updated.",
):
    if "bo7_celebrations" not in st.session_state:
        st.session_state.bo7_celebrations = []

    st.session_state.bo7_celebrations.append({
        "title": title,
        "message": message,
        "tier": tier,
        "label": label,
        "stat": stat,
        "footer": footer,
        "time": datetime.now().isoformat(timespec="seconds"),
    })


def queue_stop_celebration(stop: dict, csv_updated: bool):
    task_type = stop.get("task_type", "")
    mode = stop.get("mode", "")
    weapon = stop.get("weapon", "")
    camo = stop.get("camo", "")
    challenge = stop.get("challenge_text", "")

    sync_status = "CSV Updated" if csv_updated else "Logged Only"
    footer = "Source tracker changed." if csv_updated else "Session memory updated. Manual source sync may still be needed."

    if task_type == "camo":
        queue_celebration(
            "🎨 CAMO CLEARED",
            f"{weapon} - {camo} completed in {mode}.",
            "minor",
            label="Progress Banked",
            stat=sync_status,
            footer=footer,
        )
        return

    if task_type == "reticle":
        queue_celebration(
            "🎯 RETICLE STAGE CLEARED",
            f"{weapon} - {camo} completed in {mode}. Reticle mastery moved forward.",
            "minor",
            label="Progress Banked",
            stat=sync_status,
            footer=footer,
        )
        return

    if task_type == "weapon_prestige":
        queue_celebration(
            "⚙️ WEAPON PRESTIGE PROGRESS",
            f"{weapon} - {camo}. Weapon XP grind moved forward.",
            "minor",
            label="Weapon Route Advanced",
            stat=sync_status,
            footer=footer,
        )
        return

    if task_type == "mastery_badge_weapon":
        queue_celebration(
            "🏅 WEAPON BADGE PROGRESS",
            f"{weapon} - {camo}. Badge route advanced.",
            "minor",
            label="Badge Progress",
            stat=sync_status,
            footer=footer,
        )
        return

    if task_type == "mastery_badge_equipment":
        queue_celebration(
            "🧰 SUPPORT BADGE PROGRESS",
            f"{weapon} - {camo}. Support grind advanced.",
            "minor",
            label="Support Progress",
            stat=sync_status,
            footer=footer,
        )
        return

    if task_type == "dark_ops":
        queue_celebration(
            "💀 DARK OPS HIT",
            f"{weapon}: {challenge}",
            "major",
            label="Major Unlock",
            stat="Route Spiked",
            footer="Clip this. This is a video moment.",
        )
        return

    if task_type == "calling_card":
        queue_celebration(
            "🃏 CALLING CARD PROGRESS",
            f"{weapon} - {camo}. Calling-card route advanced.",
            "minor",
            label="Collection Progress",
            stat=sync_status,
            footer=footer,
        )
        return

    if task_type == "title":
        queue_celebration(
            "🏷 TITLE PROGRESS",
            f"{weapon}: {challenge}",
            "minor",
            label="Title Progress",
            stat=sync_status,
            footer=footer,
        )
        return

    queue_celebration(
        "✅ OBJECTIVE LOGGED",
        f"{weapon} - {camo}",
        "minor",
        label="Progress Banked",
        stat=sync_status,
        footer=footer,
    )

def render_queued_celebrations():
    celebrations = st.session_state.get("bo7_celebrations", [])

    if not celebrations:
        return

    for celebration in celebrations:
        title = celebration.get("title", "✅ Progress")
        message = celebration.get("message", "")
        tier = celebration.get("tier", "minor")
        label = celebration.get("label", "Progress Banked")
        stat = celebration.get("stat", "Logged")
        footer = celebration.get("footer", "Commander route updated.")
        recorded_time = celebration.get("time", "")

        tier_class = "major" if tier == "major" else "minor"
        icon = "🔥" if tier == "major" else "✅"

        st.toast(f"{title} - {message}", icon=icon)

        render_recording_markup(
            f"""
            <div class="progress-pop-card progress-pop-{loadout_html(tier_class)}">
                <div class="progress-pop-eyebrow">{loadout_html(label)}</div>
                <div class="progress-pop-title">{loadout_html(title)}</div>
                <div class="progress-pop-message">{loadout_html(message)}</div>
                <div class="progress-pop-grid">
                    <div><span>Status</span><strong>{loadout_html(stat)}</strong></div>
                    <div><span>Logged</span><strong>{loadout_html(recorded_time[-8:] if recorded_time else "Now")}</strong></div>
                    <div><span>Rule</span><strong>No reroll</strong></div>
                </div>
                <div class="recording-rule">{loadout_html(footer)}</div>
            </div>
            """
        )

    st.session_state.bo7_celebrations = []

def build_session_debrief(plan: dict, stop_results: dict, account_levels_gained: float, actual_minutes_played: int = 0) -> dict:
    stops = plan.get("stops", []) if plan else []

    counts = {
        "done": 0,
        "partial": 0,
        "skipped": 0,
        "pending": 0,
    }

    completed_types = {}
    completed_items = []
    skipped_items = []

    for stop in stops:
        task_id = stop.get("task_id", "")
        result = stop_results.get(task_id, {})
        status = result.get("status", "pending")

        if status not in counts:
            status = "pending"

        counts[status] += 1

        if status == "done":
            task_type = stop.get("task_type", "unknown")
            completed_types[task_type] = completed_types.get(task_type, 0) + 1
            completed_items.append(
                f"{stop.get('weapon', 'Unknown')} - {stop.get('camo', 'Objective')}"
            )

        if status == "skipped":
            skipped_items.append(
                f"{stop.get('weapon', 'Unknown')} - {stop.get('camo', 'Objective')}"
            )

    route_summary = plan.get("route_summary", {}) if plan else {}

    if counts["done"] >= 3:
        verdict = "Strong session. The tracker moved."
    elif counts["done"] >= 1:
        verdict = "Progress banked. Good enough counts."
    elif counts["partial"] >= 1:
        verdict = "Partial progress logged. Not wasted."
    else:
        verdict = "No confirmed completions. Reset and re-route next time."

    return {
        "mode": plan.get("mode", "Unknown") if plan else "Unknown",
        "available_minutes": plan.get("available_minutes", 0) if plan else 0,
        "estimated_minutes": plan.get("estimated_minutes", 0) if plan else 0,
        "actual_minutes_played": actual_minutes_played,
        "primary_route": route_summary.get("primary_route", "Unknown route"),
        "counts": counts,
        "completed_types": completed_types,
        "completed_items": completed_items[:5],
        "skipped_items": skipped_items[:3],
        "account_levels_gained": account_levels_gained,
        "verdict": verdict,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def render_session_debrief():
    debrief = st.session_state.get("bo7_last_debrief")

    if not debrief:
        return

    st.markdown("### Commander Debrief")

    counts = debrief.get("counts", {})

    debrief_cols = st.columns(6)

    with debrief_cols[0]:
        st.metric("Done", counts.get("done", 0))

    with debrief_cols[1]:
        st.metric("Partial", counts.get("partial", 0))

    with debrief_cols[2]:
        st.metric("Skipped", counts.get("skipped", 0))

    with debrief_cols[3]:
        st.metric("Pending", counts.get("pending", 0))

    with debrief_cols[4]:
        st.metric(
            "Account Levels",
            f"+{float(debrief.get('account_levels_gained', 0.0)):g}",
        )

    with debrief_cols[5]:
        st.metric(
            "Actual Time",
            f"{int(debrief.get('actual_minutes_played', 0) or 0)} min",
            f"{int(debrief.get('estimated_minutes', 0) or 0)} min est.",
        )

    st.success(
        f"**{debrief.get('verdict', 'Session closed.')}**  \n"
        f"Route: {debrief.get('primary_route', 'Unknown route')}  \n"
        f"Mode: {debrief.get('mode', 'Unknown')}"
    )

    completed_types = debrief.get("completed_types", {})
    if completed_types:
        mix_text = " · ".join(
            f"{task_type}: {count}"
            for task_type, count in completed_types.items()
        )
        st.caption(f"Completed mix: {mix_text}")

    completed_items = debrief.get("completed_items", [])
    if completed_items:
        with st.expander("Completed this session"):
            for item in completed_items:
                st.write(f"- {item}")

    skipped_items = debrief.get("skipped_items", [])
    if skipped_items:
        with st.expander("Skipped this session"):
            for item in skipped_items:
                st.write(f"- {item}")

    if st.button("CLEAR DEBRIEF", use_container_width=True):
        st.session_state.bo7_last_debrief = None
        st.rerun()

def tracker_bucket_is_done(bucket: dict) -> bool:
    done = int(bucket.get("done", 0) or 0)
    total = int(bucket.get("total", 0) or 0)
    return total > 0 and done >= total


def tuple_bucket_is_done(value) -> bool:
    if not value:
        return False

    done, total = value
    done = int(done or 0)
    total = int(total or 0)

    return total > 0 and done >= total


def capture_milestone_snapshot() -> dict:
    summary = compute_full_tracker_summary(CLEAN_DATA_DIR)

    snapshot = {
        "camo_calling_card_unlocks": {},
        "camo_true_final": {},
        "reticle_modes": {},
        "reticle_total": False,
        "calling_card_modes": {},
        "title_modes": {},
        "title_total": False,
    }

    camos = summary.get("camos", {})
    for chain_label, data in camos.items():
        snapshot["camo_calling_card_unlocks"][chain_label] = tracker_bucket_is_done({
            "done": data.get("mastery_unlock_done", min(data.get("mastery_done", 0), 30)),
            "total": data.get("mastery_unlock_total", 30),
        })

        snapshot["camo_true_final"][chain_label] = tracker_bucket_is_done({
            "done": data.get("mastery_done", 0),
            "total": data.get("mastery_total", 0),
        })

    reticles = summary.get("reticles", {})
    reticle_total = reticles.get("total", {})
    snapshot["reticle_total"] = tracker_bucket_is_done(reticle_total)

    for mode, data in reticles.get("by_mode", {}).items():
        snapshot["reticle_modes"][mode] = tracker_bucket_is_done(data)

    calling_cards = summary.get("calling_cards", {})
    for mode, value in calling_cards.items():
        snapshot["calling_card_modes"][mode] = tuple_bucket_is_done(value)

    titles = summary.get("titles", {})
    title_total = titles.get("total", {})
    snapshot["title_total"] = tracker_bucket_is_done(title_total)

    for mode, data in titles.get("by_mode", {}).items():
        snapshot["title_modes"][mode] = tracker_bucket_is_done(data)

    return snapshot


def crossed_to_done(before: dict, after: dict, section: str, key: str) -> bool:
    before_value = before.get(section, {}).get(key, False)
    after_value = after.get(section, {}).get(key, False)

    return not before_value and after_value


def queue_milestone_celebrations(before: dict, after: dict):
    for chain_label in after.get("camo_calling_card_unlocks", {}):
        if crossed_to_done(before, after, "camo_calling_card_unlocks", chain_label):
            queue_celebration(
                "🔥 MASTERY CALLING CARD UNLOCKED",
                f"{chain_label} reached 30/30. The mastery calling-card gate is cleared.",
                "major",
            )

    for chain_label in after.get("camo_true_final", {}):
        if crossed_to_done(before, after, "camo_true_final", chain_label):
            queue_celebration(
                "🚨 TRUE FINAL CAMO CHAIN COMPLETE",
                f"{chain_label} is fully complete. That camo route is shut.",
                "major",
            )

    for mode in after.get("reticle_modes", {}):
        if crossed_to_done(before, after, "reticle_modes", mode):
            queue_celebration(
                "🎯 RETICLE MODE COMPLETE",
                f"All {mode} reticle progress is complete.",
                "major",
            )

    if not before.get("reticle_total", False) and after.get("reticle_total", False):
        queue_celebration(
            "🚨 ALL RETICLES COMPLETE",
            "Every reticle route is complete. No more optic chores.",
            "major",
        )

    for mode in after.get("calling_card_modes", {}):
        if crossed_to_done(before, after, "calling_card_modes", mode):
            queue_celebration(
                "🃏 CALLING CARD MODE COMPLETE",
                f"{mode} calling cards are 100% complete.",
                "major",
            )

    for mode in after.get("title_modes", {}):
        if crossed_to_done(before, after, "title_modes", mode):
            queue_celebration(
                "🏷 TITLE MODE COMPLETE",
                f"All {mode} titles are unlocked.",
                "major",
            )

    if not before.get("title_total", False) and after.get("title_total", False):
        queue_celebration(
            "👑 ALL TITLES COMPLETE",
            "The full title collection is complete.",
            "major",
        )

def is_true_cell(value):
    return str(value).strip().upper() in {"TRUE", "YES", "DONE", "COMPLETE", "COMPLETED", "✅"}

CALLING_CARD_FINAL_ROWS = {
    "calling_cards_sp.csv": "Co-Op Campaign 100 Percenter",
    "calling_cards_wz.csv": "Warzone 100 Percenter",
}

CALLING_CARD_FILES_SET = {
    "calling_cards_sp.csv",
    "calling_cards_mp.csv",
    "calling_cards_zm.csv",
    "calling_cards_wz.csv",
}

OPTIONAL_100_PERCENT_VALUES = {"FALSE", "NO", "0", "N", "OPTIONAL", "EXTRA"}


def row_counts_for_100_percent(row):
    value = str(row.get("counts_for_100_percent", "")).strip().upper()

    if not value:
        return True

    return value not in OPTIONAL_100_PERCENT_VALUES


def fill_inactive_calling_card_tiers(dataframe):
    """
    Calling-card rows often only have Tier 1, while Tier 2-5 targets are N/A.

    For cockpit/grid display and saves, inactive tiers should behave as already
    satisfied. This avoids red Xs on tiers that do not exist and prevents them
    from blocking completed/master calculations.
    """
    if dataframe is None or dataframe.empty:
        return dataframe

    updated_dataframe = dataframe.copy()

    for tier_number in range(1, 6):
        complete_column = f"tier{tier_number}_complete"
        target_column = f"tier{tier_number}_target"

        if complete_column not in updated_dataframe.columns or target_column not in updated_dataframe.columns:
            continue

        inactive_mask = (
            updated_dataframe[target_column]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .isin({"", "N/A", "NA", "NONE"})
        )

        updated_dataframe.loc[inactive_mask, complete_column] = "TRUE"

    return updated_dataframe


def calling_card_tier_is_applicable(row, tier_number: int) -> bool:
    complete_column = f"tier{tier_number}_complete"
    target_column = f"tier{tier_number}_target"

    if target_column in row.index:
        target_value = str(row.get(target_column, "")).strip().upper()
        if target_value in {"", "N/A", "NA", "NONE"}:
            return False

    complete_value = str(row.get(complete_column, "")).strip().upper()
    return complete_value not in {"", "N/A", "NA", "NONE"}


def normalise_calling_card_completion(dataframe, filename):
    if filename not in CALLING_CARD_FILES_SET:
        return dataframe

    updated_dataframe = fill_inactive_calling_card_tiers(dataframe)

    tier_columns = [
        "tier1_complete",
        "tier2_complete",
        "tier3_complete",
        "tier4_complete",
        "tier5_complete",
    ]

    # First pass: if every real/applicable tier is complete, mark the card complete.
    # Tiers whose target is N/A are treated as already satisfied.
    for row_index, row in updated_dataframe.iterrows():
        applicable_tiers = [
            column for tier_number, column in enumerate(tier_columns, start=1)
            if column in updated_dataframe.columns
            and calling_card_tier_is_applicable(row, tier_number)
        ]

        if applicable_tiers and all(is_true_cell(row.get(column, "")) for column in applicable_tiers):
            updated_dataframe.loc[row_index, "completed"] = "TRUE"

    final_card = CALLING_CARD_FINAL_ROWS.get(filename)

    if not final_card or "challenge" not in updated_dataframe.columns:
        return updated_dataframe

    final_card_mask = (
        updated_dataframe["challenge"].fillna("").str.strip() == final_card
    )

    if not final_card_mask.any():
        return updated_dataframe

    counted_mask = updated_dataframe.apply(row_counts_for_100_percent, axis=1)
    prerequisite_mask = counted_mask & ~final_card_mask

    prerequisites_done = updated_dataframe.loc[prerequisite_mask, "completed"].apply(is_true_cell)

    if len(prerequisites_done) > 0 and prerequisites_done.all():
        updated_dataframe.loc[final_card_mask, "tier1_complete"] = "TRUE"
        updated_dataframe.loc[final_card_mask, "completed"] = "TRUE"

    return updated_dataframe


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
    # Rewards / Unlocks / Collectibles
    "Zombies rewards": "rewards_zombies.csv",
    "Endgame operations": "rewards_endgame_operations.csv",
    "Endgame unlocks": "rewards_endgame_unlocks.csv",
    "Intel": "intel.csv",
    # Titles / Cosmetics / Upgrade systems
    "Titles": "titles.csv",
    "Zombies augments": "augments_zombies.csv",
    "Multiplayer overclocks": "overclocks_mp.csv",
}

QUICK_UPDATE_METADATA_COLUMNS = {
    "counts_for_100_percent",
    "display_as_extra",
    "stage_20_required",
    "stage_40_required",
    "stage_60_required",
    "stage_80_required",
    "stage_100_required",
    "bronze_required",
    "silver_required",
    "gold_required",
    "diamond_required",
    "requirement",
    "criteria",
    "max_level",
    "current_level",
    "unlock_criteria",
    "source",
    "item_type",
    "operator",
}
 
QUICK_UPDATE_ID_COLUMNS = {
    "apocalypse_status.csv": ["mode", "chain", "weapon_class", "weapon"],
    "singularity_status.csv": ["mode", "chain", "weapon_class", "weapon"],
    "infestation_status.csv": ["mode", "chain", "weapon_class", "weapon"],
    "genesis_status.csv": ["mode", "chain", "weapon_class", "weapon"],
    "weapon_prestige.csv": ["weapon_class", "weapon", "max_level", "current_level"],
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
    "rewards_zombies.csv": ["map", "category", "item"],
    "rewards_endgame_operations.csv": ["operation", "step"],
    "rewards_endgame_unlocks.csv": ["category", "operator", "item_type", "item", "unlock_criteria", "source"],
    "intel.csv": ["mode", "map", "category", "item"],
    "augments_zombies.csv": ["mode", "category", "item"],
    "overclocks_mp.csv": ["mode", "category", "item"],
}



def bool_to_csv_value(value):
    return "TRUE" if bool(value) else "FALSE"

def quick_update_status_columns(filename, dataframe):
    id_columns = QUICK_UPDATE_ID_COLUMNS.get(filename, [])
    ignored_columns = set(id_columns) | QUICK_UPDATE_METADATA_COLUMNS

    return [
        column for column in dataframe.columns
        if column not in ignored_columns
        and not column.endswith("_required")
        and not column.endswith("_target")
    ]

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
        height=720,
        hide_index=False,
        disabled=id_columns,
        column_config=column_config,
        key=f"quick_update_grid_{filename}",
    )

    if st.button("SAVE QUICK UPDATE", use_container_width=True):
        milestone_before = capture_milestone_snapshot()

        updated_dataframe = dataframe.copy()
        for row_index, edited_row in edited_dataframe.iterrows():
            for column in status_columns:
                updated_dataframe.loc[row_index, column] = bool_to_csv_value(edited_row[column])

        updated_dataframe = apply_smart_completion_rules(updated_dataframe, filename)
        updated_dataframe = normalise_calling_card_completion(updated_dataframe, filename)
        save_quick_update_csv(filename, updated_dataframe)
        milestone_after = capture_milestone_snapshot()
        queue_milestone_celebrations(milestone_before, milestone_after)
        queue_celebration(
            "📌 QUICK UPDATE SAVED",
            f"{selected_label} updated. Commander orders reloaded from clean CSV data.",
            "minor",
        )

        st.session_state.bo7_completion_state = load_completion_state()
        st.session_state.bo7_tasks = apply_completion_state(
            load_tracker_tasks(), st.session_state.bo7_completion_state,
        )
        st.session_state.bo7_progress = load_hub_progress()
        st.session_state.bo7_latest_mission = None

        st.success("Quick update saved. Orders reloaded from clean CSV data.")
        st.rerun()

def render_weapon_level_quick_update():
    st.caption(
        "One-time setup for current weapon levels. After this, Commander objective logging can keep these updated."
    )

    filename = "weapon_prestige.csv"
    dataframe = load_quick_update_csv(filename)

    if dataframe.empty:
        st.warning("No weapon_prestige.csv found.")
        return

    if "weapon" not in dataframe.columns:
        st.warning("weapon_prestige.csv is missing the weapon column.")
        return

    if "current_level" not in dataframe.columns:
        dataframe["current_level"] = "0"

    editable_dataframe = dataframe.copy()

    for column in ["current_level", "max_level"]:
        if column in editable_dataframe.columns:
            editable_dataframe[column] = pd.to_numeric(
                editable_dataframe[column],
                errors="coerce",
            ).fillna(0)

    display_columns = [
        column for column in [
            "weapon_class",
            "weapon",
            "current_level",
            "max_level",
            "p1_complete",
            "p2_complete",
            "wpm_complete",
            "lvl_100_complete",
            "lvl_150_complete",
            "lvl_200_complete",
            "lvl_250_complete",
        ]
        if column in editable_dataframe.columns
    ]

    class_options = ["All"]

    if "weapon_class" in editable_dataframe.columns:
        class_options += sorted(
            value for value in editable_dataframe["weapon_class"].dropna().unique().tolist()
            if str(value).strip()
        )

    selected_class = st.selectbox(
        "Weapon class",
        class_options,
        key="weapon_level_quick_class",
    )

    filtered_dataframe = editable_dataframe.copy()

    if selected_class != "All" and "weapon_class" in filtered_dataframe.columns:
        filtered_dataframe = filtered_dataframe[
            filtered_dataframe["weapon_class"] == selected_class
        ]

    editable_status_columns = [
        column for column in [
            "p1_complete",
            "p2_complete",
            "wpm_complete",
            "lvl_100_complete",
            "lvl_150_complete",
            "lvl_200_complete",
            "lvl_250_complete",
        ]
        if column in display_columns
    ]

    for column in editable_status_columns:
        filtered_dataframe[column] = filtered_dataframe[column].apply(is_true_cell)

    edited_dataframe = st.data_editor(
        filtered_dataframe[display_columns],
        use_container_width=True,
        height=720,
        hide_index=False,
        disabled=[
            column for column in display_columns
            if column not in {"current_level", *editable_status_columns}
        ],
        column_config={
            "current_level": st.column_config.NumberColumn(
                "Current Level",
                min_value=0,
                max_value=250,
                step=1,
            ),
            "max_level": st.column_config.NumberColumn(
                "Max Level",
                disabled=True,
            ),
            **{
                column: st.column_config.CheckboxColumn(column)
                for column in editable_status_columns
            },
        },
        key="weapon_level_quick_grid",
    )

    if st.button("SAVE WEAPON LEVELS", use_container_width=True):
        updated_dataframe = dataframe.copy()

        if "current_level" not in updated_dataframe.columns:
            updated_dataframe["current_level"] = "0"

        for row_index, edited_row in edited_dataframe.iterrows():
            updated_dataframe.loc[row_index, "current_level"] = f"{float(edited_row['current_level']):g}"

            for column in editable_status_columns:
                updated_dataframe.loc[row_index, column] = bool_to_csv_value(
                    edited_row.get(column, False)
                )

        save_quick_update_csv(filename, updated_dataframe)

        st.session_state.bo7_completion_state = load_completion_state()
        st.session_state.bo7_tasks = apply_completion_state(
            load_tracker_tasks(),
            st.session_state.bo7_completion_state,
        )
        st.session_state.bo7_progress = load_hub_progress()
        st.session_state.bo7_latest_mission = None

        queue_celebration(
            "📈 WEAPON LEVELS UPDATED",
            "Current weapon levels saved to weapon_prestige.csv.",
            "minor",
        )

        st.success("Weapon levels saved. Commander orders reloaded.")
        st.rerun()


# ─── TRACKER COCKPIT HELPERS ─────────────────────────────────────────────────

WEAPON_BADGE_DIAMOND_REQUIREMENTS = {
    "Assault Rifles": 6,
    "Submachine Guns": 6,
    "Shotguns": 3,
    "LMGs": 2,
    "Marksman Rifles": 3,
    "Sniper Rifles": 3,
    "Pistols": 3,
    "Launchers": 2,
    "Specials": 2,
    "Melee": 2,
    "Wonder Weapons": 3,
}

COCKPIT_CONFIGS = {
    "apocalypse_status.csv": {
        "label": "Apocalypse / Warzone Camos",
        "id_columns": ["weapon_class", "weapon"],
        "filter_columns": ["weapon_class"],
        "status_columns": None,
        "cascade": "row_order",
    },
    "singularity_status.csv": {
        "label": "Singularity / Multiplayer Camos",
        "id_columns": ["weapon_class", "weapon"],
        "filter_columns": ["weapon_class"],
        "status_columns": None,
        "cascade": "row_order",
    },
    "infestation_status.csv": {
        "label": "Infestation / Zombies Camos",
        "id_columns": ["weapon_class", "weapon"],
        "filter_columns": ["weapon_class"],
        "status_columns": None,
        "cascade": "row_order",
    },
    "genesis_status.csv": {
        "label": "Genesis / Co-Op Camos",
        "id_columns": ["weapon_class", "weapon"],
        "filter_columns": ["weapon_class"],
        "status_columns": None,
        "cascade": "row_order",
    },
    "weapon_prestige.csv": {
        "label": "Weapon Prestige",
        "id_columns": ["weapon_class", "weapon", "current_level", "max_level"],
        "filter_columns": ["weapon_class"],
        "status_columns": [
            "p1_complete", "p2_complete", "wpm_complete",
            "lvl_100_complete", "lvl_150_complete", "lvl_200_complete", "lvl_250_complete",
        ],
        "cascade": "row_order",
    },
    "mastery_badges_weapons.csv": {
        "label": "Weapon Mastery Badges",
        "id_columns": ["weapon_class", "weapon"],
        "filter_columns": ["weapon_class"],
        "status_columns": [
            "mp_bronze_complete", "mp_silver_complete", "mp_gold_complete", "mp_diamond_complete",
            "zm_bronze_complete", "zm_silver_complete", "zm_gold_complete", "zm_diamond_complete",
        ],
        "cascade": "weapon_badges",
    },
    "mastery_badges_equipment_mp.csv": {
        "label": "MP Equipment Mastery Badges",
        "id_columns": ["mode", "category", "item"],
        "filter_columns": ["category"],
        "status_columns": ["bronze_complete", "silver_complete", "gold_complete", "diamond_complete"],
        "cascade": "equipment_badges",
    },
    "mastery_badges_equipment_zombies.csv": {
        "label": "Zombies Equipment Mastery Badges",
        "id_columns": ["mode", "category", "item"],
        "filter_columns": ["category"],
        "status_columns": ["bronze_complete", "silver_complete", "gold_complete", "diamond_complete"],
        "cascade": "equipment_badges",
    },
    "reticles.csv": {
        "label": "Reticles",
        "id_columns": ["mode", "classification", "reticle"],
        "filter_columns": ["mode", "classification"],
        "status_columns": [
            "stage_20_complete", "stage_40_complete", "stage_60_complete",
            "stage_80_complete", "stage_100_complete",
        ],
        "cascade": "row_order",
    },
    "calling_cards_sp.csv": {
        "label": "Co-Op / Endgame Calling Cards",
        "id_columns": ["mode", "category", "sub_category", "challenge", "requirement"],
        "filter_columns": ["category", "sub_category"],
        "status_columns": [
            "tier1_complete", "tier2_complete", "tier3_complete",
            "tier4_complete", "tier5_complete", "completed",
        ],
        "cascade": "calling_cards",
    },
    "calling_cards_mp.csv": {
        "label": "Multiplayer Calling Cards",
        "id_columns": ["mode", "category", "sub_category", "challenge", "requirement"],
        "filter_columns": ["category", "sub_category"],
        "status_columns": [
            "tier1_complete", "tier2_complete", "tier3_complete",
            "tier4_complete", "tier5_complete", "completed",
        ],
        "cascade": "calling_cards",
    },
    "calling_cards_zm.csv": {
        "label": "Zombies Calling Cards",
        "id_columns": ["mode", "category", "sub_category", "challenge", "requirement"],
        "filter_columns": ["category", "sub_category"],
        "status_columns": [
            "tier1_complete", "tier2_complete", "tier3_complete",
            "tier4_complete", "tier5_complete", "completed",
        ],
        "cascade": "calling_cards",
    },
    "calling_cards_wz.csv": {
        "label": "Warzone Calling Cards",
        "id_columns": ["mode", "category", "sub_category", "challenge", "requirement"],
        "filter_columns": ["category", "sub_category"],
        "status_columns": [
            "tier1_complete", "tier2_complete", "tier3_complete",
            "tier4_complete", "tier5_complete", "completed",
        ],
        "cascade": "calling_cards",
    },
    "rewards_zombies.csv": {
        "label": "Zombies Rewards",
        "id_columns": ["map", "category", "item"],
        "filter_columns": ["map", "category"],
        "status_columns": ["earned"],
        "cascade": "simple",
    },
    "rewards_endgame_operations.csv": {
        "label": "Endgame Operations",
        "id_columns": ["operation", "step"],
        "filter_columns": ["operation"],
        "status_columns": ["earned"],
        "cascade": "simple",
    },
    "rewards_endgame_unlocks.csv": {
        "label": "Endgame Unlocks",
        "id_columns": ["category", "operator", "item_type", "item", "unlock_criteria", "source"],
        "filter_columns": ["category", "operator", "item_type", "source"],
        "status_columns": ["earned"],
        "cascade": "simple",
    },
    "intel.csv": {
        "label": "Intel",
        "id_columns": ["mode", "map", "category", "item"],
        "filter_columns": ["mode", "map", "category"],
        "status_columns": ["found"],
        "cascade": "simple",
    },
    "titles.csv": {
        "label": "Titles",
        "id_columns": ["mode", "title", "criteria"],
        "filter_columns": ["mode"],
        "status_columns": ["earned"],
        "cascade": "simple",
    },
    "colours.csv": {
        "label": "Colours",
        "id_columns": ["level_required", "colour"],
        "filter_columns": [],
        "status_columns": ["unlocked"],
        "cascade": "simple",
    },
    "augments_zombies.csv": {
        "label": "Zombies Augments",
        "id_columns": ["mode", "category", "item"],
        "filter_columns": ["category"],
        "status_columns": [
            "minor1", "major1", "minor2", "major2", "minor3",
            "major3", "minor4", "major4", "extra_slot",
        ],
        "cascade": "row_order",
    },
    "overclocks_mp.csv": {
        "label": "Multiplayer Overclocks",
        "id_columns": ["mode", "category", "item"],
        "filter_columns": ["category"],
        "status_columns": ["oc1_complete", "oc2_complete"],
        "cascade": "row_order",
    },
}


def cockpit_status_columns(filename: str, dataframe: pd.DataFrame) -> list[str]:
    config = COCKPIT_CONFIGS.get(filename, {})
    configured = config.get("status_columns")

    if configured is not None:
        return [column for column in configured if column in dataframe.columns]

    id_columns = set(["mode", "chain", "weapon_class", "weapon"])
    ignored = id_columns | QUICK_UPDATE_METADATA_COLUMNS

    return [
        column for column in dataframe.columns
        if column not in ignored
        and not column.endswith("_required")
        and not column.endswith("_target")
    ]


def status_symbol(value) -> str:
    text = str(value).strip().upper()

    if text in {"N/A", "NA", "NONE", ""}:
        return "N/A"

    if is_true_cell(text):
        return "✅"

    return "❌"



def style_status_grid(dataframe: pd.DataFrame, status_columns: list[str], id_columns: list[str]):
    def cell_style(value):
        text = str(value).strip()

        if text == "✅":
            return (
                "background-color: rgba(48, 209, 88, 0.22); "
                "color: #d9ffe2; "
                "font-weight: 900; "
                "text-align: center;"
            )

        if text == "❌":
            return (
                "background-color: rgba(255, 69, 58, 0.18); "
                "color: #ffd8d6; "
                "font-weight: 900; "
                "text-align: center;"
            )

        if text.upper() in {"N/A", "NA", "NONE"}:
            return (
                "background-color: rgba(142, 142, 147, 0.16); "
                "color: #b8b8b8; "
                "font-weight: 700; "
                "text-align: center;"
            )

        return ""

    def header_style(column_name):
        if column_name in id_columns:
            return (
                "background-color: rgba(255,255,255,0.08); "
                "color: #ffffff; "
                "font-weight: 900;"
            )

        return (
            "background-color: rgba(255, 75, 75, 0.16); "
            "color: #ffffff; "
            "font-weight: 850; "
            "text-align: center;"
        )

    styled = dataframe.style.applymap(cell_style, subset=status_columns)

    for column in dataframe.columns:
        styled = styled.set_properties(
            subset=[column],
            **{
                "border": "1px solid rgba(255,255,255,0.08)",
                "font-size": "0.92rem",
            },
        )

    styled = styled.set_table_styles([
        {
            "selector": "th",
            "props": [
                ("background-color", "rgba(255,255,255,0.08)"),
                ("color", "#ffffff"),
                ("font-weight", "900"),
                ("border", "1px solid rgba(255,255,255,0.12)"),
                ("font-size", "0.86rem"),
            ],
        },
        {
            "selector": "td",
            "props": [
                ("border", "1px solid rgba(255,255,255,0.08)"),
            ],
        },
    ])

    for column in dataframe.columns:
        styled = styled.set_properties(
            subset=[column],
            **({"text-align": "left"} if column in id_columns else {"text-align": "center"}),
        )

    return styled


def cockpit_completion_caption(dataframe: pd.DataFrame, status_columns: list[str]) -> str:
    total = 0
    done = 0

    for _, row in dataframe.iterrows():
        for column in status_columns:
            value = str(row.get(column, "")).strip().upper()

            if value in {"", "N/A", "NA", "NONE"}:
                continue

            total += 1
            if is_true_cell(value):
                done += 1

    return f"{done}/{total} complete ({_pct(done, total):.1f}%)"


def fill_row_for_highest_true(dataframe: pd.DataFrame, status_columns: list[str]) -> pd.DataFrame:
    updated = dataframe.copy()

    for row_index, row in updated.iterrows():
        highest_true_index = None

        for index, column in enumerate(status_columns):
            value = str(row.get(column, "")).strip().upper()

            if value in {"", "N/A", "NA", "NONE"}:
                continue

            if is_true_cell(value):
                highest_true_index = index

        if highest_true_index is None:
            continue

        for column in status_columns[:highest_true_index + 1]:
            value = str(row.get(column, "")).strip().upper()
            if value not in {"", "N/A", "NA", "NONE"}:
                updated.loc[row_index, column] = "TRUE"

    return updated


def apply_weapon_badge_smart_rules(dataframe: pd.DataFrame) -> pd.DataFrame:
    updated = dataframe.copy()

    for prefix in ["mp", "zm"]:
        stage_columns = [
            f"{prefix}_bronze_complete",
            f"{prefix}_silver_complete",
            f"{prefix}_gold_complete",
            f"{prefix}_diamond_complete",
        ]

        existing_columns = [column for column in stage_columns if column in updated.columns]
        updated = fill_row_for_highest_true(updated, existing_columns)

        gold_column = f"{prefix}_gold_complete"
        diamond_column = f"{prefix}_diamond_complete"

        if gold_column not in updated.columns or diamond_column not in updated.columns:
            continue

        for weapon_class, requirement in WEAPON_BADGE_DIAMOND_REQUIREMENTS.items():
            class_mask = updated["weapon_class"].fillna("").str.strip().eq(weapon_class)

            if not class_mask.any():
                continue

            gold_count = int(updated.loc[class_mask, gold_column].apply(is_true_cell).sum())

            if gold_count >= requirement:
                updated.loc[class_mask, diamond_column] = "TRUE"

    return updated


def apply_equipment_badge_smart_rules(dataframe: pd.DataFrame) -> pd.DataFrame:
    updated = dataframe.copy()
    stage_columns = [
        "bronze_complete",
        "silver_complete",
        "gold_complete",
        "diamond_complete",
    ]

    updated = fill_row_for_highest_true(updated, [column for column in stage_columns if column in updated.columns])

    if "category" not in updated.columns or "gold_complete" not in updated.columns or "diamond_complete" not in updated.columns:
        return updated

    for category in sorted(updated["category"].fillna("").unique().tolist()):
        category_mask = updated["category"].fillna("").str.strip().eq(str(category).strip())

        if not category_mask.any():
            continue

        required_values = updated.loc[category_mask, "diamond_required"].dropna().astype(str).str.strip()
        required_values = [safe_int_like(value) for value in required_values if value and value.upper() not in {"N/A", "NA", "NONE"}]

        if not required_values:
            continue

        required = max(required_values)
        gold_count = int(updated.loc[category_mask, "gold_complete"].apply(is_true_cell).sum())

        if required > 0 and gold_count >= required:
            updated.loc[category_mask, "diamond_complete"] = "TRUE"

    return updated


def safe_int_like(value, fallback: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return fallback


def apply_calling_card_smart_rules(dataframe: pd.DataFrame, filename: str) -> pd.DataFrame:
    updated = fill_inactive_calling_card_tiers(dataframe)
    tier_columns = [
        "tier1_complete",
        "tier2_complete",
        "tier3_complete",
        "tier4_complete",
        "tier5_complete",
    ]

    updated = fill_row_for_highest_true(updated, [column for column in tier_columns if column in updated.columns])

    existing_tiers = [column for column in tier_columns if column in updated.columns]

    if "completed" in updated.columns:
        for row_index, row in updated.iterrows():
            if is_true_cell(row.get("completed", "")):
                for tier_number, column in enumerate(existing_tiers, start=1):
                    if calling_card_tier_is_applicable(row, tier_number):
                        updated.loc[row_index, column] = "TRUE"
                continue

            applicable_tiers = [
                column for tier_number, column in enumerate(existing_tiers, start=1)
                if calling_card_tier_is_applicable(row, tier_number)
            ]

            if applicable_tiers and all(is_true_cell(row.get(column, "")) for column in applicable_tiers):
                updated.loc[row_index, "completed"] = "TRUE"

    return normalise_calling_card_completion(updated, filename)


def apply_smart_completion_rules(dataframe: pd.DataFrame, filename: str) -> pd.DataFrame:
    config = COCKPIT_CONFIGS.get(filename, {})
    cascade = config.get("cascade", "simple")
    status_columns = cockpit_status_columns(filename, dataframe)

    if not status_columns:
        return dataframe

    if cascade == "row_order":
        return fill_row_for_highest_true(dataframe, status_columns)

    if cascade == "weapon_badges":
        return apply_weapon_badge_smart_rules(dataframe)

    if cascade == "equipment_badges":
        return apply_equipment_badge_smart_rules(dataframe)

    if cascade == "calling_cards":
        return apply_calling_card_smart_rules(dataframe, filename)

    return dataframe.copy()


def save_cockpit_dataframe(filename: str, updated_dataframe: pd.DataFrame, success_label: str):
    milestone_before = capture_milestone_snapshot()

    updated_dataframe = apply_smart_completion_rules(updated_dataframe, filename)
    if filename in CALLING_CARD_FILES_SET:
        updated_dataframe = normalise_calling_card_completion(updated_dataframe, filename)

    save_quick_update_csv(filename, updated_dataframe)

    milestone_after = capture_milestone_snapshot()
    queue_milestone_celebrations(milestone_before, milestone_after)

    st.session_state.bo7_completion_state = load_completion_state()
    st.session_state.bo7_tasks = apply_completion_state(
        load_tracker_tasks(),
        st.session_state.bo7_completion_state,
    )
    st.session_state.bo7_progress = load_hub_progress()
    st.session_state.bo7_latest_mission = None

    queue_celebration(
        "✅ TRACKER COCKPIT SAVED",
        f"{success_label} saved. Smart tick rules applied.",
        "minor",
    )


def render_cockpit_editor(
    filename: str,
    title: str | None = None,
    key_prefix: str = "cockpit",
):
    dataframe = load_quick_update_csv(filename)

    if dataframe.empty:
        st.warning(f"No data found for `{filename}`.")
        return

    config = COCKPIT_CONFIGS.get(filename, {})
    label = title or config.get("label", filename)

    status_columns = cockpit_status_columns(filename, dataframe)
    id_columns = [
        column for column in config.get("id_columns", QUICK_UPDATE_ID_COLUMNS.get(filename, []))
        if column in dataframe.columns
    ]

    if not status_columns:
        st.warning(f"No editable status columns found for `{filename}`.")
        st.dataframe(dataframe, use_container_width=True, hide_index=True)
        return

    st.markdown(f"#### {label}")
    st.caption(cockpit_completion_caption(dataframe, status_columns))

    filtered_dataframe = dataframe.copy()

    filter_columns = [
        column for column in config.get("filter_columns", [])
        if column in filtered_dataframe.columns
    ]

    if filter_columns:
        filter_cols = st.columns(min(len(filter_columns), 4))

        for index, column in enumerate(filter_columns):
            options = ["All"] + sorted(
                str(value) for value in filtered_dataframe[column].dropna().unique().tolist()
                if str(value).strip()
            )

            with filter_cols[index % len(filter_cols)]:
                selected = st.selectbox(
                    column.replace("_", " ").title(),
                    options,
                    key=f"{key_prefix}_filter_{filename}_{column}",
                )

            if selected != "All":
                filtered_dataframe = filtered_dataframe[
                    filtered_dataframe[column].fillna("").astype(str).str.strip().eq(selected)
                ]

    display_columns = [
        column for column in id_columns + status_columns
        if column in filtered_dataframe.columns
    ]

    if filtered_dataframe.empty:
        st.info("No rows match the current filters.")
        return

    cockpit_dataframe = (
        fill_inactive_calling_card_tiers(filtered_dataframe)
        if filename in CALLING_CARD_FILES_SET
        else filtered_dataframe
    )

    editor_dataframe = cockpit_dataframe[display_columns].copy()

    for column in status_columns:
        if column in editor_dataframe.columns:
            editor_dataframe[column] = editor_dataframe[column].apply(is_true_cell)

    disabled_columns = [
        column for column in display_columns
        if column not in status_columns
    ]

    column_config = {
        column: st.column_config.CheckboxColumn(column.replace("_", " ").title())
        for column in status_columns
        if column in display_columns
    }

    preview_dataframe = cockpit_dataframe[display_columns].copy()
    for column in status_columns:
        if column in preview_dataframe.columns:
            preview_dataframe[column] = preview_dataframe[column].apply(status_symbol)

    st.markdown("##### Sheet View")
    st.dataframe(
        style_status_grid(preview_dataframe, status_columns, id_columns),
        use_container_width=True,
        height=720,
        hide_index=True,
    )

    with st.expander("Edit tracker grid", expanded=False):
        edited_dataframe = st.data_editor(
            editor_dataframe,
            use_container_width=True,
            height=720,
            hide_index=False,
            disabled=disabled_columns,
            column_config=column_config,
            key=f"{key_prefix}_editor_{filename}",
        )

    if st.button(
        f"SAVE {label.upper()}",
        use_container_width=True,
        key=f"{key_prefix}_save_{filename}",
    ):
        updated_dataframe = dataframe.copy()

        for row_index, edited_row in edited_dataframe.iterrows():
            for column in status_columns:
                if column not in edited_dataframe.columns:
                    continue

                original_value = str(updated_dataframe.loc[row_index, column]).strip().upper()

                if original_value in {"N/A", "NA", "NONE", ""} and not bool(edited_row[column]):
                    continue

                updated_dataframe.loc[row_index, column] = bool_to_csv_value(edited_row[column])

        save_cockpit_dataframe(filename, updated_dataframe, label)
        st.success(f"{label} saved.")
        st.rerun()

SESSION_CATCHUP_TRACKERS = [
    ("MP Equipment Badges", "mastery_badges_equipment_mp.csv"),
    ("Weapon Mastery Badges", "mastery_badges_weapons.csv"),
    ("Weapon Prestige", "weapon_prestige.csv"),
    ("Multiplayer Camos", "singularity_status.csv"),
    ("Reticles", "reticles.csv"),
    ("MP Calling Cards", "calling_cards_mp.csv"),
    ("Overclocks", "overclocks_mp.csv"),
]


def render_session_catchup_panel():
    with st.expander("➕ Unexpected completion during session", expanded=False):
        st.markdown("### Session Catch-Up")
        st.caption(
            "Use this when you accidentally complete extra progress during a Commander session. "
            "Tick as many rows or milestones as needed, then save. Smart fill still applies."
        )

        tabs = st.tabs([label for label, _ in SESSION_CATCHUP_TRACKERS])

        for index, (label, filename) in enumerate(SESSION_CATCHUP_TRACKERS):
            with tabs[index]:
                render_cockpit_editor(
                    filename,
                    title=f"Unexpected Completion · {label}",
                    key_prefix=f"session_catchup_{filename.replace('.', '_')}",
                )

def render_tracker_cockpit(summary: dict):
    cockpit_tabs = st.tabs([
        "Overview",
        "Camos",
        "Weapon Prestige",
        "Weapon Badges",
        "Equipment Badges",
        "Reticles",
        "Calling Cards",
        "Rewards",
        "Intel",
        "Titles",
        "Colours",
        "Augments",
        "Overclocks",
    ])

    with cockpit_tabs[0]:
        st.markdown("### Tracker Cockpit")
        st.caption(
            "Sheet-style cockpit views live in the tabs above. Use the grids to tick progress directly. "
            "Smart tick rules fill earlier milestones when you tick a later one."
        )

        summary_cols = st.columns(4)

        with summary_cols[0]:
            total = summary.get("overall", {}) if isinstance(summary.get("overall", {}), dict) else {}
            st.metric("Open Steps", len(st.session_state.get("bo7_tasks", [])))

        with summary_cols[1]:
            st.metric("Camo Chains", "4")

        with summary_cols[2]:
            st.metric("Editable Trackers", str(len(COCKPIT_CONFIGS)))

        with summary_cols[3]:
            st.metric("Smart Fill", "ON")

        st.info(
            "Use Overview for the existing dashboard below, or jump into a cockpit tab for sheet-style editing."
        )

    with cockpit_tabs[1]:
        st.markdown("### Camos")
        camo_tabs = st.tabs(["Warzone", "Multiplayer", "Zombies", "Co-Op / Endgame"])
        with camo_tabs[0]:
            render_cockpit_editor("apocalypse_status.csv")
        with camo_tabs[1]:
            render_cockpit_editor("singularity_status.csv")
        with camo_tabs[2]:
            render_cockpit_editor("infestation_status.csv")
        with camo_tabs[3]:
            render_cockpit_editor("genesis_status.csv")

    with cockpit_tabs[2]:
        st.markdown("### Weapon Prestige")
        st.caption(
            "Ticking a later milestone fills the earlier prestige milestones. Current level is still edited from Quick Update → Weapon Levels."
        )
        render_cockpit_editor("weapon_prestige.csv")

    with cockpit_tabs[3]:
        st.markdown("### Weapon Mastery Badges")
        st.caption(
            "Ticking Silver fills Bronze. Ticking Gold fills Bronze/Silver. If the final Gold for a class is reached, Diamond auto-fills for that class."
        )
        render_cockpit_editor("mastery_badges_weapons.csv")

    with cockpit_tabs[4]:
        st.markdown("### Equipment Mastery Badges")
        equipment_tabs = st.tabs(["Multiplayer", "Zombies"])
        with equipment_tabs[0]:
            render_cockpit_editor("mastery_badges_equipment_mp.csv")
        with equipment_tabs[1]:
            render_cockpit_editor("mastery_badges_equipment_zombies.csv")

    with cockpit_tabs[5]:
        st.markdown("### Reticles")
        st.caption("Ticking Stage 100 fills Stage 20, 40, 60 and 80 for that mode and reticle only.")
        render_cockpit_editor("reticles.csv")

    with cockpit_tabs[6]:
        st.markdown("### Calling Cards")
        card_tabs = st.tabs(["Co-Op / Endgame", "Multiplayer", "Zombies", "Warzone"])
        with card_tabs[0]:
            render_cockpit_editor("calling_cards_sp.csv")
        with card_tabs[1]:
            render_cockpit_editor("calling_cards_mp.csv")
        with card_tabs[2]:
            render_cockpit_editor("calling_cards_zm.csv")
        with card_tabs[3]:
            render_cockpit_editor("calling_cards_wz.csv")

    with cockpit_tabs[7]:
        st.markdown("### Rewards / Operations")
        reward_tabs = st.tabs(["Zombies Rewards", "Endgame Operations", "Endgame Unlocks"])
        with reward_tabs[0]:
            render_cockpit_editor("rewards_zombies.csv")
        with reward_tabs[1]:
            render_cockpit_editor("rewards_endgame_operations.csv")
        with reward_tabs[2]:
            render_cockpit_editor("rewards_endgame_unlocks.csv")

    with cockpit_tabs[8]:
        st.markdown("### Intel")
        render_cockpit_editor("intel.csv")

    with cockpit_tabs[9]:
        st.markdown("### Titles")
        render_cockpit_editor("titles.csv")

    with cockpit_tabs[10]:
        st.markdown("### Colours")
        render_cockpit_editor("colours.csv")

    with cockpit_tabs[11]:
        st.markdown("### Augments")
        render_cockpit_editor("augments_zombies.csv")

    with cockpit_tabs[12]:
        st.markdown("### Overclocks")
        render_cockpit_editor("overclocks_mp.csv")


initialise_state()

# ─── STYLES ───────────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    .main {
        background: radial-gradient(circle at top, #141821 0%, #07080a 55%, #020303 100%);
    }
    .block-container {
        max-width: 98vw;
        padding-top: 1rem;
        padding-bottom: 2rem;
        padding-left: 1.25rem;
        padding-right: 1.25rem;
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
    .route-primary-label {
    font-size: 0.8rem;
    font-weight: 800;
    letter-spacing: 0.14em;
    color: #999999;
    text-transform: uppercase;
    margin-bottom: 0.25rem;
    }

    .route-primary-value {
        font-size: 1.45rem;
        font-weight: 850;
        color: #ffffff;
        line-height: 1.2;
        margin-bottom: 0.75rem;
    }

    .route-subtext {
        font-size: 1rem;
        color: #aaaaaa;
        font-family: monospace;
        margin-bottom: 0.75rem;
    }

    .completion-card {
        border: 1px solid rgba(255,255,255,0.12);
        border-left: 4px solid #666666;
        border-radius: 0.55rem;
        padding: 0.8rem 0.9rem;
        margin-bottom: 0.75rem;
        background: rgba(255,255,255,0.035);
    }

    .completion-card-done {
        border-left-color: #30d158;
        background: rgba(48,209,88,0.10);
        box-shadow: 0 0 18px rgba(48,209,88,0.08);
    }

    .completion-status {
        font-size: 0.72rem;
        font-weight: 850;
        letter-spacing: 0.14em;
        color: #999999;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }

    .completion-card-done .completion-status {
        color: #30d158;
    }

    .completion-label {
        font-size: 1rem;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 0.2rem;
    }

    .completion-pct {
        font-size: 1.55rem;
        font-weight: 900;
        color: #ffffff;
        line-height: 1.1;
    }

    .completion-count {
        font-size: 0.85rem;
        color: #aaaaaa;
        font-family: monospace;
        margin-top: 0.15rem;
    }

    .cockpit-note {
        border-left: 4px solid #30d158;
        background: rgba(48,209,88,0.08);
        padding: 0.75rem 1rem;
        margin: 0.75rem 0 1rem 0;
        color: #d6f7df;
        font-family: monospace;
    }

    .recording-card {
        border: 1px solid rgba(255,75,75,0.42);
        border-left: 6px solid #ff4b4b;
        background: linear-gradient(135deg, rgba(255,75,75,0.12), rgba(255,255,255,0.04));
        padding: 1rem 1.25rem;
        margin: 1rem 0;
        box-shadow: 0 0 26px rgba(0,0,0,0.28);
    }

    .decision-card {
        border-left-width: 10px;
        background:
            radial-gradient(circle at top right, rgba(255,75,75,0.24), rgba(255,75,75,0.02) 34%, transparent 58%),
            linear-gradient(135deg, rgba(255,75,75,0.16), rgba(255,255,255,0.045));
        padding: 1.15rem 1.35rem;
        position: relative;
        overflow: hidden;
    }

    .decision-strip {
        display: inline-block;
        color: #0b0b0b;
        background: #ff4b4b;
        padding: 0.28rem 0.55rem;
        font-family: monospace;
        font-size: 0.74rem;
        font-weight: 950;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        margin-bottom: 0.65rem;
    }

    .decision-command {
        margin: 0.85rem 0;
        padding: 0.85rem 0.95rem;
        background: rgba(0,0,0,0.30);
        border: 1px solid rgba(255,75,75,0.28);
    }

    .decision-command span {
        display: block;
        color: #ff9b9b;
        font-size: 0.72rem;
        font-family: monospace;
        font-weight: 900;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
    }

    .decision-command p {
        margin: 0;
        color: #ffffff;
        font-size: 1.08rem;
        font-weight: 850;
        line-height: 1.35;
    }

    .recording-lines {
        background: rgba(255,255,255,0.045);
        border: 1px solid rgba(255,255,255,0.09);
        padding: 0.75rem 0.85rem;
    }

    .recording-section strong {
        color: #ffffff;
        font-weight: 950;
    }

    .recording-eyebrow {
        color: #ff4b4b;
        font-size: 0.78rem;
        font-weight: 900;
        letter-spacing: 0.26em;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
        font-family: monospace;
    }

    .recording-title {
        color: #ffffff;
        font-size: 2.35rem;
        font-weight: 950;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        line-height: 1.05;
    }

    .recording-subtitle {
        color: #dddddd;
        font-size: 1.1rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin: 0.25rem 0 0.85rem 0;
    }

    .recording-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.75rem;
        margin: 0.75rem 0;
    }

    .recording-grid div {
        background: rgba(0,0,0,0.22);
        border: 1px solid rgba(255,255,255,0.08);
        padding: 0.65rem;
    }

    .recording-grid span,
    .recording-section span {
        display: block;
        color: #999999;
        font-size: 0.72rem;
        font-family: monospace;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }

    .recording-grid strong {
        color: #ffffff;
        font-size: 1rem;
        font-weight: 900;
    }

    .recording-section {
        margin-top: 0.75rem;
    }

    .recording-section p {
        margin: 0;
        color: #eeeeee;
        font-size: 0.96rem;
        line-height: 1.35;
    }

    .recording-rule {
        margin-top: 0.9rem;
        padding: 0.6rem 0.75rem;
        color: #ffffff;
        background: rgba(255,75,75,0.18);
        border: 1px solid rgba(255,75,75,0.32);
        font-family: monospace;
        font-weight: 900;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .progress-pop-card {
        border: 1px solid rgba(48,209,88,0.42);
        border-left: 8px solid #30d158;
        background:
            radial-gradient(circle at top right, rgba(48,209,88,0.22), rgba(48,209,88,0.04) 38%, transparent 62%),
            linear-gradient(135deg, rgba(48,209,88,0.13), rgba(255,255,255,0.04));
        padding: 1rem 1.2rem;
        margin: 0.9rem 0;
        box-shadow: 0 0 26px rgba(0,0,0,0.30);
    }

    .progress-pop-major {
        border-color: rgba(255,75,75,0.55);
        border-left-color: #ff4b4b;
        background:
            radial-gradient(circle at top right, rgba(255,75,75,0.28), rgba(255,75,75,0.05) 38%, transparent 62%),
            linear-gradient(135deg, rgba(255,75,75,0.16), rgba(255,255,255,0.045));
    }

    .progress-pop-eyebrow {
        color: #30d158;
        font-size: 0.76rem;
        font-family: monospace;
        font-weight: 950;
        letter-spacing: 0.22em;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
    }

    .progress-pop-major .progress-pop-eyebrow {
        color: #ff4b4b;
    }

    .progress-pop-title {
        color: #ffffff;
        font-size: 1.85rem;
        font-weight: 950;
        text-transform: uppercase;
        letter-spacing: 0.045em;
        line-height: 1.05;
        margin-bottom: 0.35rem;
    }

    .progress-pop-message {
        color: #eeeeee;
        font-size: 1rem;
        line-height: 1.35;
        margin-bottom: 0.7rem;
    }

    .progress-pop-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.65rem;
    }

    .progress-pop-grid div {
        background: rgba(0,0,0,0.25);
        border: 1px solid rgba(255,255,255,0.08);
        padding: 0.55rem 0.65rem;
    }

    .progress-pop-grid span {
        display: block;
        color: #999999;
        font-size: 0.68rem;
        font-family: monospace;
        font-weight: 850;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }

    .progress-pop-grid strong {
        color: #ffffff;
        font-size: 0.96rem;
        font-weight: 900;
    }

    .debrief-card {
        border-left-width: 10px;
        background:
            radial-gradient(circle at top right, rgba(90,200,250,0.20), rgba(90,200,250,0.04) 36%, transparent 62%),
            linear-gradient(135deg, rgba(90,200,250,0.12), rgba(255,255,255,0.04));
    }

    .debrief-verdict-box {
        padding: 0.95rem 1rem;
        background: rgba(0,0,0,0.30);
        border: 1px solid rgba(90,200,250,0.26);
        margin: 0.85rem 0;
    }

    .debrief-verdict-box span {
        display: block;
        color: #5ac8fa;
        font-size: 0.72rem;
        font-family: monospace;
        font-weight: 950;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
    }

    .debrief-verdict-box p {
        color: #ffffff;
        font-size: 1.12rem;
        font-weight: 850;
        line-height: 1.35;
        margin: 0;
    }

    .debrief-line-card {
        background: rgba(255,255,255,0.045);
        border: 1px solid rgba(255,255,255,0.09);
        padding: 0.75rem 0.85rem;
        margin-top: 0.75rem;
    }

    .debrief-line-card p {
        margin: 0;
    }

    .live-hud-card {
        border: 1px solid rgba(255,255,255,0.12);
        border-left: 10px solid #ff4b4b;
        background:
            radial-gradient(circle at top right, rgba(255,75,75,0.22), rgba(255,75,75,0.035) 36%, transparent 62%),
            linear-gradient(135deg, rgba(255,255,255,0.07), rgba(255,255,255,0.025));
        padding: 1rem 1.2rem;
        margin: 0.85rem 0 1rem 0;
        box-shadow: 0 0 26px rgba(0,0,0,0.28);
    }

    .live-hud-eyebrow {
        color: #ff4b4b;
        font-size: 0.74rem;
        font-family: monospace;
        font-weight: 950;
        letter-spacing: 0.20em;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
    }

    .live-hud-title {
        color: #ffffff;
        font-size: 2rem;
        font-weight: 950;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        line-height: 1.05;
        margin-bottom: 0.25rem;
    }

    .live-hud-subtitle {
        color: #cfcfcf;
        font-size: 1rem;
        font-weight: 750;
        margin-bottom: 0.8rem;
    }

    .live-hud-command {
        background: rgba(0,0,0,0.30);
        border: 1px solid rgba(255,75,75,0.24);
        padding: 0.75rem 0.85rem;
        margin: 0.75rem 0;
    }

    .live-hud-command span {
        display: block;
        color: #ff9b9b;
        font-size: 0.68rem;
        font-family: monospace;
        font-weight: 950;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }

    .live-hud-command p {
        margin: 0;
        color: #eeeeee;
        font-size: 0.98rem;
        line-height: 1.35;
    }

    .live-hud-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.65rem;
        margin-top: 0.75rem;
    }

    .live-hud-grid div {
        background: rgba(0,0,0,0.25);
        border: 1px solid rgba(255,255,255,0.08);
        padding: 0.55rem 0.65rem;
    }

    .live-hud-grid span {
        display: block;
        color: #999999;
        font-size: 0.66rem;
        font-family: monospace;
        font-weight: 850;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 0.2rem;
    }

    .live-hud-grid strong {
        color: #ffffff;
        font-size: 0.98rem;
        font-weight: 900;
    }

    .director-card {
        border-left-width: 10px;
        background:
            radial-gradient(circle at top right, rgba(255,204,0,0.20), rgba(255,204,0,0.035) 36%, transparent 62%),
            linear-gradient(135deg, rgba(255,204,0,0.10), rgba(255,255,255,0.04));
    }

    .director-card .recording-eyebrow {
        color: #ffcc00;
    }

    .shot-list {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.65rem;
        margin-top: 0.75rem;
    }

    .shot-item {
        background: rgba(0,0,0,0.28);
        border: 1px solid rgba(255,255,255,0.09);
        padding: 0.7rem 0.8rem;
    }

    .shot-item span {
        display: block;
        color: #ffcc00;
        font-size: 0.7rem;
        font-family: monospace;
        font-weight: 950;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }

    .shot-item p {
        margin: 0;
        color: #eeeeee;
        font-size: 0.92rem;
        line-height: 1.3;
    }

    .loadout-card {
        border-left-color: #00c2ff;
        border-color: rgba(0,194,255,0.42);
        background: linear-gradient(135deg, rgba(0,194,255,0.12), rgba(255,255,255,0.04));
    }

    .loadout-card .recording-eyebrow {
        color: #00c2ff;
    }

    .debrief-card {
        border-left-color: #30d158;
        border-color: rgba(48,209,88,0.42);
        background: linear-gradient(135deg, rgba(48,209,88,0.11), rgba(255,255,255,0.04));
    }

    .debrief-card .recording-eyebrow {
        color: #30d158;
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
    recording_mode = st.checkbox(
        "Recording Mode",
        value=bool(st.session_state.get("bo7_recording_mode", False)),
        help="OBS-friendly presentation cards. Does not change planner logic.",
        key="bo7_recording_mode",
    )

    # ── STATE 2: ACTIVE PLAN ──
    st.caption(
        f"Current account level: "
        f"{float(st.session_state.bo7_account_params.get('account_level', 1.0)):g}"
    )

    render_queued_celebrations()

    if plan and plan.get("stops"):
        plan = attach_loadouts_to_plan(plan, st.session_state.bo7_tasks)
        plan = attach_series_context_to_plan(
            plan,
            summarise_tasks(st.session_state.bo7_tasks),
            st.session_state.bo7_completion_state,
        )
        st.session_state.bo7_session_plan = plan

        st.markdown(f"<div class='order-mode'>☣ {plan['mode']} — SESSION PLAN ACTIVE</div>", unsafe_allow_html=True)

        render_series_context_panel(plan)

        obs_cols = st.columns([1, 1, 3])
        with obs_cols[0]:
            if st.button("OPEN OBS RECORD VIEW", use_container_width=True, key="bo7_open_obs_record_view"):
                try:
                    st.switch_page("pages/06_Commander_Record.py")
                except Exception:
                    st.info("Open BO7: OBS Record View from the sidebar.")
        with obs_cols[1]:
            if st.button("BACK TO LAUNCH", use_container_width=True, key="bo7_back_to_launch"):
                try:
                    st.switch_page("pages/05_Commander_Launch.py")
                except Exception:
                    st.info("Open BO7: Commander Launch from the sidebar.")

        guide_bits = []
        if st.session_state.get("bo7_recovery_suggestions"):
            with st.expander("Recovery options", expanded=True):
                st.caption("The last objective was blocked or skipped. Here are the best nearby alternatives to keep momentum.")
                for suggestion in st.session_state.bo7_recovery_suggestions:
                    weapon = suggestion.get("weapon", suggestion.get("category", "Task"))
                    camo = suggestion.get("camo", suggestion.get("challenge_text", ""))
                    st.write(f"• {weapon} — {camo}")
        if plan.get("commander_mode"):
            guide_bits.append(f"Mode: {plan.get('commander_mode')}")
        if plan.get("focus_targets"):
            guide_bits.append("Focus: " + " + ".join(plan.get("focus_targets", [])))
        if plan.get("anchor_weapon"):
            guide_bits.append(f"Start weapon/item: {plan.get('anchor_weapon')}")
        if plan.get("anchor_class"):
            guide_bits.append(f"Start class/category: {plan.get('anchor_class')}")
        if plan.get("anchor_collection") and plan.get("anchor_collection") != "Any stackable progress":
            guide_bits.append(f"Collection: {plan.get('anchor_collection')}")
        if plan.get("commander_mode") == "Closest finishes":
            guide_bits.append(f"Threshold: {plan.get('minimum_closeness', 80)}%+")

        if guide_bits:
            st.caption("Commander guidance · " + " · ".join(guide_bits))

        if recording_mode:
            render_recording_order_card(plan)
            render_recording_loadout_card(plan)
            render_recording_director_card(plan)
            render_recording_debrief_card(plan)
            st.divider()

        plan_brief = generate_plan_brief(
            plan,
            st.session_state.bo7_tasks,
            st.session_state.bo7_session_log,
        )
        if plan_brief:
            st.info(plan_brief)

        diagnostics = plan.get("diagnostics", {})
        confidence = diagnostics.get("confidence", "Unknown")
        confidence_score = diagnostics.get("confidence_score", 0)

        st.metric(
            "Plan Confidence",
            confidence,
            f"{confidence_score}/100",
        )

        rationale = diagnostics.get("rationale", [])
        if rationale:
            with st.expander("Why this plan?"):
                for reason in rationale:
                    st.write(f"- {reason}")

        estimated_total_minutes = int(
            plan.get("estimated_minutes", 0)
            or sum(
                int(stop.get("estimated_minutes", 0) or 0)
                for stop in plan.get("stops", [])
            )
        )

        if estimated_total_minutes:
            st.caption(
                f"Estimated plan time: {estimated_total_minutes} minutes "
                f"for {plan.get('available_minutes', '?')} available."
            )

        route_summary = plan.get("route_summary", {})

        if route_summary:
            st.markdown("### Route Summary")

            primary_route = route_summary.get("primary_route", "Unknown")
            estimated_minutes = route_summary.get("estimated_minutes", 0)
            available_minutes = route_summary.get("available_minutes", "?")
            unlock_value = route_summary.get("main_unlock_value", "Unknown")
            stacking = route_summary.get("stacked_cleanup", "None")

            summary_cols = st.columns([2, 1, 1])

            with summary_cols[0]:
                st.markdown(
                    f"""
                    <div class="route-primary-label">PRIMARY ROUTE</div>
                    <div class="route-primary-value">{primary_route}</div>
                    """,
                    unsafe_allow_html=True,
                )

                task_mix = route_summary.get("task_mix", {})
                if task_mix:
                    task_mix_text = " · ".join(
                        f"{task_type}: {count}"
                        for task_type, count in task_mix.items()
                    )
                    st.markdown(
                        f"<div class='route-subtext'>Task mix: {task_mix_text}</div>",
                        unsafe_allow_html=True,
                    )

            with summary_cols[1]:
                st.metric(
                    "Estimated Time",
                    f"{estimated_minutes} min",
                    f"{available_minutes} min available",
                )

            with summary_cols[2]:
                high_value_count = str(unlock_value).split(" ")[0] if str(unlock_value) else "0"
                st.metric("High-Value Objectives", high_value_count)
                st.caption(unlock_value)

            st.caption(f"Stacking: {stacking}")

            actual_cluster_counts = {}

            for stop in plan.get("stops", []):
                cluster_label = stop.get("cluster_label", "Unclassified")
                actual_cluster_counts[cluster_label] = actual_cluster_counts.get(cluster_label, 0) + 1

            if actual_cluster_counts:
                cluster_text = " · ".join(
                    f"{label} ({count} objective{'s' if count != 1 else ''})"
                    for label, count in actual_cluster_counts.items()
                )
                st.markdown(
                    f"<div class='order-strategy'>Focus route: {cluster_text}</div>",
                    unsafe_allow_html=True,
                )

            st.divider()

        remaining_minutes = int(
            st.session_state.get(
                "plan_remaining_minutes",
                st.session_state.get("bo7_form_minutes", plan.get("available_minutes", 60)),
            )
        )

        ensure_active_stop_timer(plan)

        render_live_objective_hud(plan)

        time_cols = st.columns(4)
        with time_cols[0]:
            st.metric("Session Timebox", f"{plan_available_minutes(plan)} min")
        with time_cols[1]:
            st.metric("Logged Time", f"{logged_stop_minutes()} min")
        with time_cols[2]:
            st.metric("Current Objective", f"{current_stop_elapsed_minutes()} min")
        with time_cols[3]:
            st.metric("Time Left", f"{current_time_remaining(plan)} min")
        
        render_session_catchup_panel()
        st.divider()

        for stop in plan["stops"]:
            stop_number = stop["stop_number"]
            weapon = stop["weapon"]
            camo = stop["camo"]
            progress = stop["weapon_progress"]
            challenge = stop["challenge_text"]
            estimated_minutes = int(stop.get("estimated_minutes", 0) or 0)
            cluster_label = stop["cluster_label"]
            task_id = stop["task_id"]

            current_status = stop_status(task_id)
            resolved = stop_is_resolved(task_id)

            with st.container():
                status_label = {
                    "pending": "PENDING",
                    "done": "DONE",
                    "partial": "PARTIAL",
                    "skipped": "SKIPPED",
                }.get(current_status, current_status.upper())

                st.markdown(
                    f"<div class='order-weapon' style='font-size:1.6rem;'>"
                    f"{stop_number}. {weapon} · {status_label}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div class='order-camo' style='font-size:1.1rem;'>{camo} · {cluster_label}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"<div class='order-challenge'>{challenge}</div>", unsafe_allow_html=True)
                if estimated_minutes:
                    st.caption(f"Estimated objective time: {estimated_minutes} minutes")

                stop_explanation = build_stop_explanation(stop)
                if stop_explanation:
                    with st.expander("Why this objective?", expanded=False):
                        for line in stop_explanation:
                            st.write(f"• {line}")

                stacking_hint = stop.get("stacking_hint", "")
                if stacking_hint:
                    st.info(stacking_hint)
                companion_objectives = stop.get("companion_objectives", [])
                if companion_objectives:
                    with st.expander("Bonus progress to stack", expanded=True):
                        for companion in companion_objectives:
                            st.write(f"✅ {companion}")

                if resolved:
                    result = st.session_state.bo7_stop_results.get(task_id, {})
                    elapsed_text = ""
                    if result.get("elapsed_minutes") is not None:
                        elapsed_text = (
                            f" · Took {result.get('elapsed_minutes', 0)} min"
                            f" · {result.get('remaining_minutes_after', 0)} min left"
                        )

                    st.caption(
                        f"Objective logged as {status_label}. "
                        f"{result.get('result', '')} {result.get('blame', '')}"
                        f"{elapsed_text}".strip()
                    )

                    if st.button("↩️ Undo objective result", key=f"undo_{task_id}", use_container_width=True):
                        st.session_state.bo7_stop_results.pop(task_id, None)
                        st.session_state.bo7_completed_stop_ids = [
                            existing_id
                            for existing_id in st.session_state.bo7_completed_stop_ids
                            if existing_id != task_id
                        ]
                        st.rerun()

                    st.divider()
                    continue

                weapon_level_key = f"weapon_levels_gained_{task_id}"
                weapon_reset_key = f"weapon_prestige_reset_{task_id}"
                account_level_key = f"account_levels_gained_{task_id}"
                camo_reached_key = f"camo_reached_{task_id}"
                reticle_reached_key = f"reticle_reached_{task_id}"

                render_objective_progress_pulse(
                    stop=stop,
                    task_id=task_id,
                    weapon_level_key=weapon_level_key,
                    weapon_reset_key=weapon_reset_key,
                    account_level_key=account_level_key,
                    camo_reached_key=camo_reached_key,
                    reticle_reached_key=reticle_reached_key,
                )

                col1, col2, col3 = st.columns(3)

                with col1:
                    if st.button("✅ Objective Done", key=f"done_{task_id}", use_container_width=True):
                        milestone_before = capture_milestone_snapshot()

                        csv_updated = (
                            write_camo_completion_from_stop(stop)
                            or write_reticle_completion_from_stop(stop)
                        )

                        camo_reached_updated = write_camo_reached_from_stop(
                            stop,
                            st.session_state.get(camo_reached_key, "No extra update"),
                        )

                        if camo_reached_updated:
                            csv_updated = True
                            queue_celebration(
                                "🎨 CAMO PROGRESS SYNCED",
                                f"{stop.get('weapon', 'Weapon')} updated through {st.session_state.get(camo_reached_key)}.",
                                "minor",
                            )

                        reticle_reached_updated = write_reticle_reached_from_stop(
                            stop,
                            st.session_state.get(reticle_reached_key, "No extra update"),
                        )

                        if reticle_reached_updated:
                            csv_updated = True
                            queue_celebration(
                                "🎯 RETICLE PROGRESS SYNCED",
                                f"{stop.get('weapon', 'Reticle')} updated to stage {st.session_state.get(reticle_reached_key)} in {stop.get('mode', '')}.",
                                "minor",
                            )

                        level_result = write_weapon_level_progress_from_stop(
                            stop=stop,
                            levels_gained=st.session_state.get(weapon_level_key, 0.0),
                            prestiged_reset=st.session_state.get(weapon_reset_key, False),
                        )

                        if level_result.get("updated"):
                            csv_updated = True
                            queue_weapon_level_celebration(stop, level_result)

                        account_level_result = log_objective_account_level_gain(
                            stop=stop,
                            plan=plan,
                            levels_gained=st.session_state.get(account_level_key, 0.0),
                        )

                        if account_level_result.get("updated"):
                            st.session_state.bo7_session_log = load_persisted_session_log()

                        if csv_updated:
                            milestone_after = capture_milestone_snapshot()
                            queue_milestone_celebrations(milestone_before, milestone_after)

                        timing = close_active_stop_timer(stop, plan)
                        log_plan_stop(stop, "Camo completed", "Successful operation")
                        st.session_state.bo7_recovery_suggestions = []

                        record_stop_result(
                            stop=stop,
                            status="done",
                            result="Camo completed",
                            blame="Successful operation",
                            notes="CSV updated" if csv_updated else "Logged only",
                            timing=timing
                        )

                        queue_stop_celebration(stop, csv_updated)

                        if csv_updated:
                            reload_commander_from_csv()

                        st.rerun()

                with col2:
                    if st.button("⚠️ Partial Progress", key=f"partial_{task_id}", use_container_width=True):
                        milestone_before = capture_milestone_snapshot()
                        timing = close_active_stop_timer(stop, plan)
                        log_plan_stop(stop, "Partial progress", "Human avoidance")

                        csv_updated = False

                        camo_reached_updated = write_camo_reached_from_stop(
                            stop,
                            st.session_state.get(camo_reached_key, "No extra update"),
                        )

                        if camo_reached_updated:
                            csv_updated = True
                            queue_celebration(
                                "🎨 CAMO PROGRESS SYNCED",
                                f"{stop.get('weapon', 'Weapon')} updated through {st.session_state.get(camo_reached_key)}.",
                                "minor",
                            )

                        reticle_reached_updated = write_reticle_reached_from_stop(
                            stop,
                            st.session_state.get(reticle_reached_key, "No extra update"),
                        )

                        if reticle_reached_updated:
                            csv_updated = True
                            queue_celebration(
                                "🎯 RETICLE PROGRESS SYNCED",
                                f"{stop.get('weapon', 'Reticle')} updated to stage {st.session_state.get(reticle_reached_key)} in {stop.get('mode', '')}.",
                                "minor",
                            )

                        level_result = write_weapon_level_progress_from_stop(
                            stop=stop,
                            levels_gained=st.session_state.get(weapon_level_key, 0.0),
                            prestiged_reset=st.session_state.get(weapon_reset_key, False),
                        )

                        if level_result.get("updated"):
                            csv_updated = True
                            queue_weapon_level_celebration(stop, level_result)

                        account_level_result = log_objective_account_level_gain(
                            stop=stop,
                            plan=plan,
                            levels_gained=st.session_state.get(account_level_key, 0.0),
                        )

                        if account_level_result.get("updated"):
                            st.session_state.bo7_session_log = load_persisted_session_log()

                        if csv_updated:
                            milestone_after = capture_milestone_snapshot()
                            queue_milestone_celebrations(milestone_before, milestone_after)
                            reload_commander_from_csv()

                        st.session_state.bo7_recovery_suggestions = build_recovery_suggestions(
                            tasks=st.session_state.bo7_tasks,
                            current_stop=stop,
                            preferred_mode=plan.get("preferred_mode", plan.get("mode", st.session_state.bo7_form_preferred_mode)),
                            avoided_mode=plan.get("avoided_mode", st.session_state.bo7_form_avoided_mode),
                            session_goal=st.session_state.bo7_form_session_goal,
                            motivation=st.session_state.bo7_form_motivation,
                            commander_mode=plan.get("commander_mode", st.session_state.bo7_form_commander_mode),
                            focus_targets=plan.get("focus_targets", st.session_state.bo7_form_focus_targets),
                            anchor_weapon=plan.get("anchor_weapon", st.session_state.bo7_form_anchor_weapon),
                            anchor_class=plan.get("anchor_class", st.session_state.bo7_form_anchor_class),
                            anchor_collection=plan.get("anchor_collection", st.session_state.bo7_form_anchor_collection),
                            minimum_closeness=plan.get("minimum_closeness", st.session_state.bo7_form_minimum_closeness),
                        )

                        st.session_state.bo7_session_plan = build_recovery_plan(
                            tasks=st.session_state.bo7_tasks,
                            current_stop=stop,
                            preferred_mode=plan.get("preferred_mode", plan.get("mode", st.session_state.bo7_form_preferred_mode)),
                            avoided_mode=plan.get("avoided_mode", st.session_state.bo7_form_avoided_mode),
                            session_goal=st.session_state.bo7_form_session_goal,
                            motivation=st.session_state.bo7_form_motivation,
                            remaining_minutes=remaining_minutes,
                            commander_mode=plan.get("commander_mode", st.session_state.bo7_form_commander_mode),
                            focus_targets=plan.get("focus_targets", st.session_state.bo7_form_focus_targets),
                            anchor_weapon=plan.get("anchor_weapon", st.session_state.bo7_form_anchor_weapon),
                            anchor_class=plan.get("anchor_class", st.session_state.bo7_form_anchor_class),
                            anchor_collection=plan.get("anchor_collection", st.session_state.bo7_form_anchor_collection),
                            minimum_closeness=plan.get("minimum_closeness", st.session_state.bo7_form_minimum_closeness),
                            completed_task_ids=resolved_stop_ids(),
                        )

                        record_stop_result(
                            stop=stop,
                            status="partial",
                            result="Partial progress",
                            blame="Human avoidance",
                            timing=timing
                        )
                        st.rerun()

                with col3:
                    if st.button("⏭️ Skip Objective", key=f"skip_{task_id}", use_container_width=True):
                        timing = close_active_stop_timer(stop, plan)
                        log_plan_stop(stop, "Skipped", "Human choice")
                        st.session_state.bo7_recovery_suggestions = build_recovery_suggestions(
                            tasks=st.session_state.bo7_tasks,
                            current_stop=stop,
                            preferred_mode=plan.get("preferred_mode", plan.get("mode", st.session_state.bo7_form_preferred_mode)),
                            avoided_mode=plan.get("avoided_mode", st.session_state.bo7_form_avoided_mode),
                            session_goal=st.session_state.bo7_form_session_goal,
                            motivation=st.session_state.bo7_form_motivation,
                            commander_mode=plan.get("commander_mode", st.session_state.bo7_form_commander_mode),
                            focus_targets=plan.get("focus_targets", st.session_state.bo7_form_focus_targets),
                            anchor_weapon=plan.get("anchor_weapon", st.session_state.bo7_form_anchor_weapon),
                            anchor_class=plan.get("anchor_class", st.session_state.bo7_form_anchor_class),
                            anchor_collection=plan.get("anchor_collection", st.session_state.bo7_form_anchor_collection),
                            minimum_closeness=plan.get("minimum_closeness", st.session_state.bo7_form_minimum_closeness),
                        )
                        st.session_state.bo7_session_plan = build_recovery_plan(
                            tasks=st.session_state.bo7_tasks,
                            current_stop=stop,
                            preferred_mode=plan.get("preferred_mode", plan.get("mode", st.session_state.bo7_form_preferred_mode)),
                            avoided_mode=plan.get("avoided_mode", st.session_state.bo7_form_avoided_mode),
                            session_goal=st.session_state.bo7_form_session_goal,
                            motivation=st.session_state.bo7_form_motivation,
                            remaining_minutes=remaining_minutes,
                            commander_mode=plan.get("commander_mode", st.session_state.bo7_form_commander_mode),
                            focus_targets=plan.get("focus_targets", st.session_state.bo7_form_focus_targets),
                            anchor_weapon=plan.get("anchor_weapon", st.session_state.bo7_form_anchor_weapon),
                            anchor_class=plan.get("anchor_class", st.session_state.bo7_form_anchor_class),
                            anchor_collection=plan.get("anchor_collection", st.session_state.bo7_form_anchor_collection),
                            minimum_closeness=plan.get("minimum_closeness", st.session_state.bo7_form_minimum_closeness),
                            completed_task_ids=resolved_stop_ids(),
                        )
                        record_stop_result(
                            stop=stop,
                            status="skipped",
                            result="Skipped",
                            blame="Human choice",
                            timing=timing
                        )
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
                    preferred_mode=plan.get("preferred_mode", plan.get("mode", st.session_state.bo7_form_preferred_mode)),
                    session_goal=st.session_state.bo7_form_session_goal,
                    motivation=st.session_state.bo7_form_motivation,
                    completed_task_ids=resolved_stop_ids(),
                    remaining_minutes=remaining_minutes,
                    commander_mode=plan.get("commander_mode", st.session_state.bo7_form_commander_mode),
                    focus_targets=plan.get("focus_targets", st.session_state.bo7_form_focus_targets),
                    anchor_weapon=plan.get("anchor_weapon", st.session_state.bo7_form_anchor_weapon),
                    anchor_class=plan.get("anchor_class", st.session_state.bo7_form_anchor_class),
                    anchor_collection=plan.get("anchor_collection", st.session_state.bo7_form_anchor_collection),
                    minimum_closeness=plan.get("minimum_closeness", st.session_state.bo7_form_minimum_closeness),
                    avoided_mode=plan.get("avoided_mode", st.session_state.bo7_form_avoided_mode),
                )
 
                st.session_state.bo7_session_plan = attach_loadouts_to_plan(new_plan, st.session_state.bo7_tasks)
                st.rerun()
 
        with col_b:
            st.markdown("### Session Debrief")
            st.caption(
                "Progress Pulse already banked account levels during objectives. "
                "Only add extra levels here if you forgot to log them."
            )

            st.metric(
                "Account levels banked",
                f"+{float(st.session_state.get('bo7_account_levels_gained', 0.0) or 0.0):g}",
            )

            st.session_state.bo7_account_levels_debrief_adjustment = st.number_input(
                "Extra account levels missed",
                min_value=0.0,
                max_value=100.0,
                value=float(st.session_state.bo7_account_levels_debrief_adjustment),
                step=0.5,
                key="account_levels_debrief_adjustment_input",
            )
            auto_actual_minutes = logged_stop_minutes()

            st.session_state.bo7_actual_minutes_played = st.number_input(
                "Actual minutes played",
                min_value=0,
                max_value=480,
                value=int(
                    auto_actual_minutes
                    or st.session_state.bo7_actual_minutes_played
                    or plan.get("estimated_minutes", 0)
                    or plan.get("available_minutes", 0)
                ),
                step=5,
                key="actual_minutes_played_input",
                help="Auto-filled from objective timers. Edit only if the timer is wrong.",
            )

            if st.button("FINISH DEBRIEF", use_container_width=True):
                already_banked_levels = float(st.session_state.bo7_account_levels_gained or 0.0)
                extra_levels = float(st.session_state.bo7_account_levels_debrief_adjustment or 0.0)
                total_levels = already_banked_levels + extra_levels
                actual_minutes_played = int(st.session_state.bo7_actual_minutes_played or 0)

                if extra_levels > 0:
                    log_account_level_gain(
                        levels_gained=extra_levels,
                        plan=st.session_state.bo7_session_plan,
                        actual_minutes_played=actual_minutes_played,
                    )

                st.session_state.bo7_last_debrief = build_session_debrief(
                    plan=st.session_state.bo7_session_plan,
                    stop_results=st.session_state.bo7_stop_results,
                    account_levels_gained=total_levels,
                    actual_minutes_played=actual_minutes_played,
                )

                st.session_state.bo7_session_log = load_persisted_session_log()
                st.session_state.bo7_session_plan = None
                st.session_state.bo7_completed_stop_ids = []
                st.session_state.bo7_stop_results = {}
                st.session_state.bo7_account_levels_gained = 0.0
                st.session_state.bo7_account_levels_debrief_adjustment = 0.0
                st.rerun()
 
    # ── STATE 1: NO ACTIVE PLAN ──
    else:
        task_summary = summarise_tasks(st.session_state.bo7_tasks)
        render_session_debrief()
 
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
                index=safe_select_index(MODES, st.session_state.bo7_form_preferred_mode),
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
                index=safe_select_index(MODES, st.session_state.bo7_form_avoided_mode),
                key="select_avoided",
            )

        st.markdown("### Guide the Commander")

        commander_mode = st.selectbox(
            "Commander mode",
            COMMANDER_MODES,
            index=safe_select_index(COMMANDER_MODES, st.session_state.bo7_form_commander_mode),
            help=(
                "Optimise my grind keeps normal Commander behaviour. "
                "Start from my itch anchors the plan around a weapon or class. "
                "Closest finishes hunts nearly-done items. "
                "Completion stack prioritises non-camo completion and adds camo progress as a side objective."
            ),
            key="select_commander_mode",
        )

        focus_targets = st.multiselect(
            "Priority focus",
            FOCUS_TARGETS,
            default=[
                item for item in st.session_state.bo7_form_focus_targets
                if item in FOCUS_TARGETS
            ],
            help="Strong bias. Collection focus can lock the route when a specific collection is selected.",
            key="multiselect_focus_targets",
        )

        available_for_guidance = get_available_tasks(st.session_state.bo7_tasks)
        guidance_mode_filter = "" if commander_mode == "Closest finishes" or preferred_mode == "Commander chooses" else preferred_mode

        weapon_options = [""] + sorted_task_values(
            available_for_guidance,
            "weapon",
            guidance_mode_filter,
        )
        class_options = [""] + sorted_task_values(
            available_for_guidance,
            "weapon_class",
            guidance_mode_filter,
        )

        guide_cols = st.columns(3)

        with guide_cols[0]:
            anchor_weapon = st.selectbox(
                "Start weapon / item",
                weapon_options,
                index=safe_select_index(weapon_options, st.session_state.bo7_form_anchor_weapon),
                format_func=lambda value: "Any weapon/item" if not value else value,
                key="select_anchor_weapon",
            )

        with guide_cols[1]:
            anchor_class = st.selectbox(
                "Start class / category",
                class_options,
                index=safe_select_index(class_options, st.session_state.bo7_form_anchor_class),
                format_func=lambda value: "Any class/category" if not value else value,
                key="select_anchor_class",
            )

        with guide_cols[2]:
            anchor_collection = st.selectbox(
                "Collection focus",
                ANCHOR_COLLECTIONS,
                index=safe_select_index(ANCHOR_COLLECTIONS, st.session_state.bo7_form_anchor_collection),
                key="select_anchor_collection",
            )

        minimum_closeness = st.slider(
            "Closest-finish threshold",
            min_value=50,
            max_value=95,
            value=int(st.session_state.bo7_form_minimum_closeness),
            step=5,
            help="Used by Closest finishes. Final-step style tasks can still appear even under this percentage.",
            key="slider_minimum_closeness",
        )

        if commander_mode == "Start from my itch":
            st.info("Start from my itch will build the route around your selected weapon, class, or collection first.")
        elif commander_mode == "Closest finishes":
            st.info("Closest finishes prioritises near-complete items. Use Global Cleanup as the mode to let it search across all modes.")
        elif commander_mode == "Completion stack":
            st.info(
                "Completion stack avoids pure camo tunnel vision. It prefers operations, rewards, calling cards, intel, map challenges, badges, reticles, and then adds camos as stackable side progress."
            )

        st.divider()
 
        if st.button("GENERATE SESSION PLAN", type="primary", use_container_width=True):
            st.session_state.bo7_form_minutes = available_minutes
            st.session_state.bo7_form_energy = energy
            st.session_state.bo7_form_motivation = motivation
            st.session_state.bo7_form_preferred_mode = preferred_mode
            st.session_state.bo7_form_avoided_mode = avoided_mode
            st.session_state.bo7_form_session_goal = session_goal
            st.session_state.bo7_form_commander_mode = commander_mode
            st.session_state.bo7_form_focus_targets = focus_targets
            st.session_state.bo7_form_anchor_weapon = anchor_weapon
            st.session_state.bo7_form_anchor_class = anchor_class
            st.session_state.bo7_form_anchor_collection = anchor_collection
            st.session_state.bo7_form_minimum_closeness = minimum_closeness
            st.session_state.bo7_completed_stop_ids = []
            st.session_state.bo7_stop_results = {}

            new_plan = build_session_plan(
                tasks=st.session_state.bo7_tasks,
                preferred_mode=preferred_mode,
                session_goal=session_goal,
                motivation=motivation,
                available_minutes=available_minutes,
                commander_mode=commander_mode,
                focus_targets=focus_targets,
                anchor_weapon=anchor_weapon,
                anchor_class=anchor_class,
                anchor_collection=anchor_collection,
                minimum_closeness=minimum_closeness,
                avoided_mode=avoided_mode,
            )

            st.session_state.bo7_session_plan = attach_loadouts_to_plan(new_plan, st.session_state.bo7_tasks)
            st.rerun()

        if st.button("GENERATE NO-THINKING PLAN", use_container_width=True):
            st.session_state.bo7_form_minutes = available_minutes
            st.session_state.bo7_form_energy = energy
            st.session_state.bo7_form_motivation = motivation
            st.session_state.bo7_form_preferred_mode = "Commander chooses"
            st.session_state.bo7_form_avoided_mode = "Global Cleanup"
            st.session_state.bo7_form_session_goal = "Balanced progress"
            st.session_state.bo7_form_commander_mode = "Optimise my grind"
            st.session_state.bo7_form_focus_targets = []
            st.session_state.bo7_form_anchor_weapon = ""
            st.session_state.bo7_form_anchor_class = ""
            st.session_state.bo7_form_anchor_collection = "Any stackable progress"
            st.session_state.bo7_form_minimum_closeness = minimum_closeness
            st.session_state.bo7_completed_stop_ids = []
            st.session_state.bo7_stop_results = {}

            new_plan = build_session_plan(
                tasks=st.session_state.bo7_tasks,
                preferred_mode="Commander chooses",
                session_goal="Balanced progress",
                motivation=motivation,
                available_minutes=available_minutes,
                commander_mode="Optimise my grind",
                focus_targets=[],
                anchor_weapon="",
                anchor_class="",
                anchor_collection="Any stackable progress",
                minimum_closeness=minimum_closeness,
                avoided_mode="Global Cleanup",
            )

            st.session_state.bo7_session_plan = attach_loadouts_to_plan(new_plan, st.session_state.bo7_tasks)
            st.rerun()

# -- Account -- 

with tab_account:
    st.subheader("Account Parameters")
    st.caption("Settings that persist across sessions. Update when something changes — not every time you play.")
    
    st.markdown("## Account Level")

    current_account_level = float(
        st.session_state.bo7_account_params.get("account_level", 1.0)
    )

    new_account_level = st.number_input(
        "Current account level",
        min_value=1.0,
        max_value=1000.0,
        value=current_account_level,
        step=0.5,
        key="manual_account_level_input",
    )

    if st.button("SAVE ACCOUNT LEVEL", use_container_width=True):
        set_account_level(new_account_level)
        st.success(f"Account level saved: {new_account_level:g}")
        st.rerun()

    st.divider()

    st.info(
        "XP token bank tracking has been retired. Weapon level progress now lives in Quick Update → Weapon Levels and on each Commander objective."
    )

# ─── QUICK UPDATE ─────────────────────────────────────────────────────────────

# ─── QUICK UPDATE ─────────────────────────────────────────────────────────────

with tab_quick_update:
    st.markdown("### Quick Update")

    quick_update_mode = st.radio(
        "Update type",
        ["Completion Grid", "Weapon Levels"],
        horizontal=True,
        key="quick_update_mode",
    )

    if quick_update_mode == "Completion Grid":
        render_quick_completion_grid()
    else:
        render_weapon_level_quick_update()
    

# ─── TRACKER ──────────────────────────────────────────────────────────────────


with tab_tracker:
    st.subheader("100% Tracker")
 
    summary = compute_full_tracker_summary(CLEAN_DATA_DIR)

    render_tracker_cockpit(summary)
    st.divider()
    st.markdown("### Legacy Overview")

    def add_completion_bucket(buckets, mode, section, done, total):
        done = int(done or 0)
        total = int(total or 0)

        if total <= 0:
            return

        buckets["BO7 Total"]["done"] += done
        buckets["BO7 Total"]["total"] += total

        if mode not in buckets:
            buckets[mode] = {"done": 0, "total": 0, "sections": []}

        buckets[mode]["done"] += done
        buckets[mode]["total"] += total
        buckets[mode]["sections"].append({
            "section": section,
            "done": done,
            "total": total,
        })


    def tuple_metric(value):
        if isinstance(value, tuple):
            return int(value[0]), int(value[1])

        if isinstance(value, dict):
            return int(value.get("done", 0)), int(value.get("total", 0))

        return 0, 0

    def render_completion_card(label, done, total):
        done = int(done or 0)
        total = int(total or 0)
        pct = _pct(done, total)

        is_done = total > 0 and done >= total

        status_label = "✅ DONE" if is_done else "IN PROGRESS"
        card_class = "completion-card completion-card-done" if is_done else "completion-card"
        pct_text = "100%" if is_done else f"{pct:.1f}%"

        st.markdown(
            f"""
            <div class="{card_class}">
                <div class="completion-status">{status_label}</div>
                <div class="completion-label">{label}</div>
                <div class="completion-pct">{pct_text}</div>
                <div class="completion-count">{done}/{total}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    overall = {
        "BO7 Total": {"done": 0, "total": 0, "sections": []},
    }

    # Camos
    camo_mode_map = {
        "Genesis (Co-Op / Endgame)": "Co-Op / Endgame",
        "Singularity (Multiplayer)": "Multiplayer",
        "Infestation (Zombies)": "Zombies",
        "Apocalypse (Warzone)": "Warzone",
    }

    for chain_label, mode in camo_mode_map.items():
        data = summary.get("camos", {}).get(chain_label, {})

        add_completion_bucket(
            overall,
            mode,
            "Base Camos",
            data.get("base_done", 0),
            data.get("base_total", 0),
        )

        add_completion_bucket(
            overall,
            mode,
            "True Final Camos",
            data.get("mastery_done", 0),
            data.get("mastery_total", 0),
        )

    # Calling cards
    for mode, value in summary.get("calling_cards", {}).items():
        done, total = tuple_metric(value)
        add_completion_bucket(overall, mode, "Calling Cards", done, total)

    # Reticles
    reticles = summary.get("reticles", {})
    for mode, value in reticles.get("by_mode", {}).items():
        done, total = tuple_metric(value)
        add_completion_bucket(overall, mode, "Reticles", done, total)

    # Titles
    titles = summary.get("titles", {})
    for mode, value in titles.get("by_mode", {}).items():
        done, total = tuple_metric(value)
        add_completion_bucket(overall, mode, "Titles", done, total)

    # Mastery badges
    mb = summary.get("mastery_badges", {})
    weapon_stages = mb.get("weapon_stages", {})
    support_stages = mb.get("support_stages", {})
    diamond_groups = mb.get("diamond_groups", {})

    mp_mastery_done = 0
    mp_mastery_total = 0
    zm_mastery_done = 0
    zm_mastery_total = 0

    for key in ["mp_bronze", "mp_silver", "mp_gold"]:
        done, total = tuple_metric(weapon_stages.get(key, (0, 0)))
        mp_mastery_done += done
        mp_mastery_total += total

        done, total = tuple_metric(support_stages.get(key, (0, 0)))
        mp_mastery_done += done
        mp_mastery_total += total

    for key in ["zm_bronze", "zm_silver", "zm_gold"]:
        done, total = tuple_metric(weapon_stages.get(key, (0, 0)))
        zm_mastery_done += done
        zm_mastery_total += total

        done, total = tuple_metric(support_stages.get(key, (0, 0)))
        zm_mastery_done += done
        zm_mastery_total += total

    done, total = tuple_metric(diamond_groups.get("mp", {}))
    mp_mastery_done += done
    mp_mastery_total += total

    done, total = tuple_metric(diamond_groups.get("zm", {}))
    zm_mastery_done += done
    zm_mastery_total += total

    add_completion_bucket(overall, "Multiplayer", "Mastery Badges", mp_mastery_done, mp_mastery_total)
    add_completion_bucket(overall, "Zombies", "Mastery Badges", zm_mastery_done, zm_mastery_total)

    # Weapon prestige is global account progress
    prestige = summary.get("prestige", {})
    prestige_stages = prestige.get("stages", {})

    prestige_done = 0
    prestige_total = 0

    for stage_data in prestige_stages.values():
        prestige_done += int(stage_data.get("done", 0))
        prestige_total += int(stage_data.get("total", 0))

    add_completion_bucket(overall, "Global Cleanup", "Weapon Prestige", prestige_done, prestige_total)

    # Colours are global account progress
    colours = summary.get("colours", {})
    if isinstance(colours, tuple):
        colours_done, colours_total = colours
    else:
        colours_done, colours_total = tuple_metric(colours.get("total", {}))

    add_completion_bucket(overall, "Global Cleanup", "Colours", colours_done, colours_total)

    # Augments are Zombies
    aug_done, aug_total = tuple_metric(summary.get("augments", (0, 0)))
    add_completion_bucket(overall, "Zombies", "Augments", aug_done, aug_total)

    # Overclocks are Multiplayer
    oc_done, oc_total = tuple_metric(summary.get("overclocks", (0, 0)))
    add_completion_bucket(overall, "Multiplayer", "Overclocks", oc_done, oc_total)

    # Intel is Zombies
    intel_done = 0
    intel_total = 0

    for value in summary.get("intel", {}).values():
        done, total = tuple_metric(value)
        intel_done += done
        intel_total += total

    add_completion_bucket(overall, "Zombies", "Intel", intel_done, intel_total)

    # Rewards
    rewards = summary.get("rewards", {})

    z_rewards_done, z_rewards_total = tuple_metric(rewards.get("zombies_total", (0, 0)))
    add_completion_bucket(overall, "Zombies", "Rewards", z_rewards_done, z_rewards_total)

    sp_rewards_done, sp_rewards_total = tuple_metric(rewards.get("endgame_operations_total", (0, 0)))
    add_completion_bucket(overall, "Co-Op / Endgame", "Operation Rewards", sp_rewards_done, sp_rewards_total)

    endgame_unlock_done, endgame_unlock_total = tuple_metric(rewards.get("endgame_unlocks_total", (0, 0)))
    add_completion_bucket(overall, "Co-Op / Endgame", "Endgame Unlocks", endgame_unlock_done, endgame_unlock_total)

    # Render
    st.markdown("## Overall Completion")

    overall_top_cols = st.columns(5)

    overall_order = [
        "BO7 Total",
        "Multiplayer",
        "Zombies",
        "Warzone",
        "Co-Op / Endgame",
    ]

    for i, mode in enumerate(overall_order):
        data = overall.get(mode, {"done": 0, "total": 0})

        with overall_top_cols[i]:
            render_completion_card(
                mode,
                data["done"],
                data["total"],
            )

    extra_modes = [
        mode for mode in overall.keys()
        if mode not in overall_order
    ]

    if extra_modes:
        extra_cols = st.columns(min(len(extra_modes), 4))

        for i, mode in enumerate(extra_modes):
            data = overall[mode]

            with extra_cols[i % len(extra_cols)]:
                render_completion_card(
                    mode,
                    data["done"],
                    data["total"],
                )

    with st.expander("Overall completion breakdown"):
        rows = []

        for mode, data in overall.items():
            if mode == "BO7 Total":
                continue

            for section in data.get("sections", []):
                rows.append({
                    "Mode": mode,
                    "Section": section["section"],
                    "Done": section["done"],
                    "Total": section["total"],
                    "%": f"{_pct(section['done'], section['total']):.1f}%",
                })

        st.dataframe(rows, use_container_width=True, hide_index=True)

    st.divider()
 
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

    def metric_data(source, fallback_done=0, fallback_total=0):
        return {
            "done": int(source.get("done", fallback_done)),
            "total": int(source.get("total", fallback_total)),
        }

    total_badges = metric_data(mb.get("total", {}))
    weapon_badges = metric_data(mb.get("weapon", {}))
    support_badges = metric_data(mb.get("support", {}))

    st.markdown("### Total Mastery Badge Completion")
    total_cols = st.columns(3)

    with total_cols[0]:
        render_completion_card(
            "All Mastery Badges",
            total_badges["done"],
            total_badges["total"],
        )

    with total_cols[1]:
        render_completion_card(
            "Weapon Completion",
            weapon_badges["done"],
            weapon_badges["total"],
        )

    with total_cols[2]:
        render_completion_card(
            "Support Item Completion",
            support_badges["done"],
            support_badges["total"],
        )

    diamond_groups = mb.get("diamond_groups", {})

    mp_diamond_groups = metric_data(diamond_groups.get("mp", {}))
    zm_diamond_groups = metric_data(diamond_groups.get("zm", {}))
    weapon_mp_diamond_groups = metric_data(diamond_groups.get("weapon_mp", {}))
    weapon_zm_diamond_groups = metric_data(diamond_groups.get("weapon_zm", {}))
    equipment_mp_diamond_groups = metric_data(diamond_groups.get("equipment_mp", {}))
    equipment_zm_diamond_groups = metric_data(diamond_groups.get("equipment_zm", {}))

    all_diamond_group_done = mp_diamond_groups["done"] + zm_diamond_groups["done"]
    all_diamond_group_total = mp_diamond_groups["total"] + zm_diamond_groups["total"]

    st.markdown("### Diamond Group Unlocks")
    st.caption(
        "Collection truth: a class or category counts as Diamond once its required Gold badge count is met."
    )

    diamond_cols = st.columns(5)

    with diamond_cols[0]:
        render_completion_card(
            "All Diamond Groups",
            all_diamond_group_done,
            all_diamond_group_total,
        )

    with diamond_cols[1]:
        render_completion_card(
            "MP Groups",
            mp_diamond_groups["done"],
            mp_diamond_groups["total"],
        )

    with diamond_cols[2]:
        render_completion_card(
            "ZM Groups",
            zm_diamond_groups["done"],
            zm_diamond_groups["total"],
        )

    with diamond_cols[3]:
        render_completion_card(
            "Weapon Groups",
            weapon_mp_diamond_groups["done"] + weapon_zm_diamond_groups["done"],
            weapon_mp_diamond_groups["total"] + weapon_zm_diamond_groups["total"],
        )

    with diamond_cols[4]:
        render_completion_card(
            "Support Groups",
            equipment_mp_diamond_groups["done"] + equipment_zm_diamond_groups["done"],
            equipment_mp_diamond_groups["total"] + equipment_zm_diamond_groups["total"],
        )

    individual_rows = mb.get("individual_diamond_rows", {})

    weapon_mp_rows = metric_data(individual_rows.get("weapon_mp", {}))
    weapon_zm_rows = metric_data(individual_rows.get("weapon_zm", {}))
    equipment_mp_rows = metric_data(individual_rows.get("equipment_mp", {}))
    equipment_zm_rows = metric_data(individual_rows.get("equipment_zm", {}))

    st.markdown("### Individual Diamond Row Progress")
    st.caption(
        "Grind detail: this is the raw row count, useful for seeing how far beyond the group unlock you have gone."
    )

    row_cols = st.columns(4)

    with row_cols[0]:
        render_completion_card(
            "Weapon MP Rows",
            weapon_mp_rows["done"],
            weapon_mp_rows["total"],
        )

    with row_cols[1]:
        render_completion_card(
            "Weapon ZM Rows",
            weapon_zm_rows["done"],
            weapon_zm_rows["total"],
        )

    with row_cols[2]:
        render_completion_card(
            "Support MP Rows",
            equipment_mp_rows["done"],
            equipment_mp_rows["total"],
        )

    with row_cols[3]:
        render_completion_card(
            "Support ZM Rows",
            equipment_zm_rows["done"],
            equipment_zm_rows["total"],
        )

    st.divider()
 
    # ── WEAPON LEVEL / PRESTIGE ──
    st.markdown("## Weapon Prestige")
    prestige = summary["prestige"]

    prestige_stage_order = [
        "p1_complete",
        "p2_complete",
        "wpm_complete",
        "lvl_100_complete",
        "lvl_150_complete",
        "lvl_200_complete",
        "lvl_250_complete",
    ]

    prestige_stage_labels = {
        "p1_complete": "Prestige 1",
        "p2_complete": "Prestige 2",
        "wpm_complete": "WPM",
        "lvl_100_complete": "Level 100",
        "lvl_150_complete": "Level 150",
        "lvl_200_complete": "Level 200",
        "lvl_250_complete": "Level 250",
    }

    prestige_stages = prestige.get("stages", {})


    def prestige_stage_data(stage):
        data = prestige_stages.get(stage, {})
        return {
            "label": data.get("label", prestige_stage_labels.get(stage, stage)),
            "done": int(data.get("done", 0)),
            "total": int(data.get("total", 0)),
        }


    def combined_prestige_data(stages):
        rows = [prestige_stage_data(stage) for stage in stages]
        return {
            "done": sum(row["done"] for row in rows),
            "total": sum(row["total"] for row in rows),
        }


    total_weapon_level = combined_prestige_data(prestige_stage_order)
    weapon_prestige_only = combined_prestige_data([
        "p1_complete",
        "p2_complete",
    ])
    wpm_and_levels = combined_prestige_data([
        "wpm_complete",
        "lvl_100_complete",
        "lvl_150_complete",
        "lvl_200_complete",
        "lvl_250_complete",
    ])

    st.markdown("### Total Weapon Level Completion")

    top_cols = st.columns(3)

    with top_cols[0]:
        render_completion_card(
            "Total Weapon Level Completion",
            total_weapon_level["done"],
            total_weapon_level["total"],
        )

    with top_cols[1]:
        render_completion_card(
            "Weapon Prestige",
            weapon_prestige_only["done"],
            weapon_prestige_only["total"],
        )

    with top_cols[2]:
        render_completion_card(
            "WPM + Level Grind",
            wpm_and_levels["done"],
            wpm_and_levels["total"],
        )

    st.markdown("### Stage Breakdown")

    prestige_cols = st.columns(7)

    for i, stage in enumerate(prestige_stage_order):
        data = prestige_stage_data(stage)

        with prestige_cols[i]:
            render_completion_card(
                data["label"],
                data["done"],
                data["total"],
            )

    st.caption(
        "Prestige counts roll backwards: a weapon at Level 250 also counts as "
        "Level 200, Level 150, Level 100, WPM, Prestige 2, and Prestige 1."
    )

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
        data = camos.get(
            chain_label,
            {
                "base_done": 0,
                "base_total": 0,
                "mastery_unlock_done": 0,
                "mastery_unlock_total": 30,
                "mastery_done": 0,
                "mastery_total": 0,
            },
        )

        with camo_cols[i]:
            st.markdown(f"**{chain_label.split(' (')[0]}**")

            render_completion_card(
                "Base Camo",
                data["base_done"],
                data["base_total"],
            )

            render_completion_card(
                "Calling Card Unlock",
                data.get("mastery_unlock_done", min(data["mastery_done"], 30)),
                data.get("mastery_unlock_total", 30),
            )

            render_completion_card(
                "True Final Camos",
                data["mastery_done"],
                data["mastery_total"],
            )
    st.divider()
 
    # ── CALLING CARD COMPLETION BY MODE ──
    st.markdown("## Calling Card Completion by Mode")
    cc = summary["calling_cards"]
    cc_cols = st.columns(4)

    for i, mode in enumerate(["Co-Op / Endgame", "Multiplayer", "Zombies", "Warzone"]):
        done, total = cc.get(mode, (0, 0))

        with cc_cols[i]:
            render_completion_card(
                mode,
                done,
                total,
            )
 
    st.divider()
 
    # ── RETICLE COMPLETION ──
    st.markdown("## Reticles")
    ret = summary["reticles"]

    def reticle_metric_data(source):
        return {
            "done": int(source.get("done", 0)),
            "total": int(source.get("total", 0)),
        }

    ret_total = reticle_metric_data(ret.get("total", {}))
    ret_by_mode = ret.get("by_mode", {})
    ret_stage_100 = ret.get("stage_100_by_mode", {})

    st.markdown("### Total Reticle Completion")

    top_cols = st.columns(1)

    with top_cols[0]:
        render_completion_card(
            "Total Reticle Completion",
            ret_total["done"],
            ret_total["total"],
        )

    st.markdown("### Mode Breakdown")

    mode_order = [
        ("Co-Op / Endgame", "SP"),
        ("Multiplayer", "MP"),
        ("Zombies", "ZM"),
        ("Warzone", "WZ"),
    ]

    mode_cols = st.columns(4)

    for i, (mode, label) in enumerate(mode_order):
        data = reticle_metric_data(ret_by_mode.get(mode, {}))

        with mode_cols[i]:
            render_completion_card(
                label,
                data["done"],
                data["total"],
            )

    st.markdown("### Stage 100 Detail")
    st.caption("Final-stage grind detail only. Total reticle completion above counts all five stages.")

    stage_cols = st.columns(4)

    for i, (mode, label) in enumerate(mode_order):
        data = reticle_metric_data(ret_stage_100.get(mode, {}))

        with stage_cols[i]:
            render_completion_card(
                f"{label} Stage 100",
                data["done"],
                data["total"],
            )

    st.divider()
 
    # ── TITLES ──
    st.markdown("## Titles")
    titles = summary["titles"]

    title_total = titles.get("total", {"done": 0, "total": 0})
    title_by_mode = titles.get("by_mode", {})

    st.markdown("### Total Title Completion")

    render_completion_card(
        "All Titles",
        title_total["done"],
        title_total["total"],
    )

    st.markdown("### Mode Breakdown")

    title_mode_order = [
        "Global Cleanup",
        "Co-Op / Endgame",
        "Multiplayer",
        "Zombies",
        "Warzone",
    ]

    visible_title_modes = [
        mode for mode in title_mode_order
        if mode in title_by_mode
    ]

    extra_title_modes = [
        mode for mode in title_by_mode.keys()
        if mode not in visible_title_modes
    ]

    visible_title_modes.extend(extra_title_modes)

    if visible_title_modes:
        title_cols = st.columns(min(len(visible_title_modes), 5))

        for i, mode in enumerate(visible_title_modes):
            data = title_by_mode.get(mode, {"done": 0, "total": 0})

            with title_cols[i % len(title_cols)]:
                render_completion_card(
                    mode,
                    data["done"],
                    data["total"],
                )
    else:
        st.info("No titles data found.")

    st.divider()
 
    # ── COLOURS ──
    st.markdown("## Colours")
    colours = summary["colours"]

    if isinstance(colours, tuple):
        colours_total = {
            "done": int(colours[0]),
            "total": int(colours[1]),
        }
        colours_by_category = {}
        colours_by_source = {}
    else:
        colours_total = colours.get("total", {"done": 0, "total": 0})
        colours_by_category = colours.get("by_category", {})
        colours_by_source = colours.get("by_source", {})

    st.markdown("### Total Colour Completion")

    render_completion_card(
        "All Colours",
        colours_total["done"],
        colours_total["total"],
    )

    if colours_by_category:
        st.markdown("### Category Breakdown")

        category_items = list(colours_by_category.items())
        category_cols = st.columns(min(len(category_items), 5))

        for i, (category, data) in enumerate(category_items):
            with category_cols[i % len(category_cols)]:
                render_completion_card(
                    category,
                    data["done"],
                    data["total"],
                )

    if colours_by_source:
        st.markdown("### Source Breakdown")

        source_items = list(colours_by_source.items())
        source_cols = st.columns(min(len(source_items), 5))

        for i, (source, data) in enumerate(source_items):
            with source_cols[i % len(source_cols)]:
                render_completion_card(
                    source,
                    data["done"],
                    data["total"],
                )

    st.divider()
 
    # ── AUGMENTS (Zombies only) ──
    st.markdown("## Augments (Zombies)")
    aug_done, aug_total = summary["augments"]
    render_completion_card(
        "Perk-A-Colas / Ammo Mods / Field Upgrades",
        aug_done,
        aug_total,
    )
 
    st.divider()
 
    # ── OVERCLOCKS (Multiplayer only) ──
    st.markdown("## Overclocks (Multiplayer)")
    oc_done, oc_total = summary["overclocks"]
    render_completion_card(
        "Scorestreaks / Lethals / Tacticals / Field Upgrades",
        oc_done,
        oc_total,
    )
 
    st.divider()
 
    # ── INTEL BY MAP ──
    st.markdown("## Intel by Map")
    intel = summary["intel"]
    if intel:
        intel_cols = st.columns(min(len(intel), 4))
        for i, (map_name, (done, total)) in enumerate(intel.items()):
            with intel_cols[i % len(intel_cols)]:
                render_completion_card(
                    map_name,
                    done,
                    total,
                )
    else:
        st.info("No intel data found.")
 
    st.divider()
 
    # ── REWARDS ──
    st.markdown("## Rewards")
    rewards = summary["rewards"]
 
    if "zombies_total" in rewards:
        z_done, z_total = rewards["zombies_total"]
        render_completion_card(
            "Zombies Rewards",
            z_done,
            z_total,
        )
        with st.expander("Breakdown by map"):
            by_map = rewards.get("zombies_by_map", {})
            rows = [
                {"Map": map_name, "Done": done, "Total": total, "%": f"{_pct(done, total):.1f}%"}
                for map_name, (done, total) in by_map.items()
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)
 
    if "endgame_operations_total" in rewards:
        e_done, e_total = rewards["endgame_operations_total"]
        render_completion_card(
            "Endgame Operations",
            e_done,
            e_total,
        )
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
    st.markdown("## Session Log")

    session_log = st.session_state.bo7_session_log

    account_level_rows = [
        row for row in session_log
        if str(row.get("account_levels_gained", "")).strip()
    ]

    total_account_levels = 0.0
    total_logged_minutes = 0.0
    sessions_with_levels = 0

    for row in account_level_rows:
        try:
            levels_gained = float(row.get("account_levels_gained", 0) or 0)
        except ValueError:
            levels_gained = 0.0

        if levels_gained <= 0:
            continue

        total_account_levels += levels_gained
        sessions_with_levels += 1

        try:
            minutes = float(row.get("time_limit", 0) or 0)
        except ValueError:
            minutes = 0.0

        if minutes > 0:
            total_logged_minutes += minutes

    avg_levels_per_session = (
        total_account_levels / sessions_with_levels
        if sessions_with_levels > 0
        else 0.0
    )

    avg_levels_per_hour = (
        total_account_levels / (total_logged_minutes / 60)
        if total_logged_minutes > 0
        else 0.0
    )

    st.markdown("### Account Level Summary")

    level_cols = st.columns(3)

    with level_cols[0]:
        st.metric(
            "Total Account Levels Gained",
            f"{total_account_levels:g}",
        )

    with level_cols[1]:
        st.metric(
            "Average Per Logged Session",
            f"{avg_levels_per_session:.2f}",
            f"{sessions_with_levels} sessions",
        )

    with level_cols[2]:
        st.metric(
            "Average Per Hour",
            f"{avg_levels_per_hour:.2f}",
            "from logged session length",
        )

    st.divider()
    
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

import csv
import json
from pathlib import Path
import pandas as pd
from datetime import datetime

import streamlit as st

st.set_page_config(
    page_title="Perzevol OS - BO7 Completion Commander",
    page_icon="☣",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
        "notes": f"Session plan stop {stop.get('stop_number', '')}",
    })

def record_stop_result(stop, status, result="", blame="", notes=""):
    task_id = stop["task_id"]

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
    }

    # Keep legacy list alive for anything else still reading it.
    if task_id not in st.session_state.bo7_completed_stop_ids:
        st.session_state.bo7_completed_stop_ids.append(task_id)

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
    if "bo7_celebrations" not in st.session_state:
        st.session_state.bo7_celebrations = []
    if "bo7_last_debrief" not in st.session_state:
        st.session_state.bo7_last_debrief = None
    
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
    "Endgame unlocks": "rewards_endgame_unlocks.csv",
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
    "rewards_endgame_unlocks.csv": ["category", "operator", "item_type", "item", "unlock_criteria", "source"],
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

CAMO_CHAIN_FILES = {
    "Apocalypse": "apocalypse_status.csv",
    "Singularity": "singularity_status.csv",
    "Infestation": "infestation_status.csv",
    "Genesis": "genesis_status.csv",
}


def write_camo_completion_from_stop(stop) -> bool:
    """
    Writes a completed session-plan camo stop back into the source camo CSV.

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
    Writes a completed session-plan reticle stop back into reticles.csv.

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
    Marks all camo columns up to reached_camo as TRUE for the stop weapon.

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
        return {"updated": False, "message": "No weapon found on stop."}

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

def reload_commander_from_csv():
    st.session_state.bo7_completion_state = load_completion_state()
    st.session_state.bo7_tasks = apply_completion_state(
        load_tracker_tasks(),
        st.session_state.bo7_completion_state,
    )
    st.session_state.bo7_progress = load_hub_progress()
    st.session_state.bo7_latest_mission = None

def queue_celebration(title: str, message: str, tier: str = "minor"):
    if "bo7_celebrations" not in st.session_state:
        st.session_state.bo7_celebrations = []

    st.session_state.bo7_celebrations.append({
        "title": title,
        "message": message,
        "tier": tier,
        "time": datetime.now().isoformat(timespec="seconds"),
    })


def queue_stop_celebration(stop: dict, csv_updated: bool):
    task_type = stop.get("task_type", "")
    mode = stop.get("mode", "")
    weapon = stop.get("weapon", "")
    camo = stop.get("camo", "")
    challenge = stop.get("challenge_text", "")

    if task_type == "camo":
        queue_celebration(
            "🎨 CAMO CLEARED",
            f"{weapon} - {camo} completed in {mode}. Source CSV updated." if csv_updated else f"{weapon} - {camo} logged.",
            "minor",
        )
        return

    if task_type == "reticle":
        queue_celebration(
            "🎯 RETICLE STAGE CLEARED",
            f"{weapon} - {camo} completed in {mode}. Reticle mastery moved forward." if csv_updated else f"{weapon} - {camo} logged.",
            "minor",
        )
        return

    if task_type == "weapon_prestige":
        queue_celebration(
            "⚙️ WEAPON PRESTIGE PROGRESS",
            f"{weapon} - {camo}. Weapon XP grind moved forward.",
            "minor",
        )
        return

    if task_type == "mastery_badge_weapon":
        queue_celebration(
            "🏅 WEAPON BADGE PROGRESS",
            f"{weapon} - {camo}. Badge route advanced.",
            "minor",
        )
        return

    if task_type == "mastery_badge_equipment":
        queue_celebration(
            "🧰 SUPPORT BADGE PROGRESS",
            f"{weapon} - {camo}. Support grind advanced.",
            "minor",
        )
        return

    if task_type == "dark_ops":
        queue_celebration(
            "💀 DARK OPS HIT",
            f"{weapon}: {challenge}",
            "major",
        )
        return

    if task_type == "calling_card":
        queue_celebration(
            "🃏 CALLING CARD PROGRESS",
            f"{weapon} - {camo}. Calling-card route advanced.",
            "minor",
        )
        return

    if task_type == "title":
        queue_celebration(
            "🏷 TITLE PROGRESS",
            f"{weapon}: {challenge}",
            "minor",
        )
        return

    queue_celebration(
        "✅ OBJECTIVE LOGGED",
        f"{weapon} - {camo}",
        "minor",
    )


def render_queued_celebrations():
    celebrations = st.session_state.get("bo7_celebrations", [])

    if not celebrations:
        return

    for celebration in celebrations:
        title = celebration.get("title", "✅ Progress")
        message = celebration.get("message", "")
        tier = celebration.get("tier", "minor")

        if tier == "major":
            st.toast(f"{title} - {message}", icon="🔥")
            st.success(f"### {title}\n{message}")
        else:
            st.toast(f"{title} - {message}", icon="✅")
            st.info(f"**{title}**  \n{message}")

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
        "One-time setup for current weapon levels. After this, session stop logging can keep these updated."
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

    edited_dataframe = st.data_editor(
        filtered_dataframe[display_columns],
        use_container_width=True,
        height=720,
        hide_index=False,
        disabled=[
            column for column in display_columns
            if column not in {"current_level"}
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
        },
        key="weapon_level_quick_grid",
    )

    if st.button("SAVE WEAPON LEVELS", use_container_width=True):
        updated_dataframe = dataframe.copy()

        if "current_level" not in updated_dataframe.columns:
            updated_dataframe["current_level"] = "0"

        for row_index, edited_row in edited_dataframe.iterrows():
            updated_dataframe.loc[row_index, "current_level"] = f"{float(edited_row['current_level']):g}"

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


def render_cockpit_editor(filename: str, title: str | None = None):
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
                    key=f"cockpit_filter_{filename}_{column}",
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
            key=f"cockpit_editor_{filename}",
        )

    if st.button(f"SAVE {label.upper()}", use_container_width=True, key=f"cockpit_save_{filename}"):
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
            st.metric("Editable Trackers", "13")

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
    st.caption(
        f"Current account level: "
        f"{float(st.session_state.bo7_account_params.get('account_level', 1.0)):g}"
    )

    render_queued_celebrations()

    if plan and plan.get("stops"):
        st.markdown(f"<div class='order-mode'>☣ {plan['mode']} — SESSION PLAN ACTIVE</div>", unsafe_allow_html=True)

        guide_bits = []
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
                st.metric("High-Value Stops", high_value_count)
                st.caption(unlock_value)

            st.caption(f"Stacking: {stacking}")

            actual_cluster_counts = {}

            for stop in plan.get("stops", []):
                cluster_label = stop.get("cluster_label", "Unclassified")
                actual_cluster_counts[cluster_label] = actual_cluster_counts.get(cluster_label, 0) + 1

            if actual_cluster_counts:
                cluster_text = " · ".join(
                    f"{label} ({count} stop{'s' if count != 1 else ''})"
                    for label, count in actual_cluster_counts.items()
                )
                st.markdown(
                    f"<div class='order-strategy'>Focus route: {cluster_text}</div>",
                    unsafe_allow_html=True,
                )

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
                    st.caption(f"Estimated time: {estimated_minutes} minutes")
                stacking_hint = stop.get("stacking_hint", "")
                if stacking_hint:
                    st.info(stacking_hint)
                companion_objectives = stop.get("companion_objectives", [])

                if companion_objectives:
                    with st.expander("Stack while doing this", expanded=True):
                        for companion in companion_objectives:
                            st.write(f"✅ {companion}")

                companion_objectives = stop.get("companion_objectives", [])
                if companion_objectives:
                    with st.expander("Stack while doing this", expanded=True):
                        for companion in companion_objectives:
                            st.write(f"✅ {companion}")

                if resolved:
                    result = st.session_state.bo7_stop_results.get(task_id, {})
                    st.caption(
                        f"Logged as {status_label}. "
                        f"{result.get('result', '')} {result.get('blame', '')}".strip()
                    )

                    if st.button("↩️ Undo stop result", key=f"undo_{task_id}", use_container_width=True):
                        st.session_state.bo7_stop_results.pop(task_id, None)
                        st.session_state.bo7_completed_stop_ids = [
                            existing_id
                            for existing_id in st.session_state.bo7_completed_stop_ids
                            if existing_id != task_id
                        ]
                        st.rerun()

                    st.divider()
                    continue

                col1, col2, col3 = st.columns(3)
                weapon_level_key = f"weapon_levels_gained_{task_id}"
                weapon_reset_key = f"weapon_prestige_reset_{task_id}"

                with st.expander("Weapon level progress", expanded=False):
                    st.number_input(
                        "Weapon levels gained on this stop",
                        min_value=0.0,
                        max_value=250.0,
                        value=0.0,
                        step=0.5,
                        key=weapon_level_key,
                    )

                    st.checkbox(
                        "I prestiged/reset this weapon after this stop",
                        key=weapon_reset_key,
                    )

                    st.caption(
                        "Use this for actual weapon level progress. If you hit the level cap and prestige in-game, tick the reset box before pressing Done or Partial."
                    )

                camo_reached_key = f"camo_reached_{task_id}"
                reticle_reached_key = f"reticle_reached_{task_id}"

                if stop.get("task_type") == "camo":
                    with st.expander("Camo progress reached", expanded=False):
                        st.selectbox(
                            "Highest camo reached this stop",
                            camo_reached_options_from_stop(stop),
                            key=camo_reached_key,
                        )

                        st.caption(
                            "Use this if you went further than the assigned camo. "
                            "Selecting Golden Dragon marks every camo up to Golden Dragon complete for this weapon."
                        )

                if stop.get("task_type") == "reticle":
                    with st.expander("Reticle progress reached", expanded=False):
                        st.selectbox(
                            "Highest reticle stage reached this stop",
                            ["No extra update", "20", "40", "60", "80", "100"],
                            key=reticle_reached_key,
                        )

                        st.caption(
                            "Use this if you went further than the assigned reticle stage. "
                            "Selecting 100 marks every stage up to 100 complete for this mode only."
                        )

                with col1:
                    if st.button("✅ Done", key=f"done_{task_id}", use_container_width=True):
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

                        if csv_updated:
                            milestone_after = capture_milestone_snapshot()
                            queue_milestone_celebrations(milestone_before, milestone_after)

                        log_plan_stop(stop, "Camo completed", "Successful operation")

                        record_stop_result(
                            stop=stop,
                            status="done",
                            result="Camo completed",
                            blame="Successful operation",
                            notes="CSV updated" if csv_updated else "Logged only",
                        )

                        queue_stop_celebration(stop, csv_updated)

                        if csv_updated:
                            reload_commander_from_csv()

                        st.rerun()

                with col2:
                    if st.button("⚠️ Partial", key=f"partial_{task_id}", use_container_width=True):
                        milestone_before = capture_milestone_snapshot()

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

                        if csv_updated:
                            milestone_after = capture_milestone_snapshot()
                            queue_milestone_celebrations(milestone_before, milestone_after)
                            reload_commander_from_csv()

                        record_stop_result(
                            stop=stop,
                            status="partial",
                            result="Partial progress",
                            blame="Human avoidance",
                        )
                        st.rerun()

                with col3:
                    if st.button("⏭️ Skip", key=f"skip_{task_id}", use_container_width=True):
                        log_plan_stop(stop, "Skipped", "Human choice")
                        record_stop_result(
                            stop=stop,
                            status="skipped",
                            result="Skipped",
                            blame="Human choice",
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
                )
 
                st.session_state.bo7_session_plan = new_plan
                st.rerun()
 
        with col_b:
            st.markdown("### End Session Log")

            st.session_state.bo7_account_levels_gained = st.number_input(
                "Account levels gained this session",
                min_value=0.0,
                max_value=100.0,
                value=float(st.session_state.bo7_account_levels_gained),
                step=0.5,
                key="account_levels_gained_input",
            )

            st.session_state.bo7_actual_minutes_played = st.number_input(
                "Actual minutes played",
                min_value=0,
                max_value=480,
                value=int(st.session_state.bo7_actual_minutes_played or plan.get("estimated_minutes", 0) or plan.get("available_minutes", 0)),
                step=5,
                key="actual_minutes_played_input",
            )

            if st.button("END SESSION", use_container_width=True):
                levels_gained = float(st.session_state.bo7_account_levels_gained)
                actual_minutes_played = int(st.session_state.bo7_actual_minutes_played or 0)

                st.session_state.bo7_last_debrief = build_session_debrief(
                    plan=st.session_state.bo7_session_plan,
                    stop_results=st.session_state.bo7_stop_results,
                    account_levels_gained=levels_gained,
                    actual_minutes_played=actual_minutes_played,
                )

                log_account_level_gain(
                    levels_gained=levels_gained,
                    plan=st.session_state.bo7_session_plan,
                    actual_minutes_played=actual_minutes_played,
                )

                st.session_state.bo7_session_log = load_persisted_session_log()
                st.session_state.bo7_session_plan = None
                st.session_state.bo7_completed_stop_ids = []
                st.session_state.bo7_stop_results = {}
                st.session_state.bo7_account_levels_gained = 0.0
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
                "Closest finishes hunts nearly-done items."
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
            help="Strong bias, not a hard lock. Use this for Launchers + Scorestreaks style sessions.",
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
            )

            st.session_state.bo7_session_plan = new_plan
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
            )

            st.session_state.bo7_session_plan = new_plan
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
        "XP token bank tracking has been retired. Weapon level progress now lives in Quick Update → Weapon Levels and on each session stop."
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

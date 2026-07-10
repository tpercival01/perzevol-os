from pathlib import Path
from datetime import datetime
import re

import streamlit as st

from modules.ui.perzevol_theme import inject_perzevol_theme
import pandas as pd
import time

from modules.warzone.ttk_oracle_engine import (
    BUILD_GOALS,
    DEFAULT_STATS_PROFILE,
    LEGACY_STATS_PROFILE,
    SUPPORTED_STATS_PROFILES,
    FIGHT_TYPES,
    LOADOUT_PAIRINGS,
    MAP_TYPES,
    PERK_PACKAGES,
    build_base_weapon_rankings,
    build_loadout_preview,
    build_ttk_data_warnings,
    describe_weapon_build_data,
    estimate_optimizer_combo_count,
    filter_ttk_data_by_profile,
    get_compatible_attachments,
    load_ttk_data,
    optimise_full_loadouts_for_scenario,
    optimise_single_weapon_build,
    parse_codmunity_attachment_html,
    build_attachment_verification_rows,
)


st.set_page_config(
    page_title="Perzevol OS - TTK Oracle",
    page_icon="🧪",
    layout="wide",
)

inject_perzevol_theme(screen="ttk_oracle")

st.title("BO7: TTK Oracle")
st.caption(
    "Perzevol OS loadout lab. The Oracle produces candidates; the Field Test Log decides what survives contact."
)


@st.cache_data(show_spinner=False)
def load_and_validate_ttk_data():
    guns, attachments = load_ttk_data()

    before = len(guns)
    duplicate_subset = ["stats_profile", "gun_id"] if "stats_profile" in guns.columns else ["gun_id"]
    guns = guns.drop_duplicates(subset=duplicate_subset).reset_index(drop=True)
    duplicate_count = before - len(guns)

    warnings = build_ttk_data_warnings(
        guns=guns,
        attachments=attachments,
        attachment_count=5,
    )

    if duplicate_count:
        warnings.insert(0, f"Removed {duplicate_count} duplicate gun row(s) by gun_id.")

    return guns, attachments, warnings


def slugify_for_ttk(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def safe_float(value, fallback: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return fallback
        text = str(value).strip().replace("%", "").replace(",", "")
        if text == "":
            return fallback
        return float(text)
    except (TypeError, ValueError):
        return fallback


def pct_delta(base_value, observed_value) -> float:
    base_number = safe_float(base_value, 0.0)
    observed_number = safe_float(observed_value, 0.0)

    if base_number == 0:
        return 0.0

    return round(((observed_number - base_number) / base_number) * 100, 2)


def additive_delta(base_value, observed_value) -> float:
    return round(safe_float(observed_value, 0.0) - safe_float(base_value, 0.0), 2)


def clean_delta_value(value: float) -> float:
    number = round(float(value or 0.0), 2)
    if abs(number) < 0.005:
        return 0.0
    return number


def build_delta_bench_metric_template(gun: pd.Series) -> pd.DataFrame:
    """
    One editable table is faster than screenshotting every attachment.

    Base values are pulled from guns.csv where possible. Unknown in-game-only
    values start at 0, so Thomas only fills the rows that changed or matter.
    """
    base_fire_rate = safe_float(gun.get("fire_rate_rpm", 0), 0.0)
    base_velocity = safe_float(gun.get("bullet_velocity", 0), 0.0)
    base_damage = safe_float(gun.get("damage_close", 0), 0.0)
    base_range = safe_float(gun.get("range_mid_m", gun.get("range_close_m", 0)), 0.0)
    base_mag = safe_float(gun.get("mag_size", 0), 0.0)
    base_ads = safe_float(gun.get("ads_ms", 0), 0.0)
    base_sprint_to_fire = safe_float(gun.get("sprint_to_fire_ms", 0), 0.0)
    base_recoil = safe_float(gun.get("recoil", 0), 0.0)

    rows = [
        ("Fire rate rpm", "fire_rate_pct", "pct", base_fire_rate, base_fire_rate),
        ("Bullet velocity", "bullet_velocity_pct", "pct", base_velocity, base_velocity),
        ("Close damage", "damage_pct", "pct", base_damage, base_damage),
        ("Effective range metres", "range_pct", "pct", base_range, base_range),
        ("Magazine size", "mag_size_add", "add", base_mag, base_mag),
        ("ADS ms", "ads_pct", "pct", base_ads, base_ads),
        ("Sprint to fire ms", "sprint_to_fire_pct", "pct", base_sprint_to_fire, base_sprint_to_fire),
        ("Reload ms", "reload_pct", "pct", 0.0, 0.0),
        ("Jump ADS ms", "jump_ads_pct", "pct", 0.0, 0.0),
        ("Jump sprint to fire ms", "jump_sprint_to_fire_pct", "pct", 0.0, 0.0),
        ("Generic recoil", "recoil_pct", "pct", base_recoil, base_recoil),
        ("Recoil gun kick", "gun_kick_pct", "pct", 0.0, 0.0),
        ("Horizontal recoil", "horizontal_recoil_pct", "pct", 0.0, 0.0),
        ("Vertical recoil", "vertical_recoil_pct", "pct", 0.0, 0.0),
        ("First shot recoil scale", "first_shot_recoil_pct", "pct", 0.0, 0.0),
        ("Kick reset speed ms", "kick_reset_speed_pct", "pct", 0.0, 0.0),
        ("Flinch resistance", "flinch_resistance_pct", "pct", 0.0, 0.0),
        ("Movement speed", "movement_pct", "pct", 0.0, 0.0),
        ("Sprint speed", "sprint_pct", "pct", 0.0, 0.0),
        ("Crouch movement speed", "crouch_movement_pct", "pct", 0.0, 0.0),
        ("ADS movement speed", "ads_movement_pct", "pct", 0.0, 0.0),
    ]

    return pd.DataFrame(
        rows,
        columns=["metric", "target_column", "delta_mode", "base_value", "observed_value"],
    )


def calculate_delta_bench_values(metric_rows: pd.DataFrame) -> tuple[dict, str]:
    values = {column: 0.0 for column in ATTACHMENT_IMPORT_DATA_COLUMNS if column.endswith("_pct") or column.endswith("_add")}
    raw_lines = ["Delta Bench in-game comparison."]

    for _, metric in metric_rows.iterrows():
        target_column = str(metric.get("target_column", "") or "").strip()
        delta_mode = str(metric.get("delta_mode", "") or "").strip().lower()
        base_value = metric.get("base_value", 0)
        observed_value = metric.get("observed_value", 0)

        if target_column not in values:
            continue

        if safe_float(base_value, 0.0) == 0 and safe_float(observed_value, 0.0) == 0:
            continue

        if delta_mode == "add":
            delta = additive_delta(base_value, observed_value)
        else:
            delta = pct_delta(base_value, observed_value)

        delta = clean_delta_value(delta)
        values[target_column] = delta

        if delta != 0:
            suffix = " shells" if target_column == "mag_size_add" else "%"
            raw_lines.append(
                f"{metric.get('metric', target_column)}: base {base_value} -> observed {observed_value} = {delta:g}{suffix}"
            )

    # Do not auto-fill recoil_pct from detailed recoil columns.
    # The engine already combines recoil_pct with gun_kick / horizontal / vertical
    # recoil. Auto-filling here would double-count recoil changes.

    return values, "\n".join(raw_lines)


def build_delta_bench_attachment_row(
    *,
    weapon_name: str,
    weapon_class: str,
    stats_profile: str,
    attachment_name: str,
    slot: str,
    source_attachment: pd.Series | None,
    metric_rows: pd.DataFrame,
    approval_status: str,
    review_notes: str,
    extra_stat_notes: str,
) -> pd.DataFrame:
    delta_values, raw_stat_text = calculate_delta_bench_values(metric_rows)

    if extra_stat_notes.strip():
        raw_stat_text = raw_stat_text + "\nExtra in-game notes:\n" + extra_stat_notes.strip()

    attachment_id = ""
    if source_attachment is not None:
        attachment_id = str(source_attachment.get("attachment_id", "") or "").strip()

    if not attachment_id:
        attachment_id = f"{slugify_for_ttk(stats_profile)}_{slugify_for_ttk(weapon_name)}_{slugify_for_ttk(attachment_name)}"

    row = {
        "approval_status": approval_status,
        "review_notes": review_notes,
        "attachment_id": attachment_id,
        "attachment_name": attachment_name,
        "slot": slot,
        "stats_profile": stats_profile,
        "compatible_weapon_classes": weapon_class,
        "compatible_guns": weapon_name,
        "raw_stat_text": raw_stat_text,
        "source": "in-game delta bench",
        "source_date": datetime.now().date().isoformat(),
        "verification_status": approval_verification_status(approval_status),
        "verification_notes": "Built from in-game visible numbers with TTK In-Game Delta Bench.",
    }

    for column in ATTACHMENT_IMPORT_DATA_COLUMNS:
        if column not in row:
            row[column] = ""

    for column, value in delta_values.items():
        if column in row:
            row[column] = value

    return pd.DataFrame([row])


STATE_DIR = Path("data/bo7_state")
SAVED_TTK_LOADOUTS_PATH = STATE_DIR / "saved_ttk_loadouts.csv"
FIELD_TEST_LOG_PATH = STATE_DIR / "ttk_field_test_log.csv"
IMPORT_APPROVAL_LOG_PATH = STATE_DIR / "ttk_import_approval_log.csv"
IMPORT_COMMIT_LOG_PATH = STATE_DIR / "ttk_import_commit_log.csv"
TTK_DATA_DIR = Path("data/bo7_ttk")
MASTER_ATTACHMENTS_PATH = TTK_DATA_DIR / "attachments.csv"
MASTER_GUNS_PATH = TTK_DATA_DIR / "guns.csv"

PROFILED_GUN_COLUMNS = [
    "gun_id",
    "gun_name",
    "weapon_class",
    "stats_profile",
    "damage_close",
    "range_close_m",
    "damage_mid",
    "range_mid_m",
    "damage_long",
    "fire_rate_rpm",
    "ads_ms",
    "sprint_to_fire_ms",
    "recoil",
    "bullet_velocity",
    "mag_size",
]

FIELD_TEST_VERDICTS = [
    "FIELD TESTED",
    "FELT GOOD",
    "FELT BAD",
    "DATA SUSPECT",
    "REJECTED",
]

IMPORT_APPROVAL_STATUSES = [
    "APPROVE FOR MODEL",
    "NEEDS IN-GAME CHECK",
    "DATA SUSPECT",
    "EXCLUDE FROM OPTIMISER",
    "UNMODELLED",
]

IMPORT_APPROVAL_TO_VERIFICATION_STATUS = {
    "APPROVE FOR MODEL": "verified",
    "NEEDS IN-GAME CHECK": "needs_verification",
    "DATA SUSPECT": "partial",
    "EXCLUDE FROM OPTIMISER": "excluded",
    "UNMODELLED": "unmodelled",
}

ATTACHMENT_IMPORT_DATA_COLUMNS = [
    "attachment_id",
    "attachment_name",
    "slot",
    "stats_profile",
    "compatible_weapon_classes",
    "compatible_guns",
    "damage_pct",
    "fire_rate_pct",
    "ads_ms_add",
    "sprint_to_fire_ms_add",
    "recoil_pct",
    "bullet_velocity_pct",
    "range_pct",
    "mag_size_add",
    "ads_pct",
    "sprint_to_fire_pct",
    "reload_pct",
    "jump_ads_pct",
    "jump_sprint_to_fire_pct",
    "movement_pct",
    "sprint_pct",
    "crouch_movement_pct",
    "ads_movement_pct",
    "gun_kick_pct",
    "horizontal_recoil_pct",
    "vertical_recoil_pct",
    "first_shot_recoil_pct",
    "kick_reset_speed_pct",
    "flinch_resistance_pct",
    "raw_stat_text",
    "source",
    "source_date",
    "verification_status",
    "verification_notes",
]

IMPORT_APPROVAL_LOG_COLUMNS = list(
    dict.fromkeys(
        [
            "reviewed_at",
            "weapon",
            "approval_status",
            "review_notes",
            *ATTACHMENT_IMPORT_DATA_COLUMNS,
        ]
    )
)

IMPORT_COMMIT_LOG_COLUMNS = [
    "committed_at",
    "weapon",
    "commit_mode",
    "approved_rows",
    "rows_committed",
    "rows_skipped",
    "backup_path",
    "notes",
]

CANDIDATE_TRUST_FILTERS = [
    "HIDE REJECTED BUILDS",
    "SHOW ALL LAB CANDIDATES",
    "FIELD TESTED ONLY",
    "TESTED AND NOT REJECTED",
    "UNTESTED MODELLED ONLY",
]

FIELD_APPROVED_CONFIDENCE = {"FIELD TESTED", "FELT GOOD"}
FIELD_LOGGED_CONFIDENCE = {"FIELD TESTED", "FELT GOOD", "DATA SUSPECT", "REJECTED"}

ATTACHMENT_RULESETS = [
    "Warzone",
    "Zombies",
    "Co-Op / Endgame",
    "Multiplayer",
    "Multiplayer + Gunfighter Wildcard",
]

ATTACHMENT_BUDGET_PROFILES = [
    "AUTO BY MODE",
    "STANDARD BUILD - 5 ATTACHMENTS",
    "EXTENDED BUILD - 8 ATTACHMENTS",
]

OPTIMISER_DEPTH_PROFILES = [
    "FAST PASS - SLOT SHORTLIST",
    "DEEP PASS - EXHAUSTIVE AFTER PRUNING",
]

EXTENDED_ATTACHMENT_RULESETS = {
    "Zombies",
    "Co-Op / Endgame",
    "Multiplayer + Gunfighter Wildcard",
}


def attachment_count_for_profile(ruleset: str, budget_profile: str) -> int:
    profile = str(budget_profile or "").strip().upper()
    ruleset = str(ruleset or "").strip()

    if profile.startswith("STANDARD"):
        return 5

    if profile.startswith("EXTENDED"):
        return 8

    if ruleset in EXTENDED_ATTACHMENT_RULESETS:
        return 8

    return 5


def attachment_budget_summary(ruleset: str, budget_profile: str) -> str:
    attachment_count = attachment_count_for_profile(ruleset, budget_profile)

    if attachment_count == 8:
        return (
            f"EXTENDED BUILD ACTIVE: {ruleset} is using an 8-attachment lab budget. "
            "This is a separate profile from 5-attachment builds."
        )

    if str(ruleset or "").strip() == "Warzone":
        return "STANDARD BUILD ACTIVE: Warzone is capped at 5 attachments."

    return (
        f"STANDARD BUILD ACTIVE: {ruleset} is capped at 5 attachments unless "
        "a wildcard or extended mode is selected."
    )


def optimiser_mode_for_profile(depth_profile: str) -> str:
    profile = str(depth_profile or "").strip().upper()

    if profile.startswith("DEEP"):
        return "Deep"

    return "Fast"


def optimiser_depth_summary(depth_profile: str, slot_candidate_limit: int) -> str:
    optimiser_mode = optimiser_mode_for_profile(depth_profile)

    if optimiser_mode == "Deep":
        return (
            "DEEP PASS ACTIVE: exhaustive after safe pruning. "
            "Use this for final lab validation, not casual scanning."
        )

    return (
        f"FAST PASS ACTIVE: the Oracle keeps up to {slot_candidate_limit} "
        "scenario-relevant candidates per attachment slot before brute force."
    )


def render_optimizer_workload_estimate(
    *,
    guns_subset: pd.DataFrame,
    attachments: pd.DataFrame,
    map_type: str,
    fight_type: str,
    build_goal: str,
    enemy_health: int,
    attachment_count: int,
    optimiser_mode: str,
    slot_candidate_limit: int,
):
    workload = estimate_optimizer_combo_count(
        guns=guns_subset,
        attachments=attachments,
        map_type=map_type,
        fight_type=fight_type,
        build_goal=build_goal,
        enemy_health=enemy_health,
        attachment_count=attachment_count,
        optimiser_mode=optimiser_mode,
        candidate_limit_per_slot=slot_candidate_limit,
    )

    if workload.empty:
        st.caption("Workload estimate unavailable. No gun or attachment data found.")
        return

    buildable = workload[workload["buildable"] == True]  # noqa: E712
    estimated_combinations = int(buildable["estimated_combinations"].sum()) if not buildable.empty else 0
    buildable_count = int(len(buildable))

    if estimated_combinations <= 0:
        st.warning("No legal build combinations found for this depth and attachment budget.")
        return

    message = (
        f"Workload estimate: {estimated_combinations:,} candidate build(s) "
        f"across {buildable_count} buildable weapon(s)."
    )

    if optimiser_mode == "Deep" and estimated_combinations > 250_000:
        st.warning(
            message
            + " This is a heavy deep pass. Use FAST PASS first unless you are validating a final Episode 2 build."
        )
    elif estimated_combinations > 50_000:
        st.info(message + " This is a serious lab pass, but still isolated from Commander.")
    else:
        st.caption(message)

    with st.expander("Workload detail", expanded=False):
        st.dataframe(
            workload[
                [
                    "gun_name",
                    "weapon_class",
                    "attachment_count",
                    "optimiser_mode",
                    "usable_slots",
                    "pool_rows_after_pruning",
                    "estimated_combinations",
                    "ignored_rows",
                    "slot_pool_summary",
                    "buildable",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )


FIELD_TEST_COLUMNS = [
    "tested_at",
    "source",
    "loadout_type",
    "weapon",
    "weapon_class",
    "attachments",
    "secondary_weapon",
    "secondary_class",
    "secondary_attachments",
    "mode_profile",
    "stats_profile",
    "attachment_budget",
    "attachment_count",
    "optimiser_depth",
    "slot_candidate_limit",
    "enemy_health",
    "fight_type",
    "build_goal",
    "raw_ttk_ms",
    "practical_ttk_ms",
    "oracle_score",
    "field_verdict",
    "feel_rating",
    "kept_build",
    "commander_eligible",
    "notes",
]

SAVED_LOADOUT_COLUMNS = [
    "saved_at",
    "save_name",
    "source",
    "mode_profile",
    "stats_profile",
    "enemy_health",
    "fight_type",
    "build_goal",
    "loadout_type",
    "attachment_count",
    "optimiser_depth",
    "slot_candidate_limit",
    "primary_weapon",
    "primary_class",
    "primary_attachments",
    "primary_slots",
    "primary_raw_ttk_ms",
    "primary_practical_ttk_ms",
    "primary_ads_ms",
    "primary_sprint_to_fire_ms",
    "primary_recoil",
    "secondary_weapon",
    "secondary_class",
    "secondary_attachments",
    "secondary_slots",
    "secondary_raw_ttk_ms",
    "secondary_practical_ttk_ms",
    "secondary_ads_ms",
    "secondary_sprint_to_fire_ms",
    "secondary_recoil",
    "perk_package",
    "perk_1",
    "perk_2",
    "perk_3",
    "perk_4",
    "notes",
    "favourite",
    "used_in_video",
    "archived",
]


def ensure_saved_loadout_store():
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if not SAVED_TTK_LOADOUTS_PATH.exists():
        pd.DataFrame(columns=SAVED_LOADOUT_COLUMNS).to_csv(
            SAVED_TTK_LOADOUTS_PATH,
            index=False,
        )


def load_saved_ttk_loadouts() -> pd.DataFrame:
    ensure_saved_loadout_store()

    saved = pd.read_csv(SAVED_TTK_LOADOUTS_PATH, dtype=str).fillna("")

    for column in SAVED_LOADOUT_COLUMNS:
        if column not in saved.columns:
            saved[column] = ""

    return saved[SAVED_LOADOUT_COLUMNS]


def save_saved_ttk_loadouts(dataframe: pd.DataFrame):
    ensure_saved_loadout_store()
    updated = dataframe.copy()

    for column in SAVED_LOADOUT_COLUMNS:
        if column not in updated.columns:
            updated[column] = ""

    updated[SAVED_LOADOUT_COLUMNS].to_csv(SAVED_TTK_LOADOUTS_PATH, index=False)


def append_saved_ttk_loadout(row: dict):
    saved = load_saved_ttk_loadouts()
    clean_row = {column: str(row.get(column, "")) for column in SAVED_LOADOUT_COLUMNS}
    updated = pd.concat([saved, pd.DataFrame([clean_row])], ignore_index=True)
    save_saved_ttk_loadouts(updated)


def ensure_field_test_log_store():
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if not FIELD_TEST_LOG_PATH.exists():
        pd.DataFrame(columns=FIELD_TEST_COLUMNS).to_csv(
            FIELD_TEST_LOG_PATH,
            index=False,
        )


def load_ttk_field_test_log() -> pd.DataFrame:
    ensure_field_test_log_store()

    field_log = pd.read_csv(FIELD_TEST_LOG_PATH, dtype=str).fillna("")

    for column in FIELD_TEST_COLUMNS:
        if column not in field_log.columns:
            field_log[column] = ""

    return field_log[FIELD_TEST_COLUMNS]


def save_ttk_field_test_log(dataframe: pd.DataFrame):
    ensure_field_test_log_store()
    updated = dataframe.copy()

    for column in FIELD_TEST_COLUMNS:
        if column not in updated.columns:
            updated[column] = ""

    updated[FIELD_TEST_COLUMNS].to_csv(FIELD_TEST_LOG_PATH, index=False)


def append_ttk_field_test(row: dict):
    field_log = load_ttk_field_test_log()
    clean_row = {column: str(row.get(column, "")) for column in FIELD_TEST_COLUMNS}
    updated = pd.concat([field_log, pd.DataFrame([clean_row])], ignore_index=True)
    save_ttk_field_test_log(updated)


def ensure_import_approval_log_store():
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if not IMPORT_APPROVAL_LOG_PATH.exists():
        pd.DataFrame(columns=IMPORT_APPROVAL_LOG_COLUMNS).to_csv(
            IMPORT_APPROVAL_LOG_PATH,
            index=False,
        )


def load_ttk_import_approval_log() -> pd.DataFrame:
    ensure_import_approval_log_store()

    approval_log = pd.read_csv(IMPORT_APPROVAL_LOG_PATH, dtype=str).fillna("")

    for column in IMPORT_APPROVAL_LOG_COLUMNS:
        if column not in approval_log.columns:
            approval_log[column] = ""

    return approval_log[IMPORT_APPROVAL_LOG_COLUMNS]


def save_ttk_import_approval_log(dataframe: pd.DataFrame):
    ensure_import_approval_log_store()
    updated = dataframe.copy()

    for column in IMPORT_APPROVAL_LOG_COLUMNS:
        if column not in updated.columns:
            updated[column] = ""

    updated[IMPORT_APPROVAL_LOG_COLUMNS].to_csv(
        IMPORT_APPROVAL_LOG_PATH,
        index=False,
    )


def approval_verification_status(approval_status: str) -> str:
    status = str(approval_status or "").strip().upper()
    return IMPORT_APPROVAL_TO_VERIFICATION_STATUS.get(
        status,
        "needs_verification",
    )


def append_note(existing: str, addition: str) -> str:
    existing = str(existing or "").strip()
    addition = str(addition or "").strip()

    if existing and addition:
        return f"{existing} {addition}"

    return existing or addition


def apply_import_approval_decisions(reviewed_rows: pd.DataFrame) -> pd.DataFrame:
    if reviewed_rows.empty:
        return reviewed_rows.copy()

    approved = reviewed_rows.copy()

    if "approval_status" not in approved.columns:
        approved["approval_status"] = "NEEDS IN-GAME CHECK"

    if "review_notes" not in approved.columns:
        approved["review_notes"] = ""

    if "verification_status" not in approved.columns:
        approved["verification_status"] = ""

    if "verification_notes" not in approved.columns:
        approved["verification_notes"] = ""

    for index, row in approved.iterrows():
        approval_status = str(row.get("approval_status", "") or "").strip().upper()
        review_notes = str(row.get("review_notes", "") or "").strip()
        verification_status = approval_verification_status(approval_status)

        approved.at[index, "verification_status"] = verification_status
        approved.at[index, "verification_notes"] = append_note(
            row.get("verification_notes", ""),
            f"Import approval: {approval_status}." + (f" {review_notes}" if review_notes else ""),
        )

    return approved.drop(
        columns=["approval_status", "review_notes"],
        errors="ignore",
    )


def append_ttk_import_approval_log(reviewed_rows: pd.DataFrame, weapon: str):
    if reviewed_rows.empty:
        return

    approval_log = load_ttk_import_approval_log()
    reviewed_at = datetime.now().isoformat(timespec="seconds")
    approved_rows = apply_import_approval_decisions(reviewed_rows)

    log_rows = []

    for index, row in reviewed_rows.iterrows():
        approved_row = approved_rows.loc[index] if index in approved_rows.index else row

        log_row = {
            "reviewed_at": reviewed_at,
            "weapon": weapon,
            "approval_status": row.get("approval_status", ""),
            "review_notes": row.get("review_notes", ""),
        }

        for column in ATTACHMENT_IMPORT_DATA_COLUMNS:
            log_row[column] = approved_row.get(column, row.get(column, ""))

        log_rows.append(log_row)

    updated = pd.concat([approval_log, pd.DataFrame(log_rows)], ignore_index=True)
    save_ttk_import_approval_log(updated)


def ensure_import_commit_log_store():
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if not IMPORT_COMMIT_LOG_PATH.exists():
        pd.DataFrame(columns=IMPORT_COMMIT_LOG_COLUMNS).to_csv(
            IMPORT_COMMIT_LOG_PATH,
            index=False,
        )


def load_ttk_import_commit_log() -> pd.DataFrame:
    ensure_import_commit_log_store()

    commit_log = pd.read_csv(IMPORT_COMMIT_LOG_PATH, dtype=str).fillna("")

    for column in IMPORT_COMMIT_LOG_COLUMNS:
        if column not in commit_log.columns:
            commit_log[column] = ""

    return commit_log[IMPORT_COMMIT_LOG_COLUMNS]


def save_ttk_import_commit_log(dataframe: pd.DataFrame):
    ensure_import_commit_log_store()
    updated = dataframe.copy()

    for column in IMPORT_COMMIT_LOG_COLUMNS:
        if column not in updated.columns:
            updated[column] = ""

    updated[IMPORT_COMMIT_LOG_COLUMNS].to_csv(
        IMPORT_COMMIT_LOG_PATH,
        index=False,
    )


def append_ttk_import_commit_log(row: dict):
    commit_log = load_ttk_import_commit_log()
    clean_row = {column: str(row.get(column, "")) for column in IMPORT_COMMIT_LOG_COLUMNS}
    updated = pd.concat([commit_log, pd.DataFrame([clean_row])], ignore_index=True)
    save_ttk_import_commit_log(updated)


def load_master_guns() -> pd.DataFrame:
    if MASTER_GUNS_PATH.exists():
        guns = pd.read_csv(MASTER_GUNS_PATH, dtype=str).fillna("")
    else:
        guns = pd.DataFrame(columns=PROFILED_GUN_COLUMNS)

    for column in PROFILED_GUN_COLUMNS:
        if column not in guns.columns:
            guns[column] = LEGACY_STATS_PROFILE if column == "stats_profile" else ""

    return guns[PROFILED_GUN_COLUMNS]


def save_master_guns(guns: pd.DataFrame):
    TTK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    updated = guns.copy()

    for column in PROFILED_GUN_COLUMNS:
        if column not in updated.columns:
            updated[column] = LEGACY_STATS_PROFILE if column == "stats_profile" else ""

    updated[PROFILED_GUN_COLUMNS].to_csv(MASTER_GUNS_PATH, index=False)


def upsert_profiled_gun_row(row: dict, replace_existing: bool = True) -> dict:
    guns = load_master_guns()
    clean_row = {column: str(row.get(column, "")) for column in PROFILED_GUN_COLUMNS}

    key_mask = (
        guns["gun_id"].fillna("").astype(str).str.strip().eq(clean_row["gun_id"])
        & guns["stats_profile"].fillna("").astype(str).str.strip().eq(clean_row["stats_profile"])
    )

    if key_mask.any() and not replace_existing:
        return {
            "written": False,
            "message": f"{clean_row['gun_name']} already has a {clean_row['stats_profile']} baseline row.",
        }

    backup_path = ""
    if MASTER_GUNS_PATH.exists() and key_mask.any():
        backup_path_obj = (
            MASTER_GUNS_PATH.parent
            / f"guns_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        guns.to_csv(backup_path_obj, index=False)
        backup_path = readable_csv_path(backup_path_obj)

    if key_mask.any():
        guns = guns[~key_mask].copy()

    updated = pd.concat([guns, pd.DataFrame([clean_row])], ignore_index=True)
    save_master_guns(updated)

    message = f"Saved {clean_row['stats_profile']} baseline for {clean_row['gun_name']}."
    if backup_path:
        message += f" Backup created: {backup_path}."

    return {"written": True, "message": message}


def render_gun_baseline_bench(all_guns: pd.DataFrame, active_stats_profile: str):
    st.subheader("Profiled Gun Baseline")
    st.caption(
        f"Enter the base weapon numbers from the {active_stats_profile} details panel before adding attachments."
    )

    if all_guns.empty:
        st.warning("No source gun list exists yet.")
        return

    source = all_guns.copy()
    source["display"] = (
        source["gun_name"].astype(str)
        + " | "
        + source["weapon_class"].astype(str)
        + " | "
        + source["stats_profile"].astype(str)
    )

    selected_display = st.selectbox(
        "Weapon baseline source",
        source["display"].tolist(),
        key="gun_baseline_source",
        help="Use this only as a name/class seed. Replace the numbers with the current in-game profile values.",
    )

    seed = source[source["display"] == selected_display].iloc[0]
    cols = st.columns(3)

    with cols[0]:
        gun_name = st.text_input("Gun name", value=str(seed.get("gun_name", "")), key="gun_baseline_name")
        weapon_class = st.text_input("Weapon class", value=str(seed.get("weapon_class", "")), key="gun_baseline_class")
        damage_close = st.number_input("Close damage", value=safe_float(seed.get("damage_close", 0)), step=0.01, key="gun_baseline_damage_close")
        range_close = st.number_input("Close range m", value=safe_float(seed.get("range_close_m", 0)), step=0.01, key="gun_baseline_range_close")

    with cols[1]:
        damage_mid = st.number_input("Mid damage", value=safe_float(seed.get("damage_mid", 0)), step=0.01, key="gun_baseline_damage_mid")
        range_mid = st.number_input("Mid range m", value=safe_float(seed.get("range_mid_m", 0)), step=0.01, key="gun_baseline_range_mid")
        damage_long = st.number_input("Long damage", value=safe_float(seed.get("damage_long", 0)), step=0.01, key="gun_baseline_damage_long")
        fire_rate = st.number_input("Fire rate rpm", value=safe_float(seed.get("fire_rate_rpm", 0)), step=0.01, key="gun_baseline_fire_rate")

    with cols[2]:
        ads_ms = st.number_input("ADS ms", value=safe_float(seed.get("ads_ms", 0)), step=0.01, key="gun_baseline_ads")
        sprint_to_fire = st.number_input("Sprint to fire ms", value=safe_float(seed.get("sprint_to_fire_ms", 0)), step=0.01, key="gun_baseline_stf")
        recoil = st.number_input("Recoil", value=safe_float(seed.get("recoil", 0)), step=0.01, key="gun_baseline_recoil")
        bullet_velocity = st.number_input("Bullet velocity", value=safe_float(seed.get("bullet_velocity", 0)), step=0.01, key="gun_baseline_velocity")
        mag_size = st.number_input("Mag size", value=safe_float(seed.get("mag_size", 0)), step=1.0, key="gun_baseline_mag")

    gun_id = slugify_for_ttk(gun_name)

    preview_row = {
        "gun_id": gun_id,
        "gun_name": gun_name,
        "weapon_class": weapon_class,
        "stats_profile": active_stats_profile,
        "damage_close": damage_close,
        "range_close_m": range_close,
        "damage_mid": damage_mid,
        "range_mid_m": range_mid,
        "damage_long": damage_long,
        "fire_rate_rpm": fire_rate,
        "ads_ms": ads_ms,
        "sprint_to_fire_ms": sprint_to_fire,
        "recoil": recoil,
        "bullet_velocity": bullet_velocity,
        "mag_size": mag_size,
    }

    st.dataframe(pd.DataFrame([preview_row]), use_container_width=True, hide_index=True)

    if st.button("COMMIT BASELINE GUN ROW", type="primary", use_container_width=True, key="commit_gun_baseline_row"):
        result = upsert_profiled_gun_row(preview_row, replace_existing=True)

        if result["written"]:
            try:
                load_and_validate_ttk_data.clear()
            except Exception:
                pass
            st.success(result["message"])
        else:
            st.warning(result["message"])


def readable_csv_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def master_attachment_commit_columns(existing: pd.DataFrame, new_rows: pd.DataFrame) -> list[str]:
    columns: list[str] = []

    for dataframe in [existing, new_rows]:
        for column in dataframe.columns:
            if column not in columns:
                columns.append(column)

    return columns


def approved_attachment_rows_for_commit(reviewed_rows: pd.DataFrame) -> pd.DataFrame:
    if reviewed_rows.empty or "approval_status" not in reviewed_rows.columns:
        return pd.DataFrame()

    approved_mask = (
        reviewed_rows["approval_status"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .eq("APPROVE FOR MODEL")
    )

    approved_rows = reviewed_rows[approved_mask].copy()

    if approved_rows.empty:
        return approved_rows

    approved_rows = apply_import_approval_decisions(approved_rows)

    drop_columns = {
        "reviewed_at",
        "weapon",
        "approval_status",
        "review_notes",
        "commit_mode",
        "committed_at",
    }

    approved_rows = approved_rows.drop(
        columns=[column for column in drop_columns if column in approved_rows.columns],
        errors="ignore",
    )

    if "attachment_id" not in approved_rows.columns:
        return pd.DataFrame()

    approved_rows["attachment_id"] = approved_rows["attachment_id"].fillna("").astype(str).str.strip()
    if "stats_profile" not in approved_rows.columns:
        approved_rows["stats_profile"] = LEGACY_STATS_PROFILE
    approved_rows["stats_profile"] = approved_rows["stats_profile"].fillna("").astype(str).str.strip()
    approved_rows = approved_rows[approved_rows["attachment_id"] != ""]
    approved_rows = approved_rows.drop_duplicates(subset=["stats_profile", "attachment_id"], keep="last")

    return approved_rows


def commit_approved_attachment_rows(
    reviewed_rows: pd.DataFrame,
    weapon: str,
    replace_existing: bool = False,
) -> dict:
    TTK_DATA_DIR.mkdir(parents=True, exist_ok=True)

    approved_rows = approved_attachment_rows_for_commit(reviewed_rows)
    approved_count = len(approved_rows)

    result = {
        "approved_rows": approved_count,
        "rows_committed": 0,
        "rows_skipped": 0,
        "backup_path": "",
        "message": "",
    }

    if approved_rows.empty:
        result["message"] = "No APPROVE FOR MODEL rows were available to commit."
        return result

    if MASTER_ATTACHMENTS_PATH.exists():
        existing = pd.read_csv(MASTER_ATTACHMENTS_PATH, dtype=str).fillna("")
    else:
        existing = pd.DataFrame()

    if "attachment_id" in existing.columns:
        existing["attachment_id"] = existing["attachment_id"].fillna("").astype(str).str.strip()
    else:
        existing["attachment_id"] = ""

    if "stats_profile" not in existing.columns:
        existing["stats_profile"] = LEGACY_STATS_PROFILE

    existing["stats_profile"] = existing["stats_profile"].fillna("").astype(str).str.strip()

    approved_rows["_profile_attachment_key"] = (
        approved_rows["stats_profile"].astype(str) + "::" + approved_rows["attachment_id"].astype(str)
    )
    existing["_profile_attachment_key"] = (
        existing["stats_profile"].astype(str) + "::" + existing["attachment_id"].astype(str)
    )

    approved_ids = set(approved_rows["_profile_attachment_key"].astype(str))
    existing_ids = set(existing["_profile_attachment_key"].astype(str)) if not existing.empty else set()

    if replace_existing:
        retained_existing = existing[~existing["_profile_attachment_key"].isin(approved_ids)].copy()
        rows_to_commit = approved_rows.copy()
        skipped = 0
        commit_mode = "REPLACE MATCHING PROFILE IDS"
    else:
        rows_to_commit = approved_rows[~approved_rows["_profile_attachment_key"].isin(existing_ids)].copy()
        retained_existing = existing.copy()
        skipped = approved_count - len(rows_to_commit)
        commit_mode = "APPEND NEW PROFILE IDS ONLY"

    retained_existing = retained_existing.drop(columns=["_profile_attachment_key"], errors="ignore")
    rows_to_commit = rows_to_commit.drop(columns=["_profile_attachment_key"], errors="ignore")

    result["rows_skipped"] = skipped

    if rows_to_commit.empty:
        result["message"] = "All approved rows already exist in attachments.csv. Nothing was written."
        append_ttk_import_commit_log(
            {
                "committed_at": datetime.now().isoformat(timespec="seconds"),
                "weapon": weapon,
                "commit_mode": commit_mode,
                "approved_rows": approved_count,
                "rows_committed": 0,
                "rows_skipped": skipped,
                "backup_path": "",
                "notes": result["message"],
            }
        )
        return result

    backup_path = ""

    if MASTER_ATTACHMENTS_PATH.exists():
        backup_path_obj = (
            MASTER_ATTACHMENTS_PATH.parent
            / f"attachments_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        existing.to_csv(backup_path_obj, index=False)
        backup_path = readable_csv_path(backup_path_obj)

    columns = master_attachment_commit_columns(retained_existing, rows_to_commit)
    retained_existing = retained_existing.reindex(columns=columns, fill_value="")
    rows_to_commit = rows_to_commit.reindex(columns=columns, fill_value="")

    updated = pd.concat([retained_existing, rows_to_commit], ignore_index=True)
    updated.to_csv(MASTER_ATTACHMENTS_PATH, index=False)

    result["rows_committed"] = len(rows_to_commit)
    result["backup_path"] = backup_path
    result["message"] = (
        f"Committed {len(rows_to_commit)} approved attachment row(s) to "
        f"{readable_csv_path(MASTER_ATTACHMENTS_PATH)}."
    )

    append_ttk_import_commit_log(
        {
            "committed_at": datetime.now().isoformat(timespec="seconds"),
            "weapon": weapon,
            "commit_mode": commit_mode,
            "approved_rows": approved_count,
            "rows_committed": len(rows_to_commit),
            "rows_skipped": skipped,
            "backup_path": backup_path,
            "notes": result["message"],
        }
    )

    return result


def render_ttk_import_commit_log():
    st.subheader("Import Commit Log")
    st.caption(
        "Only APPROVE FOR MODEL rows can be written into the master Oracle attachment data."
    )

    commit_log = load_ttk_import_commit_log()

    if commit_log.empty:
        st.info("No approved import commits yet.")
        return

    st.dataframe(
        commit_log.sort_values("committed_at", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download import commit log CSV",
        data=commit_log.to_csv(index=False),
        file_name="ttk_import_commit_log.csv",
        mime="text/csv",
        use_container_width=True,
    )




def render_ttk_import_approval_log():
    st.subheader("Import Approval Log")
    st.caption(
        "This is the staging record. Attachments are only written when you press COMMIT APPROVED TO ORACLE."
    )

    approval_log = load_ttk_import_approval_log()

    if approval_log.empty:
        st.info("No import approvals banked yet.")
        return

    filter_cols = st.columns(3)

    with filter_cols[0]:
        weapons = ["All"] + sorted(
            weapon
            for weapon in approval_log["weapon"].dropna().astype(str).unique().tolist()
            if weapon.strip()
        )
        selected_weapon = st.selectbox(
            "Import weapon",
            weapons,
            key="import_approval_weapon_filter",
        )

    with filter_cols[1]:
        statuses = ["All"] + IMPORT_APPROVAL_STATUSES
        selected_status = st.selectbox(
            "Approval status",
            statuses,
            key="import_approval_status_filter",
        )

    with filter_cols[2]:
        show_blocked_only = st.checkbox(
            "Blocked only",
            value=False,
            key="import_approval_blocked_only",
        )

    visible = approval_log.copy()

    if selected_weapon != "All":
        visible = visible[visible["weapon"] == selected_weapon]

    if selected_status != "All":
        visible = visible[visible["approval_status"] == selected_status]

    if show_blocked_only:
        visible = visible[
            visible["verification_status"].str.lower().isin({"excluded", "unmodelled"})
        ]

    st.dataframe(
        visible[
            [
                "reviewed_at",
                "weapon",
                "attachment_name",
                "slot",
                "approval_status",
                "verification_status",
                "raw_stat_text",
                "review_notes",
                "verification_notes",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download import approval log CSV",
        data=approval_log.to_csv(index=False),
        file_name="ttk_import_approval_log.csv",
        mime="text/csv",
        use_container_width=True,
    )


def commander_eligible_from_verdict(verdict: str, kept_build: bool) -> str:
    if kept_build and verdict in {"FIELD TESTED", "FELT GOOD"}:
        return "TRUE"

    return "FALSE"


def build_single_field_test_row(
    *,
    best: pd.Series,
    context: dict,
    field_verdict: str,
    feel_rating: int,
    kept_build: bool,
    notes: str,
) -> dict:
    return {
        "tested_at": datetime.now().isoformat(timespec="seconds"),
        "source": "Single Weapon Lab",
        "loadout_type": "single_weapon",
        "weapon": best.get("gun_name", ""),
        "weapon_class": best.get("weapon_class", ""),
        "attachments": best.get("attachments", ""),
        "secondary_weapon": "",
        "secondary_class": "",
        "secondary_attachments": "",
        "mode_profile": context.get("mode_profile", ""),
        "stats_profile": context.get("stats_profile", ""),
        "attachment_budget": context.get("attachment_budget", ""),
        "attachment_count": context.get("attachment_count", ""),
        "optimiser_depth": context.get("optimiser_depth", ""),
        "slot_candidate_limit": context.get("slot_candidate_limit", ""),
        "enemy_health": context.get("enemy_health", ""),
        "fight_type": context.get("fight_type", ""),
        "build_goal": context.get("build_goal", ""),
        "raw_ttk_ms": format_stat(best.get("raw_ttk_ms", "")),
        "practical_ttk_ms": format_stat(best.get("practical_ttk_ms", "")),
        "oracle_score": format_stat(best.get("oracle_score", ""), 3),
        "field_verdict": field_verdict,
        "feel_rating": feel_rating,
        "kept_build": "TRUE" if kept_build else "FALSE",
        "commander_eligible": commander_eligible_from_verdict(field_verdict, kept_build),
        "notes": notes,
    }


def build_full_field_test_row(
    *,
    best: pd.Series,
    context: dict,
    field_verdict: str,
    feel_rating: int,
    kept_build: bool,
    notes: str,
) -> dict:
    return {
        "tested_at": datetime.now().isoformat(timespec="seconds"),
        "source": "Two-Weapon Loadout Lab",
        "loadout_type": "two_weapon_loadout",
        "weapon": best.get("primary_weapon", ""),
        "weapon_class": best.get("primary_class", ""),
        "attachments": best.get("primary_attachments", ""),
        "secondary_weapon": best.get("secondary_weapon", ""),
        "secondary_class": best.get("secondary_class", ""),
        "secondary_attachments": best.get("secondary_attachments", ""),
        "mode_profile": context.get("mode_profile", ""),
        "stats_profile": context.get("stats_profile", ""),
        "attachment_budget": context.get("attachment_budget", ""),
        "attachment_count": context.get("attachment_count", ""),
        "optimiser_depth": context.get("optimiser_depth", ""),
        "slot_candidate_limit": context.get("slot_candidate_limit", ""),
        "enemy_health": context.get("enemy_health", ""),
        "fight_type": context.get("fight_type", ""),
        "build_goal": context.get("build_goal", ""),
        "raw_ttk_ms": format_stat(best.get("primary_raw_ttk_ms", "")),
        "practical_ttk_ms": format_stat(best.get("primary_practical_ttk_ms", "")),
        "oracle_score": format_stat(best.get("full_loadout_score", ""), 3),
        "field_verdict": field_verdict,
        "feel_rating": feel_rating,
        "kept_build": "TRUE" if kept_build else "FALSE",
        "commander_eligible": commander_eligible_from_verdict(field_verdict, kept_build),
        "notes": notes,
    }


def render_single_field_test_form(best: pd.Series, context: dict):
    st.markdown("### Field Test Log")
    st.caption(
        "The Oracle can calculate a candidate. Only field testing can make it trusted."
    )

    with st.form("single_field_test_form"):
        form_cols = st.columns([1.1, 0.8, 0.8])

        with form_cols[0]:
            field_verdict = st.selectbox(
                "Field verdict",
                FIELD_TEST_VERDICTS,
                index=1 if "FELT GOOD" in FIELD_TEST_VERDICTS else 0,
                key="single_field_verdict",
            )

        with form_cols[1]:
            feel_rating = st.slider(
                "Feel rating",
                min_value=1,
                max_value=10,
                value=7,
                key="single_feel_rating",
            )

        with form_cols[2]:
            kept_build = st.checkbox(
                "Keep as trusted candidate",
                value=True,
                key="single_kept_build",
            )

        notes = st.text_area(
            "Lab notes",
            value="",
            height=80,
            key="single_field_notes",
            placeholder="What happened in-game? Recoil, handling, range, consistency, panic fights.",
        )

        submitted = st.form_submit_button(
            "LOG FIELD TEST",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        append_ttk_field_test(
            build_single_field_test_row(
                best=best,
                context=context,
                field_verdict=field_verdict,
                feel_rating=feel_rating,
                kept_build=kept_build,
                notes=notes,
            )
        )
        st.success("Field test banked. The lab now has a reality check.")


def render_full_field_test_form(best: pd.Series, context: dict):
    st.markdown("### Field Test Log")
    st.caption(
        "Two-weapon loadouts are not trusted until the field test says they survive contact."
    )

    with st.form("full_field_test_form"):
        form_cols = st.columns([1.1, 0.8, 0.8])

        with form_cols[0]:
            field_verdict = st.selectbox(
                "Field verdict",
                FIELD_TEST_VERDICTS,
                index=1 if "FELT GOOD" in FIELD_TEST_VERDICTS else 0,
                key="full_field_verdict",
            )

        with form_cols[1]:
            feel_rating = st.slider(
                "Feel rating",
                min_value=1,
                max_value=10,
                value=7,
                key="full_feel_rating",
            )

        with form_cols[2]:
            kept_build = st.checkbox(
                "Keep as trusted candidate",
                value=True,
                key="full_kept_build",
            )

        notes = st.text_area(
            "Lab notes",
            value="",
            height=80,
            key="full_field_notes",
            placeholder="Did the pairing work? Did the secondary save you? Did the primary actually hold range?",
        )

        submitted = st.form_submit_button(
            "LOG FIELD TEST",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        append_ttk_field_test(
            build_full_field_test_row(
                best=best,
                context=context,
                field_verdict=field_verdict,
                feel_rating=feel_rating,
                kept_build=kept_build,
                notes=notes,
            )
        )
        st.success("Field test banked. Model output now has field evidence.")


def render_ttk_field_test_log():
    st.subheader("Field Test Log")
    st.caption(
        "Model output is lab work. Field-tested rows are the only builds that can become trusted later."
    )

    field_log = load_ttk_field_test_log()

    if field_log.empty:
        st.info("No field tests logged yet. Optimise a candidate, play it, then bank the result.")
        return

    visible = field_log.copy()

    filter_cols = st.columns(4)

    with filter_cols[0]:
        verdicts = ["All"] + FIELD_TEST_VERDICTS
        selected_verdict = st.selectbox(
            "Verdict filter",
            verdicts,
            key="field_log_verdict_filter",
        )

    with filter_cols[1]:
        weapons = ["All"] + sorted(
            weapon for weapon in visible["weapon"].dropna().astype(str).unique().tolist()
            if weapon.strip()
        )
        selected_weapon = st.selectbox(
            "Weapon filter",
            weapons,
            key="field_log_weapon_filter",
        )

    with filter_cols[2]:
        eligible_only = st.checkbox(
            "Commander-eligible only",
            value=False,
            key="field_log_eligible_only",
        )

    with filter_cols[3]:
        kept_only = st.checkbox(
            "Kept only",
            value=False,
            key="field_log_kept_only",
        )

    if selected_verdict != "All":
        visible = visible[visible["field_verdict"].eq(selected_verdict)]

    if selected_weapon != "All":
        visible = visible[visible["weapon"].eq(selected_weapon)]

    if eligible_only:
        visible = visible[visible["commander_eligible"].str.upper().eq("TRUE")]

    if kept_only:
        visible = visible[visible["kept_build"].str.upper().eq("TRUE")]

    display_columns = [
        "tested_at",
        "field_verdict",
        "feel_rating",
        "commander_eligible",
        "weapon",
        "attachments",
        "secondary_weapon",
        "secondary_attachments",
        "mode_profile",
        "stats_profile",
        "attachment_budget",
        "attachment_count",
        "enemy_health",
        "fight_type",
        "build_goal",
        "oracle_score",
        "raw_ttk_ms",
        "practical_ttk_ms",
        "notes",
    ]

    st.dataframe(
        visible[display_columns],
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download field test log CSV",
        data=field_log.to_csv(index=False),
        file_name="ttk_field_test_log.csv",
        mime="text/csv",
        use_container_width=True,
    )


def format_stat(value, decimals: int = 0) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:.{decimals}f}"


def boolish(value) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def available_columns(dataframe: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if column in dataframe.columns]


def shotgun_truth_columns(prefix: str = "") -> list[str]:
    return [
        f"{prefix}shotgun_truth_score",
        f"{prefix}shotgun_one_shot_potential",
        f"{prefix}shotgun_two_shot_consistency",
        f"{prefix}shotgun_range_coverage",
        f"{prefix}shotgun_handling_index",
        f"{prefix}shotgun_mag_safety",
        f"{prefix}shotgun_truth_note",
    ]


def render_shotgun_truth_panel(row, prefix: str = ""):
    is_shotgun_key = f"{prefix}is_shotgun"
    is_shotgun = boolish(row.get(is_shotgun_key, ""))

    if not is_shotgun:
        return

    score = row.get(f"{prefix}shotgun_truth_score", "")
    one_shot = row.get(f"{prefix}shotgun_one_shot_potential", "")
    two_shot = row.get(f"{prefix}shotgun_two_shot_consistency", "")
    range_coverage = row.get(f"{prefix}shotgun_range_coverage", "")
    handling_index = row.get(f"{prefix}shotgun_handling_index", "")
    mag_safety = row.get(f"{prefix}shotgun_mag_safety", "")
    note = str(row.get(f"{prefix}shotgun_truth_note", "") or "").strip()

    st.markdown("#### Shotgun Truth Model")
    cols = st.columns(5)
    cols[0].metric("Truth Score", format_stat(score, 3) or "n/a")
    cols[1].metric("One-Shot", str(one_shot or "n/a"))
    cols[2].metric("Two-Shot", str(two_shot or "n/a"))
    cols[3].metric("Range Cover", format_stat(range_coverage, 2) or "n/a")
    cols[4].metric("Mag Safety", format_stat(mag_safety, 2) or "n/a")

    st.caption(
        f"Handling index: {format_stat(handling_index, 2) or 'n/a'}. "
        "Shotgun outputs are data-limited until field tested."
    )

    if note:
        st.warning(note)


def render_loadout_role_panel(best: pd.Series):
    verdict = str(best.get("loadout_role_verdict", "") or "").strip()
    primary_label = str(best.get("primary_role_label", "") or "").strip()
    secondary_label = str(best.get("secondary_role_label", "") or "").strip()

    if not verdict and not primary_label and not secondary_label:
        return

    st.markdown("### Role Verdict")

    cols = st.columns(4)
    cols[0].metric("Role Balance", format_stat(best.get("role_balance_score", ""), 3) or "n/a")
    cols[1].metric("Primary Role", primary_label or "n/a")
    cols[2].metric("Primary Score", format_stat(best.get("primary_role_score", ""), 3) or "n/a")
    cols[3].metric("Secondary Score", format_stat(best.get("secondary_role_score", ""), 3) or "n/a")

    cols = st.columns(2)
    cols[0].metric("Secondary Role", secondary_label or "n/a")
    cols[1].metric("Loadout Score", format_stat(best.get("full_loadout_score", ""), 3) or "n/a")

    if verdict:
        st.info(verdict)


def normalise_match_text(value) -> str:
    return str(value or "").strip().lower()


def normalise_match_number(value) -> str:
    try:
        return str(int(float(str(value or "").strip())))
    except (TypeError, ValueError):
        return str(value or "").strip()


def normalise_attachment_key(value) -> str:
    parts = [
        part.strip().lower()
        for part in str(value or "").split("|")
        if part.strip()
    ]
    return " | ".join(sorted(parts))


def latest_matching_field_test(field_log: pd.DataFrame, criteria: dict) -> dict:
    if field_log.empty:
        return {}

    visible = field_log.copy()

    for column in FIELD_TEST_COLUMNS:
        if column not in visible.columns:
            visible[column] = ""

    for column, expected in criteria.items():
        if column not in visible.columns:
            return {}

        if column in {"attachments", "secondary_attachments"}:
            expected_key = normalise_attachment_key(expected)
            visible = visible[
                visible[column].apply(normalise_attachment_key).eq(expected_key)
            ]
        elif column in {"enemy_health", "attachment_count"}:
            expected_key = normalise_match_number(expected)
            visible = visible[
                visible[column].apply(normalise_match_number).eq(expected_key)
            ]
        else:
            expected_key = normalise_match_text(expected)
            visible = visible[
                visible[column].apply(normalise_match_text).eq(expected_key)
            ]

        if visible.empty:
            return {}

    visible = visible.sort_values("tested_at")
    return visible.iloc[-1].to_dict()


def confidence_from_field_row(field_row: dict) -> dict:
    if not field_row:
        return {
            "confidence": "MODELLED",
            "field_verdict": "",
            "feel_rating": "",
            "kept_build": "",
            "tested_at": "",
            "summary": "The maths supports this candidate, but no field test has been logged.",
        }

    verdict = str(field_row.get("field_verdict", "") or "").strip().upper()
    kept_build = str(field_row.get("kept_build", "") or "").strip().upper() == "TRUE"

    if verdict in {"REJECTED", "FELT BAD"}:
        confidence = "REJECTED"
        summary = "A field test rejected this candidate. Keep it visible, but do not trust it."
    elif verdict == "DATA SUSPECT":
        confidence = "DATA SUSPECT"
        summary = "A field test flagged the data or in-game feel as questionable."
    elif verdict == "FIELD TESTED":
        confidence = "FIELD TESTED"
        summary = "This candidate has field evidence."
    elif verdict == "FELT GOOD":
        confidence = "FELT GOOD"
        summary = "This candidate felt good in-game and is worth keeping in the lab."
    else:
        confidence = "MODELLED"
        summary = "The maths supports this candidate, but the latest field row is not a final approval."

    if confidence in {"FIELD TESTED", "FELT GOOD"} and not kept_build:
        summary += " It was not marked as kept, so it is not Commander-eligible."

    return {
        "confidence": confidence,
        "field_verdict": verdict,
        "feel_rating": field_row.get("feel_rating", ""),
        "kept_build": field_row.get("kept_build", ""),
        "tested_at": field_row.get("tested_at", ""),
        "summary": summary,
    }


def single_build_confidence(best: pd.Series, context: dict, field_log: pd.DataFrame | None = None) -> dict:
    field_log = load_ttk_field_test_log() if field_log is None else field_log

    match = latest_matching_field_test(
        field_log,
        {
            "loadout_type": "single_weapon",
            "weapon": best.get("gun_name", ""),
            "attachments": best.get("attachments", ""),
            "mode_profile": context.get("mode_profile", ""),
            "attachment_count": context.get("attachment_count", ""),
            "enemy_health": context.get("enemy_health", ""),
            "fight_type": context.get("fight_type", ""),
            "build_goal": context.get("build_goal", ""),
        },
    )

    return confidence_from_field_row(match)


def full_loadout_confidence(best: pd.Series, context: dict, field_log: pd.DataFrame | None = None) -> dict:
    field_log = load_ttk_field_test_log() if field_log is None else field_log

    match = latest_matching_field_test(
        field_log,
        {
            "loadout_type": "two_weapon_loadout",
            "weapon": best.get("primary_weapon", ""),
            "attachments": best.get("primary_attachments", ""),
            "secondary_weapon": best.get("secondary_weapon", ""),
            "secondary_attachments": best.get("secondary_attachments", ""),
            "mode_profile": context.get("mode_profile", ""),
            "attachment_count": context.get("attachment_count", ""),
            "enemy_health": context.get("enemy_health", ""),
            "fight_type": context.get("fight_type", ""),
            "build_goal": context.get("build_goal", ""),
        },
    )

    return confidence_from_field_row(match)


def render_confidence_badge(confidence: dict):
    label = confidence.get("confidence", "MODELLED")
    detail = confidence.get("summary", "")

    suffix_parts = []
    if confidence.get("field_verdict"):
        suffix_parts.append(f"Field verdict: {confidence['field_verdict']}")
    if confidence.get("feel_rating"):
        suffix_parts.append(f"Feel: {confidence['feel_rating']}/10")
    if confidence.get("tested_at"):
        suffix_parts.append(f"Tested: {confidence['tested_at']}")

    message = f"**Confidence: {label}.** {detail}"
    if suffix_parts:
        message = f"{message} {' | '.join(suffix_parts)}"

    if label in {"FIELD TESTED", "FELT GOOD"}:
        st.success(message)
    elif label == "REJECTED":
        st.error(message)
    elif label == "DATA SUSPECT":
        st.warning(message)
    else:
        st.info(message)


def annotate_single_results_with_confidence(results: pd.DataFrame, context: dict) -> pd.DataFrame:
    if results.empty:
        return results

    field_log = load_ttk_field_test_log()
    annotated = results.copy()
    confidence_rows = []

    for _, row in annotated.iterrows():
        confidence_rows.append(single_build_confidence(row, context, field_log))

    annotated["confidence"] = [item.get("confidence", "MODELLED") for item in confidence_rows]
    annotated["field_verdict"] = [item.get("field_verdict", "") for item in confidence_rows]
    annotated["field_feel_rating"] = [item.get("feel_rating", "") for item in confidence_rows]
    annotated["field_tested_at"] = [item.get("tested_at", "") for item in confidence_rows]

    return annotated


def annotate_full_results_with_confidence(results: pd.DataFrame, context: dict) -> pd.DataFrame:
    if results.empty:
        return results

    field_log = load_ttk_field_test_log()
    annotated = results.copy()
    confidence_rows = []

    for _, row in annotated.iterrows():
        confidence_rows.append(full_loadout_confidence(row, context, field_log))

    annotated["confidence"] = [item.get("confidence", "MODELLED") for item in confidence_rows]
    annotated["field_verdict"] = [item.get("field_verdict", "") for item in confidence_rows]
    annotated["field_feel_rating"] = [item.get("feel_rating", "") for item in confidence_rows]
    annotated["field_tested_at"] = [item.get("tested_at", "") for item in confidence_rows]

    return annotated


def filter_candidate_results(results: pd.DataFrame, trust_filter: str) -> pd.DataFrame:
    if results.empty or "confidence" not in results.columns:
        return results

    filtered = results.copy()
    confidence = filtered["confidence"].fillna("MODELLED").astype(str).str.upper().str.strip()
    verdict = filtered.get("field_verdict", pd.Series([""] * len(filtered), index=filtered.index))
    verdict = verdict.fillna("").astype(str).str.upper().str.strip()

    rejected = confidence.eq("REJECTED") | verdict.eq("REJECTED")
    approved = confidence.isin(FIELD_APPROVED_CONFIDENCE)
    logged = confidence.isin(FIELD_LOGGED_CONFIDENCE) | verdict.ne("")
    modelled_only = confidence.eq("MODELLED") & verdict.eq("")

    if trust_filter == "SHOW ALL LAB CANDIDATES":
        return filtered

    if trust_filter == "FIELD TESTED ONLY":
        return filtered[approved].copy()

    if trust_filter == "TESTED AND NOT REJECTED":
        return filtered[logged & ~rejected].copy()

    if trust_filter == "UNTESTED MODELLED ONLY":
        return filtered[modelled_only].copy()

    return filtered[~rejected].copy()


def render_candidate_filter_summary(results: pd.DataFrame, visible_results: pd.DataFrame, trust_filter: str):
    hidden_count = max(0, len(results) - len(visible_results))

    st.caption(
        f"Candidate filter: {trust_filter}. "
        f"Showing {len(visible_results)} of {len(results)} candidate(s)."
    )

    if hidden_count:
        st.caption(f"{hidden_count} candidate(s) hidden by the current trust filter.")


def selected_perk_rows(perk_package: str) -> dict:
    perks = PERK_PACKAGES.get(perk_package, {})
    return {
        "perk_package": perk_package,
        "perk_1": perks.get("perk_1", ""),
        "perk_2": perks.get("perk_2", ""),
        "perk_3": perks.get("perk_3", ""),
        "perk_4": perks.get("perk_4", ""),
    }


def build_saved_single_weapon_row(best: pd.Series, context: dict, save_name: str, notes: str, favourite: bool, used_in_video: bool) -> dict:
    perk_data = selected_perk_rows(context.get("perk_package", ""))

    return {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "save_name": save_name,
        "source": "Commander Weapon Optimiser",
        "mode_profile": context.get("mode_profile", ""),
        "stats_profile": context.get("stats_profile", ""),
        "enemy_health": context.get("enemy_health", ""),
        "fight_type": context.get("fight_type", ""),
        "build_goal": context.get("build_goal", ""),
        "loadout_type": "single_weapon",
        "attachment_count": context.get("attachment_count", ""),
        "optimiser_depth": context.get("optimiser_depth", ""),
        "slot_candidate_limit": context.get("slot_candidate_limit", ""),
        "primary_weapon": best.get("gun_name", ""),
        "primary_class": best.get("weapon_class", ""),
        "primary_attachments": best.get("attachments", ""),
        "primary_slots": best.get("slots", ""),
        "primary_raw_ttk_ms": format_stat(best.get("raw_ttk_ms", "")),
        "primary_practical_ttk_ms": format_stat(best.get("practical_ttk_ms", "")),
        "primary_ads_ms": format_stat(best.get("ads_ms", "")),
        "primary_sprint_to_fire_ms": format_stat(best.get("sprint_to_fire_ms", "")),
        "primary_recoil": format_stat(best.get("recoil", ""), 2),
        "secondary_weapon": "",
        "secondary_class": "",
        "secondary_attachments": "",
        "secondary_slots": "",
        "secondary_raw_ttk_ms": "",
        "secondary_practical_ttk_ms": "",
        "secondary_ads_ms": "",
        "secondary_sprint_to_fire_ms": "",
        "secondary_recoil": "",
        **perk_data,
        "notes": notes,
        "favourite": "TRUE" if favourite else "FALSE",
        "used_in_video": "TRUE" if used_in_video else "FALSE",
        "archived": "FALSE",
    }


def build_saved_full_loadout_row(best: pd.Series, context: dict, save_name: str, notes: str, favourite: bool, used_in_video: bool) -> dict:
    perk_package = best.get("perk_package", context.get("perk_package", ""))
    perk_data = selected_perk_rows(perk_package)

    return {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "save_name": save_name,
        "source": "Full Loadout Optimiser",
        "mode_profile": context.get("mode_profile", ""),
        "stats_profile": context.get("stats_profile", ""),
        "enemy_health": context.get("enemy_health", ""),
        "fight_type": context.get("fight_type", ""),
        "build_goal": context.get("build_goal", ""),
        "loadout_type": "two_weapon_loadout",
        "attachment_count": context.get("attachment_count", ""),
        "optimiser_depth": context.get("optimiser_depth", ""),
        "slot_candidate_limit": context.get("slot_candidate_limit", ""),
        "primary_weapon": best.get("primary_weapon", ""),
        "primary_class": best.get("primary_class", ""),
        "primary_attachments": best.get("primary_attachments", ""),
        "primary_slots": best.get("primary_slots", ""),
        "primary_raw_ttk_ms": format_stat(best.get("primary_raw_ttk_ms", "")),
        "primary_practical_ttk_ms": format_stat(best.get("primary_practical_ttk_ms", "")),
        "primary_ads_ms": format_stat(best.get("primary_ads_ms", "")),
        "primary_sprint_to_fire_ms": format_stat(best.get("primary_sprint_to_fire_ms", "")),
        "primary_recoil": format_stat(best.get("primary_recoil", ""), 2),
        "secondary_weapon": best.get("secondary_weapon", ""),
        "secondary_class": best.get("secondary_class", ""),
        "secondary_attachments": best.get("secondary_attachments", ""),
        "secondary_slots": best.get("secondary_slots", ""),
        "secondary_raw_ttk_ms": format_stat(best.get("secondary_raw_ttk_ms", "")),
        "secondary_practical_ttk_ms": format_stat(best.get("secondary_practical_ttk_ms", "")),
        "secondary_ads_ms": format_stat(best.get("secondary_ads_ms", "")),
        "secondary_sprint_to_fire_ms": format_stat(best.get("secondary_sprint_to_fire_ms", "")),
        "secondary_recoil": format_stat(best.get("secondary_recoil", ""), 2),
        **perk_data,
        "notes": notes,
        "favourite": "TRUE" if favourite else "FALSE",
        "used_in_video": "TRUE" if used_in_video else "FALSE",
        "archived": "FALSE",
    }


def render_keep_single_weapon_build(best: pd.Series, context: dict):
    st.markdown("### Keep This Build")

    default_name = (
        f"{best.get('gun_name', 'Weapon')} - "
        f"{context.get('fight_type', 'Fight')} - "
        f"{context.get('build_goal', 'Build')}"
    )

    keep_cols = st.columns([2, 1, 1])

    with keep_cols[0]:
        save_name = st.text_input(
            "Saved build name",
            value=default_name,
            key="keep_single_save_name",
        )

    with keep_cols[1]:
        favourite = st.checkbox(
            "Favourite",
            value=True,
            key="keep_single_favourite",
        )

    with keep_cols[2]:
        used_in_video = st.checkbox(
            "Video build",
            value=True,
            key="keep_single_video",
        )

    notes = st.text_area(
        "Notes",
        value="Commander-assigned weapon build. Keep if it felt good in-game.",
        height=80,
        key="keep_single_notes",
    )

    if st.button("💾 KEEP BUILD", type="primary", use_container_width=True, key="keep_single_button"):
        append_saved_ttk_loadout(
            build_saved_single_weapon_row(
                best=best,
                context=context,
                save_name=save_name,
                notes=notes,
                favourite=favourite,
                used_in_video=used_in_video,
            )
        )
        st.success(f"Saved build: {save_name}")


def render_keep_full_loadout(best: pd.Series, context: dict):
    st.markdown("### Keep This Loadout")

    default_name = (
        f"{best.get('primary_weapon', 'Primary')} + "
        f"{best.get('secondary_weapon', 'Secondary')} - "
        f"{context.get('fight_type', 'Fight')}"
    )

    keep_cols = st.columns([2, 1, 1])

    with keep_cols[0]:
        save_name = st.text_input(
            "Saved loadout name",
            value=default_name,
            key="keep_full_save_name",
        )

    with keep_cols[1]:
        favourite = st.checkbox(
            "Favourite",
            value=True,
            key="keep_full_favourite",
        )

    with keep_cols[2]:
        used_in_video = st.checkbox(
            "Video build",
            value=True,
            key="keep_full_video",
        )

    notes = st.text_area(
        "Notes",
        value="Full Oracle loadout with perks.",
        height=80,
        key="keep_full_notes",
    )

    if st.button("💾 KEEP LOADOUT", type="primary", use_container_width=True, key="keep_full_button"):
        append_saved_ttk_loadout(
            build_saved_full_loadout_row(
                best=best,
                context=context,
                save_name=save_name,
                notes=notes,
                favourite=favourite,
                used_in_video=used_in_video,
            )
        )
        st.success(f"Saved loadout: {save_name}")


def render_saved_ttk_loadouts():
    st.subheader("Saved Oracle Builds")

    saved = load_saved_ttk_loadouts()

    if saved.empty:
        st.info("No saved Oracle builds yet. Optimise a weapon or full loadout, then press KEEP.")
        return

    visible = saved[saved["archived"].str.upper().ne("TRUE")].copy()

    filter_cols = st.columns(4)

    with filter_cols[0]:
        weapons = ["All"] + sorted(
            {
                weapon
                for weapon in visible["primary_weapon"].dropna().astype(str).tolist()
                + visible["secondary_weapon"].dropna().astype(str).tolist()
                if weapon.strip()
            }
        )
        selected_weapon = st.selectbox("Weapon filter", weapons, key="saved_weapon_filter")

    with filter_cols[1]:
        loadout_types = ["All"] + sorted(
            [value for value in visible["loadout_type"].dropna().unique().tolist() if value]
        )
        selected_type = st.selectbox("Type filter", loadout_types, key="saved_type_filter")

    with filter_cols[2]:
        favourite_only = st.checkbox("Favourite only", value=False, key="saved_favourite_only")

    with filter_cols[3]:
        video_only = st.checkbox("Video builds only", value=False, key="saved_video_only")

    if selected_weapon != "All":
        visible = visible[
            visible["primary_weapon"].eq(selected_weapon)
            | visible["secondary_weapon"].eq(selected_weapon)
        ]

    if selected_type != "All":
        visible = visible[visible["loadout_type"].eq(selected_type)]

    if favourite_only:
        visible = visible[visible["favourite"].str.upper().eq("TRUE")]

    if video_only:
        visible = visible[visible["used_in_video"].str.upper().eq("TRUE")]

    display_columns = [
        "saved_at",
        "save_name",
        "loadout_type",
        "mode_profile",
        "enemy_health",
        "primary_weapon",
        "primary_attachments",
        "secondary_weapon",
        "secondary_attachments",
        "perk_package",
        "perk_1",
        "perk_2",
        "perk_3",
        "perk_4",
        "favourite",
        "used_in_video",
        "notes",
    ]

    st.dataframe(
        visible[display_columns],
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download saved loadouts CSV",
        data=saved.to_csv(index=False),
        file_name="saved_ttk_loadouts.csv",
        mime="text/csv",
        use_container_width=True,
    )


def render_single_weapon_result(best: pd.Series, enemy_health: int, confidence: dict | None = None):
    st.markdown("### Optimised Assigned Weapon")

    depth_label = str(best.get("optimiser_mode", "") or "").strip()
    slot_limit = str(best.get("slot_candidate_limit", "") or "").strip()
    if depth_label:
        slot_text = f" | slot shortlist: {slot_limit}" if slot_limit else ""
        st.caption(f"Oracle depth: {depth_label}{slot_text}")

    if confidence:
        render_confidence_badge(confidence)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Weapon", best["gun_name"])
    col2.metric("Oracle Score", f"{best['oracle_score']:.3f}")
    col3.metric("Raw TTK", f"{best['raw_ttk_ms']:.0f} ms")
    col4.metric("Practical TTK", f"{best['practical_ttk_ms']:.0f} ms")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("ADS", f"{best['ads_ms']:.0f} ms")
    col2.metric("Sprint to Fire", f"{best['sprint_to_fire_ms']:.0f} ms")
    col3.metric("Recoil", f"{best['recoil']:.1f}")
    col4.metric("Damage / Mag", f"{best['damage_per_mag']:.0f}")

    render_shotgun_truth_panel(best)

    trust_note = str(best.get("attachment_trust_note", "") or "").strip()
    effect_note = str(best.get("attachment_effects", "") or "").strip()

    st.info(
        f"""
        **Why this build won:** the Oracle kept the Commander-assigned weapon locked to **{best['gun_name']}** and brute-forced legal attachment combinations for this scenario.  
        It ranked builds by raw TTK, practical TTK, recoil, handling, range, bullet velocity, and magazine value depending on the selected goal.  
        Shotguns also receive a separate truth score for one-shot potential, two-shot consistency, range coverage, and mag safety.  
        **Enemy health:** {enemy_health} HP.
        """
    )

    if trust_note:
        st.caption(f"Trust gate: {trust_note}")

    if effect_note:
        with st.expander("Modelled attachment effects", expanded=False):
            for item in effect_note.split(" || "):
                clean_item = item.strip()
                if clean_item:
                    st.write(f"- {clean_item}")

    st.markdown("### Copyable Commander Build")
    st.code(
        f"""
WEAPON: {best['gun_name']}
CLASS: {best['weapon_class']}

ATTACHMENTS:
{best['attachments']}

SLOTS:
{best['slots']}

RAW TTK: {best['raw_ttk_ms']:.0f} ms
PRACTICAL TTK: {best['practical_ttk_ms']:.0f} ms
        """.strip()
    )

    st.markdown("### Attachments")
    render_attachment_list(best["attachments"])


def render_full_loadout_result(full_loadout_results: pd.DataFrame, elapsed_seconds: float, enemy_health: int, confidence: dict | None = None):
    best = full_loadout_results.iloc[0]

    st.success(f"Loadout found in {elapsed_seconds:.2f} seconds.")

    depth_label = str(best.get("optimiser_mode", "") or "").strip()
    slot_limit = str(best.get("slot_candidate_limit", "") or "").strip()
    if depth_label:
        slot_text = f" | slot shortlist: {slot_limit}" if slot_limit else ""
        st.caption(f"Oracle depth: {depth_label}{slot_text}")

    st.markdown("### Optimum Loadout")

    if confidence:
        render_confidence_badge(confidence)

    st.caption(
        f"Primary role: {best['primary_fight_type']} / {best['primary_build_goal']} | "
        f"Secondary role: {best['secondary_fight_type']} / {best['secondary_build_goal']}"
    )

    render_loadout_role_panel(best)

    col1, col2, col3 = st.columns(3)
    col1.metric("Loadout Score", f"{best['full_loadout_score']:.3f}")
    col2.metric("Primary", best["primary_weapon"])
    col3.metric("Secondary", best["secondary_weapon"])

    st.markdown("### Why This Loadout Won")

    st.info(
        f"""
        **Scenario:** {best['map_type']} / {best['fight_type']}  
        **Enemy health:** {enemy_health} HP  
        **Pairing:** {best['loadout_pairing']}  
        **Primary importance:** {best['primary_weight'] * 100:.0f}%  
        **Secondary importance:** {best['secondary_weight'] * 100:.0f}%  
        **Role balance:** {float(best.get('role_balance_score', 0.0) or 0.0):.3f}  

        The primary weapon was optimised for **{best['primary_fight_type']} / {best['primary_build_goal']}**.  
        The secondary weapon was optimised for **{best['secondary_fight_type']} / {best['secondary_build_goal']}**.  
        The role verdict checks whether both halves of the loadout are doing separate jobs instead of chasing one blended score.
        """
    )

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Primary Build")
        st.write(f"**Weapon:** {best['primary_weapon']}")
        st.write(f"**Class:** {best['primary_class']}")
        st.write(f"**Raw TTK:** {best['primary_raw_ttk_ms']:.0f} ms")
        st.write(f"**Practical TTK:** {best['primary_practical_ttk_ms']:.0f} ms")
        st.write(f"**Recoil:** {best['primary_recoil']:.1f}")
        st.write(f"**ADS:** {best['primary_ads_ms']:.0f} ms")
        render_shotgun_truth_panel(best, prefix="primary_")
        st.markdown("**Attachments:**")
        render_attachment_list(best["primary_attachments"])

    with col2:
        st.markdown("### Secondary Build")
        st.write(f"**Weapon:** {best['secondary_weapon']}")
        st.write(f"**Class:** {best['secondary_class']}")
        st.write(f"**Raw TTK:** {best['secondary_raw_ttk_ms']:.0f} ms")
        st.write(f"**Practical TTK:** {best['secondary_practical_ttk_ms']:.0f} ms")
        st.write(f"**Recoil:** {best['secondary_recoil']:.1f}")
        st.write(f"**ADS:** {best['secondary_ads_ms']:.0f} ms")
        render_shotgun_truth_panel(best, prefix="secondary_")
        st.markdown("**Attachments:**")
        render_attachment_list(best["secondary_attachments"])

    st.divider()

    st.markdown("### Perks")
    selected_perks = PERK_PACKAGES[best["perk_package"]]

    st.write(f"**Package:** {best['perk_package']}")
    st.write(f"- Perk 1: {selected_perks['perk_1']}")
    st.write(f"- Perk 2: {selected_perks['perk_2']}")
    st.write(f"- Perk 3: {selected_perks['perk_3']}")
    st.write(f"- Perk 4: {selected_perks['perk_4']}")

    st.markdown("### Copyable Loadout")

    st.code(
        f"""
PRIMARY: {best['primary_weapon']}
{best['primary_attachments']}

SECONDARY: {best['secondary_weapon']}
{best['secondary_attachments']}

PERKS:
{selected_perks['perk_1']}
{selected_perks['perk_2']}
{selected_perks['perk_3']}
{selected_perks['perk_4']}

SCENARIO:
{best['map_type']} / {best['fight_type']}
Enemy Health: {enemy_health}
        """.strip()
    )



def numeric_compare_value(value) -> float | None:
    try:
        if value is None:
            return None
        text = str(value).strip().replace(",", "")
        if text == "":
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def format_compare_value(value, suffix: str = "", decimals: int = 0) -> str:
    number = numeric_compare_value(value)
    if number is None:
        return "n/a"

    if decimals <= 0:
        return f"{number:.0f}{suffix}"

    return f"{number:.{decimals}f}{suffix}"


def confidence_rank(label: str) -> int:
    ranks = {
        "REJECTED": 0,
        "DATA SUSPECT": 1,
        "MODELLED": 2,
        "FELT GOOD": 3,
        "FIELD TESTED": 4,
    }
    return ranks.get(str(label or "").strip().upper(), 2)


def compare_metric_line(
    *,
    label: str,
    a_value,
    b_value,
    lower_is_better: bool,
    suffix: str = "",
    decimals: int = 0,
) -> dict:
    a_number = numeric_compare_value(a_value)
    b_number = numeric_compare_value(b_value)

    if a_number is None or b_number is None:
        winner = "No call"
        delta = "n/a"
    else:
        difference = a_number - b_number

        if abs(difference) < 0.0001:
            winner = "Tie"
            delta = "0"

        elif lower_is_better:
            winner = "A" if difference < 0 else "B"
            delta = f"{abs(difference):.{decimals}f}{suffix}" if decimals else f"{abs(difference):.0f}{suffix}"

        else:
            winner = "A" if difference > 0 else "B"
            delta = f"{abs(difference):.{decimals}f}{suffix}" if decimals else f"{abs(difference):.0f}{suffix}"

    return {
        "Metric": label,
        "A": format_compare_value(a_value, suffix, decimals),
        "B": format_compare_value(b_value, suffix, decimals),
        "Winner": winner,
        "Gap": delta,
    }


def compare_confidence_line(a_confidence: str, b_confidence: str) -> dict:
    a_rank = confidence_rank(a_confidence)
    b_rank = confidence_rank(b_confidence)

    if a_rank == b_rank:
        winner = "Tie"
    else:
        winner = "A" if a_rank > b_rank else "B"

    return {
        "Metric": "Confidence",
        "A": a_confidence or "MODELLED",
        "B": b_confidence or "MODELLED",
        "Winner": winner,
        "Gap": "trust",
    }


def candidate_label(prefix: str, index: int, row: pd.Series, weapon_columns: list[str]) -> str:
    weapons = [
        str(row.get(column, "") or "").strip()
        for column in weapon_columns
        if str(row.get(column, "") or "").strip()
    ]

    weapon_text = " + ".join(weapons) if weapons else "Candidate"
    confidence = str(row.get("confidence", "MODELLED") or "MODELLED")
    practical = row.get("practical_ttk_ms", row.get("primary_practical_ttk_ms", ""))
    score = row.get("oracle_score", row.get("full_loadout_score", ""))

    if numeric_compare_value(practical) is not None:
        stat = f"{format_compare_value(practical, 'ms')} practical"
    elif numeric_compare_value(score) is not None:
        stat = f"{format_compare_value(score, '', 3)} score"
    else:
        stat = "unscored"

    return f"{prefix}{index + 1}: {weapon_text} | {confidence} | {stat}"


def build_single_compare_pool(last_single_build: dict, trust_filter: str) -> pd.DataFrame:
    if not last_single_build:
        return pd.DataFrame()

    results = last_single_build.get("top_results", pd.DataFrame())

    if results is None or results.empty:
        stored_result = last_single_build.get("result", {})
        results = pd.DataFrame([stored_result]) if stored_result else pd.DataFrame()

    if results.empty:
        return results

    annotated = annotate_single_results_with_confidence(results, last_single_build)
    return filter_candidate_results(annotated, trust_filter)


def build_full_compare_pool(last_full_loadout: dict, trust_filter: str) -> pd.DataFrame:
    if not last_full_loadout:
        return pd.DataFrame()

    results = last_full_loadout.get("top_results", pd.DataFrame())

    if results is None or results.empty:
        stored_result = last_full_loadout.get("result", {})
        results = pd.DataFrame([stored_result]) if stored_result else pd.DataFrame()

    if results.empty:
        return results

    annotated = annotate_full_results_with_confidence(results, last_full_loadout)
    return filter_candidate_results(annotated, trust_filter)


def build_single_compare_table(candidate_a: pd.Series, candidate_b: pd.Series) -> pd.DataFrame:
    rows = [
        compare_confidence_line(
            str(candidate_a.get("confidence", "MODELLED")),
            str(candidate_b.get("confidence", "MODELLED")),
        ),
        compare_metric_line(
            label="Oracle score",
            a_value=candidate_a.get("oracle_score", ""),
            b_value=candidate_b.get("oracle_score", ""),
            lower_is_better=False,
            decimals=3,
        ),
        compare_metric_line(
            label="Raw TTK",
            a_value=candidate_a.get("raw_ttk_ms", ""),
            b_value=candidate_b.get("raw_ttk_ms", ""),
            lower_is_better=True,
            suffix="ms",
        ),
        compare_metric_line(
            label="Practical TTK",
            a_value=candidate_a.get("practical_ttk_ms", ""),
            b_value=candidate_b.get("practical_ttk_ms", ""),
            lower_is_better=True,
            suffix="ms",
        ),
        compare_metric_line(
            label="ADS",
            a_value=candidate_a.get("ads_ms", ""),
            b_value=candidate_b.get("ads_ms", ""),
            lower_is_better=True,
            suffix="ms",
        ),
        compare_metric_line(
            label="Sprint to fire",
            a_value=candidate_a.get("sprint_to_fire_ms", ""),
            b_value=candidate_b.get("sprint_to_fire_ms", ""),
            lower_is_better=True,
            suffix="ms",
        ),
        compare_metric_line(
            label="Recoil",
            a_value=candidate_a.get("recoil", ""),
            b_value=candidate_b.get("recoil", ""),
            lower_is_better=True,
            decimals=2,
        ),
        compare_metric_line(
            label="Range",
            a_value=candidate_a.get("range_m", ""),
            b_value=candidate_b.get("range_m", ""),
            lower_is_better=False,
            suffix="m",
            decimals=1,
        ),
        compare_metric_line(
            label="Damage per mag",
            a_value=candidate_a.get("damage_per_mag", ""),
            b_value=candidate_b.get("damage_per_mag", ""),
            lower_is_better=False,
        ),
    ]

    if boolish(candidate_a.get("is_shotgun", "")) or boolish(candidate_b.get("is_shotgun", "")):
        rows.extend(
            [
                compare_metric_line(
                    label="Shotgun truth",
                    a_value=candidate_a.get("shotgun_truth_score", ""),
                    b_value=candidate_b.get("shotgun_truth_score", ""),
                    lower_is_better=False,
                    decimals=3,
                ),
                compare_metric_line(
                    label="Shotgun range cover",
                    a_value=candidate_a.get("shotgun_range_coverage", ""),
                    b_value=candidate_b.get("shotgun_range_coverage", ""),
                    lower_is_better=False,
                    decimals=2,
                ),
                compare_metric_line(
                    label="Shotgun mag safety",
                    a_value=candidate_a.get("shotgun_mag_safety", ""),
                    b_value=candidate_b.get("shotgun_mag_safety", ""),
                    lower_is_better=False,
                    decimals=2,
                ),
            ]
        )

    return pd.DataFrame(rows)


def build_full_compare_table(candidate_a: pd.Series, candidate_b: pd.Series) -> pd.DataFrame:
    rows = [
        compare_confidence_line(
            str(candidate_a.get("confidence", "MODELLED")),
            str(candidate_b.get("confidence", "MODELLED")),
        ),
        compare_metric_line(
            label="Loadout score",
            a_value=candidate_a.get("full_loadout_score", ""),
            b_value=candidate_b.get("full_loadout_score", ""),
            lower_is_better=False,
            decimals=3,
        ),
        compare_metric_line(
            label="Primary raw TTK",
            a_value=candidate_a.get("primary_raw_ttk_ms", ""),
            b_value=candidate_b.get("primary_raw_ttk_ms", ""),
            lower_is_better=True,
            suffix="ms",
        ),
        compare_metric_line(
            label="Primary practical TTK",
            a_value=candidate_a.get("primary_practical_ttk_ms", ""),
            b_value=candidate_b.get("primary_practical_ttk_ms", ""),
            lower_is_better=True,
            suffix="ms",
        ),
        compare_metric_line(
            label="Primary ADS",
            a_value=candidate_a.get("primary_ads_ms", ""),
            b_value=candidate_b.get("primary_ads_ms", ""),
            lower_is_better=True,
            suffix="ms",
        ),
        compare_metric_line(
            label="Primary sprint to fire",
            a_value=candidate_a.get("primary_sprint_to_fire_ms", ""),
            b_value=candidate_b.get("primary_sprint_to_fire_ms", ""),
            lower_is_better=True,
            suffix="ms",
        ),
        compare_metric_line(
            label="Primary recoil",
            a_value=candidate_a.get("primary_recoil", ""),
            b_value=candidate_b.get("primary_recoil", ""),
            lower_is_better=True,
            decimals=2,
        ),
        compare_metric_line(
            label="Secondary raw TTK",
            a_value=candidate_a.get("secondary_raw_ttk_ms", ""),
            b_value=candidate_b.get("secondary_raw_ttk_ms", ""),
            lower_is_better=True,
            suffix="ms",
        ),
        compare_metric_line(
            label="Secondary practical TTK",
            a_value=candidate_a.get("secondary_practical_ttk_ms", ""),
            b_value=candidate_b.get("secondary_practical_ttk_ms", ""),
            lower_is_better=True,
            suffix="ms",
        ),
        compare_metric_line(
            label="Secondary ADS",
            a_value=candidate_a.get("secondary_ads_ms", ""),
            b_value=candidate_b.get("secondary_ads_ms", ""),
            lower_is_better=True,
            suffix="ms",
        ),
        compare_metric_line(
            label="Secondary sprint to fire",
            a_value=candidate_a.get("secondary_sprint_to_fire_ms", ""),
            b_value=candidate_b.get("secondary_sprint_to_fire_ms", ""),
            lower_is_better=True,
            suffix="ms",
        ),
        compare_metric_line(
            label="Secondary recoil",
            a_value=candidate_a.get("secondary_recoil", ""),
            b_value=candidate_b.get("secondary_recoil", ""),
            lower_is_better=True,
            decimals=2,
        ),
    ]

    if boolish(candidate_a.get("primary_is_shotgun", "")) or boolish(candidate_b.get("primary_is_shotgun", "")):
        rows.append(
            compare_metric_line(
                label="Primary shotgun truth",
                a_value=candidate_a.get("primary_shotgun_truth_score", ""),
                b_value=candidate_b.get("primary_shotgun_truth_score", ""),
                lower_is_better=False,
                decimals=3,
            )
        )

    if boolish(candidate_a.get("secondary_is_shotgun", "")) or boolish(candidate_b.get("secondary_is_shotgun", "")):
        rows.append(
            compare_metric_line(
                label="Secondary shotgun truth",
                a_value=candidate_a.get("secondary_shotgun_truth_score", ""),
                b_value=candidate_b.get("secondary_shotgun_truth_score", ""),
                lower_is_better=False,
                decimals=3,
            )
        )

    return pd.DataFrame(rows)


def build_compare_verdict(compare_table: pd.DataFrame, candidate_a: pd.Series, candidate_b: pd.Series, build_type: str) -> str:
    if compare_table.empty:
        return "Oracle verdict: not enough comparable data."

    wins = compare_table["Winner"].value_counts().to_dict()
    a_wins = int(wins.get("A", 0))
    b_wins = int(wins.get("B", 0))

    a_confidence = str(candidate_a.get("confidence", "MODELLED") or "MODELLED")
    b_confidence = str(candidate_b.get("confidence", "MODELLED") or "MODELLED")
    a_confidence_rank = confidence_rank(a_confidence)
    b_confidence_rank = confidence_rank(b_confidence)

    if build_type == "single":
        a_practical = numeric_compare_value(candidate_a.get("practical_ttk_ms", ""))
        b_practical = numeric_compare_value(candidate_b.get("practical_ttk_ms", ""))

        if a_practical is not None and b_practical is not None:
            ttk_gap = abs(a_practical - b_practical)
            faster = "A" if a_practical < b_practical else "B" if b_practical < a_practical else "neither"
        else:
            ttk_gap = 0
            faster = "neither"

        if a_confidence_rank != b_confidence_rank and ttk_gap <= 100:
            safer = "A" if a_confidence_rank > b_confidence_rank else "B"
            return (
                f"Oracle verdict: {safer} is the safer real build. "
                f"The practical TTK gap is {ttk_gap:.0f}ms, but the trust badge is stronger."
            )

        if faster in {"A", "B"}:
            return (
                f"Oracle verdict: {faster} is the faster kill build by {ttk_gap:.0f}ms practical TTK. "
                f"Use the metrics table to decide whether the handling cost is worth it."
            )

    else:
        a_score = numeric_compare_value(candidate_a.get("full_loadout_score", ""))
        b_score = numeric_compare_value(candidate_b.get("full_loadout_score", ""))

        if a_confidence_rank != b_confidence_rank:
            safer = "A" if a_confidence_rank > b_confidence_rank else "B"
            if a_score is None or b_score is None or abs(a_score - b_score) <= 0.05:
                return (
                    f"Oracle verdict: {safer} is the safer real loadout. "
                    "The score gap is small enough that trust should win."
                )

        if a_score is not None and b_score is not None and abs(a_score - b_score) > 0.0001:
            winner = "A" if a_score > b_score else "B"
            return (
                f"Oracle verdict: {winner} is the stronger modelled loadout by "
                f"{abs(a_score - b_score):.3f} score."
            )

    if a_wins > b_wins:
        return f"Oracle verdict: A wins more comparison rows ({a_wins} vs {b_wins}), but field feel still decides."
    if b_wins > a_wins:
        return f"Oracle verdict: B wins more comparison rows ({b_wins} vs {a_wins}), but field feel still decides."

    return "Oracle verdict: too close to crown. Field test both or pick the stronger confidence badge."


def render_compare_candidate_details(candidate_a: pd.Series, candidate_b: pd.Series, build_type: str):
    a_col, b_col = st.columns(2)

    if build_type == "single":
        with a_col:
            st.markdown("#### Candidate A")
            render_confidence_badge(single_build_confidence(candidate_a, st.session_state.get("ttk_last_single_build", {})))
            st.write(f"**Weapon:** {candidate_a.get('gun_name', '')}")
            st.write(f"**Slots:** {candidate_a.get('slots', '')}")
            render_shotgun_truth_panel(candidate_a)
            render_attachment_list(candidate_a.get("attachments", ""))

        with b_col:
            st.markdown("#### Candidate B")
            render_confidence_badge(single_build_confidence(candidate_b, st.session_state.get("ttk_last_single_build", {})))
            st.write(f"**Weapon:** {candidate_b.get('gun_name', '')}")
            st.write(f"**Slots:** {candidate_b.get('slots', '')}")
            render_shotgun_truth_panel(candidate_b)
            render_attachment_list(candidate_b.get("attachments", ""))
    else:
        with a_col:
            st.markdown("#### Candidate A")
            render_confidence_badge(full_loadout_confidence(candidate_a, st.session_state.get("ttk_last_full_loadout", {})))
            st.write(f"**Primary:** {candidate_a.get('primary_weapon', '')}")
            render_shotgun_truth_panel(candidate_a, prefix="primary_")
            render_attachment_list(candidate_a.get("primary_attachments", ""))
            st.write(f"**Secondary:** {candidate_a.get('secondary_weapon', '')}")
            render_shotgun_truth_panel(candidate_a, prefix="secondary_")
            render_attachment_list(candidate_a.get("secondary_attachments", ""))

        with b_col:
            st.markdown("#### Candidate B")
            render_confidence_badge(full_loadout_confidence(candidate_b, st.session_state.get("ttk_last_full_loadout", {})))
            st.write(f"**Primary:** {candidate_b.get('primary_weapon', '')}")
            render_shotgun_truth_panel(candidate_b, prefix="primary_")
            render_attachment_list(candidate_b.get("primary_attachments", ""))
            st.write(f"**Secondary:** {candidate_b.get('secondary_weapon', '')}")
            render_shotgun_truth_panel(candidate_b, prefix="secondary_")
            render_attachment_list(candidate_b.get("secondary_attachments", ""))


def render_build_compare(candidate_trust_filter: str):
    st.subheader("Build Compare")
    st.caption(
        "A/B test Oracle candidates. This does not generate new builds; it compares the latest lab results already in session."
    )

    compare_type = st.radio(
        "Compare pool",
        ["Assigned Weapon Candidates", "Two-Weapon Loadouts"],
        horizontal=True,
        key="ttk_compare_type",
    )

    if compare_type == "Assigned Weapon Candidates":
        pool = build_single_compare_pool(
            st.session_state.get("ttk_last_single_build", {}),
            candidate_trust_filter,
        )
        build_type = "single"
        weapon_columns = ["gun_name"]
        prefix = "SW"

    else:
        pool = build_full_compare_pool(
            st.session_state.get("ttk_last_full_loadout", {}),
            candidate_trust_filter,
        )
        build_type = "full"
        weapon_columns = ["primary_weapon", "secondary_weapon"]
        prefix = "TL"

    if pool.empty:
        st.info(
            "No candidates available for this compare pool under the current trust filter. "
            "Run an optimiser first or switch the trust filter to SHOW ALL LAB CANDIDATES."
        )
        return

    if len(pool) < 2:
        st.info("Only one candidate is available. Generate at least two results before comparing.")
        return

    pool = pool.reset_index(drop=True)
    labels = [
        candidate_label(prefix, index, row, weapon_columns)
        for index, row in pool.iterrows()
    ]

    compare_cols = st.columns(2)

    with compare_cols[0]:
        choice_a = st.selectbox(
            "Candidate A",
            labels,
            index=0,
            key=f"{build_type}_compare_a",
        )

    with compare_cols[1]:
        choice_b = st.selectbox(
            "Candidate B",
            labels,
            index=1 if len(labels) > 1 else 0,
            key=f"{build_type}_compare_b",
        )

    index_a = labels.index(choice_a)
    index_b = labels.index(choice_b)

    if index_a == index_b:
        st.warning("Choose two different candidates.")
        return

    candidate_a = pd.Series(pool.iloc[index_a])
    candidate_b = pd.Series(pool.iloc[index_b])

    compare_table = (
        build_single_compare_table(candidate_a, candidate_b)
        if build_type == "single"
        else build_full_compare_table(candidate_a, candidate_b)
    )

    st.dataframe(compare_table, use_container_width=True, hide_index=True)
    st.info(build_compare_verdict(compare_table, candidate_a, candidate_b, build_type))

    with st.expander("Candidate detail", expanded=False):
        render_compare_candidate_details(candidate_a, candidate_b, build_type)



def audit_status_from_data(status_5: dict, status_8: dict) -> str:
    trusted_slots = int(status_5.get("trusted_slots", 0) or 0)
    compatible_attachments = int(status_5.get("compatible_attachments", 0) or 0)

    if trusted_slots >= 8:
        return "EXTENDED READY"

    if trusted_slots >= 5:
        return "STANDARD READY"

    if trusted_slots > 0:
        return "PARTIAL"

    if compatible_attachments > 0:
        return "UNMODELLED"

    return "NO DATA"


def audit_action_for_status(status: str) -> str:
    actions = {
        "EXTENDED READY": "Safe for 8-attachment brute force.",
        "STANDARD READY": "Safe for 5-attachment brute force. Needs more trusted slots before 8-attachment lab work.",
        "PARTIAL": "Do not call this finished. Enter or verify more attachment slots.",
        "UNMODELLED": "Rows exist, but the Oracle is ignoring them until stat effects are modelled.",
        "NO DATA": "Add gun-compatible attachment rows before optimisation.",
    }
    return actions.get(status, "Review this weapon before trusting the Oracle.")


def build_ttk_data_audit(guns: pd.DataFrame, attachments: pd.DataFrame) -> pd.DataFrame:
    rows = []

    if guns.empty:
        return pd.DataFrame(
            columns=[
                "data_status",
                "gun_name",
                "weapon_class",
                "trusted_slots",
                "trusted_attachments",
                "compatible_attachments",
                "ignored_attachments",
                "standard_5_ready",
                "extended_8_ready",
                "trusted_slot_list",
                "oracle_action",
            ]
        )

    for _, gun in guns.iterrows():
        gun_name = str(gun.get("gun_name", "")).strip()
        weapon_class = str(gun.get("weapon_class", "")).strip()

        status_5 = describe_weapon_build_data(
            guns=guns,
            attachments=attachments,
            weapon_name=gun_name,
            attachment_count=5,
        )
        status_8 = describe_weapon_build_data(
            guns=guns,
            attachments=attachments,
            weapon_name=gun_name,
            attachment_count=8,
        )

        data_status = audit_status_from_data(status_5, status_8)
        trusted_slots = int(status_5.get("trusted_slots", 0) or 0)
        trusted_slot_list = status_5.get("trusted_slots_list", []) or []

        rows.append(
            {
                "data_status": data_status,
                "gun_name": gun_name,
                "weapon_class": weapon_class,
                "trusted_slots": trusted_slots,
                "trusted_attachments": int(status_5.get("trusted_attachments", 0) or 0),
                "compatible_attachments": int(status_5.get("compatible_attachments", 0) or 0),
                "ignored_attachments": int(status_5.get("ignored_attachments", 0) or 0),
                "standard_5_ready": "YES" if status_5.get("buildable", False) else "NO",
                "extended_8_ready": "YES" if status_8.get("buildable", False) else "NO",
                "trusted_slot_list": " | ".join(str(slot) for slot in trusted_slot_list),
                "oracle_action": audit_action_for_status(data_status),
            }
        )

    audit = pd.DataFrame(rows)

    if audit.empty:
        return audit

    status_order = {
        "EXTENDED READY": 0,
        "STANDARD READY": 1,
        "PARTIAL": 2,
        "UNMODELLED": 3,
        "NO DATA": 4,
    }

    audit["_status_order"] = audit["data_status"].map(status_order).fillna(99)
    audit = audit.sort_values(
        by=["_status_order", "weapon_class", "gun_name"],
        ascending=[True, True, True],
    ).drop(columns=["_status_order"])

    return audit.reset_index(drop=True)


def render_ttk_data_audit(guns: pd.DataFrame, attachments: pd.DataFrame, stats_profile: str):
    st.subheader("Data Audit")
    st.caption(
        f"Weapon readiness for {stats_profile}. This separates 5-attachment-ready weapons from true 8-attachment lab candidates."
    )

    audit = build_ttk_data_audit(guns, attachments)

    if audit.empty:
        st.warning("No gun rows loaded. Add guns.csv data before auditing attachments.")
        return

    ready_8 = int((audit["data_status"] == "EXTENDED READY").sum())
    ready_5 = int((audit["data_status"] == "STANDARD READY").sum())
    partial = int(audit["data_status"].isin(["PARTIAL", "UNMODELLED"]).sum())
    no_data = int((audit["data_status"] == "NO DATA").sum())

    audit_cols = st.columns(4)
    audit_cols[0].metric("8-slot ready", ready_8)
    audit_cols[1].metric("5-slot ready", ready_5)
    audit_cols[2].metric("Partial / unmodelled", partial)
    audit_cols[3].metric("No data", no_data)

    filter_cols = st.columns(3)

    with filter_cols[0]:
        status_options = [
            "EXTENDED READY",
            "STANDARD READY",
            "PARTIAL",
            "UNMODELLED",
            "NO DATA",
        ]
        selected_statuses = st.multiselect(
            "Audit status",
            status_options,
            default=status_options,
            key="ttk_data_audit_statuses",
        )

    with filter_cols[1]:
        class_options = ["All"] + sorted(
            value
            for value in audit["weapon_class"].dropna().astype(str).unique().tolist()
            if value
        )
        selected_class = st.selectbox(
            "Weapon class",
            class_options,
            key="ttk_data_audit_class",
        )

    with filter_cols[2]:
        only_blockers = st.toggle(
            "Show blockers only",
            value=False,
            key="ttk_data_audit_blockers_only",
            help="Shows weapons that are not ready for 8-attachment optimisation.",
        )

    visible_audit = audit.copy()

    if selected_statuses:
        visible_audit = visible_audit[visible_audit["data_status"].isin(selected_statuses)]

    if selected_class != "All":
        visible_audit = visible_audit[visible_audit["weapon_class"] == selected_class]

    if only_blockers:
        visible_audit = visible_audit[visible_audit["data_status"] != "EXTENDED READY"]

    st.dataframe(
        visible_audit[
            [
                "data_status",
                "gun_name",
                "weapon_class",
                "trusted_slots",
                "trusted_attachments",
                "compatible_attachments",
                "ignored_attachments",
                "standard_5_ready",
                "extended_8_ready",
                "trusted_slot_list",
                "oracle_action",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Inspect one weapon's attachment rows", expanded=False):
        audit_weapon_names = audit["gun_name"].dropna().astype(str).tolist()

        if not audit_weapon_names:
            st.info("No weapons available for inspection.")
            return

        inspected_weapon = st.selectbox(
            "Weapon to inspect",
            audit_weapon_names,
            key="ttk_data_audit_inspect_weapon",
        )

        inspected_gun_rows = guns[guns["gun_name"].astype(str) == inspected_weapon]

        if inspected_gun_rows.empty:
            st.warning("Selected weapon was not found in guns.csv.")
            return

        compatible_rows = get_compatible_attachments(
            inspected_gun_rows.iloc[0],
            attachments,
        )

        if compatible_rows.empty:
            st.warning("No compatible attachment rows found for this weapon.")
            return

        detail_columns = [
            column
            for column in [
                "attachment_name",
                "slot",
                "stats_profile",
                "verification_status",
                "verification_notes",
                "raw_stat_text",
                "source",
                "source_date",
            ]
            if column in compatible_rows.columns
        ]

        if not detail_columns:
            detail_columns = compatible_rows.columns.tolist()

        st.dataframe(
            compatible_rows[detail_columns],
            use_container_width=True,
            hide_index=True,
        )


def render_in_game_delta_bench(guns: pd.DataFrame, attachments: pd.DataFrame, active_stats_profile: str):
    st.subheader("TTK In-Game Delta Bench")
    st.caption(
        f"Type the numbers shown by the in-game details panel for {active_stats_profile}. "
        "The Oracle calculates the attachment deltas and creates one reviewed import row."
    )

    if guns.empty:
        st.warning("Add guns.csv rows before using the Delta Bench.")
        return

    weapon_options = sorted(guns["gun_name"].dropna().astype(str).tolist())
    bench_cols = st.columns(3)

    with bench_cols[0]:
        bench_weapon = st.selectbox(
            "Weapon",
            weapon_options,
            key="delta_bench_weapon",
        )

    selected_gun = guns[guns["gun_name"] == bench_weapon].iloc[0]
    weapon_class = str(selected_gun.get("weapon_class", "") or "").strip()

    compatible_rows = get_compatible_attachments(
        gun=selected_gun,
        attachments=attachments,
    ) if not attachments.empty else pd.DataFrame()

    attachment_display_options = ["Manual new attachment"]

    if not compatible_rows.empty and "attachment_name" in compatible_rows.columns:
        for _, row in compatible_rows.sort_values(["slot", "attachment_name"]).iterrows():
            attachment_display_options.append(
                f"{row.get('slot', 'Unknown')} | {row.get('attachment_name', '')}"
            )

    with bench_cols[1]:
        attachment_choice = st.selectbox(
            "Attachment source",
            attachment_display_options,
            key="delta_bench_attachment_choice",
        )

    source_attachment = None

    if attachment_choice != "Manual new attachment" and not compatible_rows.empty:
        chosen_name = attachment_choice.split("|", 1)[1].strip() if "|" in attachment_choice else attachment_choice
        matched = compatible_rows[
            compatible_rows["attachment_name"].fillna("").astype(str).str.strip().eq(chosen_name)
        ]
        if not matched.empty:
            source_attachment = matched.iloc[0]

    with bench_cols[2]:
        approval_status = st.selectbox(
            "Bench verdict",
            IMPORT_APPROVAL_STATUSES,
            index=0,
            key="delta_bench_approval_status",
        )

    detail_cols = st.columns(2)

    with detail_cols[0]:
        default_attachment_name = ""
        if source_attachment is not None:
            default_attachment_name = str(source_attachment.get("attachment_name", "") or "")

        attachment_name = st.text_input(
            "Attachment name",
            value=default_attachment_name,
            key="delta_bench_attachment_name",
        )

    with detail_cols[1]:
        default_slot = ""
        if source_attachment is not None:
            default_slot = str(source_attachment.get("slot", "") or "")

        known_slots = ["", "Muzzle", "Barrel", "Magazine", "Rear Grip", "Stock", "Laser", "Fire Mods", "Optic", "Underbarrel"]
        slot_index = known_slots.index(default_slot) if default_slot in known_slots else 0

        slot = st.selectbox(
            "Slot",
            known_slots,
            index=slot_index,
            key="delta_bench_attachment_slot",
        )

    if not attachment_name.strip():
        st.warning("Select or type an attachment name before generating the import row.")
        return

    st.markdown("#### In-game numbers")
    st.caption(
        "Leave unchanged rows alone. Only edit values visible on the game panel. "
        "Base values come from guns.csv, but you can override them when the in-game base panel differs."
    )

    metric_template = build_delta_bench_metric_template(selected_gun)

    edited_metrics = st.data_editor(
        metric_template,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key=f"delta_bench_metrics_{slugify_for_ttk(bench_weapon)}_{slugify_for_ttk(attachment_name)}",
        column_config={
            "metric": st.column_config.TextColumn("Metric", disabled=True),
            "target_column": st.column_config.TextColumn("Oracle column", disabled=True),
            "delta_mode": st.column_config.TextColumn("Mode", disabled=True),
            "base_value": st.column_config.NumberColumn("Base value", step=0.01, format="%.2f"),
            "observed_value": st.column_config.NumberColumn("Observed value", step=0.01, format="%.2f"),
        },
    )

    notes_cols = st.columns(2)

    with notes_cols[0]:
        review_notes = st.text_area(
            "Review notes",
            value="In-game numbers entered manually from expanded Gunsmith details.",
            height=90,
            key="delta_bench_review_notes",
        )

    with notes_cols[1]:
        extra_stat_notes = st.text_area(
            "Extra stats not modelled yet",
            placeholder="Example: ADS pellet spread 3.20 -> 2.56, hipfire spread 9.30 -> 8.37, damage range table...",
            height=90,
            key="delta_bench_extra_notes",
        )

    bench_row = build_delta_bench_attachment_row(
        weapon_name=bench_weapon,
        weapon_class=weapon_class,
        stats_profile=active_stats_profile,
        attachment_name=attachment_name,
        slot=slot,
        source_attachment=source_attachment,
        metric_rows=edited_metrics,
        approval_status=approval_status,
        review_notes=review_notes,
        extra_stat_notes=extra_stat_notes,
    )

    preview_columns = [
        column for column in [
            "approval_status",
            "attachment_id",
            "attachment_name",
            "slot",
            "stats_profile",
            "damage_pct",
            "fire_rate_pct",
            "bullet_velocity_pct",
            "range_pct",
            "mag_size_add",
            "ads_pct",
            "sprint_to_fire_pct",
            "reload_pct",
            "jump_ads_pct",
            "jump_sprint_to_fire_pct",
            "recoil_pct",
            "gun_kick_pct",
            "horizontal_recoil_pct",
            "vertical_recoil_pct",
            "first_shot_recoil_pct",
            "kick_reset_speed_pct",
            "movement_pct",
            "sprint_pct",
            "crouch_movement_pct",
            "ads_movement_pct",
            "flinch_resistance_pct",
            "verification_status",
            "verification_notes",
        ] if column in bench_row.columns
    ]

    st.markdown("#### Generated Oracle row")
    st.dataframe(
        bench_row[preview_columns],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Raw Delta Bench notes", expanded=False):
        st.text(bench_row.iloc[0].get("raw_stat_text", ""))

    action_cols = st.columns(4)

    with action_cols[0]:
        st.download_button(
            "Download this row",
            bench_row[ATTACHMENT_IMPORT_DATA_COLUMNS].to_csv(index=False).encode("utf-8"),
            file_name=f"{slugify_for_ttk(bench_weapon)}_{slugify_for_ttk(attachment_name)}_delta_bench_row.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with action_cols[1]:
        if st.button(
            "BANK BENCH ROW",
            use_container_width=True,
            key="delta_bench_bank_row",
        ):
            append_ttk_import_approval_log(bench_row, bench_weapon)
            st.success("Delta Bench row banked to Import Approval Log. attachments.csv was not changed.")

    replace_existing = action_cols[2].checkbox(
        "Replace ID",
        value=True,
        key="delta_bench_replace_existing",
        help="Replace the matching attachment_id when committing this row.",
    )

    with action_cols[3]:
        if st.button(
            "COMMIT BENCH ROW",
            use_container_width=True,
            key="delta_bench_commit_row",
        ):
            append_ttk_import_approval_log(bench_row, bench_weapon)
            commit_result = commit_approved_attachment_rows(
                bench_row,
                bench_weapon,
                replace_existing=replace_existing,
            )

            if commit_result["rows_committed"]:
                try:
                    load_and_validate_ttk_data.clear()
                except Exception:
                    pass

                st.success(commit_result["message"])
                if commit_result.get("backup_path"):
                    st.caption(f"Backup created: {commit_result['backup_path']}")
            else:
                st.warning(commit_result["message"])




try:
    all_guns, all_attachments, data_warnings = load_and_validate_ttk_data()
except Exception as error:
    st.error(f"TTK data failed to load: {error}")
    st.stop()

profile_index = (
    SUPPORTED_STATS_PROFILES.index(DEFAULT_STATS_PROFILE)
    if DEFAULT_STATS_PROFILE in SUPPORTED_STATS_PROFILES
    else 0
)
active_stats_profile = st.radio(
    "Stats profile",
    SUPPORTED_STATS_PROFILES,
    index=profile_index,
    horizontal=True,
    help="The Oracle never mixes Multiplayer and Warzone stats. Existing legacy rows are marked Multiplayer until re-entered.",
)

guns, attachments = filter_ttk_data_by_profile(
    all_guns,
    all_attachments,
    active_stats_profile,
)

weapon_names = sorted(guns["gun_name"].dropna().astype(str).tolist())

if data_warnings:
    with st.expander(f"⚠️ {len(data_warnings)} data quality issue(s) detected", expanded=True):
        for warning in data_warnings:
            st.warning(warning)

st.success("TTK Oracle engine connected.")

metric_cols = st.columns(4)

with metric_cols[0]:
    st.metric("Active profile", active_stats_profile)

with metric_cols[1]:
    st.metric("Profile guns", len(guns))

with metric_cols[2]:
    st.metric("Profile attachments", len(attachments))

with metric_cols[3]:
    st.metric("All attachment rows", len(all_attachments))

if guns.empty:
    st.warning(
        f"No {active_stats_profile} gun baseline rows are loaded yet. "
        "Switch to Multiplayer to inspect legacy data, or add Warzone base gun rows before optimising."
    )

render_ttk_data_audit(guns, attachments, active_stats_profile)

st.divider()

with st.expander("Data Entry Lab: Profiled Gun Baseline", expanded=False):
    render_gun_baseline_bench(all_guns, active_stats_profile)

with st.expander("Data Entry Lab: Codmunity HTML parser and verification", expanded=False):
    st.caption(
        "Paste a copied Codmunity attachment table for one weapon. The parser creates draft attachment rows, then generates one or two before/after stat checks to verify against in-game expanded stats before committing."
    )

    if not weapon_names:
        st.warning("Add gun data before using the parser.")
        data_entry_weapon = ""
        data_entry_html = ""
        selected_data_gun = None
    else:
        data_entry_weapon = st.selectbox(
            "Weapon for pasted attachment table",
            weapon_names,
            key="data_entry_weapon",
        )

        selected_data_gun = guns[guns["gun_name"] == data_entry_weapon].iloc[0]
        data_entry_html = st.text_area(
            "Paste Codmunity attachment table HTML",
            height=180,
            key="codmunity_attachment_html",
        )

    sample_count = st.slider(
        "Verification samples",
        min_value=1,
        max_value=4,
        value=2,
        key="verification_sample_count",
    )

    verification_seed = st.number_input(
        "Verification sample seed",
        min_value=1,
        max_value=9999,
        value=7,
        step=1,
        key="verification_seed",
        help="Change this if you want different random attachments to spot-check.",
    )

    if selected_data_gun is not None and data_entry_html.strip():
        parsed_attachment_rows = parse_codmunity_attachment_html(
            data_entry_html,
            compatible_weapon_classes="",
            compatible_guns=data_entry_weapon,
            source="codmunity.gg",
            stats_profile=active_stats_profile,
        )

        if parsed_attachment_rows.empty:
            st.warning("No attachment rows parsed. Check that you copied the attachment table HTML, not just visible text.")
        else:
            st.success(
                f"Parsed {len(parsed_attachment_rows)} attachment row(s) for {data_entry_weapon}. Do not commit until the verification rows match in-game expanded stats."
            )

            verification_rows = build_attachment_verification_rows(
                selected_data_gun,
                parsed_attachment_rows,
                sample_size=sample_count,
                random_state=int(verification_seed),
            )

            st.markdown("#### Verification rows")
            st.dataframe(
                verification_rows,
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("#### Import approval")
            st.caption(
                "Approve rows into a reviewed CSV, mark suspect rows, or block unmodelled parts before they ever reach the optimiser."
            )

            review_workbench = parsed_attachment_rows.copy()
            review_workbench.insert(0, "approval_status", "NEEDS IN-GAME CHECK")
            review_workbench.insert(1, "review_notes", "")

            review_columns = [
                column
                for column in [
                    "approval_status",
                    "review_notes",
                    "attachment_name",
                    "slot",
                    "stats_profile",
                    "verification_status",
                    "raw_stat_text",
                    "verification_notes",
                    "source",
                    "source_date",
                ]
                if column in review_workbench.columns
            ]

            edited_review_rows = st.data_editor(
                review_workbench[review_columns],
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                key="ttk_import_approval_editor",
                column_config={
                    "approval_status": st.column_config.SelectboxColumn(
                        "Approval status",
                        options=IMPORT_APPROVAL_STATUSES,
                        required=True,
                    ),
                    "review_notes": st.column_config.TextColumn(
                        "Review notes",
                        help="Manual check notes, in-game stat mismatch, or reason for exclusion.",
                    ),
                },
            )

            reviewed_attachment_rows = parsed_attachment_rows.copy()
            reviewed_attachment_rows["approval_status"] = edited_review_rows["approval_status"].tolist()
            reviewed_attachment_rows["review_notes"] = edited_review_rows["review_notes"].tolist()

            reviewed_download_rows = apply_import_approval_decisions(
                reviewed_attachment_rows,
            )

            status_counts = (
                reviewed_attachment_rows["approval_status"]
                .value_counts()
                .reset_index()
            )
            status_counts.columns = ["Approval status", "Rows"]

            st.dataframe(
                status_counts,
                use_container_width=True,
                hide_index=True,
            )

            download_cols = [
                column
                for column in [
                    "attachment_id",
                    "attachment_name",
                    "slot",
                    "compatible_weapon_classes",
                    "compatible_guns",
                    "verification_status",
                    "raw_stat_text",
                    "verification_notes",
                    "source",
                    "source_date",
                ]
                if column in reviewed_download_rows.columns
            ]

            st.markdown("#### Reviewed attachment rows")
            st.dataframe(
                reviewed_download_rows[download_cols] if download_cols else reviewed_download_rows,
                use_container_width=True,
                hide_index=True,
            )

            commit_replace_existing = st.checkbox(
                "Replace matching attachment IDs when committing approved rows",
                value=False,
                key="ttk_import_commit_replace_existing",
                help=(
                    "Off = append new attachment IDs only. "
                    "On = replace existing rows with the same attachment_id after creating a backup."
                ),
            )

            action_cols = st.columns(3)

            with action_cols[0]:
                st.download_button(
                    "Download reviewed attachment rows",
                    reviewed_download_rows.to_csv(index=False).encode("utf-8"),
                    file_name=f"{data_entry_weapon.lower().replace(' ', '_')}_reviewed_attachments.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            with action_cols[1]:
                if st.button(
                    "BANK IMPORT REVIEW",
                    use_container_width=True,
                    key="bank_import_review",
                ):
                    append_ttk_import_approval_log(
                        reviewed_attachment_rows,
                        data_entry_weapon,
                    )
                    st.success("Import review banked. Master attachment data was not rewritten.")

            with action_cols[2]:
                if st.button(
                    "COMMIT APPROVED TO ORACLE",
                    use_container_width=True,
                    key="commit_approved_to_oracle",
                ):
                    append_ttk_import_approval_log(
                        reviewed_attachment_rows,
                        data_entry_weapon,
                    )
                    commit_result = commit_approved_attachment_rows(
                        reviewed_attachment_rows,
                        data_entry_weapon,
                        replace_existing=commit_replace_existing,
                    )

                    if commit_result["rows_committed"]:
                        try:
                            load_and_validate_ttk_data.clear()
                        except Exception:
                            pass

                        st.success(commit_result["message"])

                        if commit_result.get("backup_path"):
                            st.caption(f"Backup created: {commit_result['backup_path']}")
                    else:
                        st.warning(commit_result["message"])

with st.expander("Data Entry Lab: In-Game Delta Bench", expanded=False):
    render_in_game_delta_bench(guns, attachments, active_stats_profile)

with st.expander("Import Approval Log", expanded=False):
    render_ttk_import_approval_log()

with st.expander("Import Commit Log", expanded=False):
    render_ttk_import_commit_log()

enemy_health = st.slider(
    "Enemy health",
    min_value=100,
    max_value=400,
    value=300,
    step=50,
)

candidate_trust_filter = st.selectbox(
    "Candidate trust filter",
    CANDIDATE_TRUST_FILTERS,
    index=0,
    help=(
        "Controls which generated builds are allowed to appear as the current optimum. "
        "Use Show All Lab Candidates when you want to inspect rejected or suspect science."
    ),
)

if guns.empty:
    st.warning(f"{active_stats_profile} has no base gun rows yet. Enter one in Data Entry Lab: Profiled Gun Baseline.")
    st.stop()

if attachments.empty:
    st.warning(f"{active_stats_profile} has no attachment rows yet. Enter rows with Codmunity Import or In-Game Delta Bench.")
    st.stop()

st.divider()

st.subheader("Commander Weapon Optimiser")
st.caption(
    "Use this when Completion Commander assigns a weapon. The Oracle is locked to that weapon and cannot dodge the order."
)

commander_cols = st.columns(4)

with commander_cols[0]:
    assigned_weapon = st.selectbox(
        "Assigned weapon",
        weapon_names,
        index=0,
        key="commander_assigned_weapon",
    )

with commander_cols[1]:
    commander_map_type = st.selectbox(
        "Mode profile",
        MAP_TYPES,
        index=0,
        key="commander_map_type",
    )

with commander_cols[2]:
    commander_fight_type = st.selectbox(
        "Fight type",
        FIGHT_TYPES,
        index=1 if "Mid range" in FIGHT_TYPES else 0,
        key="commander_fight_type",
    )

with commander_cols[3]:
    commander_build_goal = st.selectbox(
        "Build goal",
        BUILD_GOALS,
        index=0,
        key="commander_build_goal",
    )

commander_cols = st.columns(4)

with commander_cols[0]:
    commander_ruleset = st.selectbox(
        "Attachment ruleset",
        ATTACHMENT_RULESETS,
        index=0,
        key="commander_attachment_ruleset",
    )

with commander_cols[1]:
    commander_attachment_budget = st.selectbox(
        "Attachment budget",
        ATTACHMENT_BUDGET_PROFILES,
        index=0,
        key="commander_attachment_budget",
    )

with commander_cols[2]:
    commander_results = st.slider(
        "Commander build results",
        min_value=5,
        max_value=25,
        value=10,
        step=5,
        key="commander_results",
    )

with commander_cols[3]:
    commander_perk_package = st.selectbox(
        "Perk package to save",
        list(PERK_PACKAGES.keys()),
        index=list(PERK_PACKAGES.keys()).index("Balanced") if "Balanced" in PERK_PACKAGES else 0,
        key="commander_perk_package",
    )

commander_attachment_count = attachment_count_for_profile(
    commander_ruleset,
    commander_attachment_budget,
)
st.caption(
    attachment_budget_summary(
        commander_ruleset,
        commander_attachment_budget,
    )
)

commander_depth_cols = st.columns(2)

with commander_depth_cols[0]:
    commander_depth_profile = st.selectbox(
        "Optimiser depth",
        OPTIMISER_DEPTH_PROFILES,
        index=0,
        key="commander_optimiser_depth",
    )

with commander_depth_cols[1]:
    commander_slot_candidate_limit = st.slider(
        "Fast-pass candidates per slot",
        min_value=1,
        max_value=5,
        value=3,
        step=1,
        key="commander_slot_candidate_limit",
    )

commander_optimiser_mode = optimiser_mode_for_profile(commander_depth_profile)
st.caption(
    optimiser_depth_summary(
        commander_depth_profile,
        commander_slot_candidate_limit,
    )
)

render_optimizer_workload_estimate(
    guns_subset=guns[guns["gun_name"] == assigned_weapon],
    attachments=attachments,
    map_type=commander_map_type,
    fight_type=commander_fight_type,
    build_goal=commander_build_goal,
    enemy_health=enemy_health,
    attachment_count=commander_attachment_count,
    optimiser_mode=commander_optimiser_mode,
    slot_candidate_limit=commander_slot_candidate_limit,
)

weapon_data_status = describe_weapon_build_data(
    guns=guns,
    attachments=attachments,
    weapon_name=assigned_weapon,
    attachment_count=commander_attachment_count,
)

if weapon_data_status.get("buildable"):
    st.caption(
        f"{weapon_data_status['message']} Slots: {', '.join(weapon_data_status.get('slots', []))}"
    )
else:
    st.warning(weapon_data_status["message"])

if st.button("Optimise Assigned Weapon", type="primary", use_container_width=True):
    start_time = time.perf_counter()

    with st.spinner(f"Brute-forcing {assigned_weapon} {commander_attachment_count}-attachment builds..."):
        assigned_weapon_results = optimise_single_weapon_build(
            guns=guns,
            attachments=attachments,
            weapon_name=assigned_weapon,
            map_type=commander_map_type,
            fight_type=commander_fight_type,
            build_goal=commander_build_goal,
            enemy_health=enemy_health,
            attachment_count=commander_attachment_count,
            top_n=commander_results,
            optimiser_mode=commander_optimiser_mode,
            candidate_limit_per_slot=commander_slot_candidate_limit,
        )

    elapsed_seconds = time.perf_counter() - start_time

    if assigned_weapon_results.empty:
        st.error(
            "No valid assigned-weapon build found. This usually means the selected weapon does not have enough entered attachment slots yet."
        )
    else:
        st.session_state.ttk_last_single_build = {
            "elapsed_seconds": elapsed_seconds,
            "result": assigned_weapon_results.iloc[0].to_dict(),
            "top_results": assigned_weapon_results,
            "mode_profile": f"{active_stats_profile} | {commander_map_type} | {commander_ruleset}",
            "stats_profile": active_stats_profile,
            "fight_type": commander_fight_type,
            "build_goal": commander_build_goal,
            "enemy_health": enemy_health,
            "attachment_budget": commander_attachment_budget,
            "attachment_count": commander_attachment_count,
            "optimiser_depth": commander_depth_profile,
            "slot_candidate_limit": commander_slot_candidate_limit,
            "perk_package": commander_perk_package,
        }

last_single_build = st.session_state.get("ttk_last_single_build")

if last_single_build:
    assigned_weapon_results = last_single_build.get("top_results", pd.DataFrame())

    if assigned_weapon_results.empty:
        best_single = pd.Series(last_single_build["result"])
        visible_single_results = pd.DataFrame()
    else:
        assigned_weapon_results = annotate_single_results_with_confidence(
            assigned_weapon_results,
            last_single_build,
        )
        visible_single_results = filter_candidate_results(
            assigned_weapon_results,
            candidate_trust_filter,
        )
        best_single = (
            pd.Series(visible_single_results.iloc[0])
            if not visible_single_results.empty
            else pd.Series(dtype=object)
        )

    if visible_single_results.empty:
        st.warning(
            "No assigned-weapon candidate survives the current trust filter. "
            "Switch to SHOW ALL LAB CANDIDATES to inspect the raw Oracle output."
        )
    else:
        st.success(
            f"{best_single.get('gun_name', 'Assigned weapon')} {last_single_build.get('attachment_count', '')}-attachment build found in "
            f"{float(last_single_build.get('elapsed_seconds', 0.0)):.2f} seconds."
        )
        single_confidence = single_build_confidence(best_single, last_single_build)
        render_single_weapon_result(
            best_single,
            int(last_single_build.get("enemy_health", enemy_health)),
            single_confidence,
        )
        render_single_field_test_form(best_single, last_single_build)

        selected_perks = selected_perk_rows(last_single_build.get("perk_package", ""))
        if selected_perks.get("perk_package"):
            st.markdown("### Saved Perk Package")
            st.write(
                f"**{selected_perks['perk_package']}**: "
                f"{selected_perks['perk_1']} / {selected_perks['perk_2']} / "
                f"{selected_perks['perk_3']} / {selected_perks['perk_4']}"
            )

        render_keep_single_weapon_build(best_single, last_single_build)

    st.markdown("### Top Assigned-Weapon Builds")

    if not assigned_weapon_results.empty:
        render_candidate_filter_summary(
            assigned_weapon_results,
            visible_single_results,
            candidate_trust_filter,
        )

        single_result_columns = available_columns(
            visible_single_results,
            [
                "confidence",
                "optimiser_mode",
                "slot_candidate_limit",
                "field_verdict",
                "field_feel_rating",
                "field_tested_at",
                "oracle_score",
                "gun_name",
                "weapon_class",
                "raw_ttk_ms",
                "practical_ttk_ms",
                "shotgun_truth_score",
                "shotgun_one_shot_potential",
                "shotgun_two_shot_consistency",
                "shotgun_range_coverage",
                "ads_ms",
                "sprint_to_fire_ms",
                "recoil",
                "bullet_velocity",
                "range_m",
                "damage_per_mag",
                "slots",
                "attachments",
                "shotgun_truth_note",
            ],
        )

        st.dataframe(
            visible_single_results[single_result_columns],
            use_container_width=True,
            hide_index=True,
        )

st.divider()

st.subheader("Optimum Full Loadout")
st.caption(
    "Standalone Oracle mode. Choose the map, fight type, and build goal. The Oracle brute-forces valid two-weapon loadouts."
)

full_cols = st.columns(4)

with full_cols[0]:
    loadout_pairing = st.selectbox(
        "Loadout pairing",
        LOADOUT_PAIRINGS,
        index=0,
    )

with full_cols[1]:
    perk_package = st.selectbox(
        "Perk package",
        list(PERK_PACKAGES.keys()),
        index=1,
    )

with full_cols[2]:
    full_ruleset = st.selectbox(
        "Attachment ruleset",
        ATTACHMENT_RULESETS,
        index=0,
        key="full_attachment_ruleset",
    )

with full_cols[3]:
    full_attachment_budget = st.selectbox(
        "Attachment budget",
        ATTACHMENT_BUDGET_PROFILES,
        index=0,
        key="full_attachment_budget",
    )

full_attachment_count = attachment_count_for_profile(
    full_ruleset,
    full_attachment_budget,
)
st.caption(
    attachment_budget_summary(
        full_ruleset,
        full_attachment_budget,
    )
)

full_cols = st.columns(3)

with full_cols[0]:
    map_type = st.selectbox(
        "Map type",
        MAP_TYPES,
        index=0,
    )

with full_cols[1]:
    fight_type = st.selectbox(
        "Fight type",
        FIGHT_TYPES,
        index=0,
    )

with full_cols[2]:
    build_goal = st.selectbox(
        "Build goal",
        BUILD_GOALS,
        index=1,
    )

top_n = st.slider(
    "Full loadout results",
    min_value=5,
    max_value=50,
    value=20,
    step=5,
)

full_depth_cols = st.columns(2)

with full_depth_cols[0]:
    full_depth_profile = st.selectbox(
        "Full-loadout optimiser depth",
        OPTIMISER_DEPTH_PROFILES,
        index=0,
        key="full_optimiser_depth",
    )

with full_depth_cols[1]:
    full_slot_candidate_limit = st.slider(
        "Full fast-pass candidates per slot",
        min_value=1,
        max_value=5,
        value=3,
        step=1,
        key="full_slot_candidate_limit",
    )

full_optimiser_mode = optimiser_mode_for_profile(full_depth_profile)
st.caption(
    optimiser_depth_summary(
        full_depth_profile,
        full_slot_candidate_limit,
    )
)

if full_optimiser_mode == "Deep" and full_attachment_count == 8:
    st.warning(
        "DEEP + 8 ATTACHMENTS can be heavy. Use it for final validation after FAST PASS finds a candidate."
    )

if st.button("Find Best Full Loadout", use_container_width=True):
    start_time = time.perf_counter()

    with st.spinner(f"Brute-forcing {full_attachment_count}-attachment full loadouts..."):
        full_loadout_results = optimise_full_loadouts_for_scenario(
            guns=guns,
            attachments=attachments,
            map_type=map_type,
            fight_type=fight_type,
            build_goal=build_goal,
            loadout_pairing=loadout_pairing,
            perk_package=perk_package,
            enemy_health=enemy_health,
            attachment_count=full_attachment_count,
            top_n=top_n,
            optimiser_mode=full_optimiser_mode,
            candidate_limit_per_slot=full_slot_candidate_limit,
        )

    elapsed_seconds = time.perf_counter() - start_time

    if full_loadout_results.empty:
        st.warning("No valid full loadouts found. Check weapon classes, attachment slots, or compatibility.")
    else:
        st.session_state.ttk_last_full_loadout = {
            "elapsed_seconds": elapsed_seconds,
            "result": full_loadout_results.iloc[0].to_dict(),
            "top_results": full_loadout_results,
            "mode_profile": f"{active_stats_profile} | {map_type} | {full_ruleset}",
            "stats_profile": active_stats_profile,
            "fight_type": fight_type,
            "build_goal": build_goal,
            "enemy_health": enemy_health,
            "attachment_budget": full_attachment_budget,
            "attachment_count": full_attachment_count,
            "optimiser_depth": full_depth_profile,
            "slot_candidate_limit": full_slot_candidate_limit,
            "perk_package": perk_package,
            "loadout_pairing": loadout_pairing,
        }

last_full_loadout = st.session_state.get("ttk_last_full_loadout")

if last_full_loadout:
    full_loadout_results = last_full_loadout.get("top_results", pd.DataFrame())

    if not full_loadout_results.empty:
        full_loadout_results = annotate_full_results_with_confidence(
            full_loadout_results,
            last_full_loadout,
        )
        visible_full_loadout_results = filter_candidate_results(
            full_loadout_results,
            candidate_trust_filter,
        )

        if visible_full_loadout_results.empty:
            st.warning(
                "No full-loadout candidate survives the current trust filter. "
                "Switch to SHOW ALL LAB CANDIDATES to inspect the raw Oracle output."
            )
        else:
            best_full = pd.Series(visible_full_loadout_results.iloc[0])
            full_confidence = full_loadout_confidence(best_full, last_full_loadout)
            render_full_loadout_result(
                visible_full_loadout_results,
                float(last_full_loadout.get("elapsed_seconds", 0.0)),
                int(last_full_loadout.get("enemy_health", enemy_health)),
                full_confidence,
            )

            render_keep_full_loadout(best_full, last_full_loadout)
            render_full_field_test_form(best_full, last_full_loadout)

        st.divider()

        st.markdown("### Top Full Loadouts")
        render_candidate_filter_summary(
            full_loadout_results,
            visible_full_loadout_results,
            candidate_trust_filter,
        )

        full_result_columns = available_columns(
            visible_full_loadout_results,
            [
                "confidence",
                "optimiser_mode",
                "slot_candidate_limit",
                "field_verdict",
                "field_feel_rating",
                "field_tested_at",
                "full_loadout_score",
                "role_balance_score",
                "loadout_role_verdict",
                "primary_weapon",
                "primary_class",
                "primary_role_label",
                "primary_role_score",
                "primary_fight_type",
                "primary_build_goal",
                "primary_shotgun_truth_score",
                "primary_shotgun_one_shot_potential",
                "primary_shotgun_two_shot_consistency",
                "secondary_weapon",
                "secondary_class",
                "secondary_role_label",
                "secondary_role_score",
                "secondary_fight_type",
                "secondary_build_goal",
                "secondary_shotgun_truth_score",
                "secondary_shotgun_one_shot_potential",
                "secondary_shotgun_two_shot_consistency",
                "perk_package",
                "primary_raw_ttk_ms",
                "secondary_raw_ttk_ms",
                "primary_practical_ttk_ms",
                "secondary_practical_ttk_ms",
                "primary_recoil",
                "secondary_recoil",
                "primary_attachments",
                "secondary_attachments",
            ],
        )

        st.dataframe(
            visible_full_loadout_results[full_result_columns],
            use_container_width=True,
            hide_index=True,
        )

st.divider()

render_build_compare(candidate_trust_filter)

st.divider()

render_saved_ttk_loadouts()

st.divider()

render_ttk_field_test_log()

st.divider()

st.subheader("Base Weapon TTK Ranking")

base_rankings = build_base_weapon_rankings(
    guns=guns,
    enemy_health=enemy_health,
)

if base_rankings.empty:
    st.warning("No gun data loaded yet.")
else:
    base_ranking_columns = available_columns(
        base_rankings,
        [
            "gun_name",
            "weapon_class",
            "damage",
            "fire_rate_rpm",
            "shots_to_kill",
            "raw_ttk_ms",
            "practical_ttk_ms",
            "shotgun_truth_score",
            "shotgun_one_shot_potential",
            "shotgun_two_shot_consistency",
            "ads_ms",
            "sprint_to_fire_ms",
            "recoil",
            "bullet_velocity",
            "range_m",
            "mag_size",
        ],
    )

    st.dataframe(
        base_rankings[base_ranking_columns],
        use_container_width=True,
        hide_index=True,
    )

st.divider()

st.subheader("Manual Loadout Preview")
st.caption(
    "Manual preview stays below the optimiser. It is for checking a hand-built class, "
    "not for overriding the current optimum."
)

preview_cols = st.columns(3)

with preview_cols[0]:
    selected_gun_name = st.selectbox(
        "Choose weapon",
        weapon_names,
    )

with preview_cols[1]:
    preview_ruleset = st.selectbox(
        "Preview attachment ruleset",
        ATTACHMENT_RULESETS,
        index=0,
        key="manual_preview_attachment_ruleset",
    )

with preview_cols[2]:
    preview_attachment_budget = st.selectbox(
        "Preview attachment budget",
        ATTACHMENT_BUDGET_PROFILES,
        index=0,
        key="manual_preview_attachment_budget",
    )

preview_attachment_count = attachment_count_for_profile(
    preview_ruleset,
    preview_attachment_budget,
)

st.caption(
    attachment_budget_summary(
        preview_ruleset,
        preview_attachment_budget,
    )
)

selected_gun = guns[guns["gun_name"] == selected_gun_name].iloc[0]

compatible_attachments = get_compatible_attachments(
    gun=selected_gun,
    attachments=attachments,
)

selected_attachment_names = st.multiselect(
    f"Choose attachments - max {preview_attachment_count}",
    compatible_attachments["attachment_name"].tolist(),
    max_selections=preview_attachment_count,
)

selected_attachments = compatible_attachments[
    compatible_attachments["attachment_name"].isin(selected_attachment_names)
]

st.caption(
    f"Manual preview using {len(selected_attachment_names)}/{preview_attachment_count} attachments."
)

preview = build_loadout_preview(
    gun=selected_gun,
    selected_attachments=selected_attachments,
    enemy_health=enemy_health,
    fight_type=fight_type,
)

preview_cols = st.columns(4)
preview_cols[0].metric("Final TTK", f"{preview['raw_ttk_ms']:.0f} ms")
preview_cols[1].metric("Shots to Kill", int(preview["shots_to_kill"]))
preview_cols[2].metric("ADS", f"{preview['ads_ms']:.0f} ms")
preview_cols[3].metric("Recoil", f"{preview['recoil']:.1f}")

render_shotgun_truth_panel(pd.Series(preview))

st.dataframe(
    pd.DataFrame(
        [
            {"Stat": "Damage", "Value": round(preview["damage"], 2)},
            {"Stat": "Fire Rate", "Value": round(preview["fire_rate_rpm"], 2)},
            {"Stat": "ADS", "Value": round(preview["ads_ms"], 2)},
            {"Stat": "Sprint to Fire", "Value": round(preview["sprint_to_fire_ms"], 2)},
            {"Stat": "Recoil", "Value": round(preview["recoil"], 2)},
            {"Stat": "Bullet Velocity", "Value": round(preview["bullet_velocity"], 2)},
            {"Stat": "Range", "Value": round(preview["range_m"], 2)},
            {"Stat": "Magazine Size", "Value": round(preview["mag_size"], 2)},
            {"Stat": "Shotgun Truth Score", "Value": preview.get("shotgun_truth_score", "")},
            {"Stat": "Shotgun One-Shot Potential", "Value": preview.get("shotgun_one_shot_potential", "")},
            {"Stat": "Shotgun Two-Shot Consistency", "Value": preview.get("shotgun_two_shot_consistency", "")},
        ]
    ),
    use_container_width=True,
    hide_index=True,
)

st.divider()

with st.expander("Raw active-profile data", expanded=False):
    st.caption("Diagnostic only. The optimiser uses the active stats profile above.")
    st.subheader("Gun Data")
    st.dataframe(guns, use_container_width=True, hide_index=True)

    st.subheader("Attachment Data")
    st.dataframe(attachments, use_container_width=True, hide_index=True)

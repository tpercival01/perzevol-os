from pathlib import Path
from datetime import datetime
import json
import re

import streamlit as st

from modules.ui.perzevol_theme import inject_perzevol_theme
import pandas as pd
import time

from modules.warzone.oracle_data import (
    ATTACHMENTS_PATH,
    DEFAULT_STATS_PROFILE,
    LEGACY_STATS_PROFILE,
    SUPPORTED_STATS_PROFILES,
    filter_ttk_data_by_profile,
    load_ttk_data,
)
from modules.warzone.attachment_import import (
    parse_codmunity_attachment_html,
)
from modules.warzone.challenge_rules import (
    CHALLENGE_REQUIREMENT_OPTIONS,
    CHALLENGE_ROLE_SCOPES,
    apply_attachment_count_requirement,
    build_challenge_constraints,
    split_challenge_rules_by_scope,
)
from modules.warzone.weapon_session import (
    build_weapon_session,
    challenge_adjusted_oracle_context,
)
from modules.warzone.weapon_lab import (
    BUILD_GOALS,
    FIGHT_TYPES,
    MAP_TYPES,
    build_base_weapon_rankings,
    get_compatible_attachments,
    describe_weapon_build_data,
    build_ttk_data_warnings,
    build_attachment_verification_rows,
    build_loadout_preview,
    estimate_optimizer_combo_count,
    optimise_single_weapon_build,
    optimise_two_weapon_loadouts_for_scenario,
)
from modules.warzone.loadout_lab import (
    LOADOUT_PAIRINGS,
    PERK_PACKAGES,
    PERK_SELECTION_OPTIONS,
    WILDCARD_SELECTION_OPTIONS,
    effective_wildcard_id,
    loadout_legality_warnings,
    loadout_pairing_requires_overkill,
    optimise_full_loadouts_for_scenario,
    wildcard_id_from_selection,
    wildcard_name_from_id,
)
from modules.warzone.session_builder import prepare_session_from_mission
from modules.warzone.session_console import (
    MISSION_CHALLENGE_PRESETS,
    build_manual_mission_profile,
    render_session_brief,
)
from modules.warzone.field_planner import (
    OPTIC_PREFERENCE_OPTIONS,
    TACTICAL_GOAL_OPTIONS,
    TACTICAL_MAP_SIZE_OPTIONS,
    TACTICAL_PLAYLIST_STYLE_OPTIONS,
    build_tactical_advice,
)
from modules.warzone.meta_baselines import (
    attachment_fields as meta_attachment_fields,
    load_meta_loadouts,
    loadout_attachment_values,
    matching_meta_loadouts,
    normalise_meta_challenge_tag,
    upsert_meta_loadout,
)
from modules.warzone.ttk_data_health import build_ttk_data_health_report
from modules.warzone.best_ttk_cache import (
    BEST_TTK_CACHE_DIR,
    best_ttk_cache_key,
    clear_best_ttk_cache as clear_best_ttk_cache_files,
    load_best_ttk_cache,
    save_best_ttk_cache,
    wrap_best_ttk_session,
)

try:
    from modules.warzone.ttk_oracle_engine import (
        calculate_practical_ttk_ms,
        combo_has_attachment_conflicts,
    )
except ImportError:
    def calculate_practical_ttk_ms(stats: dict) -> float:
        return safe_float(stats.get("practical_ttk_ms", stats.get("raw_ttk_ms", 0)), 0.0)

    def combo_has_attachment_conflicts(combo) -> bool:
        return False


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


def format_optional_ms(value) -> str:
    number = safe_float(value, 0.0)
    if number <= 0:
        return "not modelled"
    return f"{number:.0f} ms"


def format_optional_number(value, decimals: int = 1) -> str:
    number = safe_float(value, 0.0)
    if number <= 0:
        return "not modelled"
    return f"{number:.{decimals}f}"


def selected_wildcard_effective_id(selection: str, *, loadout_pairing: str, attachment_count: int, build_goal: str, fight_type: str, challenge_requirements: str = "", tactical_context: dict | None = None) -> str:
    tactical_context = tactical_context or {}
    return effective_wildcard_id(
        selection,
        loadout_pairing=loadout_pairing,
        attachment_count=attachment_count,
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=challenge_requirements,
        tactical_goal=tactical_context.get("tactical_goal", "Auto from build goal / challenge"),
        playlist_style=tactical_context.get("playlist_style", "Auto"),
    )


def render_wildcard_legality_notes(*, loadout_pairing: str, wildcard_selection: str, attachment_count: int, build_goal: str, fight_type: str, challenge_requirements: str = "", tactical_context: dict | None = None) -> str:
    wildcard_id = selected_wildcard_effective_id(
        wildcard_selection,
        loadout_pairing=loadout_pairing,
        attachment_count=attachment_count,
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements=challenge_requirements,
        tactical_context=tactical_context,
    )
    wildcard_name = wildcard_name_from_id(wildcard_id)
    st.caption(f"Effective wildcard: {wildcard_name}")

    notes = loadout_legality_warnings(
        loadout_pairing=loadout_pairing,
        wildcard_id=wildcard_id,
        attachment_count=attachment_count,
    )
    for note in notes:
        st.error(note)

    if loadout_pairing_requires_overkill(loadout_pairing):
        st.warning("BO7 Multiplayer legality: this two-primary pairing is only valid with Overkill.")
    elif int(attachment_count or 0) >= 8:
        st.warning("BO7 Multiplayer legality: 8 attachments require Gunfighter and only apply to the primary weapon.")

    return wildcard_id




def render_attachment_unlock_level_editor(
    attachments: pd.DataFrame,
    stats_profile: str,
):
    """Compact editor for manually entering attachment unlock levels by weapon."""
    required_columns = [
        "attachment_id",
        "attachment_name",
        "slot",
        "stats_profile",
        "unlock_weapon",
        "unlock_level",
        "unlock_method",
    ]

    working = attachments.copy()

    for column in required_columns:
        if column not in working.columns:
            working[column] = ""

    profile_rows = working[
        working["stats_profile"].astype(str).str.strip().str.lower()
        == str(stats_profile or "").strip().lower()
    ].copy()

    weapon_options = sorted(
        value
        for value in profile_rows["unlock_weapon"].astype(str).str.strip().unique()
        if value
    )

    if not weapon_options:
        st.warning(
            "No unlock_weapon values are populated for this stats profile."
        )
        return

    unlock_level_text = (
        profile_rows["unlock_level"]
        .astype(str)
        .str.strip()
        .str.lower()
    )
    unlock_level_numeric = pd.to_numeric(
        profile_rows["unlock_level"],
        errors="coerce",
    )
    blank_level_mask = (
        unlock_level_numeric.isna()
        | unlock_level_numeric.le(0)
        | unlock_level_text.isin({"", "none", "nan", "null", "<na>"})
    )

    completed = int((~blank_level_mask).sum())
    total = len(profile_rows)

    summary_cols = st.columns(3)
    summary_cols[0].metric("Profile attachments", total)
    summary_cols[1].metric("Levels entered", completed)
    summary_cols[2].metric("Still blank", total - completed)

    selected_weapon = st.selectbox(
        "Unlock weapon",
        weapon_options,
        key="attachment_unlock_editor_weapon",
        format_func=lambda value: str(value).replace("_", " ").title(),
    )

    filter_cols = st.columns(3)

    with filter_cols[0]:
        show_mode = st.selectbox(
            "Rows",
            ["Missing levels only", "All attachments"],
            key="attachment_unlock_editor_show_mode",
        )

    weapon_rows = profile_rows[
        profile_rows["unlock_weapon"].astype(str).str.strip() == selected_weapon
    ].copy()

    slot_options = sorted(
        value
        for value in weapon_rows["slot"].astype(str).str.strip().unique()
        if value
    )

    with filter_cols[1]:
        selected_slots = st.multiselect(
            "Slots",
            slot_options,
            default=slot_options,
            key="attachment_unlock_editor_slots",
            format_func=lambda value: str(value).replace("_", " ").title(),
        )

    with filter_cols[2]:
        default_method = st.selectbox(
            "Bulk unlock method",
            [
                "weapon_level",
                "default",
                "shared",
                "armory",
                "event",
                "challenge",
                "prestige",
            ],
            index=0,
            key="attachment_unlock_editor_default_method",
        )

    if selected_slots:
        weapon_rows = weapon_rows[
            weapon_rows["slot"].astype(str).isin(selected_slots)
        ]

    if show_mode == "Missing levels only":
        weapon_level_text = (
            weapon_rows["unlock_level"]
            .astype(str)
            .str.strip()
            .str.lower()
        )
        weapon_level_numeric = pd.to_numeric(
            weapon_rows["unlock_level"],
            errors="coerce",
        )
        missing_level_mask = (
            weapon_level_numeric.isna()
            | weapon_level_numeric.le(0)
            | weapon_level_text.isin({"", "none", "nan", "null", "<na>"})
        )
        weapon_rows = weapon_rows[missing_level_mask]

    weapon_rows = weapon_rows.sort_values(
        ["slot", "attachment_name"],
        kind="stable",
    )

    if weapon_rows.empty:
        st.success("No matching attachment levels remain to be entered.")
        return

    editor_columns = [
        "attachment_id",
        "attachment_name",
        "slot",
        "unlock_level",
        "unlock_method",
    ]

    editor_rows = weapon_rows[editor_columns].copy()
    editor_rows["unlock_level"] = pd.to_numeric(
        editor_rows["unlock_level"],
        errors="coerce",
    )
    editor_rows["unlock_method"] = (
        editor_rows["unlock_method"]
        .astype(str)
        .str.strip()
        .replace(
            {
                "weapon level": "weapon_level",
                "weapon-level": "weapon_level",
            }
        )
    )
    editor_rows.loc[
        editor_rows["unlock_method"].eq(""),
        "unlock_method",
    ] = default_method

    st.caption(
        "Type levels directly into the table. Attachment name and slot are "
        "locked to prevent accidental data corruption."
    )

    edited = st.data_editor(
        editor_rows,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key=f"attachment_unlock_level_editor_{selected_weapon}_{show_mode}",
        disabled=["attachment_id", "attachment_name", "slot"],
        column_config={
            "attachment_id": st.column_config.TextColumn(
                "Attachment ID",
                width="small",
            ),
            "attachment_name": st.column_config.TextColumn(
                "Attachment",
                width="large",
            ),
            "slot": st.column_config.TextColumn(
                "Slot",
                width="small",
            ),
            "unlock_level": st.column_config.NumberColumn(
                "Unlock level",
                min_value=0,
                max_value=999,
                step=1,
                format="%d",
                required=False,
            ),
            "unlock_method": st.column_config.SelectboxColumn(
                "Unlock method",
                options=[
                    "weapon_level",
                    "default",
                    "shared",
                    "armory",
                    "event",
                    "challenge",
                    "prestige",
                ],
                required=True,
            ),
        },
    )

    action_cols = st.columns(3)

    with action_cols[0]:
        fill_method = st.button(
            "APPLY BULK METHOD",
            use_container_width=True,
            key="attachment_unlock_apply_bulk_method",
        )

    with action_cols[1]:
        clear_levels = st.button(
            "CLEAR VISIBLE LEVELS",
            use_container_width=True,
            key="attachment_unlock_clear_visible",
        )

    with action_cols[2]:
        save_changes = st.button(
            "SAVE LEVELS TO CSV",
            type="primary",
            use_container_width=True,
            key="attachment_unlock_save",
        )

    if fill_method:
        edited["unlock_method"] = default_method
        st.session_state[
            f"attachment_unlock_level_editor_{selected_weapon}_{show_mode}"
        ] = edited
        st.rerun()

    if clear_levels:
        edited["unlock_level"] = None
        st.session_state[
            f"attachment_unlock_level_editor_{selected_weapon}_{show_mode}"
        ] = edited
        st.rerun()

    if save_changes:
        latest = pd.read_csv(ATTACHMENTS_PATH, dtype=str).fillna("")

        for column in ["unlock_weapon", "unlock_level", "unlock_method"]:
            if column not in latest.columns:
                latest[column] = ""

        edited_by_id = edited.set_index("attachment_id")

        for attachment_id, row in edited_by_id.iterrows():
            match = latest["attachment_id"].astype(str) == str(attachment_id)

            level_value = row.get("unlock_level")
            if pd.isna(level_value) or str(level_value).strip() == "":
                saved_level = ""
            else:
                saved_level = str(int(float(level_value)))

            latest.loc[match, "unlock_level"] = saved_level
            latest.loc[match, "unlock_method"] = str(
                row.get("unlock_method", default_method) or default_method
            ).strip()
            latest.loc[match, "unlock_weapon"] = selected_weapon

        backup_dir = ATTACHMENTS_PATH.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / (
            f"attachments_before_unlock_edit_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

        current = pd.read_csv(ATTACHMENTS_PATH, dtype=str).fillna("")
        current.to_csv(backup_path, index=False)
        latest.to_csv(ATTACHMENTS_PATH, index=False)

        st.cache_data.clear()
        st.success(
            f"Saved {len(edited)} visible row(s) for "
            f"{selected_weapon.replace('_', ' ').title()}. "
            f"Backup: {backup_path}"
        )
        st.rerun()

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
    base_head_damage = safe_float(gun.get("head_damage_close", 0), 0.0)
    base_range = safe_float(gun.get("range_mid_m", gun.get("range_close_m", 0)), 0.0)
    base_mag = safe_float(gun.get("mag_size", 0), 0.0)
    base_ads = safe_float(gun.get("ads_ms", 0), 0.0)
    base_sprint_to_fire = safe_float(gun.get("sprint_to_fire_ms", 0), 0.0)
    base_recoil = safe_float(gun.get("recoil", 0), 0.0)

    rows = [
        ("Fire rate rpm", "fire_rate_pct", "pct", base_fire_rate, base_fire_rate),
        ("Bullet velocity", "bullet_velocity_pct", "pct", base_velocity, base_velocity),
        ("Close damage", "damage_pct", "pct", base_damage, base_damage),
        ("Close head damage", "head_damage_pct", "pct", base_head_damage, base_head_damage),
        ("Close head damage only", "head_damage_close_pct", "pct", base_head_damage, base_head_damage),
        ("Mid head damage only", "head_damage_mid_pct", "pct", 0.0, 0.0),
        ("Long head damage only", "head_damage_long_pct", "pct", 0.0, 0.0),
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
        ("Aiming idle sway", "aiming_idle_sway_pct", "pct", 0.0, 0.0),
        ("Visual recoil", "visual_recoil_pct", "pct", 0.0, 0.0),
        ("Slide to fire", "slide_to_fire_pct", "pct", 0.0, 0.0),
        ("Dive to fire", "dive_to_fire_pct", "pct", 0.0, 0.0),
        ("Hipfire spread", "hipfire_spread_pct", "pct", 0.0, 0.0),
        ("Jump hipfire spread", "jump_hipfire_spread_pct", "pct", 0.0, 0.0),
        ("Slide hipfire spread", "slide_hipfire_spread_pct", "pct", 0.0, 0.0),
        ("Dive hipfire spread", "dive_hipfire_spread_pct", "pct", 0.0, 0.0),
        ("Extra magazines", "mags_add", "add", 0.0, 0.0),
        ("Optic zoom", "optic_zoom", "add", 0.0, 0.0),
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
    values = {
        column: 0.0
        for column in ATTACHMENT_IMPORT_DATA_COLUMNS
        if column.endswith("_pct") or column.endswith("_add") or column == "optic_zoom"
    }
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
            if target_column == "mag_size_add":
                suffix = " shells"
            elif target_column == "optic_zoom":
                suffix = "x"
            else:
                suffix = "%"
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


def oracle_console_block(lines: list[str]) -> str:
    return "\n".join(f"> {line}" for line in lines[-18:])



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
    "head_damage_close",
    "head_damage_mid",
    "head_damage_long",
    "head_multiplier",
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
    "aiming_idle_sway_pct",
    "visual_recoil_pct",
    "range_profile",
    "mags_add",
    "dive_hipfire_spread_pct",
    "slide_hipfire_spread_pct",
    "jump_hipfire_spread_pct",
    "hipfire_spread_pct",
    "dive_to_fire_pct",
    "slide_to_fire_pct",
    "optic_zoom",
    "optic_type",
    "attachment_type",
    "head_damage_pct",
    "head_damage_close_pct",
    "head_damage_mid_pct",
    "head_damage_long_pct",
    "head_damage_close_add",
    "head_damage_mid_add",
    "head_damage_long_add",
    "head_damage_close",
    "head_damage_mid",
    "head_damage_long",
    "head_multiplier",
    "head_multiplier_pct",
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











def render_challenge_lock_controls(prefix: str, *, allow_role_scope: bool = False) -> tuple[list[dict], bool, str, str]:
    active = st.checkbox(
        "Challenge requirement active",
        value=False,
        key=f"{prefix}_challenge_active",
        help=(
            "Use this when a camo/challenge requires a hard condition like a suppressor, "
            "underbarrel launcher, 4.0x+ optic, 5+ attachments, or 8 attachments. "
            "The Oracle will lock the requirement first, then optimise the remaining slots."
        ),
    )

    if not active:
        return [], False, "", "Both weapons"

    cols = st.columns(3 if allow_role_scope else 2)

    with cols[0]:
        requirement = st.selectbox(
            "Challenge lock",
            CHALLENGE_REQUIREMENT_OPTIONS,
            index=0,
            key=f"{prefix}_challenge_requirement",
        )

    custom_text = ""

    with cols[1]:
        if requirement == "Specific attachment name contains":
            custom_text = st.text_input(
                "Attachment text",
                value="",
                key=f"{prefix}_challenge_custom_text",
                placeholder='Example: 4.0x, Suppressor, Long Barrel, Launcher',
            )
        else:
            st.caption("Hard lock enabled. The optimiser will build around this requirement.")

    role_scope = "Both weapons"

    if allow_role_scope:
        with cols[2]:
            role_scope = st.selectbox(
                "Apply to",
                CHALLENGE_ROLE_SCOPES,
                index=0,
                key=f"{prefix}_challenge_role_scope",
            )

    constraints = build_challenge_constraints(
        requirement=requirement,
        custom_text=custom_text,
        role_scope=role_scope,
    )
    rules = constraints.rules
    required_attachment_count = constraints.required_attachment_count
    summary = constraints.summary

    st.info(
        f"{summary}. The Oracle treats this as a hard constraint, not a soft preference."
    )

    return rules, required_attachment_count, summary, role_scope




def challenge_attachment_count_override(
    current_count: int,
    required_attachment_count,
    summary: str,
) -> int:
    try:
        required_count = int(required_attachment_count or 0)
    except (TypeError, ValueError):
        required_count = 0

    if required_count <= 0:
        return current_count

    if current_count < required_count:
        st.warning(
            f"{summary}: attachment budget overridden to {required_count} for this run."
        )

    return apply_attachment_count_requirement(current_count, required_count)


def challenge_min_attachment_count(required_attachment_count) -> int:
    try:
        return max(0, int(required_attachment_count or 0))
    except (TypeError, ValueError):
        return 0


def attachment_budget_run_summary(
    *,
    attachment_count: int,
    min_attachment_count: int = 0,
    attachment_count_mode: str = "up_to",
) -> str:
    mode = str(attachment_count_mode or "").strip().lower()
    minimum = max(0, int(min_attachment_count or 0))
    maximum = max(0, int(attachment_count or 0))

    if mode in {"up_to", "upto", "budget", "best_within_budget", "variable", "auto"}:
        if minimum > 0 and minimum < maximum:
            return f"Oracle will search builds from {minimum} to {maximum} attachments and keep whichever scores best."
        if minimum >= maximum and maximum > 0:
            return f"Oracle must use {maximum} attachment(s) because the challenge requires it."
        return f"Oracle will search builds using up to {maximum} attachments and keep whichever scores best."

    return f"Oracle will search exact {maximum}-attachment builds."



def render_tactical_context_controls() -> dict:
    st.subheader("TACTICAL CONTEXT")
    st.caption(
        "This does not change the brute-force maths yet. It tells the Oracle how the build will be used, "
        "then adds game-mode advice, optic warnings, and challenge-specific field notes."
    )

    cols = st.columns(4)

    with cols[0]:
        tactical_goal = st.selectbox(
            "Challenge / grind intent",
            TACTICAL_GOAL_OPTIONS,
            index=0,
            key="ttk_tactical_goal",
        )

    with cols[1]:
        map_size = st.selectbox(
            "Map size",
            TACTICAL_MAP_SIZE_OPTIONS,
            index=0,
            key="ttk_tactical_map_size",
        )

    with cols[2]:
        playlist_style = st.selectbox(
            "Playlist style",
            TACTICAL_PLAYLIST_STYLE_OPTIONS,
            index=0,
            key="ttk_tactical_playlist_style",
        )

    with cols[3]:
        optic_preference = st.selectbox(
            "Optic preference",
            OPTIC_PREFERENCE_OPTIONS,
            index=0,
            key="ttk_tactical_optic_preference",
            help="This is currently advisory. Use it to flag thermal or high-zoom choices before Groq gets added.",
        )

    return {
        "tactical_goal": tactical_goal,
        "map_size": map_size,
        "playlist_style": playlist_style,
        "optic_preference": optic_preference,
    }


def render_tactical_advice_panel(advice: dict):
    if not advice:
        return

    st.markdown("### Tactical Advisor")

    summary = str(advice.get("summary", "") or "").strip()
    if summary:
        st.info(summary)

    optic_note = str(advice.get("optic_note", "") or "").strip()
    if optic_note:
        st.caption(optic_note)

    cols = st.columns(3)

    with cols[0]:
        st.markdown("**Recommended modes**")
        for item in advice.get("recommended_modes", []) or []:
            st.write(f"- {item}")

    with cols[1]:
        st.markdown("**Avoid / use carefully**")
        for item in advice.get("avoid_modes", []) or []:
            st.write(f"- {item}")

    with cols[2]:
        st.markdown("**Field priorities**")
        for item in advice.get("priorities", []) or []:
            st.write(f"- {item}")

    warnings = advice.get("warnings", []) or []
    if warnings:
        with st.expander("Tactical warnings", expanded=True):
            for item in warnings:
                st.warning(item)


def _split_double_pipe_notes(value) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.split(" || ") if item.strip()]


def render_perk_loadout_advice_panel(row):
    if row is None:
        return

    summary = str(row.get("perk_recommendation_summary", "") or "").strip()
    reasons = _split_double_pipe_notes(row.get("perk_reasons", ""))
    equipment = _split_double_pipe_notes(row.get("equipment_priorities", ""))
    playstyle = _split_double_pipe_notes(row.get("playstyle_notes", ""))
    warnings = _split_double_pipe_notes(row.get("perk_warnings", ""))
    evidence_json = str(row.get("perk_lab_evidence_json", "") or "").strip()
    wildcard_name = str(row.get("wildcard_name", "") or "").strip()
    recommended_tactical = str(row.get("recommended_tactical", "") or "").strip()
    recommended_lethal = str(row.get("recommended_lethal", "") or "").strip()
    recommended_field_upgrade = str(row.get("recommended_field_upgrade", "") or "").strip()
    recommended_tactical_overclock = str(row.get("recommended_tactical_overclock", "") or "").strip()
    recommended_tactical_overclock_description = str(row.get("recommended_tactical_overclock_description", "") or "").strip()
    recommended_lethal_overclock = str(row.get("recommended_lethal_overclock", "") or "").strip()
    recommended_lethal_overclock_description = str(row.get("recommended_lethal_overclock_description", "") or "").strip()
    recommended_field_upgrade_overclock = str(row.get("recommended_field_upgrade_overclock", "") or "").strip()
    recommended_field_upgrade_overclock_description = str(row.get("recommended_field_upgrade_overclock_description", "") or "").strip()
    equipment_overclock_summary = str(row.get("equipment_overclock_summary", "") or "").strip()
    equipment_overclock_warnings = _split_double_pipe_notes(row.get("equipment_overclock_warnings", ""))
    equipment_overclock_evidence_json = str(row.get("equipment_overclock_lab_evidence_json", "") or "").strip()
    scorestreak_summary = str(row.get("scorestreak_recommendation_summary", "") or "").strip()
    recommended_scorestreaks = _split_double_pipe_notes(row.get("recommended_scorestreaks", ""))
    scorestreak_warnings = _split_double_pipe_notes(row.get("scorestreak_warnings", ""))
    scorestreak_evidence_json = str(row.get("scorestreak_lab_evidence_json", "") or "").strip()

    if not any([
        summary,
        reasons,
        equipment,
        playstyle,
        warnings,
        evidence_json,
        wildcard_name,
        scorestreak_summary,
        recommended_scorestreaks,
        equipment_overclock_summary,
        recommended_tactical_overclock,
        recommended_lethal_overclock,
        recommended_field_upgrade_overclock,
    ]):
        return

    st.markdown("### Loadout / Perk Advisor")

    if summary:
        st.info(summary)

    picks = st.columns(4)
    picks[0].metric("Wildcard", wildcard_name or "None")

    picks[1].metric("Tactical", recommended_tactical or "Field choice")
    if recommended_tactical_overclock:
        picks[1].caption(f"Overclock: {recommended_tactical_overclock}")
    if recommended_tactical_overclock_description:
        picks[1].caption(recommended_tactical_overclock_description)

    picks[2].metric("Lethal", recommended_lethal or "Field choice")
    if recommended_lethal_overclock:
        picks[2].caption(f"Overclock: {recommended_lethal_overclock}")
    if recommended_lethal_overclock_description:
        picks[2].caption(recommended_lethal_overclock_description)

    picks[3].metric("Field Upgrade", recommended_field_upgrade or "Field choice")
    if recommended_field_upgrade_overclock:
        picks[3].caption(f"Overclock: {recommended_field_upgrade_overclock}")
    if recommended_field_upgrade_overclock_description:
        picks[3].caption(recommended_field_upgrade_overclock_description)

    if equipment_overclock_summary:
        st.info(equipment_overclock_summary)

    if scorestreak_summary or recommended_scorestreaks:
        st.markdown("#### Scorestreak package")
        if scorestreak_summary:
            st.info(scorestreak_summary)
        if recommended_scorestreaks:
            streak_cols = st.columns(min(4, max(1, len(recommended_scorestreaks))))
            for index, streak in enumerate(recommended_scorestreaks):
                streak_cols[index % len(streak_cols)].metric(f"Streak {index + 1}", streak)

    cols = st.columns(3)

    with cols[0]:
        st.markdown("**Why this package**")
        for item in reasons:
            st.write(f"- {item}")

    with cols[1]:
        st.markdown("**Equipment priorities**")
        if equipment:
            for item in equipment:
                st.write(f"- {item}")
        else:
            st.caption("No specific equipment pressure detected from the current tactical context.")

    with cols[2]:
        st.markdown("**How to play it**")
        if playstyle:
            for item in playstyle:
                st.write(f"- {item}")
        else:
            st.caption("Use the build normally and field test lobby flow.")

    combined_warnings = list(warnings) + list(equipment_overclock_warnings) + list(scorestreak_warnings)
    if combined_warnings:
        with st.expander("Loadout warnings", expanded=True):
            for item in combined_warnings:
                st.warning(item)

    if equipment_overclock_evidence_json:
        with st.expander("Equipment overclock evidence packet", expanded=False):
            st.code(equipment_overclock_evidence_json, language="json")

    if scorestreak_evidence_json:
        with st.expander("Scorestreak evidence packet", expanded=False):
            st.code(scorestreak_evidence_json, language="json")

    if evidence_json:
        with st.expander("Perk/loadout evidence packet", expanded=False):
            st.code(evidence_json, language="json")



def render_secondary_slot_advice_panel(row):
    if row is None:
        return

    recommendation = str(row.get("secondary_slot_recommendation", "") or "").strip()
    role = str(row.get("secondary_field_role", "") or "").strip()
    summary = str(row.get("secondary_advisor_summary", "") or "").strip()
    source = str(row.get("secondary_slot_source", "") or "").strip()
    warnings = _split_double_pipe_notes(row.get("secondary_advisor_warnings", ""))
    evidence_json = str(row.get("secondary_advisor_evidence_json", "") or "").strip()

    if not any([recommendation, role, summary, warnings, evidence_json]):
        return

    st.markdown("### Secondary Slot Advisor")

    if summary:
        st.info(summary)

    cols = st.columns(3)
    cols[0].metric("Recommendation", recommendation or "n/a")
    cols[1].metric("Role", role or "n/a")
    cols[2].metric("Source", source.replace("_", " ").title() if source else "n/a")

    if warnings:
        with st.expander("Secondary slot warnings", expanded=True):
            for item in warnings:
                st.warning(item)

    if evidence_json:
        with st.expander("Secondary advisor evidence packet", expanded=False):
            st.code(evidence_json, language="json")


def tactical_advice_for_row(row, context: dict, prefix: str = "") -> dict:
    return build_tactical_advice(
        build_goal=context.get("build_goal", ""),
        fight_type=context.get("fight_type", ""),
        challenge_requirements=context.get("challenge_requirements", ""),
        tactical_goal=context.get("tactical_goal", "Auto from build goal / challenge"),
        map_size=context.get("map_size", "Auto"),
        playlist_style=context.get("playlist_style", "Auto"),
        optic_preference=context.get("optic_preference", "Any optic"),
        row=row,
        prefix=prefix,
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
    forced_attachment_rules=None,
    min_attachment_count: int = 0,
    attachment_count_mode: str = "exact",
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
        forced_attachment_rules=forced_attachment_rules,
        min_attachment_count=min_attachment_count,
        attachment_count_mode=attachment_count_mode,
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

    if optimiser_mode == "Exact TTK":
        st.caption(
            message
            + " Exact TTK uses a lethality-core scan plus Pareto support fill, so this is not a full comfort brute-force."
        )
    elif optimiser_mode == "Deep" and estimated_combinations > 250_000:
        st.warning(
            message
            + " This is a heavy deep pass. Use FAST PASS first unless you are validating a final Episode 2 build."
        )
    elif estimated_combinations > 50_000:
        st.info(message + " This is a serious lab pass, but still isolated from Completion Commander.")
    else:
        st.caption(message)

    with st.expander("Workload detail", expanded=False):
        detail_columns = [
            "gun_name",
            "weapon_class",
            "attachment_count",
            "attachment_count_mode",
            "min_attachment_count",
            "optimiser_mode",
            "usable_slots",
            "pool_rows_after_pruning",
            "estimated_combinations",
            "ignored_rows",
            "slot_pool_summary",
            "challenge_requirements",
            "challenge_required_slots",
            "challenge_missing",
            "buildable",
        ]
        st.dataframe(
            workload[[column for column in detail_columns if column in workload.columns]],
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
    "recommended_scorestreaks",
    "recommended_tactical",
    "recommended_lethal",
    "recommended_field_upgrade",
    "recommended_field_upgrade_overclock",
    "recommended_lethal_overclock",
    "recommended_tactical_overclock",
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
        head_damage_close = st.number_input("Close head damage", value=safe_float(seed.get("head_damage_close", 0)), step=0.01, key="gun_baseline_head_close")
        head_damage_mid = st.number_input("Mid head damage", value=safe_float(seed.get("head_damage_mid", 0)), step=0.01, key="gun_baseline_head_mid")
        head_damage_long = st.number_input("Long head damage", value=safe_float(seed.get("head_damage_long", 0)), step=0.01, key="gun_baseline_head_long")
        head_multiplier = st.number_input("Head multiplier", value=safe_float(seed.get("head_multiplier", 0)), step=0.01, key="gun_baseline_head_multiplier")

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
        "head_damage_close": head_damage_close,
        "head_damage_mid": head_damage_mid,
        "head_damage_long": head_damage_long,
        "head_multiplier": head_multiplier,
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
        "source": "Single Gun Attachment Optimiser",
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
        "recommended_scorestreaks": "",
        "recommended_tactical": "",
        "recommended_lethal": "",
        "recommended_field_upgrade": "",
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
        "recommended_scorestreaks": best.get("recommended_scorestreaks", ""),
        "recommended_tactical": best.get("recommended_tactical", ""),
        "recommended_lethal": best.get("recommended_lethal", ""),
        "recommended_field_upgrade": best.get("recommended_field_upgrade", ""),
        "recommended_tactical_overclock": best.get("recommended_tactical_overclock", ""),
        "recommended_lethal_overclock": best.get("recommended_lethal_overclock", ""),
        "recommended_field_upgrade_overclock": best.get("recommended_field_upgrade_overclock", ""),
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
        value="Single gun lab candidate. Keep if it felt good in-game.",
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
        "recommended_scorestreaks",
        "recommended_tactical",
        "recommended_lethal",
        "recommended_field_upgrade",
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

def render_attachment_list(attachments, slots=""):
    """Render optimiser attachment output safely.

    The optimiser returns attachments as a pipe-separated string:
    "Barrel A | Muzzle B | Grip C"

    Slots are also pipe-separated:
    "Barrel | Muzzle | Rear Grip"
    """
    def split_pipe_cell(value):
        if value is None:
            return []

        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]

        text = str(value or "").strip()

        if not text:
            return []

        if "|" in text:
            return [part.strip() for part in text.split("|") if part.strip()]

        return [text]

    attachment_names = split_pipe_cell(attachments)
    slot_names = split_pipe_cell(slots)

    st.markdown("#### Attachments")

    if not attachment_names:
        st.caption("No attachments selected.")
        return

    for index, attachment_name in enumerate(attachment_names):
        slot = slot_names[index] if index < len(slot_names) else "Attachment"
        st.markdown(f"{index + 1}. **{slot}:** {attachment_name}")


def _split_lab_notes(value) -> list[str]:
    text = str(value or "").strip()

    if not text:
        return []

    return [
        item.strip()
        for item in text.split(" || ")
        if item.strip()
    ]


def render_build_reasoning_panel(row, prefix: str = ""):
    summary = str(row.get(f"{prefix}build_reason_summary", "") or "").strip()
    weights = str(row.get(f"{prefix}score_weight_summary", "") or "").strip()
    optic_status = str(row.get(f"{prefix}optic_status", "") or "").strip()
    selected_notes = _split_lab_notes(row.get(f"{prefix}selected_attachment_notes", ""))
    rejected_notes = _split_lab_notes(row.get(f"{prefix}rejected_breakpoint_notes", ""))
    evidence_json = str(row.get(f"{prefix}lab_evidence_json", "") or "").strip()

    if not any([summary, weights, optic_status, selected_notes, rejected_notes, evidence_json]):
        return

    st.markdown("#### Why This Build?")

    if summary:
        st.info(summary)

    if weights:
        st.caption(f"Score weights: {weights}")

    if optic_status:
        st.caption(f"Optic status: {optic_status}")

    if selected_notes:
        with st.expander("Modelled attachment reasoning", expanded=True):
            for note in selected_notes:
                st.write(f"- {note}")

    if rejected_notes:
        with st.expander("Rejected headshot breakpoint trade-offs", expanded=True):
            for note in rejected_notes:
                st.warning(note)

    if evidence_json:
        with st.expander("Groq evidence packet", expanded=False):
            st.code(evidence_json, language="json")

def render_single_weapon_result(best: pd.Series, enemy_health: int, confidence: dict | None = None):
    st.markdown("### Optimum Build")

    depth_label = str(best.get("optimiser_mode", "") or "").strip()
    slot_limit = str(best.get("slot_candidate_limit", "") or "").strip()
    if depth_label:
        slot_text = f" | slot shortlist: {slot_limit}" if slot_limit else ""
        st.caption(f"Oracle depth: {depth_label}{slot_text}")

    if confidence:
        render_confidence_badge(confidence)

    selected_count = best.get("selected_attachment_count", "")
    attachment_budget = best.get("attachment_budget", best.get("attachment_count", ""))
    attachment_count_mode = str(best.get("attachment_count_mode", "") or "").strip()
    min_attachment_count = best.get("min_attachment_count", "")

    if selected_count != "":
        mode_text = "up-to-budget" if attachment_count_mode == "up_to" else (attachment_count_mode or "exact")
        min_text = f" | minimum {min_attachment_count}" if str(min_attachment_count or "").strip() not in {"", "0", "0.0"} else ""
        st.caption(
            f"Attachment search: {mode_text} | budget {attachment_budget} | selected {selected_count}{min_text}."
        )

    challenge_note = str(best.get("challenge_requirements", "") or "").strip()
    if challenge_note:
        st.warning(f"CHALLENGE LOCK ACTIVE: {challenge_note}")

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

    render_build_reasoning_panel(best)

    if not str(best.get("build_reason_summary", "") or "").strip():
        st.info(
            f"""
            **Why this build won:** the Oracle locked onto **{best['gun_name']}** and brute-forced legal attachment combinations for this scenario.  
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

    st.markdown("### Copyable Candidate Build")
    st.code(
        f"""
        WEAPON: {best['gun_name']}
        CLASS: {best['weapon_class']}

        CHALLENGE LOCK:
        {best.get('challenge_requirements', 'None') or 'None'}

        ATTACHMENT SEARCH:
        Budget {best.get('attachment_budget', best.get('attachment_count', ''))} | selected {best.get('selected_attachment_count', '') or 'not recorded'}

        ATTACHMENTS:
        {best['attachments']}

        SLOTS:
        {best['slots']}

        RAW TTK: {best['raw_ttk_ms']:.0f} ms
        PRACTICAL TTK: {best['practical_ttk_ms']:.0f} ms
        """.strip()
    )

    st.markdown("### Attachments")
    render_attachment_list(
        best.get("attachments", ""),
        best.get("slots", ""),
    )


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

    challenge_note = str(best.get("challenge_requirements", "") or "").strip()
    if challenge_note:
        st.warning(f"CHALLENGE LOCK ACTIVE: {challenge_note}")

    render_loadout_role_panel(best)
    render_secondary_slot_advice_panel(best)

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
        **Wildcard:** {best.get('wildcard_name', 'None')}  
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
        primary_challenge = str(best.get("primary_challenge_requirements", "") or "").strip()
        if primary_challenge:
            st.warning(f"Challenge lock: {primary_challenge}")
        render_shotgun_truth_panel(best, prefix="primary_")
        st.markdown("**Attachments:**")
        render_attachment_list(best["primary_attachments"])
        render_build_reasoning_panel(best, prefix="primary_")

    with col2:
        st.markdown("### Secondary Build")
        st.write(f"**Weapon:** {best['secondary_weapon']}")
        st.write(f"**Class:** {best['secondary_class']}")
        st.write(f"**Raw TTK:** {format_optional_ms(best.get('secondary_raw_ttk_ms', 0))}")
        st.write(f"**Practical TTK:** {format_optional_ms(best.get('secondary_practical_ttk_ms', 0))}")
        st.write(f"**Recoil:** {format_optional_number(best.get('secondary_recoil', 0), 1)}")
        st.write(f"**ADS:** {format_optional_ms(best.get('secondary_ads_ms', 0))}")
        secondary_challenge = str(best.get("secondary_challenge_requirements", "") or "").strip()
        if secondary_challenge:
            st.warning(f"Challenge lock: {secondary_challenge}")
        render_shotgun_truth_panel(best, prefix="secondary_")
        st.markdown("**Attachments:**")
        render_attachment_list(best["secondary_attachments"])
        render_build_reasoning_panel(best, prefix="secondary_")

    st.divider()

    st.markdown("### Perks")
    selected_perks = PERK_PACKAGES.get(best["perk_package"], {})

    st.write(f"**Package:** {best['perk_package']}")
    st.write(f"**Wildcard:** {best.get('wildcard_name', 'None')}")
    st.write(f"**Role:** {best.get('perk_role', 'Loadout shell')}")
    st.write(f"- Perk 1: {selected_perks.get('perk_1', '')}")
    st.write(f"- Perk 2: {selected_perks.get('perk_2', '')}")
    st.write(f"- Perk 3: {selected_perks.get('perk_3', '')}")
    st.write(f"- Perk 4: {selected_perks.get('perk_4', '')}")

    render_perk_loadout_advice_panel(best)

    st.markdown("### Copyable Loadout")

    st.code(
        f"""
PRIMARY: {best['primary_weapon']}
{best['primary_attachments']}

SECONDARY: {best['secondary_weapon']}
{best['secondary_attachments']}

WILDCARD:
{best.get('wildcard_name', 'None')}

PERKS:
{selected_perks.get('perk_1', '')}
{selected_perks.get('perk_2', '')}
{selected_perks.get('perk_3', '')}
{selected_perks.get('perk_4', '')}

TACTICAL:
{best.get('recommended_tactical', '')}
Overclock: {best.get('recommended_tactical_overclock', '')}

LETHAL:
{best.get('recommended_lethal', '')}
Overclock: {best.get('recommended_lethal_overclock', '')}

FIELD UPGRADE:
{best.get('recommended_field_upgrade', '')}
Overclock: {best.get('recommended_field_upgrade_overclock', '')}

SCORESTREAKS:
{str(best.get('recommended_scorestreaks', '') or '').replace(' || ', ' | ')}

SCENARIO:
{best['map_type']} / {best['fight_type']}
Enemy Health: {enemy_health}

CHALLENGE LOCK:
{best.get('challenge_requirements', 'None') or 'None'}
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

        known_slots = ["", "muzzle", "barrel", "magazine", "rear_grip", "stock", "laser", "fire_mod", "optic", "underbarrel"]
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






def render_two_weapon_result(two_weapon_results: pd.DataFrame, elapsed_seconds: float, enemy_health: int, confidence: dict | None = None):
    best = two_weapon_results.iloc[0]

    st.success(f"Two-gun candidate found in {elapsed_seconds:.2f} seconds.")

    depth_label = str(best.get("optimiser_mode", "") or "").strip()
    slot_limit = str(best.get("slot_candidate_limit", "") or "").strip()
    if depth_label:
        slot_text = f" | slot shortlist: {slot_limit}" if slot_limit else ""
        st.caption(f"Oracle depth: {depth_label}{slot_text}")

    st.markdown("### Optimum Two-Gun Pairing")

    if confidence:
        render_confidence_badge(confidence)

    st.caption(
        f"Primary role: {best['primary_fight_type']} / {best['primary_build_goal']} | "
        f"Secondary role: {best['secondary_fight_type']} / {best['secondary_build_goal']}"
    )

    challenge_note = str(best.get("challenge_requirements", "") or "").strip()
    if challenge_note:
        st.warning(f"CHALLENGE LOCK ACTIVE: {challenge_note}")

    render_loadout_role_panel(best)
    render_secondary_slot_advice_panel(best)

    col1, col2, col3 = st.columns(3)
    col1.metric("Pair Score", f"{best['full_loadout_score']:.3f}")
    col2.metric("Primary", best["primary_weapon"])
    col3.metric("Secondary", best["secondary_weapon"])

    st.info(
        f"""
        **Scenario:** {best['map_type']} / {best['fight_type']}  
        **Enemy health:** {enemy_health} HP  
        **Pairing:** {best['loadout_pairing']}  
        **Wildcard:** {best.get('wildcard_name', 'None')}  
        **Primary importance:** {best['primary_weight'] * 100:.0f}%  
        **Secondary importance:** {best['secondary_weight'] * 100:.0f}%  
        **Role balance:** {float(best.get('role_balance_score', 0.0) or 0.0):.3f}  

        This mode ignores perks and tests whether the two weapons cover separate jobs before a full class is built.
        """
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Primary Build")
        st.write(f"**Weapon:** {best['primary_weapon']}")
        st.write(f"**Class:** {best['primary_class']}")
        st.write(f"**Raw TTK:** {best['primary_raw_ttk_ms']:.0f} ms")
        st.write(f"**Practical TTK:** {best['primary_practical_ttk_ms']:.0f} ms")
        st.write(f"**Recoil:** {best['primary_recoil']:.1f}")
        st.write(f"**ADS:** {best['primary_ads_ms']:.0f} ms")
        primary_challenge = str(best.get("primary_challenge_requirements", "") or "").strip()
        if primary_challenge:
            st.warning(f"Challenge lock: {primary_challenge}")
        render_shotgun_truth_panel(best, prefix="primary_")
        render_attachment_list(best["primary_attachments"])
        render_build_reasoning_panel(best, prefix="primary_")

    with col2:
        st.markdown("### Secondary Build")
        st.write(f"**Weapon:** {best['secondary_weapon']}")
        st.write(f"**Class:** {best['secondary_class']}")
        st.write(f"**Raw TTK:** {format_optional_ms(best.get('secondary_raw_ttk_ms', 0))}")
        st.write(f"**Practical TTK:** {format_optional_ms(best.get('secondary_practical_ttk_ms', 0))}")
        st.write(f"**Recoil:** {format_optional_number(best.get('secondary_recoil', 0), 1)}")
        st.write(f"**ADS:** {format_optional_ms(best.get('secondary_ads_ms', 0))}")
        secondary_challenge = str(best.get("secondary_challenge_requirements", "") or "").strip()
        if secondary_challenge:
            st.warning(f"Challenge lock: {secondary_challenge}")
        render_shotgun_truth_panel(best, prefix="secondary_")
        render_attachment_list(best["secondary_attachments"])
        render_build_reasoning_panel(best, prefix="secondary_")

    st.markdown("### Copyable Pairing")
    st.code(
        f"""
PRIMARY: {best['primary_weapon']}
{best['primary_attachments']}

SECONDARY: {best['secondary_weapon']}
{best['secondary_attachments']}

SCENARIO:
{best['map_type']} / {best['fight_type']}
Enemy Health: {enemy_health}

CHALLENGE LOCK:
{best.get('challenge_requirements', 'None') or 'None'}
        """.strip()
    )


try:
    all_guns, all_attachments, data_warnings = load_and_validate_ttk_data()
except Exception as error:
    st.error(f"TTK data failed to load: {error}")
    st.stop()

st.warning(
    "UNVERIFIED DATA: TTK Oracle is a public experiment. The model can produce strong candidates, "
    "but the CSVs are still being rebuilt and every winner needs field testing."
)

profile_index = (
    SUPPORTED_STATS_PROFILES.index(DEFAULT_STATS_PROFILE)
    if DEFAULT_STATS_PROFILE in SUPPORTED_STATS_PROFILES
    else 0
)

control_cols = st.columns([1.5, 1, 1.4])

with control_cols[0]:
    active_stats_profile = st.radio(
        "Stats profile",
        SUPPORTED_STATS_PROFILES,
        index=profile_index,
        horizontal=True,
        help="The Oracle never mixes Multiplayer and Warzone stats. Existing legacy rows are marked Multiplayer until re-entered.",
    )

with control_cols[1]:
    enemy_health = st.slider(
        "Enemy health",
        min_value=100,
        max_value=400,
        value=300,
        step=50,
    )

with control_cols[2]:
    candidate_trust_filter = st.selectbox(
        "Candidate trust filter",
        CANDIDATE_TRUST_FILTERS,
        index=0,
        help=(
            "Controls which generated builds are allowed to appear as the current optimum. "
            "Use Show All Lab Candidates when you want to inspect rejected or suspect science."
        ),
    )

guns, attachments = filter_ttk_data_by_profile(
    all_guns,
    all_attachments,
    active_stats_profile,
)

weapon_names = sorted(guns["gun_name"].dropna().astype(str).tolist())

metric_cols = st.columns(4)

with metric_cols[0]:
    st.metric("Active profile", active_stats_profile)

with metric_cols[1]:
    st.metric("Profile guns", len(guns))

with metric_cols[2]:
    st.metric("Profile attachments", len(attachments))

with metric_cols[3]:
    st.metric("All attachment rows", len(all_attachments))

if data_warnings:
    with st.expander(f"⚠️ {len(data_warnings)} data quality issue(s) detected", expanded=False):
        for warning in data_warnings:
            st.warning(warning)

try:
    data_health = build_ttk_data_health_report(active_stats_profile=active_stats_profile)
except Exception as error:
    st.warning(f"Data health audit could not run: {error}")
    data_health = None

if data_health:
    health_summary = data_health.get("summary", {})
    health_issue_count = (
        int(health_summary.get("malformed_attachment_rows", 0) or 0)
        + int(health_summary.get("malformed_gun_rows", 0) or 0)
        + int(health_summary.get("conversion_risk_rows", 0) or 0)
        + int(health_summary.get("missing_conflict_columns", 0) or 0)
    )

    if health_issue_count:
        with st.expander(f"🧬 CSV HEALTH GUARD: {health_issue_count} issue(s)", expanded=False):
            summary_cols = st.columns(4)
            summary_cols[0].metric("Gun rows", health_summary.get("gun_rows", 0))
            summary_cols[1].metric("Attachment rows", health_summary.get("attachment_rows", 0))
            summary_cols[2].metric("Malformed attachments", health_summary.get("malformed_attachment_rows", 0))
            summary_cols[3].metric("Conversion risks", health_summary.get("conversion_risk_rows", 0))

            unsafe_weapons = str(health_summary.get("unsafe_weapons", "") or "").strip()
            if unsafe_weapons:
                st.error(f"Do not validate final builds for these weapons yet: {unsafe_weapons}")

            missing_conflict_columns = data_health.get("missing_conflict_columns", [])
            if missing_conflict_columns:
                st.warning(
                    "CSV schema is missing conflict columns: "
                    + ", ".join(missing_conflict_columns)
                    + ". Hardcoded conflict rules may still work, but legality should move into data."
                )

            malformed_attachments = data_health.get("malformed_attachment_rows")
            if malformed_attachments is not None and not malformed_attachments.empty:
                st.error("Malformed attachment rows can shift values into the wrong columns. Fix these before trusting that weapon.")
                st.dataframe(malformed_attachments, use_container_width=True, hide_index=True)

            malformed_guns = data_health.get("malformed_gun_rows")
            if malformed_guns is not None and not malformed_guns.empty:
                st.error("Malformed gun rows found.")
                st.dataframe(malformed_guns, use_container_width=True, hide_index=True)

            conversion_risks = data_health.get("conversion_risks")
            if conversion_risks is not None and not conversion_risks.empty:
                st.warning(
                    "These rows look like conversion, pellet, ammo or alternate-fire attachments but are not blocked. "
                    "Mark as conversion_unmodelled unless the changed profile is fully modelled."
                )
                st.dataframe(conversion_risks, use_container_width=True, hide_index=True)

            unlock_coverage = data_health.get("unlock_coverage")
            if unlock_coverage is not None and not unlock_coverage.empty:
                st.caption("Current-level reliability by weapon. Max-level theorycraft is unaffected by unknown unlocks.")
                st.dataframe(unlock_coverage, use_container_width=True, hide_index=True)

data_ready = bool(weapon_names) and not guns.empty and not attachments.empty

if not data_ready:
    st.info(
        f"LOADOUT LAB is waiting for {active_stats_profile} gun and attachment rows. "
        "Testing tools remain available below so the CSV rebuild can continue."
    )

with st.expander("Advanced tactical context", expanded=False):
    tactical_context = render_tactical_context_controls()

single_tab, operations_tab, testing_tab, two_gun_tab, full_loadout_tab = st.tabs(
    [
        "🎯 BEST TTK",
        "🛰️ MISSION PREP",
        "🧪 DATA / TESTING",
        "⚔️ TWO GUN",
        "🎒 FULL LOADOUT",
    ]
)

with operations_tab:
    st.subheader("MISSION RECEIVED")
    st.caption(
        "Temporary manual Commander input. Pick the assigned weapon and current challenge, "
        "then let Oracle prepare the exact weapon build and field plan."
    )

    if not data_ready:
        st.warning(f"No buildable {active_stats_profile} weapon and attachment data is loaded yet.")
    else:
        operation_cols = st.columns(4)

        with operation_cols[0]:
            operation_weapon = st.selectbox(
                "Commander weapon",
                weapon_names,
                index=0,
                key="operations_weapon",
            )

        with operation_cols[1]:
            operation_target = st.text_input(
                "Target",
                value="Arc Light",
                key="operations_target",
            )

        with operation_cols[2]:
            operation_preset = st.selectbox(
                "Current challenge",
                list(MISSION_CHALLENGE_PRESETS),
                index=0,
                key="operations_challenge_preset",
            )

        with operation_cols[3]:
            operation_remaining = st.number_input(
                "Remaining",
                min_value=0,
                max_value=999,
                value=80,
                step=1,
                key="operations_remaining",
            )

        default_challenge = MISSION_CHALLENGE_PRESETS[operation_preset]
        operation_challenge = st.text_input(
            "Challenge wording",
            value=default_challenge,
            key=f"operations_challenge_text_{operation_preset}",
            help="Commander will supply this automatically once the page integration is complete.",
        )

        settings_cols = st.columns(3)
        with settings_cols[0]:
            operation_health = st.number_input(
                "Enemy health",
                min_value=1,
                max_value=500,
                value=100,
                step=1,
                key="operations_enemy_health",
            )

        with settings_cols[1]:
            operation_attachment_count = st.selectbox(
                "Attachment budget",
                [5, 8],
                index=0,
                key="operations_attachment_count",
            )

        with settings_cols[2]:
            operation_candidate_limit = st.slider(
                "Fast-pass candidates per slot",
                min_value=1,
                max_value=5,
                value=3,
                key="operations_candidate_limit",
            )

        if st.button(
            "PREPARE SESSION",
            type="primary",
            use_container_width=True,
            key="operations_prepare_session",
        ):
            mission = build_manual_mission_profile(
                weapon_id=operation_weapon,
                target=operation_target,
                challenge_name=operation_challenge,
                remaining=int(operation_remaining),
                stats_profile=active_stats_profile,
                enemy_health=int(operation_health),
                attachment_count=int(operation_attachment_count),
            )

            try:
                with st.spinner("Weapon Lab running. Field plan will follow."):
                    st.session_state["oracle_session_brief"] = prepare_session_from_mission(
                        mission,
                        guns=all_guns,
                        attachments=all_attachments,
                        optimiser_mode="Fast",
                        candidate_limit_per_slot=int(operation_candidate_limit),
                        top_n=1,
                    )
            except ValueError as error:
                st.session_state.pop("oracle_session_brief", None)
                st.error(str(error))

        current_brief = st.session_state.get("oracle_session_brief")
        if current_brief is not None:
            render_session_brief(current_brief)

with testing_tab:
    st.subheader("BRUTE FORCE PASS / TESTING CONTROL")
    st.caption(
        "All beta tools live here: data audit, import staging, saved candidates, comparison, and field test logs. "
        "The playable lab is limited to the three optimiser tabs."
    )

    render_ttk_data_audit(guns, attachments, active_stats_profile)

    with st.expander(
        "Data Entry Lab: Attachment Unlock Level Editor",
        expanded=True,
    ):
        st.caption(
            "Enter attachment unlock levels one weapon at a time. "
            "Saving creates a timestamped backup before updating attachments.csv."
        )
        render_attachment_unlock_level_editor(
            all_attachments,
            active_stats_profile,
        )

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

    with st.expander("Build Compare", expanded=False):
        render_build_compare(candidate_trust_filter)

    with st.expander("Saved TTK Loadouts", expanded=False):
        render_saved_ttk_loadouts()

    with st.expander("Field Test Log", expanded=False):
        render_ttk_field_test_log()

    with st.expander("Base Weapon TTK Ranking", expanded=False):
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

SIMPLE_CHALLENGE_OPTIONS = [
    "No challenge / Best TTK",
    "Headshots",
    "Point Blank Kills",
    "One Shot Kills",
    "Longshots",
    "Hipfire Kills",
    "Close Range Kills",
    "Melee Kills",
    "5+ attachments",
    "8 attachments",
    "Any suppressor",
    "Underbarrel launcher",
    "4.0x+ optic",
    "Any optic / reticle",
]


def _simple_challenge_context(challenge: str, weapon_class: str) -> dict:
    challenge_text = str(challenge or "").strip()
    challenge_key = challenge_text.lower()

    build_goal = "Fastest TTK"
    fight_type = "Mid range"
    map_type = "Small map / Resurgence"

    if challenge_key in {"headshots", "military camo headshots"}:
        build_goal = "Military Camo Headshots"
        fight_type = "Mid range"

    elif any(term in challenge_key for term in ["point blank", "hipfire", "hip fire", "close range", "melee"]):
        build_goal = "Aggressive mobility"
        fight_type = "Close range"

    elif "one shot" in challenge_key:
        build_goal = "One-shot consistency" if "One-shot consistency" in BUILD_GOALS else "Fastest TTK"
        fight_type = "Close range" if str(weapon_class or "").strip().lower() == "shotgun" else "Mid range"

    elif "longshot" in challenge_key or "long shot" in challenge_key or "4.0x" in challenge_key or "4x" in challenge_key:
        build_goal = "Long-range consistency" if "Long-range consistency" in BUILD_GOALS else "Low recoil beam"
        fight_type = "Long range"
        map_type = "Large map / Battle Royale"

    adjusted = challenge_adjusted_oracle_context(
        build_goal=build_goal,
        fight_type=fight_type,
        challenge_requirements="" if challenge_key.startswith("no challenge") else challenge_text,
        weapon_class=weapon_class,
    )

    return {
        "build_goal": str(adjusted.get("build_goal", build_goal) or build_goal),
        "fight_type": str(adjusted.get("fight_type", fight_type) or fight_type),
        "map_type": map_type,
        "changed": bool(adjusted.get("changed")),
        "base_build_goal": build_goal,
        "base_fight_type": fight_type,
    }


def _simple_challenge_constraints(challenge: str) -> tuple[list[dict], int, str]:
    challenge_text = str(challenge or "").strip()

    if not challenge_text or challenge_text == "No challenge / Best TTK":
        return [], 0, ""

    soft_only = {
        "Headshots",
        "Point Blank Kills",
        "One Shot Kills",
        "Longshots",
        "Hipfire Kills",
        "Close Range Kills",
        "Melee Kills",
    }

    if challenge_text in soft_only:
        return [], 0, challenge_text

    constraints = build_challenge_constraints(
        requirement=challenge_text,
        custom_text="",
        role_scope="Both weapons",
    )

    return constraints.rules, constraints.required_attachment_count, constraints.summary


def _split_pipe_cell_for_ttk(value) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    if "|" in text:
        return [part.strip() for part in text.split("|") if part.strip()]
    return [text]


def _selected_build_unlock_summary(
    *,
    best: pd.Series,
    attachments: pd.DataFrame,
    current_level,
) -> dict:
    names = _split_pipe_cell_for_ttk(best.get("attachments", ""))
    name_keys = {slugify_for_ttk(name) for name in names if name}

    if not name_keys or attachments.empty or "attachment_name" not in attachments.columns:
        return {
            "required_level": "",
            "locked_now": [],
        }

    working = attachments.copy()
    working["_name_key"] = working["attachment_name"].fillna("").astype(str).apply(slugify_for_ttk)
    selected_rows = working[working["_name_key"].isin(name_keys)].copy()

    if selected_rows.empty:
        return {
            "required_level": "",
            "locked_now": [],
        }

    levels = pd.to_numeric(selected_rows.get("unlock_level", ""), errors="coerce").fillna(0)
    required_level = int(levels.max()) if not levels.empty and levels.max() > 0 else ""

    try:
        current = int(float(current_level)) if current_level not in {None, ""} else None
    except (TypeError, ValueError):
        current = None

    locked_now = []
    if current is not None:
        for _, row in selected_rows.iterrows():
            level = safe_float(row.get("unlock_level", 0), 0.0)
            if level > current:
                locked_now.append(
                    f"{row.get('attachment_name', 'Attachment')} · level {int(level)}"
                )

    return {
        "required_level": required_level,
        "locked_now": locked_now,
    }


def _selected_weapon_series(weapon_name: str) -> pd.Series | None:
    matches = guns[guns["gun_name"].astype(str).eq(str(weapon_name or ""))]
    if matches.empty:
        return None
    return matches.iloc[0]


def _selected_weapon_id(weapon_name: str) -> str:
    row = _selected_weapon_series(weapon_name)
    if row is None:
        return slugify_for_ttk(weapon_name)
    return slugify_for_ttk(row.get("gun_id", "") or weapon_name)


def _compatible_attachment_rows_for_weapon(weapon_name: str) -> pd.DataFrame:
    row = _selected_weapon_series(weapon_name)
    if row is None:
        return pd.DataFrame()
    return get_compatible_attachments(row, attachments)


def _oracle_attachment_ids_from_best(
    *,
    best: pd.Series,
    selected_weapon: str,
) -> tuple[list[str], list[str]]:
    names = _split_pipe_cell_for_ttk(best.get("attachments", ""))
    slots = _split_pipe_cell_for_ttk(best.get("slots", ""))
    compatible = _compatible_attachment_rows_for_weapon(selected_weapon)

    if compatible.empty:
        return [], ["No compatible attachment rows were found for this weapon."]

    ids: list[str] = []
    warnings: list[str] = []
    used_ids: set[str] = set()

    working = compatible.copy()
    working["_name_key"] = working["attachment_name"].apply(slugify_for_ttk) if "attachment_name" in working.columns else ""
    working["_slot_key"] = working["slot"].apply(slugify_for_ttk) if "slot" in working.columns else ""

    for index, name in enumerate(names):
        name_key = slugify_for_ttk(name)
        slot = slots[index] if index < len(slots) else ""
        slot_key = slugify_for_ttk(slot)

        candidates = working[working["_name_key"].eq(name_key)].copy()

        if slot_key and not candidates.empty:
            slot_candidates = candidates[candidates["_slot_key"].eq(slot_key)].copy()
            if not slot_candidates.empty:
                candidates = slot_candidates

        if candidates.empty:
            warnings.append(f"Could not map Oracle attachment '{name}' back to an attachment_id.")
            continue

        chosen = candidates.iloc[0]
        attachment_id = str(chosen.get("attachment_id", "") or "").strip()

        if not attachment_id:
            warnings.append(f"Oracle attachment '{name}' has no attachment_id.")
            continue

        if attachment_id in used_ids:
            warnings.append(f"Duplicate attachment_id skipped: {attachment_id}.")
            continue

        ids.append(attachment_id)
        used_ids.add(attachment_id)

    return ids, warnings


def render_save_oracle_as_meta_button(
    *,
    best: pd.Series,
    selected_weapon: str,
    simple_challenge: str,
    label: str,
) -> None:
    attachment_ids, warnings = _oracle_attachment_ids_from_best(
        best=best,
        selected_weapon=selected_weapon,
    )

    if warnings:
        with st.expander("Oracle to Meta mapping warnings", expanded=False):
            for warning in warnings:
                st.warning(warning)

    if not attachment_ids:
        st.caption("Oracle build cannot be saved as a meta baseline because no attachment IDs were mapped.")
        return

    challenge_tag = normalise_meta_challenge_tag(simple_challenge)
    weapon_row = _selected_weapon_series(selected_weapon)
    weapon_id = _selected_weapon_id(selected_weapon)

    save_key = (
        f"save_oracle_meta_{slugify_for_ttk(selected_weapon)}_"
        f"{challenge_tag}_{label.lower().replace(' ', '_')}"
    )

    if st.button(
        f"SAVE {label.upper()} AS META BASELINE",
        use_container_width=True,
        key=save_key,
    ):
        row = {
            "loadout_name": f"{selected_weapon} Oracle {label}",
            "source": "oracle",
            "stats_profile": active_stats_profile,
            "weapon_id": weapon_id,
            "weapon_name": str(weapon_row.get("gun_name", selected_weapon) if weapon_row is not None else selected_weapon),
            "challenge_tag": challenge_tag,
            "enemy_health": str(int(enemy_health)),
            "notes": "Saved from Oracle BEST TTK result.",
            "verification_status": "oracle_generated",
        }

        for field, attachment_id in zip(meta_attachment_fields(), attachment_ids):
            row[field] = attachment_id

        upsert_meta_loadout(row)
        st.success("Oracle build saved as a meta baseline.")
        st.rerun()


def _attachment_display_label(row: pd.Series) -> str:
    name = str(row.get("attachment_name", "") or "").strip()
    slot = str(row.get("slot", "") or "").strip()
    attachment_id = str(row.get("attachment_id", "") or "").strip()

    bits = [name]
    if slot:
        bits.append(slot)
    if attachment_id:
        bits.append(attachment_id)

    return " · ".join(bit for bit in bits if bit)


def _meta_attachment_choice_maps(compatible: pd.DataFrame) -> tuple[list[str], dict[str, str]]:
    if compatible.empty:
        return [""], {"": ""}

    working = compatible.copy()
    working["_display"] = working.apply(_attachment_display_label, axis=1)
    working = working.sort_values(["slot", "attachment_name"], kind="stable")

    display_to_id = {"": ""}
    options = [""]

    for _, row in working.iterrows():
        display = str(row.get("_display", "") or "").strip()
        attachment_id = str(row.get("attachment_id", "") or "").strip()

        if not display or not attachment_id:
            continue

        if display in display_to_id:
            continue

        display_to_id[display] = attachment_id
        options.append(display)

    return options, display_to_id


def _resolve_meta_attachment_rows(
    attachment_values: list[str],
    compatible: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    if compatible.empty:
        return pd.DataFrame(), list(attachment_values)

    working = compatible.copy()
    working["_id_key"] = working.get("attachment_id", "").astype(str).apply(slugify_for_ttk)
    working["_name_key"] = working.get("attachment_name", "").astype(str).apply(slugify_for_ttk)

    selected_rows = []
    missing = []
    used_indices = set()

    for value in attachment_values:
        raw = str(value or "").strip()
        if not raw:
            continue

        key = slugify_for_ttk(raw)
        matches = working[
            working["_id_key"].eq(key)
            | working["_name_key"].eq(key)
        ]

        if matches.empty:
            missing.append(raw)
            continue

        match_index = matches.index[0]
        if match_index in used_indices:
            continue

        used_indices.add(match_index)
        selected_rows.append(working.loc[match_index].drop(labels=["_id_key", "_name_key"], errors="ignore"))

    if not selected_rows:
        return pd.DataFrame(), missing

    return pd.DataFrame(selected_rows).reset_index(drop=True), missing


def _preview_meta_loadout(
    *,
    meta_row: pd.Series,
    selected_weapon: str,
    build_goal: str,
    fight_type: str,
) -> dict:
    gun = _selected_weapon_series(selected_weapon)
    compatible = _compatible_attachment_rows_for_weapon(selected_weapon)
    attachment_values = loadout_attachment_values(meta_row)
    selected_attachments, missing = _resolve_meta_attachment_rows(attachment_values, compatible)

    warnings = []
    if missing:
        warnings.append("Missing attachment row(s): " + ", ".join(missing))

    if selected_attachments.empty:
        warnings.append("No matched attachments for this baseline.")

    combo_dicts = [row.to_dict() for _, row in selected_attachments.iterrows()]
    illegal_conflict = combo_has_attachment_conflicts(combo_dicts) if combo_dicts else False
    if illegal_conflict:
        warnings.append("Illegal attachment conflict detected.")

    duplicate_slots = []
    if not selected_attachments.empty and "slot" in selected_attachments.columns:
        slot_counts = selected_attachments["slot"].astype(str).str.strip().value_counts()
        duplicate_slots = [slot for slot, count in slot_counts.items() if slot and count > 1]
        if duplicate_slots:
            warnings.append("Duplicate slot(s): " + ", ".join(duplicate_slots))

    if gun is None:
        return {
            "valid": False,
            "warnings": ["Weapon row was not found."],
            "attachments": " | ".join(attachment_values),
        }

    preview = build_loadout_preview(
        gun,
        selected_attachments,
        enemy_health=int(enemy_health),
        fight_type=fight_type,
        build_goal=build_goal,
    )

    preview["damage_per_mag"] = safe_float(preview.get("damage", 0), 0.0) * safe_float(preview.get("mag_size", 0), 0.0)
    preview["practical_ttk_ms"] = calculate_practical_ttk_ms(preview)
    preview["selected_attachment_count"] = len(selected_attachments)
    preview["attachments"] = " | ".join(
        str(row.get("attachment_name", "") or "").strip()
        for _, row in selected_attachments.iterrows()
        if str(row.get("attachment_name", "") or "").strip()
    )
    preview["slots"] = " | ".join(
        str(row.get("slot", "") or "").strip()
        for _, row in selected_attachments.iterrows()
        if str(row.get("slot", "") or "").strip()
    )
    preview["meta_loadout_id"] = str(meta_row.get("meta_loadout_id", "") or "")
    preview["loadout_name"] = str(meta_row.get("loadout_name", "") or "")
    preview["source"] = str(meta_row.get("source", "") or "")
    preview["verification_status"] = str(meta_row.get("verification_status", "") or "")
    preview["warnings"] = warnings
    preview["valid"] = not warnings

    return preview


def render_meta_baseline_editor(
    *,
    selected_weapon: str,
    simple_challenge: str,
):
    st.markdown("### Meta Baselines")
    st.caption(
        "Save known season builds here. The Oracle will compare against them after a BEST TTK run, "
        "but it will not silently replace the Oracle result."
    )

    weapon_row = _selected_weapon_series(selected_weapon)
    weapon_id = _selected_weapon_id(selected_weapon)
    challenge_tag = normalise_meta_challenge_tag(simple_challenge)
    compatible = _compatible_attachment_rows_for_weapon(selected_weapon)
    options, display_to_id = _meta_attachment_choice_maps(compatible)

    existing = matching_meta_loadouts(
        load_meta_loadouts(),
        stats_profile=active_stats_profile,
        weapon_id=weapon_id,
        weapon_name=selected_weapon,
        challenge_tag=challenge_tag,
        enemy_health=int(enemy_health),
    )

    if not existing.empty:
        with st.expander("Saved baselines for this weapon/challenge", expanded=False):
            display_columns = [
                "loadout_name",
                "source",
                "challenge_tag",
                "enemy_health",
                "verification_status",
                *meta_attachment_fields(),
                "notes",
            ]
            st.dataframe(
                existing[[column for column in display_columns if column in existing.columns]],
                use_container_width=True,
                hide_index=True,
            )

    with st.form(f"meta_baseline_form_{weapon_id}_{challenge_tag}"):
        form_cols = st.columns([1.2, 1, 1])
        with form_cols[0]:
            loadout_name = st.text_input(
                "Loadout name",
                value=f"{selected_weapon} meta",
                key=f"meta_loadout_name_{weapon_id}_{challenge_tag}",
            )
        with form_cols[1]:
            source = st.text_input(
                "Source",
                value="manual",
                key=f"meta_loadout_source_{weapon_id}_{challenge_tag}",
            )
        with form_cols[2]:
            verification_status = st.selectbox(
                "Status",
                ["manual", "field_tested", "community", "needs_verification"],
                index=0,
                key=f"meta_loadout_status_{weapon_id}_{challenge_tag}",
            )

        selected_ids = []
        attachment_cols = st.columns(4)
        for index, field in enumerate(meta_attachment_fields(), start=1):
            with attachment_cols[(index - 1) % 4]:
                choice = st.selectbox(
                    f"Attachment {index}",
                    options,
                    index=0,
                    key=f"meta_{weapon_id}_{challenge_tag}_{field}",
                )
                attachment_id = display_to_id.get(choice, "")
                if attachment_id:
                    selected_ids.append(attachment_id)

        notes = st.text_area(
            "Notes",
            value="",
            height=80,
            key=f"meta_loadout_notes_{weapon_id}_{challenge_tag}",
        )

        save_meta = st.form_submit_button("SAVE META BASELINE", use_container_width=True)

    if save_meta:
        if not selected_ids:
            st.warning("Pick at least one attachment before saving a meta baseline.")
            return

        row = {
            "loadout_name": loadout_name or f"{selected_weapon} meta",
            "source": source or "manual",
            "stats_profile": active_stats_profile,
            "weapon_id": weapon_id,
            "weapon_name": str(weapon_row.get("gun_name", selected_weapon) if weapon_row is not None else selected_weapon),
            "challenge_tag": challenge_tag,
            "enemy_health": str(int(enemy_health)),
            "notes": notes,
            "verification_status": verification_status,
        }

        for field, attachment_id in zip(meta_attachment_fields(), selected_ids):
            row[field] = attachment_id

        upsert_meta_loadout(row)
        st.success("Meta baseline saved.")
        st.rerun()


def render_meta_baseline_comparison(
    *,
    selected_weapon: str,
    simple_challenge: str,
    build_goal: str,
    fight_type: str,
    oracle_best: pd.Series,
):
    weapon_id = _selected_weapon_id(selected_weapon)
    challenge_tag = normalise_meta_challenge_tag(simple_challenge)

    matches = matching_meta_loadouts(
        load_meta_loadouts(),
        stats_profile=active_stats_profile,
        weapon_id=weapon_id,
        weapon_name=selected_weapon,
        challenge_tag=challenge_tag,
        enemy_health=int(enemy_health),
    )

    if matches.empty:
        return

    oracle_raw = safe_float(oracle_best.get("raw_ttk_ms", 0), 0.0)
    oracle_practical = safe_float(oracle_best.get("practical_ttk_ms", 0), 0.0)

    rows = []
    for _, meta_row in matches.iterrows():
        preview = _preview_meta_loadout(
            meta_row=meta_row,
            selected_weapon=selected_weapon,
            build_goal=build_goal,
            fight_type=fight_type,
        )

        raw_ttk = safe_float(preview.get("raw_ttk_ms", 0), 0.0)
        practical_ttk = safe_float(preview.get("practical_ttk_ms", 0), 0.0)

        rows.append(
            {
                "Loadout": preview.get("loadout_name", ""),
                "Source": preview.get("source", ""),
                "Status": preview.get("verification_status", ""),
                "Meta raw TTK": raw_ttk,
                "Oracle raw Δ": raw_ttk - oracle_raw if raw_ttk and oracle_raw else "",
                "Meta practical TTK": practical_ttk,
                "Oracle practical Δ": practical_ttk - oracle_practical if practical_ttk and oracle_practical else "",
                "Count": preview.get("selected_attachment_count", 0),
                "Attachments": preview.get("attachments", ""),
                "Warnings": " | ".join(preview.get("warnings", [])),
            }
        )

    st.markdown("## ORACLE VS META")
    st.caption("Positive delta means the saved meta baseline is slower than the Oracle result.")

    comparison = pd.DataFrame(rows)
    st.dataframe(
        comparison,
        use_container_width=True,
        hide_index=True,
    )


def _run_best_ttk_weapon_session(
    *,
    selected_weapon: str,
    build_goal: str,
    fight_type: str,
    map_type: str,
    challenge_summary: str,
    challenge_rules: list[dict],
    min_attachment_count: int,
    attachment_unlock_mode: str,
    console_lines: list[str] | None = None,
):
    console_lines = console_lines if console_lines is not None else []

    cache_key = best_ttk_cache_key(
        selected_weapon=selected_weapon,
        build_goal=build_goal,
        fight_type=fight_type,
        map_type=map_type,
        challenge_summary=challenge_summary,
        challenge_rules=challenge_rules,
        min_attachment_count=min_attachment_count,
        attachment_unlock_mode=attachment_unlock_mode,
        stats_profile=active_stats_profile,
        enemy_health=enemy_health,
        guns_path=MASTER_GUNS_PATH,
        attachments_path=MASTER_ATTACHMENTS_PATH,
    )

    cached = load_best_ttk_cache(cache_key)
    if cached is not None:
        console_lines.append(f"CACHE HIT {attachment_unlock_mode}: {selected_weapon}")
        return cached

    console_lines.append(f"CACHE MISS {attachment_unlock_mode}: scanning {selected_weapon}")
    console_lines.append(f"route={build_goal} | fight={fight_type} | health={enemy_health}")
    console_lines.append("mode=Exact TTK Pareto support | core first, support frontier second")

    session = build_weapon_session(
        guns=guns,
        attachments=attachments,
        weapon_name=selected_weapon,
        stats_profile=active_stats_profile,
        map_type=map_type,
        fight_type=fight_type,
        build_goal=build_goal,
        enemy_health=enemy_health,
        attachment_count=8,
        top_n=10,
        optimiser_mode="Exact TTK",
        candidate_limit_per_slot=0,
        forced_attachment_rules=challenge_rules,
        challenge_requirements=challenge_summary,
        min_attachment_count=min_attachment_count,
        attachment_count_mode="up_to",
        attachment_unlock_mode=attachment_unlock_mode,
        target_weapon_level=None,
    )

    save_best_ttk_cache(cache_key, session)
    console_lines.append(f"CACHE SAVED {attachment_unlock_mode}: {cache_key[:12]}")

    return wrap_best_ttk_session(
        session,
        cache_status="MISS_SAVED",
        cache_key=cache_key,
    )

def _render_best_ttk_session(
    *,
    label: str,
    session,
    selected_weapon: str,
    context: dict,
):
    results = session.results

    if results.empty:
        st.error(f"{label}: no valid build found.")
        return None

    best = pd.Series(results.iloc[0])
    availability = session.availability.to_dict() if getattr(session, "availability", None) is not None else {}
    current_level = availability.get("current_level")
    max_level = availability.get("max_level")
    effective_level = availability.get("effective_level")

    unlock_summary = _selected_build_unlock_summary(
        best=best,
        attachments=attachments,
        current_level=current_level,
    )

    st.markdown(f"## {label}")
    metric_cols = st.columns(5)
    metric_cols[0].metric("Raw TTK", f"{safe_float(best.get('raw_ttk_ms', 0), 0.0):.0f} ms")
    metric_cols[1].metric("Practical TTK", f"{safe_float(best.get('practical_ttk_ms', 0), 0.0):.0f} ms")
    metric_cols[2].metric("Damage", f"{safe_float(best.get('damage', 0), 0.0):.0f}")
    metric_cols[3].metric("Selected", f"{int(safe_float(best.get('selected_attachment_count', best.get('attachment_count', 0)), 0.0))} / 8")
    metric_cols[4].metric("Needed level", unlock_summary["required_level"] or "unknown")

    level_bits = []
    if current_level not in {None, ""}:
        level_bits.append(f"current level {current_level}")
    if max_level not in {None, ""}:
        level_bits.append(f"unlock cap {max_level}")
    if effective_level not in {None, ""}:
        level_bits.append(f"effective {effective_level}")
    if level_bits:
        st.caption("Attachment availability: " + " · ".join(level_bits))

    cache_status = str(getattr(session, "cache_status", "") or "").strip()
    cache_key = str(getattr(session, "cache_key", "") or "").strip()
    if cache_status == "HIT":
        st.success(f"Loaded from BEST TTK cache · {cache_key[:12]}")
    elif cache_status == "MISS_SAVED":
        st.caption(f"Saved BEST TTK cache · {cache_key[:12]}")

    locked_now = unlock_summary.get("locked_now", [])
    if locked_now:
        with st.expander("Locked attachments in this build", expanded=True):
            for item in locked_now:
                st.warning(item)

    render_single_weapon_result(
        best,
        int(enemy_health),
        single_build_confidence(best, context),
    )

    render_tactical_advice_panel(
        tactical_advice_for_row(best, context)
    )

    return best


with single_tab:
    st.subheader("BEST TTK")
    st.caption(
        "Pick a weapon, choose the challenge, then press BEST TTK. "
        "The Oracle uses an up-to-8 attachment budget and only forces exact counts when the challenge requires it."
    )

    if not data_ready:
        st.warning(f"No buildable {active_stats_profile} weapon and attachment data is loaded yet.")
    else:
        simple_cols = st.columns([1.4, 1.2, 1.2])

        with simple_cols[0]:
            selected_single_weapon = st.selectbox(
                "Weapon",
                weapon_names,
                index=0,
                key="simple_best_ttk_weapon",
            )

        with simple_cols[1]:
            simple_challenge = st.selectbox(
                "Challenge",
                SIMPLE_CHALLENGE_OPTIONS,
                index=0,
                key="simple_best_ttk_challenge",
            )

        with simple_cols[2]:
            level_mode = st.selectbox(
                "Weapon level mode",
                [
                    "Current level only",
                    "Max level theorycraft",
                    "Compare current vs max",
                ],
                index=0,
                key="simple_best_ttk_level_mode",
            )

        utility_cols = st.columns([1, 1, 3])
        with utility_cols[0]:
            show_oracle_console = st.checkbox(
                "Show Oracle Console",
                value=False,
                key="simple_best_ttk_show_console",
            )
        with utility_cols[1]:
            clear_best_ttk_cache = st.button(
                "CLEAR CACHE",
                use_container_width=True,
                key="simple_best_ttk_clear_cache",
            )

        if clear_best_ttk_cache:
            removed_cache_files = clear_best_ttk_cache_files()
            st.session_state.pop("ttk_simple_best_ttk", None)
            st.success(f"Cleared BEST TTK cache ({removed_cache_files} file(s)).")
            st.rerun()

        selected_single_gun_row = guns[guns["gun_name"] == selected_single_weapon]
        selected_single_weapon_class = (
            str(selected_single_gun_row.iloc[0].get("weapon_class", "") or "")
            if not selected_single_gun_row.empty
            else ""
        )

        single_challenge_rules, challenge_required_count, single_challenge_summary = _simple_challenge_constraints(
            simple_challenge
        )

        single_min_attachment_count = challenge_min_attachment_count(challenge_required_count)
        single_context = _simple_challenge_context(
            simple_challenge,
            selected_single_weapon_class,
        )

        single_effective_build_goal = single_context["build_goal"]
        single_effective_fight_type = single_context["fight_type"]
        single_map_type = single_context["map_type"]

        st.info(
            f"Oracle route: {single_effective_build_goal} · {single_effective_fight_type} · "
            "up to 8 attachments."
        )

        st.caption(
            attachment_budget_run_summary(
                attachment_count=8,
                min_attachment_count=single_min_attachment_count,
                attachment_count_mode="up_to",
            )
        )

        if single_challenge_summary:
            st.caption(f"Challenge: {single_challenge_summary}")

        with st.expander("Meta Baselines", expanded=False):
            render_meta_baseline_editor(
                selected_weapon=selected_single_weapon,
                simple_challenge=simple_challenge,
            )

        render_optimizer_workload_estimate(
            guns_subset=guns[guns["gun_name"] == selected_single_weapon],
            attachments=attachments,
            map_type=single_map_type,
            fight_type=single_effective_fight_type,
            build_goal=single_effective_build_goal,
            enemy_health=enemy_health,
            attachment_count=8,
            optimiser_mode="Exact TTK",
            slot_candidate_limit=0,
            forced_attachment_rules=single_challenge_rules,
            min_attachment_count=single_min_attachment_count,
            attachment_count_mode="up_to",
        )

        run_best_ttk = st.button(
            "BEST TTK",
            type="primary",
            use_container_width=True,
            key="simple_best_ttk_button",
        )

        if run_best_ttk:
            start_time = time.perf_counter()
            runs = {}
            console_lines = [
                f"BOOT ORACLE: {selected_single_weapon}",
                f"CHALLENGE: {simple_challenge}",
                f"LEVEL MODE: {level_mode}",
                f"PROFILE: {active_stats_profile}",
            ]
            console_placeholder = st.empty()

            if show_oracle_console:
                console_placeholder.code(
                    oracle_console_block(console_lines),
                    language="text",
                )

            try:
                with st.spinner(f"Oracle is running objective-exact BEST TTK for {selected_single_weapon}..."):
                    if level_mode in {"Current level only", "Compare current vs max"}:
                        runs["current"] = _run_best_ttk_weapon_session(
                            selected_weapon=selected_single_weapon,
                            build_goal=single_effective_build_goal,
                            fight_type=single_effective_fight_type,
                            map_type=single_map_type,
                            challenge_summary=single_challenge_summary,
                            challenge_rules=single_challenge_rules,
                            min_attachment_count=single_min_attachment_count,
                            attachment_unlock_mode="current_level",
                            console_lines=console_lines,
                        )
                        if show_oracle_console:
                            console_placeholder.code(
                                oracle_console_block(console_lines),
                                language="text",
                            )

                    if level_mode in {"Max level theorycraft", "Compare current vs max"}:
                        runs["max"] = _run_best_ttk_weapon_session(
                            selected_weapon=selected_single_weapon,
                            build_goal=single_effective_build_goal,
                            fight_type=single_effective_fight_type,
                            map_type=single_map_type,
                            challenge_summary=single_challenge_summary,
                            challenge_rules=single_challenge_rules,
                            min_attachment_count=single_min_attachment_count,
                            attachment_unlock_mode="max_level",
                            console_lines=console_lines,
                        )
                        if show_oracle_console:
                            console_placeholder.code(
                                oracle_console_block(console_lines),
                                language="text",
                            )

            except ValueError as error:
                st.error(str(error))
                console_lines.append(f"ERROR: {error}")
                runs = {}

            elapsed_seconds = time.perf_counter() - start_time
            console_lines.append(f"DONE: {elapsed_seconds:.2f}s")

            if show_oracle_console:
                console_placeholder.code(
                    oracle_console_block(console_lines),
                    language="text",
                )

            st.session_state.ttk_simple_best_ttk = {
                "runs": runs,
                "elapsed_seconds": elapsed_seconds,
                "selected_weapon": selected_single_weapon,
                "mode_profile": f"{active_stats_profile} | {single_map_type} | Best TTK",
                "stats_profile": active_stats_profile,
                "fight_type": single_effective_fight_type,
                "build_goal": single_effective_build_goal,
                "enemy_health": enemy_health,
                "attachment_budget": "Up to 8",
                "attachment_count": 8,
                "min_attachment_count": single_min_attachment_count,
                "attachment_count_mode": "up_to",
                "optimiser_depth": "Exact TTK",
                "slot_candidate_limit": "",
                "perk_package": "",
                "challenge_requirements": single_challenge_summary,
                "simple_challenge": simple_challenge,
                "oracle_console_lines": console_lines,
                **tactical_context,
            }

        last_simple_build = st.session_state.get("ttk_simple_best_ttk")

        if last_simple_build:
            runs = last_simple_build.get("runs", {})
            st.caption(
                f"Last run: {last_simple_build.get('selected_weapon', selected_single_weapon)} · "
                f"{last_simple_build.get('build_goal', '')} · "
                f"{last_simple_build.get('fight_type', '')} · "
                f"{safe_float(last_simple_build.get('elapsed_seconds', 0), 0.0):.2f}s"
            )

            if show_oracle_console and last_simple_build.get("oracle_console_lines"):
                with st.expander("Oracle Console", expanded=True):
                    st.code(
                        oracle_console_block(last_simple_build.get("oracle_console_lines", [])),
                        language="text",
                    )

            current_best = None
            max_best = None

            if "current" in runs:
                current_best = _render_best_ttk_session(
                    label="BEST CURRENT BUILD",
                    session=runs["current"],
                    selected_weapon=selected_single_weapon,
                    context=last_simple_build,
                )

            if "max" in runs:
                max_best = _render_best_ttk_session(
                    label="BEST MAX-LEVEL BUILD",
                    session=runs["max"],
                    selected_weapon=selected_single_weapon,
                    context=last_simple_build,
                )

            if current_best is not None and max_best is not None:
                current_ttk = safe_float(current_best.get("practical_ttk_ms", 0), 0.0)
                max_ttk = safe_float(max_best.get("practical_ttk_ms", 0), 0.0)
                if current_ttk > 0 and max_ttk > 0:
                    gain = current_ttk - max_ttk
                    st.markdown("## LEVEL-UP VALUE")
                    st.metric(
                        "Max-level improvement",
                        f"{gain:.0f} ms",
                        help="Positive means the max-level build is faster than the current-level build.",
                    )

            comparison_best = max_best if max_best is not None else current_best
            if comparison_best is not None:
                comparison_weapon = last_simple_build.get("selected_weapon", selected_single_weapon)
                comparison_challenge = last_simple_build.get("simple_challenge", simple_challenge)

                render_meta_baseline_comparison(
                    selected_weapon=comparison_weapon,
                    simple_challenge=comparison_challenge,
                    build_goal=last_simple_build.get("build_goal", single_effective_build_goal),
                    fight_type=last_simple_build.get("fight_type", single_effective_fight_type),
                    oracle_best=comparison_best,
                )

                with st.expander("Save Oracle result", expanded=False):
                    render_save_oracle_as_meta_button(
                        best=comparison_best,
                        selected_weapon=comparison_weapon,
                        simple_challenge=comparison_challenge,
                        label="Oracle build",
                    )

            if runs:
                first_session = runs.get("current") or runs.get("max")
                result_table = first_session.results if first_session is not None else pd.DataFrame()
                if result_table is not None and not result_table.empty:
                    st.markdown("### Candidate builds")
                    single_result_columns = available_columns(
                        result_table,
                        [
                            "oracle_score",
                            "gun_name",
                            "raw_ttk_ms",
                            "practical_ttk_ms",
                            "damage",
                            "shots_to_kill",
                            "one_shot_margin",
                            "shotgun_best_close_route",
                            "selected_attachment_count",
                            "slots",
                            "attachments",
                            "build_reason_summary",
                        ],
                    )
                    st.dataframe(
                        result_table[single_result_columns],
                        use_container_width=True,
                        hide_index=True,
                    )

with two_gun_tab:
    st.subheader("TWO GUN OPTIMISER")
    st.caption(
        "Find the best two-primary weapon pairing before perks enter the conversation. "
        "In BO7 Multiplayer this is only legal when the Overkill wildcard is active."
    )

    if not data_ready:
        st.warning(f"No buildable {active_stats_profile} weapon and attachment data is loaded yet.")
    else:
        two_cols = st.columns(5)

        with two_cols[0]:
            overkill_pairing_options = [
                pairing for pairing in LOADOUT_PAIRINGS
                if loadout_pairing_requires_overkill(pairing)
            ] or LOADOUT_PAIRINGS
            two_loadout_pairing = st.selectbox(
                "Loadout pairing",
                overkill_pairing_options,
                index=0,
                key="two_gun_pairing",
                help="Two-gun BO7 Multiplayer builds require Overkill because the secondary is another primary weapon.",
            )

        with two_cols[1]:
            two_wildcard_selection = st.selectbox(
                "Wildcard",
                WILDCARD_SELECTION_OPTIONS,
                index=WILDCARD_SELECTION_OPTIONS.index("Overkill") if "Overkill" in WILDCARD_SELECTION_OPTIONS else 0,
                key="two_gun_wildcard",
            )

        with two_cols[2]:
            two_map_type = st.selectbox(
                "Map type",
                MAP_TYPES,
                index=0,
                key="two_gun_map_type",
            )

        with two_cols[3]:
            two_fight_type = st.selectbox(
                "Fight type",
                FIGHT_TYPES,
                index=0,
                key="two_gun_fight_type",
            )

        with two_cols[4]:
            two_build_goal = st.selectbox(
                "Build goal",
                BUILD_GOALS,
                index=0,
                key="two_gun_build_goal",
            )

        two_cols = st.columns(4)

        with two_cols[0]:
            two_ruleset = st.selectbox(
                "Attachment ruleset",
                ATTACHMENT_RULESETS,
                index=0,
                key="two_gun_attachment_ruleset",
            )

        with two_cols[1]:
            two_attachment_budget = st.selectbox(
                "Attachment budget",
                ATTACHMENT_BUDGET_PROFILES,
                index=0,
                key="two_gun_attachment_budget",
            )

        with two_cols[2]:
            two_results_count = st.slider(
                "Pairing candidates",
                min_value=5,
                max_value=25,
                value=10,
                step=5,
                key="two_gun_results",
            )

        with two_cols[3]:
            two_depth_profile = st.selectbox(
                "Optimiser depth",
                OPTIMISER_DEPTH_PROFILES,
                index=0,
                key="two_gun_optimiser_depth",
            )

        two_attachment_count = attachment_count_for_profile(
            two_ruleset,
            two_attachment_budget,
        )
        two_optimiser_mode = optimiser_mode_for_profile(two_depth_profile)

        two_depth_cols = st.columns([1, 2])

        with two_depth_cols[0]:
            two_slot_candidate_limit = st.slider(
                "Fast-pass candidates per slot",
                min_value=1,
                max_value=5,
                value=3,
                step=1,
                key="two_gun_slot_candidate_limit",
            )

        with two_depth_cols[1]:
            st.caption(attachment_budget_summary(two_ruleset, two_attachment_budget))
            st.caption(optimiser_depth_summary(two_depth_profile, two_slot_candidate_limit))

        two_challenge_rules, two_force_eight, two_challenge_summary, two_challenge_scope = render_challenge_lock_controls(
            "two_gun",
            allow_role_scope=True,
        )
        two_attachment_count = challenge_attachment_count_override(
            two_attachment_count,
            two_force_eight,
            two_challenge_summary,
        )
        two_primary_challenge_rules, two_secondary_challenge_rules = split_challenge_rules_by_scope(
            two_challenge_rules,
            two_challenge_scope,
        )

        two_effective_wildcard_id = render_wildcard_legality_notes(
            loadout_pairing=two_loadout_pairing,
            wildcard_selection=two_wildcard_selection,
            attachment_count=two_attachment_count,
            build_goal=two_build_goal,
            fight_type=two_fight_type,
            challenge_requirements=two_challenge_summary,
            tactical_context=tactical_context,
        )

        render_optimizer_workload_estimate(
            guns_subset=guns,
            attachments=attachments,
            map_type=two_map_type,
            fight_type=two_fight_type,
            build_goal=two_build_goal,
            enemy_health=enemy_health,
            attachment_count=two_attachment_count,
            optimiser_mode=two_optimiser_mode,
            slot_candidate_limit=two_slot_candidate_limit,
            forced_attachment_rules=two_challenge_rules if two_challenge_scope == "Both weapons" else None,
        )

        if st.button("RUN TWO GUN OPTIMISER", type="primary", use_container_width=True):
            start_time = time.perf_counter()

            with st.spinner(f"Brute-forcing {two_loadout_pairing} weapon pairings..."):
                two_weapon_results = optimise_two_weapon_loadouts_for_scenario(
                    guns=guns,
                    attachments=attachments,
                    map_type=two_map_type,
                    fight_type=two_fight_type,
                    build_goal=two_build_goal,
                    loadout_pairing=two_loadout_pairing,
                    enemy_health=enemy_health,
                    attachment_count=two_attachment_count,
                    top_n=two_results_count,
                    candidate_pool=15,
                    optimiser_mode=two_optimiser_mode,
                    candidate_limit_per_slot=two_slot_candidate_limit,
                    primary_forced_attachment_rules=two_primary_challenge_rules,
                    secondary_forced_attachment_rules=two_secondary_challenge_rules,
                    wildcard_id=two_effective_wildcard_id,
                )

            elapsed_seconds = time.perf_counter() - start_time

            if two_weapon_results.empty:
                st.error(
                    "No valid two-gun pairing found. In BO7 Multiplayer this usually means Overkill is not active, the build is trying to use 8 attachments with Overkill, or one side lacks enough entered attachment slots."
                )
            else:
                st.session_state.ttk_last_two_gun_loadout = {
                    "elapsed_seconds": elapsed_seconds,
                    "result": two_weapon_results.iloc[0].to_dict(),
                    "top_results": two_weapon_results,
                    "mode_profile": f"{active_stats_profile} | {two_map_type} | {two_ruleset}",
                    "stats_profile": active_stats_profile,
                    "fight_type": two_fight_type,
                    "build_goal": two_build_goal,
                    "enemy_health": enemy_health,
                    "attachment_budget": two_attachment_budget,
                    "attachment_count": two_attachment_count,
                    "optimiser_depth": two_depth_profile,
                    "slot_candidate_limit": two_slot_candidate_limit,
                    "perk_package": "Weapons only",
                    "wildcard_id": two_effective_wildcard_id,
                    "wildcard_name": wildcard_name_from_id(two_effective_wildcard_id),
                    "loadout_pairing": two_loadout_pairing,
                    "challenge_requirements": two_challenge_summary,
                    "challenge_scope": two_challenge_scope,
                    **tactical_context,
                }

        last_two_gun_loadout = st.session_state.get("ttk_last_two_gun_loadout")

        if last_two_gun_loadout:
            two_weapon_results = last_two_gun_loadout.get("top_results", pd.DataFrame())

            if not two_weapon_results.empty:
                two_weapon_results = annotate_full_results_with_confidence(
                    two_weapon_results,
                    last_two_gun_loadout,
                )
                visible_two_weapon_results = filter_candidate_results(
                    two_weapon_results,
                    candidate_trust_filter,
                )

                if visible_two_weapon_results.empty:
                    st.warning(
                        "No two-gun candidate survives the current trust filter. "
                        "Switch to SHOW ALL LAB CANDIDATES to inspect the raw Oracle output."
                    )
                else:
                    best_two = pd.Series(visible_two_weapon_results.iloc[0])
                    two_confidence = full_loadout_confidence(best_two, last_two_gun_loadout)
                    st.markdown("## OPTIMUM PAIRING")
                    st.caption("FIELD TEST REQUIRED: this is a modelled candidate, not a proven meta.")
                    render_two_weapon_result(
                        visible_two_weapon_results,
                        float(last_two_gun_loadout.get("elapsed_seconds", 0.0)),
                        int(last_two_gun_loadout.get("enemy_health", enemy_health)),
                        two_confidence,
                    )
                    render_tactical_advice_panel(
                        tactical_advice_for_row(best_two, last_two_gun_loadout, prefix="primary_")
                    )

                    st.markdown("### Candidate Pairings")
                    render_candidate_filter_summary(
                        two_weapon_results,
                        visible_two_weapon_results,
                        candidate_trust_filter,
                    )

                    two_result_columns = available_columns(
                        visible_two_weapon_results,
                        [
                            "confidence",
                            "challenge_requirements",
                            "optimiser_mode",
                            "slot_candidate_limit",
                            "field_verdict",
                            "field_feel_rating",
                            "field_tested_at",
                            "full_loadout_score",
                            "role_balance_score",
                            "loadout_role_verdict",
                            "wildcard_name",
                            "recommended_tactical",
                            "recommended_lethal",
                            "recommended_field_upgrade",
                            "primary_weapon",
                            "primary_class",
                            "primary_role_label",
                            "secondary_weapon",
                            "secondary_class",
                            "secondary_role_label",
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
                        visible_two_weapon_results[two_result_columns],
                        use_container_width=True,
                        hide_index=True,
                    )

with full_loadout_tab:
    st.subheader("FULL LOADOUT OPTIMISER")
    st.caption(
        "Build a legal BO7 Multiplayer class: primary weapon, standard secondary slot, wildcard, perks, equipment, and scenario. "
        "Two primary weapons are only allowed when Overkill is selected."
    )

    if not data_ready:
        st.warning(f"No buildable {active_stats_profile} weapon and attachment data is loaded yet.")
    else:
        full_cols = st.columns(5)

        with full_cols[0]:
            loadout_pairing = st.selectbox(
                "Loadout pairing",
                LOADOUT_PAIRINGS,
                index=0,
                key="full_loadout_pairing",
            )

        with full_cols[1]:
            full_wildcard_selection = st.selectbox(
                "Wildcard",
                WILDCARD_SELECTION_OPTIONS,
                index=0 if "Oracle recommends" in WILDCARD_SELECTION_OPTIONS else 0,
                key="full_loadout_wildcard",
                help="Overkill is required for two-primary pairings. Gunfighter is required for 8 primary attachments.",
            )

        with full_cols[2]:
            perk_package = st.selectbox(
                "Perk package",
                PERK_SELECTION_OPTIONS,
                index=0 if "Oracle recommends" in PERK_SELECTION_OPTIONS else 0,
                key="full_loadout_perk_package",
                help="Use Oracle recommends to let the tactical context choose the perk shell before the full loadout is scored.",
            )

        with full_cols[3]:
            full_ruleset = st.selectbox(
                "Attachment ruleset",
                ATTACHMENT_RULESETS,
                index=0,
                key="full_loadout_attachment_ruleset",
            )

        with full_cols[4]:
            full_attachment_budget = st.selectbox(
                "Attachment budget",
                ATTACHMENT_BUDGET_PROFILES,
                index=0,
                key="full_loadout_attachment_budget",
            )

        full_attachment_count = attachment_count_for_profile(
            full_ruleset,
            full_attachment_budget,
        )

        full_cols = st.columns(4)

        with full_cols[0]:
            map_type = st.selectbox(
                "Map type",
                MAP_TYPES,
                index=0,
                key="full_loadout_map_type",
            )

        with full_cols[1]:
            fight_type = st.selectbox(
                "Fight type",
                FIGHT_TYPES,
                index=0,
                key="full_loadout_fight_type",
            )

        with full_cols[2]:
            build_goal = st.selectbox(
                "Build goal",
                BUILD_GOALS,
                index=0,
                key="full_loadout_build_goal",
            )

        with full_cols[3]:
            full_results_count = st.slider(
                "Loadout candidates",
                min_value=5,
                max_value=25,
                value=10,
                step=5,
                key="full_loadout_results",
            )

        full_depth_cols = st.columns(3)

        with full_depth_cols[0]:
            full_depth_profile = st.selectbox(
                "Optimiser depth",
                OPTIMISER_DEPTH_PROFILES,
                index=0,
                key="full_loadout_optimiser_depth",
            )

        with full_depth_cols[1]:
            full_slot_candidate_limit = st.slider(
                "Fast-pass candidates per slot",
                min_value=1,
                max_value=5,
                value=3,
                step=1,
                key="full_loadout_slot_candidate_limit",
            )

        with full_depth_cols[2]:
            st.caption(attachment_budget_summary(full_ruleset, full_attachment_budget))
            st.caption(optimiser_depth_summary(full_depth_profile, full_slot_candidate_limit))

        full_challenge_rules, full_force_eight, full_challenge_summary, full_challenge_scope = render_challenge_lock_controls(
            "full_loadout",
            allow_role_scope=True,
        )
        full_attachment_count = challenge_attachment_count_override(
            full_attachment_count,
            full_force_eight,
            full_challenge_summary,
        )
        full_primary_challenge_rules, full_secondary_challenge_rules = split_challenge_rules_by_scope(
            full_challenge_rules,
            full_challenge_scope,
        )

        full_effective_wildcard_id = render_wildcard_legality_notes(
            loadout_pairing=loadout_pairing,
            wildcard_selection=full_wildcard_selection,
            attachment_count=full_attachment_count,
            build_goal=build_goal,
            fight_type=fight_type,
            challenge_requirements=full_challenge_summary,
            tactical_context=tactical_context,
        )

        full_optimiser_mode = optimiser_mode_for_profile(full_depth_profile)

        render_optimizer_workload_estimate(
            guns_subset=guns,
            attachments=attachments,
            map_type=map_type,
            fight_type=fight_type,
            build_goal=build_goal,
            enemy_health=enemy_health,
            attachment_count=full_attachment_count,
            optimiser_mode=full_optimiser_mode,
            slot_candidate_limit=full_slot_candidate_limit,
            forced_attachment_rules=full_challenge_rules if full_challenge_scope == "Both weapons" else None,
        )

        if st.button("RUN FULL LOADOUT OPTIMISER", type="primary", use_container_width=True):
            start_time = time.perf_counter()

            with st.spinner(f"Brute-forcing {loadout_pairing} full loadouts..."):
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
                    top_n=full_results_count,
                    candidate_pool=15,
                    optimiser_mode=full_optimiser_mode,
                    candidate_limit_per_slot=full_slot_candidate_limit,
                    primary_forced_attachment_rules=full_primary_challenge_rules,
                    secondary_forced_attachment_rules=full_secondary_challenge_rules,
                    wildcard_id=full_effective_wildcard_id,
                    tactical_goal=tactical_context.get("tactical_goal", "Auto from build goal / challenge"),
                    tactical_map_size=tactical_context.get("map_size", "Auto"),
                    playlist_style=tactical_context.get("playlist_style", "Auto"),
                )

            elapsed_seconds = time.perf_counter() - start_time

            if full_loadout_results.empty:
                st.error(
                    "No valid full loadout found. Check wildcard legality first: two-primary pairings require Overkill, while 8 primary attachments require Gunfighter. If using a standard secondary, its weapon stats may not be captured yet."
                )
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
                    "wildcard_id": full_effective_wildcard_id,
                    "wildcard_name": wildcard_name_from_id(full_effective_wildcard_id),
                    "loadout_pairing": loadout_pairing,
                    "challenge_requirements": full_challenge_summary,
                    "challenge_scope": full_challenge_scope,
                    **tactical_context,
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
                    st.markdown("## OPTIMUM LOADOUT")
                    st.caption("FIELD TEST REQUIRED: this is a modelled candidate, not a proven meta.")
                    render_full_loadout_result(
                        visible_full_loadout_results,
                        float(last_full_loadout.get("elapsed_seconds", 0.0)),
                        int(last_full_loadout.get("enemy_health", enemy_health)),
                        full_confidence,
                    )
                    render_tactical_advice_panel(
                        tactical_advice_for_row(best_full, last_full_loadout, prefix="primary_")
                    )

                    with st.expander("Save this loadout", expanded=False):
                        render_keep_full_loadout(best_full, last_full_loadout)

                    st.markdown("### Candidate Loadouts")
                    render_candidate_filter_summary(
                        full_loadout_results,
                        visible_full_loadout_results,
                        candidate_trust_filter,
                    )

                    full_result_columns = available_columns(
                        visible_full_loadout_results,
                        [
                            "confidence",
                            "challenge_requirements",
                            "optimiser_mode",
                            "slot_candidate_limit",
                            "field_verdict",
                            "field_feel_rating",
                            "field_tested_at",
                            "full_loadout_score",
                            "role_balance_score",
                            "loadout_role_verdict",
                            "wildcard_name",
                            "recommended_tactical",
                            "recommended_lethal",
                            "recommended_field_upgrade",
                            "primary_weapon",
                            "primary_class",
                            "primary_role_label",
                            "secondary_weapon",
                            "secondary_class",
                            "secondary_role_label",
                            "perk_package",
                            "perk_role",
                            "perk_fit_score",
                            "perk_score_bonus",
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

st.subheader("MANUAL LOADOUT PREVIEW")
st.caption(
    "Manual preview stays below the optimiser. It is for checking a hand-built class, not for overriding the current optimum."
)

if not data_ready:
    st.warning(f"No {active_stats_profile} manual preview data is loaded yet.")
else:
    preview_cols = st.columns(4)

    with preview_cols[0]:
        selected_gun_name = st.selectbox(
            "Choose weapon",
            weapon_names,
            key="manual_preview_weapon",
        )

    with preview_cols[1]:
        preview_fight_type = st.selectbox(
            "Preview fight type",
            FIGHT_TYPES,
            index=1 if "Mid range" in FIGHT_TYPES else 0,
            key="manual_preview_fight_type",
        )

    with preview_cols[2]:
        preview_build_goal = st.selectbox(
            "Preview build goal",
            BUILD_GOALS,
            index=0,
            key="manual_preview_build_goal",
        )

    with preview_cols[3]:
        preview_attachment_budget = st.selectbox(
            "Preview attachment budget",
            ATTACHMENT_BUDGET_PROFILES,
            index=0,
            key="manual_preview_attachment_budget",
        )

    preview_ruleset = st.selectbox(
        "Preview attachment ruleset",
        ATTACHMENT_RULESETS,
        index=0,
        key="manual_preview_attachment_ruleset",
    )

    preview_attachment_count = attachment_count_for_profile(
        preview_ruleset,
        preview_attachment_budget,
    )

    st.caption(attachment_budget_summary(preview_ruleset, preview_attachment_budget))

    selected_gun = guns[guns["gun_name"] == selected_gun_name].iloc[0]

    compatible_attachments = get_compatible_attachments(
        gun=selected_gun,
        attachments=attachments,
    )

    selected_attachment_names = st.multiselect(
        f"Choose attachments - max {preview_attachment_count}",
        compatible_attachments["attachment_name"].tolist(),
        max_selections=preview_attachment_count,
        key="manual_preview_attachments",
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
        fight_type=preview_fight_type,
        build_goal=preview_build_goal,
    )

    preview_cols = st.columns(4)
    preview_cols[0].metric("RAW TTK", f"{preview['raw_ttk_ms']:.0f} ms")
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

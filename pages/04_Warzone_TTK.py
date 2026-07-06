from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
import time

from modules.warzone.ttk_oracle_engine import (
    BUILD_GOALS,
    FIGHT_TYPES,
    LOADOUT_PAIRINGS,
    MAP_TYPES,
    PERK_PACKAGES,
    build_base_weapon_rankings,
    build_loadout_preview,
    build_ttk_data_warnings,
    describe_weapon_build_data,
    get_compatible_attachments,
    load_ttk_data,
    optimise_full_loadouts_for_scenario,
    optimise_single_weapon_build,
    parse_codmunity_attachment_html,
    build_attachment_verification_rows,
)


st.title("BO7: TTK Oracle")
st.caption(
    "Perzevol OS build optimiser. Use it standalone for Warzone, or use it to optimise the weapon the Completion Commander assigned."
)


@st.cache_data(show_spinner=False)
def load_and_validate_ttk_data():
    guns, attachments = load_ttk_data()

    before = len(guns)
    guns = guns.drop_duplicates(subset=["gun_id"]).reset_index(drop=True)
    duplicate_count = before - len(guns)

    warnings = build_ttk_data_warnings(
        guns=guns,
        attachments=attachments,
        attachment_count=5,
    )

    if duplicate_count:
        warnings.insert(0, f"Removed {duplicate_count} duplicate gun row(s) by gun_id.")

    return guns, attachments, warnings


def render_attachment_list(attachments_text: str):
    for attachment in str(attachments_text or "").split(" | "):
        clean_attachment = attachment.strip()
        if clean_attachment:
            st.write(f"- {clean_attachment}")



STATE_DIR = Path("data/bo7_state")
SAVED_TTK_LOADOUTS_PATH = STATE_DIR / "saved_ttk_loadouts.csv"

SAVED_LOADOUT_COLUMNS = [
    "saved_at",
    "save_name",
    "source",
    "mode_profile",
    "enemy_health",
    "fight_type",
    "build_goal",
    "loadout_type",
    "attachment_count",
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


def format_stat(value, decimals: int = 0) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:.{decimals}f}"


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
        "enemy_health": context.get("enemy_health", ""),
        "fight_type": context.get("fight_type", ""),
        "build_goal": context.get("build_goal", ""),
        "loadout_type": "single_weapon",
        "attachment_count": context.get("attachment_count", ""),
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
        "enemy_health": context.get("enemy_health", ""),
        "fight_type": context.get("fight_type", ""),
        "build_goal": context.get("build_goal", ""),
        "loadout_type": "two_weapon_loadout",
        "attachment_count": context.get("attachment_count", ""),
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


def render_single_weapon_result(best: pd.Series, enemy_health: int):
    st.markdown("### Optimised Assigned Weapon")

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

    trust_note = str(best.get("attachment_trust_note", "") or "").strip()
    effect_note = str(best.get("attachment_effects", "") or "").strip()

    st.info(
        f"""
        **Why this build won:** the Oracle kept the Commander-assigned weapon locked to **{best['gun_name']}** and brute-forced legal attachment combinations for this scenario.  
        It ranked builds by raw TTK, practical TTK, recoil, handling, range, bullet velocity, and magazine value depending on the selected goal.  
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


def render_full_loadout_result(full_loadout_results: pd.DataFrame, elapsed_seconds: float, enemy_health: int):
    best = full_loadout_results.iloc[0]

    st.success(f"Loadout found in {elapsed_seconds:.2f} seconds.")

    st.markdown("### Optimum Loadout")

    st.caption(
        f"Primary role: {best['primary_fight_type']} / {best['primary_build_goal']} | "
        f"Secondary role: {best['secondary_fight_type']} / {best['secondary_build_goal']}"
    )

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

        The primary weapon was optimised for **{best['primary_fight_type']} / {best['primary_build_goal']}**.  
        The secondary weapon was optimised for **{best['secondary_fight_type']} / {best['secondary_build_goal']}**.
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


try:
    guns, attachments, data_warnings = load_and_validate_ttk_data()
except Exception as error:
    st.error(f"TTK data failed to load: {error}")
    st.stop()

weapon_names = sorted(guns["gun_name"].dropna().astype(str).tolist())

if data_warnings:
    with st.expander(f"⚠️ {len(data_warnings)} data quality issue(s) detected", expanded=True):
        for warning in data_warnings:
            st.warning(warning)

st.success("TTK Oracle engine connected.")

metric_cols = st.columns(2)

with metric_cols[0]:
    st.metric("Guns loaded", len(guns))

with metric_cols[1]:
    st.metric("Attachments loaded", len(attachments))

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

            st.markdown("#### Draft attachment rows")
            st.dataframe(
                parsed_attachment_rows,
                use_container_width=True,
                hide_index=True,
            )

            st.download_button(
                "Download parsed attachment rows",
                parsed_attachment_rows.to_csv(index=False).encode("utf-8"),
                file_name=f"{data_entry_weapon.lower().replace(' ', '_')}_parsed_attachments.csv",
                mime="text/csv",
                use_container_width=True,
            )

with st.expander("Debug: weapon class counts"):
    class_counts = guns["weapon_class"].value_counts().reset_index()
    class_counts.columns = ["Weapon Class", "Count"]
    st.dataframe(class_counts, use_container_width=True, hide_index=True)

enemy_health = st.slider(
    "Enemy health",
    min_value=100,
    max_value=400,
    value=300,
    step=50,
)

if guns.empty or attachments.empty:
    st.warning("Gun and attachment data are required before optimisation.")
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
        index=1 if "Balanced meta build" in BUILD_GOALS else 0,
        key="commander_build_goal",
    )

commander_cols = st.columns(3)

with commander_cols[0]:
    commander_attachment_count = st.slider(
        "Attachments for assigned weapon",
        min_value=1,
        max_value=5,
        value=5,
        key="commander_attachment_count",
    )

with commander_cols[1]:
    commander_results = st.slider(
        "Commander build results",
        min_value=5,
        max_value=25,
        value=10,
        step=5,
        key="commander_results",
    )

with commander_cols[2]:
    commander_perk_package = st.selectbox(
        "Perk package to save",
        list(PERK_PACKAGES.keys()),
        index=list(PERK_PACKAGES.keys()).index("Balanced") if "Balanced" in PERK_PACKAGES else 0,
        key="commander_perk_package",
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

    with st.spinner(f"Brute-forcing {assigned_weapon} builds..."):
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
            "mode_profile": commander_map_type,
            "fight_type": commander_fight_type,
            "build_goal": commander_build_goal,
            "enemy_health": enemy_health,
            "attachment_count": commander_attachment_count,
            "perk_package": commander_perk_package,
        }

last_single_build = st.session_state.get("ttk_last_single_build")

if last_single_build:
    best_single = pd.Series(last_single_build["result"])
    st.success(
        f"{best_single.get('gun_name', 'Assigned weapon')} build found in "
        f"{float(last_single_build.get('elapsed_seconds', 0.0)):.2f} seconds."
    )
    render_single_weapon_result(best_single, int(last_single_build.get("enemy_health", enemy_health)))

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
    assigned_weapon_results = last_single_build.get("top_results", pd.DataFrame())

    if not assigned_weapon_results.empty:
        st.dataframe(
            assigned_weapon_results[
                [
                    "oracle_score",
                    "gun_name",
                    "weapon_class",
                    "raw_ttk_ms",
                    "practical_ttk_ms",
                    "ads_ms",
                    "sprint_to_fire_ms",
                    "recoil",
                    "bullet_velocity",
                    "range_m",
                    "damage_per_mag",
                    "slots",
                    "attachments",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

st.divider()

st.subheader("Optimum Full Loadout")
st.caption(
    "Standalone Oracle mode. Choose the map, fight type, and build goal. The Oracle brute-forces valid two-weapon loadouts."
)

full_cols = st.columns(3)

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
    full_attachment_count = st.slider(
        "Attachments per weapon",
        min_value=1,
        max_value=5,
        value=5,
        key="full_attachment_count",
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

if st.button("Find Best Full Loadout", use_container_width=True):
    start_time = time.perf_counter()

    with st.spinner("Brute-forcing full loadouts..."):
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
        )

    elapsed_seconds = time.perf_counter() - start_time

    if full_loadout_results.empty:
        st.warning("No valid full loadouts found. Check weapon classes, attachment slots, or compatibility.")
    else:
        st.session_state.ttk_last_full_loadout = {
            "elapsed_seconds": elapsed_seconds,
            "result": full_loadout_results.iloc[0].to_dict(),
            "top_results": full_loadout_results,
            "mode_profile": map_type,
            "fight_type": fight_type,
            "build_goal": build_goal,
            "enemy_health": enemy_health,
            "attachment_count": full_attachment_count,
            "perk_package": perk_package,
            "loadout_pairing": loadout_pairing,
        }

last_full_loadout = st.session_state.get("ttk_last_full_loadout")

if last_full_loadout:
    best_full = pd.Series(last_full_loadout["result"])
    full_loadout_results = last_full_loadout.get("top_results", pd.DataFrame())

    if not full_loadout_results.empty:
        render_full_loadout_result(
            full_loadout_results,
            float(last_full_loadout.get("elapsed_seconds", 0.0)),
            int(last_full_loadout.get("enemy_health", enemy_health)),
        )

        render_keep_full_loadout(best_full, last_full_loadout)

        st.divider()

        st.markdown("### Top Full Loadouts")

        st.dataframe(
            full_loadout_results[
                [
                    "full_loadout_score",
                    "primary_weapon",
                    "primary_class",
                    "primary_fight_type",
                    "primary_build_goal",
                    "secondary_weapon",
                    "secondary_class",
                    "secondary_fight_type",
                    "secondary_build_goal",
                    "perk_package",
                    "primary_raw_ttk_ms",
                    "secondary_raw_ttk_ms",
                    "primary_practical_ttk_ms",
                    "secondary_practical_ttk_ms",
                    "primary_recoil",
                    "secondary_recoil",
                    "primary_attachments",
                    "secondary_attachments",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

st.divider()

render_saved_ttk_loadouts()

st.divider()

st.subheader("Base Weapon TTK Ranking")

base_rankings = build_base_weapon_rankings(
    guns=guns,
    enemy_health=enemy_health,
)

if base_rankings.empty:
    st.warning("No gun data loaded yet.")
else:
    st.dataframe(
        base_rankings[
            [
                "gun_name",
                "weapon_class",
                "damage",
                "fire_rate_rpm",
                "shots_to_kill",
                "raw_ttk_ms",
                "ads_ms",
                "sprint_to_fire_ms",
                "recoil",
                "bullet_velocity",
                "range_m",
                "mag_size",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

st.divider()

st.subheader("Manual Loadout Preview")

selected_gun_name = st.selectbox(
    "Choose weapon",
    weapon_names,
)

selected_gun = guns[guns["gun_name"] == selected_gun_name].iloc[0]

compatible_attachments = get_compatible_attachments(
    gun=selected_gun,
    attachments=attachments,
)

selected_attachment_names = st.multiselect(
    "Choose attachments",
    compatible_attachments["attachment_name"].tolist(),
    max_selections=5,
)

selected_attachments = compatible_attachments[
    compatible_attachments["attachment_name"].isin(selected_attachment_names)
]

preview = build_loadout_preview(
    gun=selected_gun,
    selected_attachments=selected_attachments,
    enemy_health=enemy_health,
)

preview_cols = st.columns(4)
preview_cols[0].metric("Final TTK", f"{preview['raw_ttk_ms']:.0f} ms")
preview_cols[1].metric("Shots to Kill", int(preview["shots_to_kill"]))
preview_cols[2].metric("ADS", f"{preview['ads_ms']:.0f} ms")
preview_cols[3].metric("Recoil", f"{preview['recoil']:.1f}")

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
        ]
    ),
    use_container_width=True,
    hide_index=True,
)

st.divider()

st.subheader("Gun Data")
st.dataframe(guns, use_container_width=True, hide_index=True)

st.subheader("Attachment Data")
st.dataframe(attachments, use_container_width=True, hide_index=True)

import streamlit as st
import pandas as pd
import time

from modules.warzone.ttk_oracle_engine import (
    BUILD_GOALS,
    FIGHT_TYPES,
    MAP_TYPES,
    build_base_weapon_rankings,
    build_loadout_preview,
    get_compatible_attachments,
    load_ttk_data,
    optimise_loadouts_for_scenario,
    LOADOUT_PAIRINGS,
    PERK_PACKAGES,
    optimise_full_loadouts_for_scenario,
)

st.title("BO7: TTK Oracle")
st.caption("Warzone loadout optimiser. Brute-force builds. Expose the meta.")


@st.cache_data(show_spinner=False)
def load_and_validate_ttk_data():
    """
    Load guns and attachments, deduplicate by gun_id, and surface any
    data quality issues so they are visible before the optimiser runs.
    """
    guns, attachments = load_ttk_data()

    # Deduplicate guns — duplicate gun_id rows cause silent scoring errors
    before = len(guns)
    guns = guns.drop_duplicates(subset=["gun_id"]).reset_index(drop=True)
    after = len(guns)

    warnings = []

    if before != after:
        warnings.append(f"Removed {before - after} duplicate gun row(s) by gun_id.")

    # Surface guns with no attachment data so you know what still needs entering
    guns_with_attachments = set(attachments["compatible_guns"].str.strip().unique())
    guns_missing_attachments = [
        row["gun_name"]
        for _, row in guns.iterrows()
        if row["gun_name"] not in guns_with_attachments
    ]

    if guns_missing_attachments:
        warnings.append(
            f"{len(guns_missing_attachments)} gun(s) have no attachment data and will be skipped by the optimiser: "
            + ", ".join(guns_missing_attachments)
        )

    return guns, attachments, warnings


try:
    guns, attachments, data_warnings = load_and_validate_ttk_data()
except Exception as error:
    st.error(f"TTK data failed to load: {error}")
    st.stop()

if data_warnings:
    with st.expander(f"⚠️ {len(data_warnings)} data quality issue(s) detected", expanded=True):
        for warning in data_warnings:
            st.warning(warning)

st.success("TTK Oracle engine connected.")

col1, col2 = st.columns(2)

with col1:
    st.metric("Guns loaded", len(guns))

with col2:
    st.metric("Attachments loaded", len(attachments))

with st.expander("Debug: weapon class counts"):
    class_counts = guns["weapon_class"].value_counts().reset_index()
    class_counts.columns = ["Weapon Class", "Count"]

    st.dataframe(
        class_counts,
        use_container_width=True,
        hide_index=True,
    )

enemy_health = st.slider(
    "Enemy health",
    min_value=100,
    max_value=400,
    value=300,
    step=50,
)

st.divider()

st.subheader("Optimum Full Loadout")
st.caption(
    "Choose the map, fight type, and build goal. The Oracle brute-forces valid builds and ranks the best options."
)

if guns.empty or attachments.empty:
    st.warning("Gun and attachment data are required before optimisation.")
else:
    col1, col2, col3 = st.columns(3)

    loadout_pairing = st.selectbox(
    "Loadout pairing",
    LOADOUT_PAIRINGS,
    index=0,
    )

    perk_package = st.selectbox(
        "Perk package",
        list(PERK_PACKAGES.keys()),
        index=1,
    )

    with col1:
        map_type = st.selectbox(
            "Map type",
            MAP_TYPES,
            index=0,
        )

    with col2:
        fight_type = st.selectbox(
            "Fight type",
            FIGHT_TYPES,
            index=0,
        )

    with col3:
        build_goal = st.selectbox(
            "Build goal",
            BUILD_GOALS,
            index=1,
        )

    weapon_classes = ["Any"] + sorted(
        guns["weapon_class"].dropna().unique().tolist()
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        optimiser_weapon_class = st.selectbox(
            "Weapon class",
            weapon_classes,
            index=0,
            key="optimiser_weapon_class",
        )

    with col2:
        attachment_count = st.slider(
            "Attachments per loadout",
            min_value=1,
            max_value=5,
            value=5,
            key="optimiser_attachment_count",
        )

    with col3:
        top_n = st.slider(
            "Results",
            min_value=5,
            max_value=50,
            value=20,
            step=5,
        )

    if st.button("Find Best Full Loadout", type="primary", use_container_width=True):
        start_time = time.perf_counter()

        with st.spinner("Brute-forcing loadouts..."):
            full_loadout_results = optimise_full_loadouts_for_scenario(
                guns=guns,
                attachments=attachments,
                map_type=map_type,
                fight_type=fight_type,
                build_goal=build_goal,
                loadout_pairing=loadout_pairing,
                perk_package=perk_package,
                enemy_health=enemy_health,
                attachment_count=attachment_count,
                top_n=top_n,
            )

        elapsed_seconds = time.perf_counter() - start_time

        if full_loadout_results.empty:
            st.warning("No valid full loadouts found. Check weapon classes, attachment slots, or compatibility.")
        else:
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
                for attachment in best["primary_attachments"].split(" | "):
                    st.write(f"- {attachment}")

            with col2:
                st.markdown("### Secondary Build")
                st.write(f"**Weapon:** {best['secondary_weapon']}")
                st.write(f"**Class:** {best['secondary_class']}")
                st.write(f"**Raw TTK:** {best['secondary_raw_ttk_ms']:.0f} ms")
                st.write(f"**Practical TTK:** {best['secondary_practical_ttk_ms']:.0f} ms")
                st.write(f"**Recoil:** {best['secondary_recoil']:.1f}")
                st.write(f"**ADS:** {best['secondary_ads_ms']:.0f} ms")

                st.markdown("**Attachments:**")
                for attachment in best["secondary_attachments"].split(" | "):
                    st.write(f"- {attachment}")

            st.divider()

            st.markdown("### Perks")

            selected_perks = PERK_PACKAGES[perk_package]

            st.write(f"**Package:** {perk_package}")
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
                        "secondary_fight_type",
                        "secondary_build_goal",
                        "secondary_weapon",
                        "secondary_class",
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

if guns.empty:
    st.warning("Add gun data before building a loadout.")
else:
    selected_gun_name = st.selectbox(
        "Choose weapon",
        guns["gun_name"].tolist(),
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

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Final TTK", f"{preview['raw_ttk_ms']:.0f} ms")
    col2.metric("Shots to Kill", int(preview["shots_to_kill"]))
    col3.metric("ADS", f"{preview['ads_ms']:.0f} ms")
    col4.metric("Recoil", f"{preview['recoil']:.1f}")

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
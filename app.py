import streamlit as st

st.set_page_config(
    page_title="Perzevol.OS",
    page_icon="terminal",
    layout="wide",
)

val_draft = st.Page(
    "modules/valorant_draft.py",
    title="Valorant: VCT Draft Analyst",
    icon="⚡",
    default=True,
)

cs2_metro = st.Page(
    "modules/cs2_metronome.py",
    title="CS2: Metronome",
    icon="⏱️",
)
wz_blacksmith = st.Page(
    "modules/warzone_blacksmith.py",
    title="Warzone: Blacksmith",
    icon="🔫",
)

pg = st.navigation(
    {
        "Active Modules": [val_draft],
        "Development Pipeline": [cs2_metro, wz_blacksmith],
    }
)

st.sidebar.markdown("### `perzevol.os`")
st.sidebar.markdown("`> code. gaming. ai.`")
st.sidebar.divider()

pg.run()
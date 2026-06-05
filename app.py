import streamlit as st

st.set_page_config(
    page_title="Perzevol.OS",
    page_icon="terminal",
    layout="wide",
)

val_draft = st.Page(
    "pages/01_Valorant.py",
    title="Valorant: VCT Draft Analyst",
    icon="⚡",
)

cs2_metro = st.Page(
    "pages/02_CS2.py",
    title="CS2: Metronome",
    icon="⏱️",
)

bo7_commander = st.Page(
    "pages/03_Warzone.py",
    title="BO7: Completion Commander",
    icon="☣️",
    default=True,
)

bo7_ttk = st.Page(
    "pages/04_Warzone_TTK.py",
    title="BO7: TTK Oracle",
    icon="🎯",
)

pg = st.navigation(
    {
        "Active Experiments": [bo7_commander, bo7_ttk],
        "Archived Prototypes": [val_draft],
        "Development Pipeline": [cs2_metro],
    }
)

st.sidebar.markdown("### `perzevol.os`")
st.sidebar.markdown("`> code. gaming. ai.`")
st.sidebar.divider()

pg.run()
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
    default=True,
)

cs2_metro = st.Page(
    "pages/02_CS2.py",
    title="CS2: Metronome",
    icon="⏱️",
)
wz_blacksmith = st.Page(
    "pages/03_Warzone.py",
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
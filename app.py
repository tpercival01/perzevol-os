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


bo7_finish_line = st.Page(
    "pages/07_BO7_Finish_Line.py",
    title="BO7: Progress Dashboard",
    icon="🏁",
)

bo7_commander_launch = st.Page(
    "pages/05_Commander_Launch.py",
    title="BO7: Tonight's Grind",
    icon="🎮",
    default=True,
)


bo7_record_view = st.Page(
    "pages/06_Commander_Record.py",
    title="BO7: OBS View",
    icon="🎬",
)

bo7_commander = st.Page(
    "pages/03_Warzone.py",
    title="BO7: Mission Control",
    icon="☣️",
)

bo7_ttk = st.Page(
    "pages/04_Warzone_TTK.py",
    title="BO7: TTK Oracle",
    icon="🎯",
)

pg = st.navigation(
    {
        "BO7 Command Centre": [bo7_commander_launch, bo7_commander, bo7_record_view, bo7_ttk, bo7_finish_line],
        "Archived Prototypes": [val_draft],
        "Development Pipeline": [cs2_metro],
    }
)

st.sidebar.markdown("### `perzevol.os`")
st.sidebar.markdown("`> code. gaming. ai.`")
st.sidebar.divider()

pg.run()

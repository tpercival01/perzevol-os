import json
import os

import streamlit as st

from groq_engine import get_ai_recommendation, get_debug_state

st.set_page_config(page_title="Draft Analyst", page_icon="⚡", layout="wide")

# 1. State & File Management
ROSTER_FILE = "../data/roster.json"

if "team_comp" not in st.session_state:
    st.session_state.team_comp = []


def load_roster():
    if os.path.exists(ROSTER_FILE):
        with open(ROSTER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_roster(roster_list):
    with open(ROSTER_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(set(roster_list)), f, indent=2)


if "roster" not in st.session_state:
    st.session_state.roster = load_roster()


def toggle_team_agent(agent_name):
    if agent_name in st.session_state.team_comp:
        st.session_state.team_comp.remove(agent_name)
    elif len(st.session_state.team_comp) < 4:
        st.session_state.team_comp.append(agent_name)


def reset_draft():
    st.session_state.team_comp = []


# 2. Load Core Data
@st.cache_data
def load_meta():
    try:
        with open("../data/processed/meta_matrix.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {"map_meta": {}, "roles": {}}


data = load_meta()
maps = list(data.get("map_meta", {}).keys())
roles_dict = data.get("roles", {})

all_agents = []
for agents in roles_dict.values():
    all_agents.extend(agents)
all_agents = sorted(set(all_agents))

if not st.session_state.roster and not os.path.exists(ROSTER_FILE):
    st.session_state.roster = ["Brimstone", "Jett", "Phoenix", "Sage", "Sova"]
    save_roster(st.session_state.roster)

# 3. Main Dashboard UI
st.title("⚡ VCT Draft Analyst v6")
st.markdown("### code. gaming. ai.")

tab1, tab2 = st.tabs(["🚀 Draft Analysis", "⚙️ My Roster"])

with tab1:
    output_container = st.container()
    st.divider()

    left_col, right_col = st.columns([1, 2], gap="large")

    with left_col:
        st.subheader("Mission Control")
        selected_map = st.selectbox("Active Map", maps if maps else ["Ascent"])

        st.write(f"**Locked Teammates:** {len(st.session_state.team_comp)}/4")
        if st.session_state.team_comp:
            for agent in st.session_state.team_comp:
                st.code(agent)
        else:
            st.info("Awaiting lock-ins...")

        debug_state = get_debug_state(
            selected_map,
            st.session_state.team_comp,
            st.session_state.roster,
        )
        with st.expander("Debug: True VCT Comp Brain", expanded=False):
            st.write("**Source type**")
            st.code(str(debug_state.get("source_type")))

            st.write("**Role counts**")
            st.json(debug_state["role_counts"])

            st.write("**Sample size**")
            st.write(
                f"{debug_state.get('sample_size_team_comps')} team comps "
                f"≈ {debug_state.get('estimated_maps_played')} maps"
            )

            st.write("**Confidence**")
            st.code(str(debug_state.get("confidence")))

            st.write("**Primary team comp**")
            st.write(debug_state.get("primary_team_comp", []))

            st.write("**Top actual team comps**")
            st.dataframe(
                debug_state.get("top_team_comps", []), use_container_width=True
            )

            st.write("**Top role templates**")
            st.dataframe(
                debug_state.get("top_role_templates", []), use_container_width=True
            )

            st.write("**Candidate scores**")
            st.dataframe(
                debug_state.get("ranked_candidates", []), use_container_width=True
            )

        st.write("")

        if st.button("🚀 EXECUTE ANALYSIS", type="primary", use_container_width=True):
            with st.spinner("Calculating optimal strategy..."):
                response = get_ai_recommendation(
                    selected_map,
                    st.session_state.team_comp,
                    st.session_state.roster,
                )

                lines = [line for line in response.split("\n") if line.strip()]
                if len(lines) >= 2:
                    agent_name = lines[0]
                    reason = " ".join(lines[1:])
                else:
                    agent_name = "OVERRIDE"
                    reason = response

                with output_container:
                    # Detect Failsafe for Visual Overrides
                    is_failsafe = "FAILSAFE" in agent_name.upper()
                    ui_color = "#ff4b4b" if is_failsafe else "#00e5ff"

                    st.markdown(
                        f"""
                        <h1 style='text-align: center; font-size: 5rem; color: {ui_color}; margin-bottom: 0;'>
                            {agent_name}
                        </h1>
                        <h3 style='text-align: center; font-weight: normal; padding: 0 10%;'>
                            {reason}
                        </h3>
                        """,
                        unsafe_allow_html=True,
                    )

        if st.button("🚨 PANIC (Top 3)", use_container_width=True):
            with st.spinner("Bypassing draft context..."):
                response = get_ai_recommendation(
                    selected_map,
                    [],
                    st.session_state.roster,
                    is_panic=True,
                )
                with output_container:
                    st.markdown(
                        f"<h2 style='text-align: center; color: #ff4b4b;'>{response}</h2>",
                        unsafe_allow_html=True,
                    )

        st.button("Reset Draft", on_click=reset_draft, use_container_width=True)

    with right_col:
        st.subheader("Agent Grid")
        role_cols = st.columns(4)

        for idx, (role_name, agent_list) in enumerate(roles_dict.items()):
            with role_cols[idx]:
                st.markdown(f"**{role_name}**")
                for agent in sorted(agent_list):
                    is_selected = agent in st.session_state.team_comp
                    button_type = "primary" if is_selected else "secondary"
                    st.button(
                        agent,
                        key=f"draft_{agent}",
                        type=button_type,
                        on_click=toggle_team_agent,
                        args=(agent,),
                        use_container_width=True,
                    )

with tab2:
    st.subheader("Account Unlocks")
    roster_cols = st.columns(4)
    for idx, agent in enumerate(all_agents):
        col_idx = idx % 4
        with roster_cols[col_idx]:
            is_owned = agent in st.session_state.roster
            new_status = st.toggle(agent, value=is_owned, key=f"roster_{agent}")

            if new_status and agent not in st.session_state.roster:
                st.session_state.roster.append(agent)
                save_roster(st.session_state.roster)
            elif not new_status and agent in st.session_state.roster:
                st.session_state.roster.remove(agent)
                save_roster(st.session_state.roster)
import streamlit as st
import json
import os
from groq_engine import get_ai_recommendation

st.set_page_config(page_title="Draft Analyst", page_icon="⚡", layout="wide")

# 1. State & File Management
ROSTER_FILE = "../data/roster.json"

if "team_comp" not in st.session_state:
    st.session_state.team_comp = []

def load_roster():
    if os.path.exists(ROSTER_FILE):
        with open(ROSTER_FILE, "r") as f:
            return json.load(f)
    return []

def save_roster(roster_list):
    with open(ROSTER_FILE, "w") as f:
        json.dump(roster_list, f)

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
        with open("../data/processed/meta_matrix.json", "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {"map_meta": {}, "roles": {}}

data = load_meta()
maps = list(data.get("map_meta", {}).keys())
roles_dict = data.get("roles", {})

all_agents = []
for agents in roles_dict.values():
    all_agents.extend(agents)
all_agents = sorted(all_agents)

# Initialize roster with free agents if completely empty
if not st.session_state.roster and not os.path.exists(ROSTER_FILE):
    st.session_state.roster = ["Brimstone", "Jett", "Phoenix", "Sage", "Sova"]
    save_roster(st.session_state.roster)

# 3. Main Dashboard UI
st.title("⚡ VCT Draft Analyst v5")
st.markdown("### code. gaming. ai.")

tab1, tab2 = st.tabs(["🚀 Draft Analysis", "⚙️ My Roster"])

with tab1:
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

        st.divider()
        
        if st.button("🚀 EXECUTE ANALYSIS", type="primary", use_container_width=True):
            with st.spinner("Querying constrained Llama-3.3-70B..."):
                response = get_ai_recommendation(
                    selected_map, 
                    st.session_state.team_comp, 
                    st.session_state.roster
                )
                st.success("Analysis Complete")
                st.code(response, language="text")
                
        if st.button("🚨 PANIC (Top 3)", use_container_width=True):
            with st.spinner("Bypassing rules..."):
                response = get_ai_recommendation(
                    selected_map, [], st.session_state.roster, is_panic=True
                )
                st.error("PANIC PROTOCOL ENGAGED")
                st.code(response, language="text")

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
                        use_container_width=True
                    )

with tab2:
    st.subheader("Account Unlocks")
    st.write("Toggle the agents currently unlocked on your Valorant account. The AI will strictly limit recommendations to this list.")
    
    # Roster Management Grid
    roster_cols = st.columns(4)
    for idx, agent in enumerate(all_agents):
        col_idx = idx % 4
        with roster_cols[col_idx]:
            is_owned = agent in st.session_state.roster
            new_status = st.toggle(agent, value=is_owned, key=f"roster_{agent}")
            
            # Detect changes and save
            if new_status and agent not in st.session_state.roster:
                st.session_state.roster.append(agent)
                save_roster(st.session_state.roster)
            elif not new_status and agent in st.session_state.roster:
                st.session_state.roster.remove(agent)
                save_roster(st.session_state.roster)
import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def load_meta_context():
    file_path = '../data/processed/meta_matrix.json'
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def check_failsafe(team_comp, meta_dict):
    roles = meta_dict.get("roles", {})
    duelists = sum(
        1 for a in team_comp if a.strip().title() in roles.get("Duelist", [])
    )
    controllers = sum(
        1 for a in team_comp if a.strip().title() in roles.get("Controller", [])
    )
    initiators = sum(
        1 for a in team_comp if a.strip().title() in roles.get("Initiator", [])
    )

    if duelists >= 3:
        return True
    if len(team_comp) >= 3 and controllers == 0 and initiators == 0:
        return True
    return False

def get_missing_roles(team_comp, map_name, meta_dict):
    roles_dict = meta_dict.get("roles", {})
    map_meta = meta_dict.get("map_meta", {}).get(map_name, {})
    template = map_meta.get("preferred_templates", [[]])[0].copy()
    
    for agent in team_comp:
        agent_title = agent.strip().title()
        role = None
        for r, agents in roles_dict.items():
            if agent_title in agents:
                role = r
                break
        
        if role in template:
            template.remove(role)
        elif "Flex" in template:
            template.remove("Flex")
            
    return template

def get_ai_recommendation(map_name, team_comp, roster, is_panic=False):
    meta_dict = load_meta_context()
    meta_data_string = json.dumps(meta_dict)
    
    # Filter the roster to remove agents already locked by teammates
    available_roster = [agent for agent in roster if agent not in team_comp]
    roster_str = ', '.join(available_roster) if available_roster else "NONE"
    
    if is_panic:
        user_prompt = (
            f"Map: {map_name}\n"
            f"Task: PANIC MODE. Ignore team comp. "
            f"Available Roster: {roster_str}\n"
            f"Give me the top 3 core agents for {map_name} from my Available Roster."
        )
        system_prompt = (
            "You output raw data. No markdown.\n"
            "Line 1: 3 AGENT NAMES\n"
            "Line 2: 1 sentence tactical justification."
        )
    else:
        team_str = ', '.join(team_comp) if team_comp else 'None'
        is_unsalvageable = check_failsafe(team_comp, meta_dict)
        
        if is_unsalvageable:
            user_prompt = (
                f"Map: {map_name}\n"
                f"Current Team: {team_str}\n"
                f"STATUS: UNSALVAGEABLE DRAFT.\n"
                f"Available Roster: {roster_str}\n"
                f"Task: Recommend the best self-sufficient carry for {map_name} from my Available Roster."
            )
            system_prompt = (
                f"Use this dataset exclusively: {meta_data_string}. "
                "Your response must be EXACTLY two lines. No markdown.\n"
                "Line 1: [FAILSAFE OVERRIDE] AGENT NAME IN ALL CAPS\n"
                "Line 2: A brutal 1 sentence justification for the failsafe."
            )
        else:
            missing_roles = get_missing_roles(team_comp, map_name, meta_dict)
            missing_str = ', '.join(missing_roles) if missing_roles else "Flex"
            
            user_prompt = (
                f"Map: {map_name}\n"
                f"Current Team: {team_str}\n"
                f"Available Roster: {roster_str}\n"
                f"SYSTEM OVERRIDE: Missing roles: {missing_str}.\n"
                f"Task: Select the best agent to fill {missing_str} ONLY from the Available Roster."
            )
            system_prompt = (
                "You are a strict Valorant AI system. You output raw data. "
                f"Use this dataset exclusively: {meta_data_string}. "
                "CRITICAL: You MUST select an agent from the User's Available Roster. "
                "Your response must be EXACTLY two lines. No markdown.\n"
                "Line 1: The suggested AGENT NAME in ALL CAPS.\n"
                "Line 2: A tactical justification based on the missing role."
            )

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.0, 
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[!] API Error: {str(e)}"
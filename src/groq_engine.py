import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def load_meta_context():
    file_path = "../data/processed/meta_matrix.json"
    try:
        with open(file_path, "r") as file:
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
    
    available_roster = [agent for agent in roster if agent not in team_comp]
    roster_str = ', '.join(available_roster) if available_roster else "NONE"
    
    if is_panic:
        user_prompt = (
            f"Map: {map_name}\n"
            f"Task: PANIC MODE. Ignore team comp. "
            f"Available Roster: {roster_str}\n"
            f"Give me the top 3 core agents for {map_name} from my roster."
        )
        system_prompt = (
            "You are a ruthless Valorant Coach. No markdown.\n"
            "Line 1: 3 AGENT NAMES\n"
            "Line 2: A punchy 1-sentence tactical justification focusing ONLY on map geometry."
        )
    else:
        team_str = ', '.join(team_comp) if team_comp else 'None'
        is_unsalvageable = check_failsafe(team_comp, meta_dict)
        
        if is_unsalvageable:
            user_prompt = (
                f"Map: {map_name}. Team: {team_str}.\n"
                f"STATUS: UNSALVAGEABLE DRAFT.\n"
                f"Allowed Agents: {roster_str}\n"
                f"Task: Recommend the best self-sufficient carry to salvage this."
            )
            system_prompt = (
                "Your response must be EXACTLY two lines. No markdown.\n"
                "Line 1: [FAILSAFE OVERRIDE] followed by the AGENT NAME IN ALL CAPS.\n"
                "Line 2: A brutal 1-sentence justification. You MUST start the sentence with 'As the failsafe choice,' and explain how this agent carries the map alone."
            )
        else:
            missing_roles = get_missing_roles(team_comp, map_name, meta_dict)

            roles_dict = meta_dict.get("roles", {})
            team_role_counts = {}
            for agent in team_comp:
                for r, agents in roles_dict.items():
                    if agent.strip().title() in agents:
                        team_role_counts[r] = team_role_counts.get(r, 0) + 1
                        break

            formatted_missing = []
            for role in missing_roles:
                count = team_role_counts.get(role, 0)
                if count == 1:
                    formatted_missing.append(f"Secondary {role}")
                elif count >= 2:
                    formatted_missing.append(f"Tertiary {role}")
                else:
                    formatted_missing.append(role)
            
            if formatted_missing:
                missing_str = ', '.join(formatted_missing)
                sentence_prefix = f"To fill the required {missing_str} role,"
            else:
                missing_str = "Flex Pick"
                sentence_prefix = "As the optimal Flex Pick,"
            
            user_prompt = (
                f"Map: {map_name}. Current Team: {team_str}.\n"
                f"Tactical Void: The VCT data demands a {missing_str}.\n"
                f"Allowed Agents: {roster_str}\n"
                f"Task: Pick the mathematically optimal agent from Allowed Agents to fill this exact void."
            )
            system_prompt = (
                "You are an elite, ruthless Valorant tactician. "
                f"Use this dataset for meta knowledge: {meta_data_string}. "
                "CRITICAL RULES:\n"
                "1. Your response must be EXACTLY two lines. No markdown.\n"
                "2. Line 1: ONLY the chosen AGENT NAME in ALL CAPS.\n"
                f"3. Line 2: MUST START EXACTLY WITH THE PHRASE: '{sentence_prefix}'. Following that phrase, explain exactly why this agent's utility dominates this map's geometry and synergizes with the current team.\n"
                "5. NEVER invent or hallucinate agents."
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
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
            return json.dumps(json.load(file))
    except FileNotFoundError:
        return "{}"

def get_ai_recommendation(map_name, team_comp, is_panic=False):
    meta_data = load_meta_context()
    
    if is_panic:
        user_prompt = (
            f"Map: {map_name}\n"
            f"PANIC MODE. Ignore team comp. "
            f"Give me the top 3 core agents for {map_name} separated by commas."
        )
    else:
        team_str = ', '.join(team_comp) if team_comp else 'None'
        user_prompt = (
            f"Map: {map_name}\n"
            f"Current Team: {team_str}\n"
            f"If team has 3+ duelists or lacks both Controller and Initiator, "
            f"trigger a failsafe. Otherwise, fill the missing structural role."
        )

    system_prompt = (
        "You are a strict Valorant AI system. You output raw data. "
        f"Use this dataset exclusively: {meta_data}. "
        "Do NOT think out loud. Do NOT list the current team members. "
        "Your response must be EXACTLY two lines. No markdown.\n"
        "Line 1: The suggested AGENT NAME in ALL CAPS (prepend [FAILSAFE OVERRIDE] if team is unsalvageable).\n"
        "Line 2: A brutal 1 to 2 sentence tactical justification."
    )

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.0, 
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[!] API Error: {str(e)}"

if __name__ == "__main__":
    print("[>] RUNNING STANDARD DRAFT TEST ON LOTUS...")
    team = ["Raze", "Neon", "Killjoy"]
    answer = get_ai_recommendation("Lotus", team, is_panic=False)
    print(f"\n{answer}\n")
    
    print("="*50)
    
    print("[>] RUNNING PANIC MODE TEST ON BIND...")
    panic_answer = get_ai_recommendation("Bind", [], is_panic=True)
    print(f"\n{panic_answer}\n")
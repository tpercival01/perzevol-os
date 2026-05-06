import os
import json
import logging
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

META_FILE_PATH = "../data/processed/meta_matrix.json"


def load_meta_context():
    try:
        with open(META_FILE_PATH, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        logger.warning("Meta file not found at %s", META_FILE_PATH)
        return {}


def normalise_agent_name(agent_name, meta_dict):
    if not agent_name:
        return agent_name

    clean = str(agent_name).strip()

    for agents in meta_dict.get("roles", {}).values():
        for known_agent in agents:
            if clean.lower() == known_agent.lower():
                return known_agent

    return clean.title()


def get_agent_role(agent_name, meta_dict):
    agent = normalise_agent_name(agent_name, meta_dict)

    for role, agents in meta_dict.get("roles", {}).items():
        if agent in agents:
            return role

    return "Unknown"


def get_available_roster(roster, team_comp, meta_dict):
    locked = {
        normalise_agent_name(agent, meta_dict).lower()
        for agent in team_comp
    }

    available = []

    for agent in roster:
        normalised = normalise_agent_name(agent, meta_dict)
        if normalised.lower() not in locked:
            available.append(normalised)

    return sorted(set(available))


def role_counts_for_agents(agents, meta_dict):
    counts = {
        "Controller": 0,
        "Initiator": 0,
        "Sentinel": 0,
        "Duelist": 0,
        "Unknown": 0,
    }

    for agent in agents:
        role = get_agent_role(agent, meta_dict)
        counts[role] = counts.get(role, 0) + 1

    return counts


def role_count_distance(a, b):
    roles = set(a.keys()) | set(b.keys())

    return sum(
        abs(a.get(role, 0) - b.get(role, 0))
        for role in roles
    )


def count_roles_from_template(template):
    counts = {
        "Controller": 0,
        "Initiator": 0,
        "Sentinel": 0,
        "Duelist": 0,
        "Unknown": 0,
    }

    for role in template:
        counts[role] = counts.get(role, 0) + 1

    return counts


def score_candidate(candidate, map_meta, team_comp, meta_dict):
    locked_agents = [
        normalise_agent_name(agent, meta_dict)
        for agent in team_comp
    ]

    final_team = sorted(set(locked_agents + [candidate]))

    candidate_role = get_agent_role(candidate, meta_dict)
    current_role_counts = role_counts_for_agents(locked_agents, meta_dict)
    final_role_counts = role_counts_for_agents(final_team, meta_dict)

    agent_pick_rate_lookup = {
        row["agent"]: row["pick_rate"]
        for row in map_meta.get("agent_pick_rates", [])
    }

    candidate_pick_rate = agent_pick_rate_lookup.get(candidate, 0)

    top_team_comps = map_meta.get("top_team_comps", [])
    top_role_templates = map_meta.get("top_role_templates", [])

    best_score = -999999
    best_reason = {
        "candidate": candidate,
        "role": candidate_role,
        "score": -999999,
        "best_matching_comp": [],
        "best_matching_template": [],
        "agent_overlap": 0,
        "locked_overlap": 0,
        "current_role_distance": 999,
        "final_role_distance": 999,
        "role_improvement": -999,
        "comp_rate": 0,
        "candidate_pick_rate": candidate_pick_rate,
    }

    for comp_row in top_team_comps:
        pro_comp = comp_row["value"]
        pro_comp_set = set(pro_comp)

        pro_role_counts = role_counts_for_agents(pro_comp, meta_dict)

        current_distance = role_count_distance(
            current_role_counts,
            pro_role_counts,
        )

        final_distance = role_count_distance(
            final_role_counts,
            pro_role_counts,
        )

        role_improvement = current_distance - final_distance

        locked_overlap = len(set(locked_agents) & pro_comp_set)
        final_overlap = len(set(final_team) & pro_comp_set)
        candidate_in_comp = candidate in pro_comp_set
        comp_rate = comp_row["rate"]

        score = 0

        # Mathematical Re-weighting: Validity > Fluke Overlaps
        score += role_improvement * 100
        score -= final_distance * 60

        if role_improvement < 0:
            score -= 300

        if role_improvement == 0:
            score -= 50

        # Create a strict penalty multiplier for obscure comps (< 10% pick rate)
        rate_multiplier = max(comp_rate / 10, 0.4) 

        score += (locked_overlap * 20) * rate_multiplier
        score += (final_overlap * 15) * rate_multiplier

        if candidate_in_comp:
            score += 25 * rate_multiplier

        # Heavily reward picking meta-valid comps
        score += comp_rate * 4
        score += candidate_pick_rate * 2.5

        if score > best_score:
            best_score = score
            best_reason = {
                "candidate": candidate,
                "role": candidate_role,
                "score": round(score, 2),
                "best_matching_comp": pro_comp,
                "best_matching_template": list(pro_role_counts.keys()),
                "agent_overlap": final_overlap,
                "locked_overlap": locked_overlap,
                "current_role_distance": current_distance,
                "final_role_distance": final_distance,
                "role_improvement": role_improvement,
                "comp_rate": comp_rate,
                "candidate_pick_rate": candidate_pick_rate,
                "candidate_in_comp": candidate_in_comp,
            }

    # Fallback if no actual comps exist.
    if not top_team_comps and top_role_templates:
        for template_row in top_role_templates:
            template = template_row["value"]
            template_counts = count_roles_from_template(template)

            current_distance = role_count_distance(
                current_role_counts,
                template_counts,
            )

            final_distance = role_count_distance(
                final_role_counts,
                template_counts,
            )

            role_improvement = current_distance - final_distance
            template_rate = template_row["rate"]

            score = 0
            score += role_improvement * 100
            score -= final_distance * 50

            if role_improvement < 0:
                score -= 300

            if role_improvement == 0:
                score -= 40

            score += template_rate * 2
            score += candidate_pick_rate * 1.5

            if score > best_score:
                best_score = score
                best_reason = {
                    "candidate": candidate,
                    "role": candidate_role,
                    "score": round(score, 2),
                    "best_matching_comp": [],
                    "best_matching_template": template,
                    "agent_overlap": 0,
                    "locked_overlap": 0,
                    "current_role_distance": current_distance,
                    "final_role_distance": final_distance,
                    "role_improvement": role_improvement,
                    "comp_rate": template_rate,
                    "candidate_pick_rate": candidate_pick_rate,
                    "candidate_in_comp": False,
                }

    return best_reason


def get_ranked_candidates(map_name, team_comp, roster):
    meta_dict = load_meta_context()
    map_meta = meta_dict.get("map_meta", {}).get(map_name, {})

    available_roster = get_available_roster(roster, team_comp, meta_dict)

    # --- THE PRE-FILTER OVERRIDE ---
    # Intercept bad Bronze drafts and force the correct role filter
    current_roles = role_counts_for_agents(team_comp, meta_dict)
    strictly_required_role = None

    if len(team_comp) >= 3 and current_roles.get("Controller", 0) == 0:
        strictly_required_role = "Controller"
        
    if strictly_required_role:
        filtered_roster = [
            agent for agent in available_roster 
            if get_agent_role(agent, meta_dict) == strictly_required_role
        ]
        if filtered_roster:
            available_roster = filtered_roster

    scored = [
        score_candidate(candidate, map_meta, team_comp, meta_dict)
        for candidate in available_roster
    ]

    scored = sorted(
        scored,
        key=lambda row: row["score"],
        reverse=True,
    )

    return scored


def get_debug_state(map_name, team_comp, roster):
    meta_dict = load_meta_context()
    map_meta = meta_dict.get("map_meta", {}).get(map_name, {})

    ranked_candidates = get_ranked_candidates(map_name, team_comp, roster)

    return {
        "source_type": meta_dict.get("source_type"),
        "map": map_name,
        "team_comp": team_comp,
        "role_counts": role_counts_for_agents(team_comp, meta_dict),
        "sample_size_team_comps": map_meta.get("sample_size_team_comps"),
        "estimated_maps_played": map_meta.get("estimated_maps_played"),
        "confidence": map_meta.get("confidence"),
        "region_breakdown": map_meta.get("region_breakdown", {}),
        "primary_team_comp": map_meta.get("primary_team_comp", []),
        "primary_role_template": map_meta.get("primary_role_template", []),
        "top_team_comps": map_meta.get("top_team_comps", [])[:5],
        "top_role_templates": map_meta.get("top_role_templates", [])[:5],
        "ranked_candidates": ranked_candidates[:10],
    }


def validate_model_pick(raw_response, fallback_agent, fallback_role):
    # Ensure standard output formatting
    lines = raw_response.splitlines()
    if len(lines) >= 2:
        return raw_response

    return (
        f"{fallback_agent}\n"
        f"To complete the closest VCT-derived team comp, this {fallback_role} is the highest-scoring valid pick from the actual pro composition data."
    )


def check_is_failsafe(team_comp, meta_dict):
    if len(team_comp) < 3: return False
    
    counts = role_counts_for_agents(team_comp, meta_dict)
    
    if counts["Duelist"] >= 3: 
        return True
        
    if counts["Controller"] == 0 and counts["Initiator"] == 0: 
        return True
        
    return False


def get_ai_recommendation(map_name, team_comp, roster, is_panic=False):
    meta_dict = load_meta_context()
    map_meta = meta_dict.get("map_meta", {}).get(map_name, {})
    ranked_candidates = get_ranked_candidates(map_name, team_comp, roster)

    logger.info("Top 5 candidate scores:")
    for row in ranked_candidates[:5]:
        logger.info(
            "%s | role=%s | score=%s | comp_rate=%s | pick_rate=%s | comp=%s",
            row["candidate"],
            row["role"],
            row["score"],
            row.get("comp_rate"),
            row["candidate_pick_rate"],
            row["best_matching_comp"],
        )

    if not ranked_candidates:
        return (
            "NO VALID PICK\n"
            "No available roster agents could be scored against the current VCT composition matrix."
        )

    if is_panic:
        top_three = ranked_candidates[:3]
        names = ", ".join(row["candidate"].upper() for row in top_three)
        return (
            f"{names}\n"
            f"As the panic shortlist, these are the highest-scoring agents from the actual VCT composition data on {map_name}."
        )

    team_str = ", ".join(team_comp) if team_comp else "None"
    best = ranked_candidates[0]
    best_agent = best["candidate"]

    # Failsafe Narrative Trigger
    is_failsafe = check_is_failsafe(team_comp, meta_dict)
    
    if is_failsafe:
        # Heavily prioritize self-sufficient carry agents if available
        carry_agents = ["Reyna", "Omen", "Phoenix", "Clove", "Chamber"]
        valid_carries = [a for a in carry_agents if a in roster and a not in team_comp]
        if valid_carries:
            best_agent = valid_carries[0]

        system_prompt = (
            "You are a ruthless tactical AI forced into an unsalvageable situation. "
            "Python has detected 3 or more Duelists, or completely unplayable synergy. "
            "You must output exactly two lines. Absolutely no markdown.\n"
            f"Line 1: EXACTLY the phrase '[FAILSAFE OVERRIDE] {best_agent.upper()}' \n"
            "Line 2: Start with 'As the failsafe choice, ' and demand a fully self-sufficient playstyle."
        )
    else:
        system_prompt = (
            "You are an elite Valorant draft analyst. "
            "The Python engine has already selected the correct agent using actual VCT team composition data. "
            "Your job is only to explain the pick. "
            "Do not choose a different agent. "
            "No markdown. Exactly two lines.\n"
            "Line 1: ONLY the recommended agent name in ALL CAPS.\n"
            "Line 2: Start with 'To complete the closest VCT-derived team comp,' then explain the pick in one sentence based purely on map geometry."
        )

    user_prompt = (
        f"Map: {map_name}\n"
        f"Current team: {team_str}\n"
        f"Python-selected agent: {best_agent}\n"
        f"Context role: {best.get('role', 'Unknown')}"
    )

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.0,
        )

        raw_response = response.choices[0].message.content.strip()
        logger.info("AI Response Generated:\n%s", raw_response)
        
        return validate_model_pick(raw_response, best_agent, best["role"])

    except Exception as e:
        logger.exception("Groq API call failed")
        return (
            f"{best_agent.upper()}\n"
            f"To complete the closest VCT-derived team comp, the local scoring engine selected this as the strongest valid pick. Groq failed: {str(e)}"
        )
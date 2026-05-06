import json
import os
from collections import Counter, defaultdict

import pandas as pd


RAW_COMP_PATH = "../data/raw/vct_data.csv"
OUTPUT_JSON_PATH = "../data/processed/meta_matrix.json"

MASTER_ROLES = {
    "Controller": ["Omen", "Viper", "Astra", "Brimstone", "Harbor", "Clove", "Miks"],
    "Initiator": ["Sova", "Fade", "Skye", "KAY/O", "Breach", "Gekko", "Tejo"],
    "Sentinel": ["Killjoy", "Cypher", "Chamber", "Sage", "Deadlock", "Vyse", "Veto"],
    "Duelist": ["Jett", "Raze", "Reyna", "Phoenix", "Yoru", "Neon", "Iso", "Waylay"],
}

AGENT_ALIASES = {
    "kayo": "KAY/O",
    "kay/o": "KAY/O",
    "kay-o": "KAY/O",
    "kay o": "KAY/O",
}


def normalise_agent(agent_name):
    if pd.isna(agent_name):
        return None

    clean = str(agent_name).strip()

    if not clean:
        return None

    alias = AGENT_ALIASES.get(clean.lower())
    if alias:
        return alias

    for agents in MASTER_ROLES.values():
        for known_agent in agents:
            if clean.lower() == known_agent.lower():
                return known_agent

    return clean.title()


def get_agent_role(agent_name):
    agent = normalise_agent(agent_name)

    for role, agents in MASTER_ROLES.items():
        if agent in agents:
            return role

    return "Unknown"


def normalise_comp(agents):
    clean_agents = []

    for agent in agents:
        normalised = normalise_agent(agent)

        if normalised:
            clean_agents.append(normalised)

    unique_agents = list(dict.fromkeys(clean_agents))

    if len(unique_agents) != 5:
        raise ValueError(
            f"Expected 5 unique agents, got {len(unique_agents)}: {unique_agents}"
        )

    return tuple(sorted(unique_agents))


def get_role_template(agents):
    role_order = {
        "Controller": 0,
        "Initiator": 1,
        "Sentinel": 2,
        "Duelist": 3,
        "Unknown": 4,
    }

    roles = [get_agent_role(agent) for agent in agents]

    return tuple(
        sorted(
            roles,
            key=lambda role: role_order.get(role, 99),
        )
    )


def counter_to_ranked_list(counter, total, limit=10):
    ranked = []

    for key, count in counter.most_common(limit):
        value = list(key) if isinstance(key, tuple) else key

        ranked.append(
            {
                "value": value,
                "count": int(count),
                "rate": round((count / total) * 100, 2) if total else 0,
            }
        )

    return ranked


def load_comp_data():
    if not os.path.exists(RAW_COMP_PATH):
        raise FileNotFoundError(f"Could not find {RAW_COMP_PATH}")

    df = pd.read_csv(RAW_COMP_PATH)

    required_columns = {
        "Region",
        "Event",
        "MatchId",
        "Map",
        "Team",
        "Opponent",
        "Result",
        "MatchUrl",
        "Agent1",
        "Agent2",
        "Agent3",
        "Agent4",
        "Agent5",
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            "vct_data.csv must contain these columns: "
            f"{sorted(required_columns)}. Missing: {sorted(missing)}"
        )

    rows = []
    bad_rows = []

    for index, row in df.iterrows():
        agents = [
            row["Agent1"],
            row["Agent2"],
            row["Agent3"],
            row["Agent4"],
            row["Agent5"],
        ]

        try:
            comp = normalise_comp(agents)
        except ValueError as error:
            bad_rows.append(
                {
                    "row_index": index,
                    "team": row.get("Team", "Unknown"),
                    "map": row.get("Map", "Unknown"),
                    "error": str(error),
                }
            )
            continue

        role_template = get_role_template(comp)

        rows.append(
            {
                "region": str(row["Region"]).strip(),
                "event": str(row["Event"]).strip(),
                "match_id": str(row["MatchId"]).strip(),
                "map": str(row["Map"]).strip(),
                "team": str(row["Team"]).strip(),
                "opponent": str(row["Opponent"]).strip(),
                "result": str(row["Result"]).strip(),
                "match_url": str(row["MatchUrl"]).strip(),
                "comp": comp,
                "role_template": role_template,
            }
        )

    if bad_rows:
        print("[!] Bad rows skipped:")
        for bad_row in bad_rows:
            print(f"    {bad_row}")

    return rows


def validate_match_pairs(rows):
    match_counts = Counter(row["match_id"] for row in rows)

    invalid = {
        match_id: count
        for match_id, count in match_counts.items()
        if count != 2
    }

    if invalid:
        print("[!] WARNING: Some MatchId values do not have exactly 2 team rows.")
        for match_id, count in sorted(invalid.items()):
            print(f"    {match_id}: {count} rows")

    return invalid


def build_agent_pick_rates(comps):
    total_team_comps = len(comps)
    agent_counter = Counter()
    role_counter = Counter()

    for row in comps:
        for agent in row["comp"]:
            agent_counter[agent] += 1
            role_counter[get_agent_role(agent)] += 1

    agent_pick_rates = []

    for agent, count in agent_counter.most_common():
        agent_pick_rates.append(
            {
                "agent": agent,
                "role": get_agent_role(agent),
                "count": int(count),
                "pick_rate": round((count / total_team_comps) * 100, 2),
            }
        )

    role_pick_rates = []

    # Each comp has 5 slots, so role denominator is team_comps * 5.
    total_role_slots = total_team_comps * 5

    for role, count in role_counter.most_common():
        role_pick_rates.append(
            {
                "role": role,
                "count": int(count),
                "slot_rate": round((count / total_role_slots) * 100, 2),
            }
        )

    return agent_pick_rates, role_pick_rates


def build_top_agents_by_role(agent_pick_rates):
    top_agents_by_role = {}

    for role in MASTER_ROLES:
        top_agents_by_role[role] = [
            row
            for row in agent_pick_rates
            if row["role"] == role
        ][:5]

    return top_agents_by_role


def build_recent_examples(comps, limit=10):
    examples = []

    for row in comps[:limit]:
        examples.append(
            {
                "match_id": row["match_id"],
                "team": row["team"],
                "opponent": row["opponent"],
                "result": row["result"],
                "comp": list(row["comp"]),
                "role_template": list(row["role_template"]),
                "match_url": row["match_url"],
            }
        )

    return examples


def get_confidence(total_team_comps):
    if total_team_comps >= 80:
        return "high"

    if total_team_comps >= 40:
        return "medium"

    return "low"


def build_matrix():
    print("[>] INITIATING TRUE VCT TEAM COMP PIPELINE...")

    rows = load_comp_data()
    validate_match_pairs(rows)

    map_rows = defaultdict(list)

    for row in rows:
        map_rows[row["map"]].append(row)

    matrix = {
        "roles": MASTER_ROLES,
        "source_type": "actual_team_compositions",
        "raw_file": RAW_COMP_PATH,
        "total_team_comps": len(rows),
        "total_maps": len({row["match_id"] for row in rows}),
        "map_meta": {},
    }

    print(
        f"[>] Loaded {len(rows)} team compositions "
        f"from {matrix['total_maps']} maps across {len(map_rows)} map names."
    )

    for map_name, comps in sorted(map_rows.items()):
        total_team_comps = len(comps)

        unique_match_ids = {
            row["match_id"]
            for row in comps
            if row["match_id"] != "Unknown"
        }

        comp_counter = Counter(row["comp"] for row in comps)
        role_template_counter = Counter(row["role_template"] for row in comps)
        region_counter = Counter(row["region"] for row in comps)
        event_counter = Counter(row["event"] for row in comps)

        top_team_comps = counter_to_ranked_list(
            comp_counter,
            total_team_comps,
            limit=15,
        )

        top_role_templates = counter_to_ranked_list(
            role_template_counter,
            total_team_comps,
            limit=10,
        )

        agent_pick_rates, role_pick_rates = build_agent_pick_rates(comps)
        top_agents_by_role = build_top_agents_by_role(agent_pick_rates)

        primary_team_comp = top_team_comps[0]["value"] if top_team_comps else []
        primary_role_template = (
            top_role_templates[0]["value"]
            if top_role_templates
            else []
        )

        confidence = get_confidence(total_team_comps)

        matrix["map_meta"][map_name] = {
            "sample_size_team_comps": total_team_comps,
            "maps_played": len(unique_match_ids),
            "confidence": confidence,
            "region_breakdown": dict(region_counter),
            "event_breakdown": dict(event_counter),

            "top_team_comps": top_team_comps,
            "top_role_templates": top_role_templates,

            "primary_team_comp": primary_team_comp,
            "primary_role_template": primary_role_template,

            "agent_pick_rates": agent_pick_rates,
            "role_pick_rates": role_pick_rates,
            "top_agents_by_role": top_agents_by_role,

            "examples": build_recent_examples(comps, limit=10),

            # Backwards-compatible fields for existing app code.
            "core_agents": primary_team_comp[:4],
            "strong_flex": primary_team_comp[4:],
            "preferred_templates": [primary_role_template],
        }

        print(
            f"    [*] {map_name.upper()} "
            f"teams={total_team_comps} "
            f"maps={len(unique_match_ids)} "
            f"primary_comp={primary_team_comp} "
            f"primary_roles={primary_role_template} "
            f"confidence={confidence}"
        )

    os.makedirs(os.path.dirname(OUTPUT_JSON_PATH), exist_ok=True)

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(matrix, file, indent=4)

    print(f"\n[>] PIPELINE COMPLETE. True comp matrix saved to {OUTPUT_JSON_PATH}")


if __name__ == "__main__":
    build_matrix()
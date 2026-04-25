import pandas as pd
import json
import os

RAW_DATA_PATH = '../data/raw/vct_data.csv'
OUTPUT_JSON_PATH = '../data/processed/meta_matrix.json'

MASTER_ROLES = {
    "Controller": ["Omen", "Viper", "Astra", "Brimstone", "Harbor", "Clove", "Miks"],
    "Initiator": ["Sova", "Fade", "Skye", "KAY/O", "Breach", "Gekko", "Tejo"],
    "Sentinel": ["Killjoy", "Cypher", "Chamber", "Sage", "Deadlock", "Vyse", "Veto"],
    "Duelist": ["Jett", "Raze", "Reyna", "Phoenix", "Yoru", "Neon", "Iso", "Waylay"]
}

def build_matrix():
    print("[>] INITIATING GLOBAL VCT DATA PIPELINE...")
    
    try:
        df = pd.read_csv(RAW_DATA_PATH)
    except FileNotFoundError:
        print(f"[!] ERROR: Could not find {RAW_DATA_PATH}")
        return

    df['TotalPicks'] = (df['PickRate'] / 100) * df['MatchesPlayed']
    
    print("[>] Aggregating Global Regions...")
    global_df = df.groupby(['Map', 'Agent', 'Role']).agg({
        'TotalPicks': 'sum',
        'MatchesPlayed': 'sum'
    }).reset_index()
    
    global_df['PickRate'] = (
        global_df['TotalPicks'] / global_df['MatchesPlayed']
    ) * 100

    matrix = {
        "roles": MASTER_ROLES,
        "map_meta": {}
    }

    maps = global_df['Map'].unique()
    print(f"[>] Analyzing Global Meta for {len(maps)} Maps...")

    for map_name in maps:
        map_data = global_df[global_df['Map'] == map_name].sort_values(
            by='PickRate', ascending=False
        )
        
        total_matches = map_data['MatchesPlayed'].max()
        if total_matches > 100:
            confidence = "high"
        elif total_matches > 50:
            confidence = "medium"
        else:
            confidence = "low"

        core_agents = map_data.head(4)['Agent'].tolist()
        strong_flex = map_data.iloc[4:7]['Agent'].tolist()
        top_5_roles = map_data.head(5)['Role'].tolist()

        matrix["map_meta"][map_name] = {
            "core_agents": core_agents,
            "strong_flex": strong_flex,
            "preferred_templates": [top_5_roles],
            "confidence": confidence,
            "sample_size": int(total_matches)
        }
        
        print(f"    [*] {map_name.upper()} Meta Locked (n={int(total_matches)})")

    os.makedirs(os.path.dirname(OUTPUT_JSON_PATH), exist_ok=True)
    with open(OUTPUT_JSON_PATH, 'w') as f:
        json.dump(matrix, f, indent=4)

    print(f"\n[>] PIPELINE COMPLETE. Global Matrix saved.")

if __name__ == "__main__":
    build_matrix()

import time
from modules.warzone.ttk_oracle_engine import (
    load_ttk_data,
    optimise_single_weapon_build,
)

guns, attachments = load_ttk_data()

for weapon in ["AK-27", "MADDOX RFB", "EGRT-17"]:
    start = time.perf_counter()
    results = optimise_single_weapon_build(
        guns=guns,
        attachments=attachments,
        weapon_name=weapon,
        map_type="Small map / Resurgence",
        fight_type="Mid range",
        build_goal="Balanced meta build",
        enemy_health=300,
        attachment_count=5,
        top_n=10,
    )
    elapsed = time.perf_counter() - start

    print(f"{weapon}: {elapsed:.2f}s, rows={len(results)}")
    if results.empty:
        raise SystemExit(f"FAILED: no result for {weapon}")

print("PASSED: Fast optimiser returns AR builds.")

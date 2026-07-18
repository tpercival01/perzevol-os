from types import SimpleNamespace
import csv

import pandas as pd

from modules.warzone import best_ttk_cache
from modules.warzone.meta_baselines import (
    load_meta_loadouts,
    matching_meta_loadouts,
    normalise_meta_challenge_tag,
    upsert_meta_loadout,
)
from modules.warzone.ttk_csv_repair import build_clean_attachment_dataframe
from modules.warzone.ttk_data_health import build_ttk_data_health_report


class DummyAvailability:
    def to_dict(self):
        return {
            "weapon_name": "XM325",
            "mode": "max_level",
            "eligible_count": 8,
        }


def test_best_ttk_cache_roundtrip_and_csv_stamp_invalidation(tmp_path, monkeypatch):
    cache_dir = tmp_path / "best_ttk_cache"
    guns_path = tmp_path / "guns.csv"
    attachments_path = tmp_path / "attachments.csv"

    guns_path.write_text("gun_id,gun_name\nxm325,XM325\n", encoding="utf-8")
    attachments_path.write_text("attachment_id\nbolt_carrier_group\n", encoding="utf-8")

    monkeypatch.setattr(best_ttk_cache, "BEST_TTK_CACHE_DIR", cache_dir)

    key_1 = best_ttk_cache.best_ttk_cache_key(
        selected_weapon="XM325",
        build_goal="Fastest TTK",
        fight_type="Mid range",
        map_type="Small map / Resurgence",
        challenge_summary="",
        challenge_rules=[],
        min_attachment_count=0,
        attachment_unlock_mode="max_level",
        stats_profile="multiplayer",
        enemy_health=300,
        guns_path=guns_path,
        attachments_path=attachments_path,
    )

    session = SimpleNamespace(
        weapon_name="XM325",
        results=pd.DataFrame(
            [
                {
                    "gun_name": "XM325",
                    "attachments": "Bolt Carrier Group",
                    "raw_ttk_ms": 822,
                    "practical_ttk_ms": 887,
                }
            ]
        ),
        availability=DummyAvailability(),
        warnings=["test warning"],
    )

    best_ttk_cache.save_best_ttk_cache(key_1, session)
    loaded = best_ttk_cache.load_best_ttk_cache(key_1)

    assert loaded is not None
    assert loaded.cache_status == "HIT"
    assert loaded.weapon_name == "XM325"
    assert loaded.results.iloc[0]["raw_ttk_ms"] == 822
    assert loaded.availability.to_dict()["eligible_count"] == 8

    attachments_path.write_text(
        "attachment_id\nbolt_carrier_group\nlti_stentorian_brake\n",
        encoding="utf-8",
    )

    key_2 = best_ttk_cache.best_ttk_cache_key(
        selected_weapon="XM325",
        build_goal="Fastest TTK",
        fight_type="Mid range",
        map_type="Small map / Resurgence",
        challenge_summary="",
        challenge_rules=[],
        min_attachment_count=0,
        attachment_unlock_mode="max_level",
        stats_profile="multiplayer",
        enemy_health=300,
        guns_path=guns_path,
        attachments_path=attachments_path,
    )

    assert key_1 != key_2


def test_meta_baseline_upsert_matching_and_challenge_normalisation(tmp_path):
    path = tmp_path / "meta_loadouts.csv"

    assert normalise_meta_challenge_tag("No challenge / Best TTK") == "best_ttk"

    upsert_meta_loadout(
        {
            "loadout_name": "XM325 Season Baseline",
            "source": "manual",
            "stats_profile": "Multiplayer",
            "weapon_id": "XM325",
            "weapon_name": "XM325",
            "challenge_tag": "No challenge / Best TTK",
            "enemy_health": "300",
            "attachment_1": "bolt_carrier_group",
            "attachment_2": "lti_stentorian_brake",
            "verification_status": "manual",
        },
        path=path,
    )

    upsert_meta_loadout(
        {
            "loadout_name": "XM325 Season Baseline",
            "source": "manual",
            "stats_profile": "multiplayer",
            "weapon_id": "xm325",
            "weapon_name": "XM325",
            "challenge_tag": "best_ttk",
            "enemy_health": "300",
            "attachment_1": "bolt_carrier_group",
            "attachment_2": "lti_stentorian_brake",
            "notes": "updated notes",
            "verification_status": "manual",
        },
        path=path,
    )

    data = load_meta_loadouts(path)
    assert len(data) == 1
    assert data.iloc[0]["notes"] == "updated notes"

    matches = matching_meta_loadouts(
        data,
        stats_profile="multiplayer",
        weapon_id="xm325",
        challenge_tag="No challenge / Best TTK",
        enemy_health=300,
    )

    assert len(matches) == 1
    assert matches.iloc[0]["attachment_1"] == "bolt_carrier_group"


def test_csv_repair_drops_malformed_rows_adds_conflicts_and_blocks_conversions(tmp_path):
    source = tmp_path / "attachments.csv"

    header = [
        "attachment_id",
        "attachment_name",
        "slot",
        "stats_profile",
        "compatible_guns",
        "verification_status",
        "verification_notes",
    ]

    with source.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerow(
            [
                "parallel_foregrip",
                "Parallel Foregrip",
                "underbarrel",
                "multiplayer",
                "xm325",
                "verified",
                "",
            ]
        )
        writer.writerow(
            [
                "xm325_titan_wield",
                "XM325 Titan Wield",
                "fire_mod",
                "multiplayer",
                "xm325",
                "partial",
                "Conversion-style behaviour is not fully modelled.",
            ]
        )
        writer.writerow(["bad_row", "Broken Row"])

    repaired, report = build_clean_attachment_dataframe(source)

    assert len(report.dropped_malformed_rows) == 1
    assert "conflicts_with_slots" in repaired.columns
    assert "XM325 Titan Wield" in report.blocked_conversion_rows

    parallel = repaired[repaired["attachment_id"].eq("parallel_foregrip")].iloc[0]
    assert parallel["conflicts_with_slots"] == "optic"

    conversion = repaired[repaired["attachment_id"].eq("xm325_titan_wield")].iloc[0]
    assert conversion["verification_status"] == "conversion_unmodelled"


def test_ttk_data_health_flags_malformed_rows_missing_conflict_schema_and_unlock_coverage(tmp_path):
    guns_path = tmp_path / "guns.csv"
    attachments_path = tmp_path / "attachments.csv"

    guns_path.write_text(
        "gun_id,gun_name,weapon_class,stats_profile\n"
        "shadow_sk,SHADOW SK,sniper_rifle,multiplayer\n"
        "xm325,XM325,lmg,multiplayer\n",
        encoding="utf-8",
    )

    with attachments_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "attachment_id",
                "attachment_name",
                "slot",
                "stats_profile",
                "compatible_weapon_classes",
                "compatible_guns",
                "unlock_weapon",
                "unlock_level",
                "unlock_method",
                "verification_status",
                "verification_notes",
            ]
        )
        writer.writerow(
            [
                "good_unlock",
                "Good Unlock",
                "muzzle",
                "multiplayer",
                "lmg",
                "",
                "xm325",
                "12",
                "weapon_level",
                "verified",
                "",
            ]
        )
        writer.writerow(
            [
                "shadow_bad",
                "Shadow Bad",
                "barrel",
                "multiplayer",
                "",
                "shadow_sk",
                "",
                "",
                "",
                "verified",
                "",
            ]
        )
        writer.writerow(["malformed_shadow", "Malformed Shadow", "barrel", "multiplayer", "", "shadow_sk"])

    report = build_ttk_data_health_report(
        active_stats_profile="multiplayer",
        guns_path=guns_path,
        attachments_path=attachments_path,
    )

    assert report["summary"]["malformed_attachment_rows"] == 1
    assert report["summary"]["missing_conflict_columns"] == 3
    assert "SHADOW SK" in report["summary"]["unsafe_weapons"]

    coverage = report["unlock_coverage"]
    xm325 = coverage[coverage["gun_name"].eq("XM325")].iloc[0]
    assert xm325["current_level_reliable"] == "YES"

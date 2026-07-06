import pandas as pd

from modules.warzone.ttk_oracle_engine import (
    build_ttk_data_warnings,
    build_attachment_verification_rows,
    calculate_raw_ttk_ms,
    describe_weapon_build_data,
    generate_legal_attachment_combos,
    parse_codmunity_attachment_html,
    apply_attachment_to_stats,
    get_compatible_attachments,
    optimise_single_weapon_build,
)


def sample_guns():
    return pd.DataFrame(
        [
            {
                "gun_id": "hawker_hx",
                "gun_name": "HAWKER HX",
                "weapon_class": "Sniper Rifle",
                "damage_close": 120,
                "range_close_m": 25,
                "damage_mid": 100,
                "range_mid_m": 60,
                "damage_long": 95,
                "fire_rate_rpm": 60,
                "ads_ms": 520,
                "sprint_to_fire_ms": 260,
                "recoil": 55,
                "bullet_velocity": 960,
                "mag_size": 7,
            },
            {
                "gun_id": "carbon_57",
                "gun_name": "CARBON 57",
                "weapon_class": "SMG",
                "damage_close": 32,
                "range_close_m": 12,
                "damage_mid": 24,
                "range_mid_m": 24,
                "damage_long": 18,
                "fire_rate_rpm": 820,
                "ads_ms": 190,
                "sprint_to_fire_ms": 95,
                "recoil": 42,
                "bullet_velocity": 550,
                "mag_size": 40,
            },
        ]
    )


def sample_attachments():
    return pd.DataFrame(
        [
            {
                "attachment_id": "sniper_muzzle",
                "attachment_name": "Test Suppressor",
                "slot": "Muzzle",
                "compatible_weapon_classes": "Sniper Rifle",
                "compatible_guns": "",
                "damage_pct": 0,
                "fire_rate_pct": 0,
                "ads_ms_add": 5,
                "sprint_to_fire_ms_add": 0,
                "recoil_pct": -5,
                "bullet_velocity_pct": 10,
                "range_pct": 5,
                "mag_size_add": 0,
            },
            {
                "attachment_id": "sniper_barrel",
                "attachment_name": "Test Barrel",
                "slot": "Barrel",
                "compatible_weapon_classes": "Sniper Rifle",
                "compatible_guns": "",
                "damage_pct": 0,
                "fire_rate_pct": 0,
                "ads_ms_add": 20,
                "sprint_to_fire_ms_add": 0,
                "recoil_pct": -2,
                "bullet_velocity_pct": 15,
                "range_pct": 10,
                "mag_size_add": 0,
            },
            {
                "attachment_id": "sniper_grip",
                "attachment_name": "Test Grip",
                "slot": "Rear Grip",
                "compatible_weapon_classes": "Sniper Rifle",
                "compatible_guns": "",
                "damage_pct": 0,
                "fire_rate_pct": 0,
                "ads_ms_add": -30,
                "sprint_to_fire_ms_add": -5,
                "recoil_pct": 3,
                "bullet_velocity_pct": 0,
                "range_pct": 0,
                "mag_size_add": 0,
            },
            {
                "attachment_id": "sniper_laser",
                "attachment_name": "Test Laser",
                "slot": "Laser",
                "compatible_weapon_classes": "Sniper Rifle",
                "compatible_guns": "",
                "damage_pct": 0,
                "fire_rate_pct": 0,
                "ads_ms_add": -25,
                "sprint_to_fire_ms_add": -20,
                "recoil_pct": 0,
                "bullet_velocity_pct": 0,
                "range_pct": 0,
                "mag_size_add": 0,
            },
            {
                "attachment_id": "sniper_bolt",
                "attachment_name": "Test Bolt",
                "slot": "Fire Mods",
                "compatible_weapon_classes": "Sniper Rifle",
                "compatible_guns": "HAWKER HX",
                "damage_pct": 0,
                "fire_rate_pct": 10,
                "ads_ms_add": 0,
                "sprint_to_fire_ms_add": 0,
                "recoil_pct": 0,
                "bullet_velocity_pct": 0,
                "range_pct": 0,
                "mag_size_add": 0,
            },
        ]
    )


def test_raw_ttk_uses_shots_minus_one():
    assert calculate_raw_ttk_ms(damage=50, fire_rate_rpm=600, enemy_health=300) == 500


def test_compatibility_accepts_class_wide_and_gun_specific_rows():
    guns = sample_guns()
    attachments = sample_attachments()
    hawker = guns[guns["gun_name"] == "HAWKER HX"].iloc[0]

    compatible = get_compatible_attachments(hawker, attachments)

    assert len(compatible) == 5
    assert "Test Bolt" in compatible["attachment_name"].tolist()


def test_legal_combo_generator_never_duplicates_slots():
    attachments = sample_attachments()
    combos = list(generate_legal_attachment_combos(attachments, attachment_count=5))

    assert len(combos) == 1
    slots = [attachment["slot"] for attachment in combos[0]]
    assert len(slots) == len(set(slots))


def test_single_weapon_optimiser_is_locked_to_selected_weapon():
    results = optimise_single_weapon_build(
        guns=sample_guns(),
        attachments=sample_attachments(),
        weapon_name="HAWKER HX",
        map_type="Small map / Resurgence",
        fight_type="Mid range",
        build_goal="Balanced meta build",
        enemy_health=300,
        attachment_count=5,
        top_n=5,
    )

    assert not results.empty
    assert set(results["gun_name"]) == {"HAWKER HX"}


def test_single_weapon_data_status_reports_missing_slots():
    status = describe_weapon_build_data(
        guns=sample_guns(),
        attachments=sample_attachments().head(3),
        weapon_name="HAWKER HX",
        attachment_count=5,
    )

    assert status["buildable"] is False
    assert status["compatible_slots"] == 3
    assert "Needs 5" in status["message"]


def test_data_warnings_use_real_compatibility_not_only_compatible_guns():
    warnings = build_ttk_data_warnings(
        guns=sample_guns().head(1),
        attachments=sample_attachments(),
        attachment_count=5,
    )

    assert not any("no compatible attachment data" in warning.lower() for warning in warnings)


def test_percentage_handling_modifiers_apply_against_base_stats():
    gun = sample_guns().iloc[0]
    stats = {
        "damage_close": float(gun["damage_close"]),
        "range_close_m": float(gun["range_close_m"]),
        "damage_mid": float(gun["damage_mid"]),
        "range_mid_m": float(gun["range_mid_m"]),
        "damage_long": float(gun["damage_long"]),
        "fire_rate_rpm": float(gun["fire_rate_rpm"]),
        "ads_ms": float(gun["ads_ms"]),
        "sprint_to_fire_ms": float(gun["sprint_to_fire_ms"]),
        "recoil": float(gun["recoil"]),
        "bullet_velocity": float(gun["bullet_velocity"]),
        "mag_size": float(gun["mag_size"]),
    }

    attachment = {
        "attachment_name": "Percent Handling Test",
        "ads_pct": -10,
        "sprint_to_fire_pct": -20,
        "gun_kick_pct": -10,
        "horizontal_recoil_pct": -20,
        "vertical_recoil_pct": -30,
        "bullet_velocity_pct": 25,
        "mag_size_add": 2,
    }

    updated = apply_attachment_to_stats(stats, attachment)

    assert round(updated["ads_ms"], 2) == 468.0
    assert round(updated["sprint_to_fire_ms"], 2) == 208.0
    assert round(updated["recoil"], 2) == 44.0
    assert round(updated["bullet_velocity"], 2) == 1200.0
    assert round(updated["mag_size"], 2) == 9.0


def test_codmunity_html_parser_extracts_attachment_rows_and_stats():
    html = """
    <table>
      <tr>
        <td><span class="attachment-name">DashLine Speed Mag</span></td>
        <td><span class="label">Fast Mag I</span></td>
        <td><span class="unlock">Level 4</span></td>
        <td><span class="slot">Magazine</span></td>
        <td>
          <div class="attachment-stats-item positive"><span class="highlight">-3.0%</span> ADS Speed </div>
          <div class="attachment-stats-item positive"><span class="highlight">-6.0%</span> Sprint To Fire </div>
          <div class="attachment-stats-item positive"><span class="highlight">+2</span> Magazine Size </div>
        </td>
      </tr>
    </table>
    """

    parsed = parse_codmunity_attachment_html(html, compatible_guns="VS RECON")

    assert len(parsed) == 1
    row = parsed.iloc[0]
    assert row["attachment_name"] == "DashLine Speed Mag"
    assert row["slot"] == "Magazine"
    assert row["compatible_guns"] == "VS RECON"
    assert row["ads_pct"] == -3.0
    assert row["sprint_to_fire_pct"] == -6.0
    assert row["mag_size_add"] == 2.0
    assert row["verification_status"] == "needs_verification"


def test_verification_rows_show_expected_before_after_stats():
    guns = sample_guns()
    hawker = guns[guns["gun_name"] == "HAWKER HX"].iloc[0]
    parsed = parse_codmunity_attachment_html(
        """
        <table>
          <tr>
            <td><span class="attachment-name">Handling Laser</span></td>
            <td><span class="slot">Laser</span></td>
            <td>
              <div class="attachment-stats-item positive"><span class="highlight">-10.0%</span> ADS Speed </div>
            </td>
          </tr>
        </table>
        """,
        compatible_guns="HAWKER HX",
    )

    verification = build_attachment_verification_rows(
        hawker,
        parsed,
        sample_size=1,
        random_state=1,
    )

    assert len(verification) == 1
    assert verification.iloc[0]["base_ads_ms"] == 520
    assert verification.iloc[0]["expected_ads_ms"] == 468

# BO7 Multiplayer Loadout Data

Source date: 2026-07-11

This bundle separates canonical in-game wording from derived tags and recommendation metadata.

## Complete captured categories

- 22 perks
- 6 Combat Specialties
- 9 wildcards
- 10 Tactical equipment items
- 10 Lethal equipment items
- 12 Field Upgrades

## Files

- `perks.csv`
- `specialties.csv`
- `specialty_rules.csv`
- `wildcards.csv`
- `wildcard_effects.csv`
- `equipment.csv`
- `field_upgrades.csv`
- `overclocks.csv`
- `loadout_slots.csv`
- `loadout_rules.csv`
- `loadout_templates.csv`
- `manifest.csv`

## Important boundaries

- `raw_description` preserves the in-game wording captured from the supplied screenshots.
- `effect_tags` and `recommendation_tags` are derived Perzevol metadata, not quoted game statistics.
- `overclocks.csv` is partial. It contains only the named active overclock visible for each captured item. It is not a complete two-option overclock catalogue.
- Account-specific levels, unlock state, badge progress, skins, and equipped-state indicators were excluded.
- Scorestreak definitions have not yet been captured.
- `loadout_templates.csv` contains the finalized schema but no derived templates yet.
- Combat Specialty calculation uses only Perk 1, Perk 2, and Perk 3. Perks granted by Perk Greed or Specialist do not count.
- Default Primary attachment limit is 5. Gunfighter raises it to 8.

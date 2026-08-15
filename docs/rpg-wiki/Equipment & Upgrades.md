# Equipment & Upgrades

Three gear slots: weapon (+ATK), armor (+DEF, +HP), and accessory (+Crit chance). Bonuses are percentage-based so gear stays relevant all the way to level 1500.

## Tiers

- ⚪ [Common Tier](Equipment%20Tiers/Common%20Tier.md) — 200 gold base price
- 🔵 [Rare Tier](Equipment%20Tiers/Rare%20Tier.md) — 800 gold base price
- 🟣 [Epic Tier](Equipment%20Tiers/Epic%20Tier.md) — 2,500 gold base price
- 🟠 [Legendary Tier](Equipment%20Tiers/Legendary%20Tier.md) — 7,000 gold base price
- 🔴 [Mythic Tier](Equipment%20Tiers/Mythic%20Tier.md) — 20,000 gold base price
- 🌈 [Ancient Tier](Equipment%20Tiers/Ancient%20Tier.md) — 60,000 gold base price
- ✨ [Primordial Tier](Equipment%20Tiers/Primordial%20Tier.md) — drop-only, not purchasable, rolls random bonus affixes

## Upgrading (enchanting)
Spend gold via `/rpgupgrade` to enchant your *equipped* item in a slot, up to +10. Each level adds another 1% on top of that item's own bonus. Cost scales with the item's tier and current enchant level. The gold spend and the enchant-level write happen in a single atomic transaction, so a failed purchase can never deduct gold without applying the upgrade (or vice versa).

Use `/rpgautoupgrade` to skip the manual grind: it repeatedly buys the cheapest available upgrade across all three equipped slots — maxing out whichever slot is currently cheapest to advance — until every slot hits +10 or you can no longer afford the next level, then reports what it spent and where it landed. Slots with a [Primordial](Equipment%20Tiers/Primordial%20Tier.md) item equipped are skipped — Primordial gear can't be enchanted, its power comes from its rolled affixes instead.

## Selling
Any owned item (gear or a [potion](Consumables.md)) can be sold back with `/rpgsell` for 40% of its shop price.

# Combat System

Turn-based combat: two [fighters](RPG%20Overview.md) alternate hits until one reaches 0 HP (or 60 rounds pass, in which case it's a draw).

## Damage formula
Percentage-based mitigation, scale-invariant across the whole 1-1500 level range:

```
mitigation = defense / (defense + attacker_atk)
damage = round(raw_damage * (1 - mitigation))
```

A defender with defense equal to the attacker's ATK mitigates 50% of incoming damage. This avoids the "death spiral" a flat subtraction formula creates once defense approaches attack.

## Class skills
Every class has one unique skill that fires automatically in combat:

- **Shield Wall** ([Warrior](Classes/Warrior.md)) — Halves the damage of the first hit taken in every fight.
- **Arcane Bolt** ([Mage](Classes/Mage.md)) — The first attack of every fight is a guaranteed critical hit.
- **Backstab** ([Rogue](Classes/Rogue.md)) — The first attack of every fight deals 70% bonus damage.
- **Divine Shield** ([Paladin](Classes/Paladin.md)) — Starts every fight with a shield absorbing 20% of max HP (soaks damage before real HP, doesn't regenerate mid-fight), and heals 15% of max HP the first time you drop below 30%.
- **Life Drain** ([Necromancer](Classes/Necromancer.md)) — The first attack of every fight heals you for two-thirds of the damage dealt.
- **Piercing Shot** ([Ranger](Classes/Ranger.md)) — The first attack of every fight ignores 85% of the target's DEF.
- **Bloodlust** ([Berserker](Classes/Berserker.md)) — Deals 15% bonus damage on every hit made while below 50% HP.
- **Counterstrike** ([Monk](Classes/Monk.md)) — Every time you're hit, a 25% chance to immediately strike back for 50% damage. Not gated to the first hit — can fire all fight long.
- **Regrowth** ([Druid](Classes/Druid.md)) — After every exchange, recovers 4% of missing HP. No threshold or once-per-fight limit, unlike Divine Shield's heal.

Each class's per-level HP/ATK/DEF growth is individually tuned (not a round number) so that every class lands in roughly the same win-rate band against equivalent-tier content — see each class's page for its exact growth rate.

## Primordial affixes
[Primordial-tier](Equipment%20Tiers/Primordial%20Tier.md) gear can roll three combat mechanics not reachable through normal gear or class skills: **Lifesteal** (heals the attacker on every hit, not just once), **Crit Damage** (pushes a critical hit's multiplier above the flat 2.0x), and **Damage Reflect** (bounces a slice of damage taken back at the attacker). All three stack with class skills and fire on every relevant hit for the whole fight.

## Shields (Paladin only)
A [shield](Equipment%20%26%20Upgrades.md) is a 4th gear slot exclusive to [Paladin](Classes/Paladin.md), across the same 6 tiers as weapon/armor/accessory. Every shield grants two effects on every hit the wearer takes, checked in this order:
1. **Block chance** — a shot at fully negating the hit (0 damage) outright.
2. **Damage reduction** — if not blocked, a flat percentage taken off the damage that gets through, applied after the normal DEF-based mitigation above.

Both stack with Divine Shield's HP-absorption buffer, so a fully-geared Paladin layers block → damage reduction → HP-absorption as three separate defenses on the same hit.

## Boss special abilities
The bosses of the 5 high-end dungeons (Titan's Forge, Chaos Rift, Eternal Throne, World Ender's Lair, Voidscar Expanse) each carry one unique ability on top of their stats, alternating between:
- **Enrage** — once the boss drops below 25% HP, its damage is permanently boosted 50% for the rest of the fight.
- **Double Strike** — 30% chance on any attack to hit with double force.

## Elite (Ambush) encounters
A random dungeon event that pits you against a 1.15x-stronger monster for 1.4x rewards. See [Dungeons](RPG%20Overview.md#dungeons-in-level-order).

## Team fights
Add `team: True` to [`/dungeon`](Commands.md) or [`/dungeonboss`](Commands.md) to open a public join lobby instead of fighting solo. Anyone with a character can hit **Join**; the party leader can **Start Now**, or it starts automatically after 30 seconds. Anyone in the lobby can also hit **Use Potion** to spend one of their own potions and heal the *entire current party's* HP by that potion's normal heal percentage — one person's potion, whole-team benefit.

When the fight starts, anyone too hurt to fight is dropped from the party rather than blocking the group (there's no cooldown gate). The monster/boss scales up with the final party size (HP scales +190% per member beyond the first, ATK scales +14% per member beyond the first) — deliberately steep enough that team fights stay a genuine challenge rather than a near-guaranteed win: a boss that's a coin-flip solo is roughly 55-80% winnable with a duo, climbing to ~85-95% by a full party of 5. Every round, all living party members attack in turn, then the monster picks one random living member to hit back.

A win pays every surviving party member the **full solo-equivalent reward** (gold, XP, and an independent loot roll each) — rewards aren't split across the party. The one exception is a [Primordial](Equipment%20Tiers/Primordial%20Tier.md) drop, which rolls once for the whole party and goes to a single random survivor.

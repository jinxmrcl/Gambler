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
- **Lay on Hands** ([Paladin](Classes/Paladin.md)) — Once per fight, heals 15% of max HP the first time you drop below 30%.
- **Life Drain** ([Necromancer](Classes/Necromancer.md)) — The first attack of every fight heals you for two-thirds of the damage dealt.
- **Piercing Shot** ([Ranger](Classes/Ranger.md)) — The first attack of every fight ignores 85% of the target's DEF.
- **Bloodlust** ([Berserker](Classes/Berserker.md)) — Deals 15% bonus damage on every hit made while below 50% HP.

Each class's per-level HP/ATK/DEF growth is individually tuned (not a round number) so that every class lands in roughly the same win-rate band against equivalent-tier content — see each class's page for its exact growth rate.

## Elite (Ambush) encounters
A random dungeon event that pits you against a 1.15x-stronger monster for 1.4x rewards. See [Dungeons](RPG%20Overview.md#dungeons-in-level-order).

## Team fights
Add `team: True` to [`/dungeon`](Commands.md) or [`/dungeonboss`](Commands.md) to open a public join lobby instead of fighting solo. Anyone with a character can hit **Join**; the party leader can **Start Now**, or it starts automatically after 30 seconds.

When the fight starts, each member's own cooldown is checked and consumed individually — anyone still on cooldown or too hurt to fight is dropped from the party rather than blocking the group. The monster/boss scales up with the final party size (HP scales 1x per member, ATK scales +20% per member beyond the first), so a bigger party faces a genuinely tougher fight, not a free win — though in practice even a duo turns a coin-flip solo boss fight into a near-certain win. Every round, all living party members attack in turn, then the monster picks one random living member to hit back.

A win pays every surviving party member the **full solo-equivalent reward** (gold, XP, and an independent loot roll each) — rewards aren't split across the party.

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
- **Lay on Hands** ([Paladin](Classes/Paladin.md)) — Once per fight, heals 20% of max HP the first time you drop below 30%.
- **Life Drain** ([Necromancer](Classes/Necromancer.md)) — The first attack of every fight heals you for two-thirds of the damage dealt.
- **Piercing Shot** ([Ranger](Classes/Ranger.md)) — The first attack of every fight ignores 65% of the target's DEF.
- **Bloodlust** ([Berserker](Classes/Berserker.md)) — Deals 15% bonus damage on every hit made while below 50% HP.

## Elite (Ambush) encounters
A random dungeon event that pits you against a 1.15x-stronger monster for 1.4x rewards. See [Dungeons](RPG%20Overview.md#dungeons-in-level-order).

# Combat System

Turn-based combat: two [[RPG Overview|fighters]] alternate hits until one reaches 0 HP (or 60 rounds pass, in which case it's a draw).

## Damage formula
Percentage-based mitigation, scale-invariant across the whole 1-1500 level range:

```
mitigation = defense / (defense + attacker_atk)
damage = round(raw_damage * (1 - mitigation))
```

A defender with defense equal to the attacker's ATK mitigates 50% of incoming damage. This avoids the "death spiral" a flat subtraction formula creates once defense approaches attack.

## Class skills
Every class has one unique skill that fires automatically in combat:

- **Shield Wall** ([[Classes/Warrior]]) — Halves the damage of the first hit taken in every fight.
- **Arcane Bolt** ([[Classes/Mage]]) — The first attack of every fight is a guaranteed critical hit.
- **Backstab** ([[Classes/Rogue]]) — The first attack of every fight deals 70% bonus damage.
- **Lay on Hands** ([[Classes/Paladin]]) — Once per fight, heals 20% of max HP the first time you drop below 30%.
- **Life Drain** ([[Classes/Necromancer]]) — The first attack of every fight heals you for two-thirds of the damage dealt.
- **Piercing Shot** ([[Classes/Ranger]]) — The first attack of every fight ignores 65% of the target's DEF.
- **Bloodlust** ([[Classes/Berserker]]) — Deals 15% bonus damage on every hit made while below 50% HP.

## Elite (Ambush) encounters
A random dungeon event that pits you against a 1.15x-stronger monster for 1.4x rewards. See [[RPG Overview#Dungeons (in level order)|Dungeons]].

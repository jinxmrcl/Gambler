import datetime

from rpg.classes import CLASSES, base_stats_at_level
from rpg.combat import Fighter
from rpg.equipment import equipment_multipliers
from rpg.leveling import prestige_stat_multiplier
from rpg.primordial import primordial_multipliers

REGEN_PCT_PER_MINUTE = 0.05


def full_stats(character: dict) -> dict:
    base = base_stats_at_level(character["class_key"], character["level"])
    prim_weapon = character.get("primordial_weapon")
    prim_armor = character.get("primordial_armor")
    prim_accessory = character.get("primordial_accessory")

    mult = equipment_multipliers(
        None if prim_weapon else character["equipped_weapon"],
        None if prim_armor else character["equipped_armor"],
        None if prim_accessory else character.get("equipped_accessory"),
        character.get("weapon_enchant", 0),
        character.get("armor_enchant", 0),
        character.get("accessory_enchant", 0),
        character.get("equipped_shield"),
        character.get("shield_enchant", 0),
    )
    prim = primordial_multipliers(prim_weapon, prim_armor, prim_accessory)
    prestige_mult = prestige_stat_multiplier(character["level"])

    return {
        "hp": int(base["hp"] * mult["hp"] * prim["hp"] * prestige_mult),
        "atk": int(base["atk"] * mult["atk"] * prim["atk"] * prestige_mult),
        "def": int(base["def"] * mult["def"] * prim["def"] * prestige_mult),
        "crit": min(1.0, base["crit"] + mult["crit_add"] + prim["crit_add"]),
        "lifesteal_pct": prim["lifesteal_pct"],
        "crit_dmg_bonus": prim["crit_dmg_bonus"],
        "reflect_pct": prim["reflect_pct"],
        "gold_find_pct": prim["gold_find_pct"],
        "damage_reduction_pct": min(0.75, mult["dr_pct"]),
        "block_chance": min(0.75, mult["block_pct"]),
    }


def current_hp(character: dict, max_hp: int, now: datetime.datetime | None = None) -> int:
    stored = character.get("current_hp")
    if stored is None:
        return max_hp

    updated_at = character.get("hp_updated_at")
    if updated_at is None:
        return min(stored, max_hp)

    now = now or datetime.datetime.utcnow()
    elapsed_minutes = max((now - updated_at).total_seconds(), 0) / 60
    regen = int(max_hp * REGEN_PCT_PER_MINUTE * elapsed_minutes)
    return min(max_hp, stored + regen)


def to_fighter(character: dict, name: str, *, hp: int | None = None) -> Fighter:
    stats = full_stats(character)
    class_def = CLASSES[character["class_key"]]
    return Fighter(
        name=name,
        max_hp=stats["hp"],
        atk=stats["atk"],
        defense=stats["def"],
        crit=stats["crit"],
        skill_key=class_def.skill_key,
        hp=stats["hp"] if hp is None else min(hp, stats["hp"]),
        lifesteal_pct=stats["lifesteal_pct"],
        crit_dmg_bonus=stats["crit_dmg_bonus"],
        reflect_pct=stats["reflect_pct"],
        damage_reduction_pct=stats["damage_reduction_pct"],
        block_chance=stats["block_chance"],
    )

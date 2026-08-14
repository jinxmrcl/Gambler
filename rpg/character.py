import datetime

from rpg.classes import CLASSES, base_stats_at_level
from rpg.combat import Fighter
from rpg.equipment import equipment_multipliers

REGEN_PCT_PER_MINUTE = 0.05


def full_stats(character: dict) -> dict:
    base = base_stats_at_level(character["class_key"], character["level"])
    mult = equipment_multipliers(
        character["equipped_weapon"],
        character["equipped_armor"],
        character.get("equipped_accessory"),
        character.get("weapon_enchant", 0),
        character.get("armor_enchant", 0),
        character.get("accessory_enchant", 0),
    )
    return {
        "hp": int(base["hp"] * mult["hp"]),
        "atk": int(base["atk"] * mult["atk"]),
        "def": int(base["def"] * mult["def"]),
        "crit": min(1.0, base["crit"] + mult["crit_add"]),
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
    )

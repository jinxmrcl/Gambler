from rpg.classes import CLASSES, base_stats_at_level
from rpg.combat import Fighter
from rpg.equipment import equipment_multipliers


def full_stats(character: dict) -> dict:
    """Combines class/level base stats with equipped gear percentage bonuses."""
    base = base_stats_at_level(character["class_key"], character["level"])
    mult = equipment_multipliers(character["equipped_weapon"], character["equipped_armor"])
    return {
        "hp": int(base["hp"] * mult["hp"]),
        "atk": int(base["atk"] * mult["atk"]),
        "def": int(base["def"] * mult["def"]),
        "crit": base["crit"],
    }


def to_fighter(character: dict, name: str) -> Fighter:
    stats = full_stats(character)
    class_def = CLASSES[character["class_key"]]
    return Fighter(
        name=name,
        max_hp=stats["hp"],
        atk=stats["atk"],
        defense=stats["def"],
        crit=stats["crit"],
        skill_key=class_def.skill_key,
    )

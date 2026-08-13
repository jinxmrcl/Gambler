import datetime

from rpg.classes import CLASSES, base_stats_at_level
from rpg.combat import Fighter
from rpg.equipment import equipment_multipliers

REGEN_PCT_PER_MINUTE = 0.05  # a full heal from 0 takes ~20 minutes of real time


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


def current_hp(character: dict, max_hp: int, now: datetime.datetime | None = None) -> int:
    """The character's HP right now, accounting for passive regen since their
    last recorded value. Doesn't write anything — callers persist the result
    themselves once they know the final post-fight HP."""
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
    """Builds a combat Fighter from a character. Pass `hp` to fight at less
    than full (e.g. PvE dungeons, which track persistent HP); omit it for a
    full-HP fight (e.g. the PvP arena, which is always a fair fight)."""
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

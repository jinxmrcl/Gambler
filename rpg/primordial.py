import random
from dataclasses import dataclass


@dataclass(frozen=True)
class PrimordialBaseDef:
    slot: str
    name: str
    atk_pct: float = 0.0
    def_pct: float = 0.0
    hp_pct: float = 0.0
    crit_pct: float = 0.0


PRIMORDIAL_BASES: dict[str, PrimordialBaseDef] = {
    "weapon": PrimordialBaseDef("weapon", "✨ Primordial Edge", atk_pct=0.70),
    "armor": PrimordialBaseDef("armor", "✨ Primordial Aegis", def_pct=0.49, hp_pct=0.70),
    "accessory": PrimordialBaseDef("accessory", "✨ Primordial Relic", crit_pct=0.28),
}


@dataclass(frozen=True)
class AffixDef:
    key: str
    label: str
    lo: float
    hi: float


AFFIXES: dict[str, AffixDef] = {
    "bonus_atk": AffixDef("bonus_atk", "ATK", 0.05, 0.15),
    "bonus_def": AffixDef("bonus_def", "DEF", 0.05, 0.15),
    "bonus_hp": AffixDef("bonus_hp", "HP", 0.05, 0.15),
    "bonus_crit": AffixDef("bonus_crit", "Crit Chance", 0.03, 0.10),
    "lifesteal": AffixDef("lifesteal", "Lifesteal", 0.05, 0.15),
    "crit_dmg": AffixDef("crit_dmg", "Crit Damage", 0.10, 0.40),
    "reflect": AffixDef("reflect", "Damage Reflect", 0.05, 0.15),
    "gold_find": AffixDef("gold_find", "Gold Find", 0.10, 0.30),
}

AFFIX_COUNT_WEIGHTS = {1: 50, 2: 35, 3: 15}

HIGH_END_DUNGEONS = ("titan_forge", "chaos_rift", "eternal_throne", "world_ender", "voidscar")
PRIMORDIAL_DROP_CHANCE = 0.04


def roll_affixes() -> list[dict]:
    count = random.choices(list(AFFIX_COUNT_WEIGHTS), weights=list(AFFIX_COUNT_WEIGHTS.values()), k=1)[0]
    keys = random.sample(list(AFFIXES.keys()), count)
    rolled = []
    for key in keys:
        a = AFFIXES[key]
        value = round(random.uniform(a.lo, a.hi), 3)
        rolled.append({"key": key, "value": value})
    return rolled


def generate_primordial_drop(slot: str) -> list[dict]:
    return roll_affixes()


def affix_totals(affixes: list[dict]) -> dict:
    totals = {key: 0.0 for key in AFFIXES}
    for a in affixes:
        totals[a["key"]] += a["value"]
    return totals


def describe_affixes(affixes: list[dict]) -> str:
    parts = []
    for a in affixes:
        label = AFFIXES[a["key"]].label
        parts.append(f"+{a['value']:.1%} {label}")
    return ", ".join(parts)


def primordial_multipliers(weapon: dict | None, armor: dict | None, accessory: dict | None) -> dict:
    atk_pct = def_pct = hp_pct = crit_pct = 0.0
    lifesteal_pct = crit_dmg_bonus = reflect_pct = gold_find_pct = 0.0

    for slot, item in (("weapon", weapon), ("armor", armor), ("accessory", accessory)):
        if not item:
            continue
        base = PRIMORDIAL_BASES[slot]
        totals = affix_totals(item["affixes"])
        atk_pct += base.atk_pct + totals["bonus_atk"]
        def_pct += base.def_pct + totals["bonus_def"]
        hp_pct += base.hp_pct + totals["bonus_hp"]
        crit_pct += base.crit_pct + totals["bonus_crit"]
        lifesteal_pct += totals["lifesteal"]
        crit_dmg_bonus += totals["crit_dmg"]
        reflect_pct += totals["reflect"]
        gold_find_pct += totals["gold_find"]

    return {
        "atk": 1 + atk_pct, "def": 1 + def_pct, "hp": 1 + hp_pct, "crit_add": crit_pct,
        "lifesteal_pct": lifesteal_pct, "crit_dmg_bonus": crit_dmg_bonus,
        "reflect_pct": reflect_pct, "gold_find_pct": gold_find_pct,
    }

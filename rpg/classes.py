from dataclasses import dataclass


@dataclass(frozen=True)
class ClassDef:
    key: str
    name: str
    emoji: str
    description: str
    base_hp: int
    base_atk: int
    base_def: int
    base_crit: float  # crit chance, 0-1
    hp_growth: int
    atk_growth: int
    def_growth: int
    skill_key: str
    skill_name: str
    skill_desc: str


CLASSES: dict[str, ClassDef] = {
    "warrior": ClassDef(
        "warrior", "Warrior", "🛡️",
        "A frontline fighter with heavy armor and raw strength.",
        base_hp=120, base_atk=14, base_def=10, base_crit=0.05,
        hp_growth=14, atk_growth=2, def_growth=2,
        skill_key="shield_wall", skill_name="Shield Wall",
        skill_desc="Halves the damage of the first hit taken in every fight.",
    ),
    "mage": ClassDef(
        "mage", "Mage", "🔮",
        "A spellcaster with devastating magic but a fragile body.",
        base_hp=80, base_atk=20, base_def=4, base_crit=0.10,
        hp_growth=8, atk_growth=3, def_growth=1,
        skill_key="arcane_bolt", skill_name="Arcane Bolt",
        skill_desc="The first attack of every fight is a guaranteed critical hit.",
    ),
    "rogue": ClassDef(
        "rogue", "Rogue", "🗡️",
        "A quick striker who lands brutal critical hits.",
        base_hp=95, base_atk=16, base_def=6, base_crit=0.25,
        hp_growth=10, atk_growth=2, def_growth=1,
        skill_key="backstab", skill_name="Backstab",
        skill_desc="The first attack of every fight deals 50% bonus damage.",
    ),
    "paladin": ClassDef(
        "paladin", "Paladin", "✨",
        "A balanced holy warrior with steady sustain.",
        base_hp=105, base_atk=13, base_def=8, base_crit=0.08,
        hp_growth=12, atk_growth=2, def_growth=2,
        skill_key="lay_on_hands", skill_name="Lay on Hands",
        skill_desc="Once per fight, heals 20% of max HP the first time you drop below 30%.",
    ),
}


def base_stats_at_level(class_key: str, level: int) -> dict:
    """Class + level stats, before equipment bonuses."""
    c = CLASSES[class_key]
    n = level - 1
    return {
        "hp": c.base_hp + c.hp_growth * n,
        "atk": c.base_atk + c.atk_growth * n,
        "def": c.base_def + c.def_growth * n,
        "crit": c.base_crit,
    }

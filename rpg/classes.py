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
    base_crit: float
    hp_growth: float
    atk_growth: float
    def_growth: float
    skill_key: str
    skill_name: str
    skill_desc: str


CLASSES: dict[str, ClassDef] = {
    "warrior": ClassDef(
        "warrior", "Warrior", "🛡️",
        "A frontline fighter with heavy armor and raw strength.",
        base_hp=120, base_atk=14, base_def=10, base_crit=0.05,
        hp_growth=13.88, atk_growth=1.98, def_growth=1.98,
        skill_key="shield_wall", skill_name="Shield Wall",
        skill_desc="Halves the damage of the first hit taken in every fight.",
    ),
    "mage": ClassDef(
        "mage", "Mage", "🔮",
        "A spellcaster with devastating magic but a fragile body.",
        base_hp=80, base_atk=23, base_def=4, base_crit=0.10,
        hp_growth=8.26, atk_growth=2.75, def_growth=1.84,
        skill_key="arcane_bolt", skill_name="Arcane Bolt",
        skill_desc="The first attack of every fight is a guaranteed critical hit.",
    ),
    "rogue": ClassDef(
        "rogue", "Rogue", "🗡️",
        "A quick striker who lands brutal critical hits.",
        base_hp=95, base_atk=18, base_def=7, base_crit=0.27,
        hp_growth=12.09, atk_growth=2.2, def_growth=1.1,
        skill_key="backstab", skill_name="Backstab",
        skill_desc="The first attack of every fight deals 70% bonus damage.",
    ),
    "paladin": ClassDef(
        "paladin", "Paladin", "✨",
        "A balanced holy warrior with steady sustain.",
        base_hp=105, base_atk=13, base_def=8, base_crit=0.08,
        hp_growth=11.32, atk_growth=2.06, def_growth=2.06,
        skill_key="lay_on_hands", skill_name="Lay on Hands",
        skill_desc="Once per fight, heals 15% of max HP the first time you drop below 30%.",
    ),
    "necromancer": ClassDef(
        "necromancer", "Necromancer", "💀",
        "A dark caster who drains life from their enemies to sustain themselves.",
        base_hp=90, base_atk=21, base_def=6, base_crit=0.09,
        hp_growth=8.56, atk_growth=2.85, def_growth=1.9,
        skill_key="life_drain", skill_name="Life Drain",
        skill_desc="The first attack of every fight heals you for two-thirds of the damage dealt.",
    ),
    "ranger": ClassDef(
        "ranger", "Ranger", "🏹",
        "A sharpshooter who never misses a vital shot.",
        base_hp=100, base_atk=18, base_def=7, base_crit=0.20,
        hp_growth=13.32, atk_growth=2.22, def_growth=1.11,
        skill_key="piercing_shot", skill_name="Piercing Shot",
        skill_desc="The first attack of every fight ignores 85% of the target's DEF.",
    ),
    "berserker": ClassDef(
        "berserker", "Berserker", "🪓",
        "A glass cannon who hits devastatingly hard but can't take much back.",
        base_hp=85, base_atk=20, base_def=3, base_crit=0.12,
        hp_growth=6.86, atk_growth=3.92, def_growth=0.98,
        skill_key="bloodlust", skill_name="Bloodlust",
        skill_desc="Deals 15% bonus damage on every hit made while below 50% HP.",
    ),
}


def base_stats_at_level(class_key: str, level: int) -> dict:
    c = CLASSES[class_key]
    n = level - 1
    return {
        "hp": int(c.base_hp + c.hp_growth * n),
        "atk": int(c.base_atk + c.atk_growth * n),
        "def": int(c.base_def + c.def_growth * n),
        "crit": c.base_crit,
    }

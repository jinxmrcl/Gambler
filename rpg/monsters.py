import dataclasses
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Monster:
    name: str
    emoji: str
    hp: int
    atk: int
    defense: int
    crit: float
    xp_reward: int
    gold_reward: tuple[int, int]
    loot_pool: tuple[str, ...] = field(default_factory=tuple)
    loot_chance: float = 0.0


@dataclass(frozen=True)
class Dungeon:
    key: str
    name: str
    emoji: str
    min_level: int
    monsters: list[Monster]
    boss: Monster | None = None


DUNGEONS: dict[str, Dungeon] = {
    "forest": Dungeon(
        "forest", "Whispering Forest", "🌲", 1,
        [
            Monster("Wild Boar", "🐗", 40, 8, 2, 0.05, 25, (30, 60), ("wooden_sword", "leather_armor", "lucky_charm"), 0.12),
            Monster("Goblin", "👺", 50, 10, 3, 0.08, 30, (40, 70), ("wooden_sword", "leather_armor"), 0.12),
            Monster("Giant Spider", "🕷️", 45, 12, 2, 0.10, 35, (40, 80), ("wooden_sword", "leather_armor"), 0.12),
        ],
    ),
    "cave": Dungeon(
        "cave", "Shadowed Cave", "🕳️", 8,
        [
            Monster("Cave Troll", "🧌", 140, 18, 8, 0.06, 80, (120, 200), ("iron_sword", "chainmail", "hawk_eye_ring"), 0.15),
            Monster("Skeleton Warrior", "💀", 110, 20, 6, 0.10, 75, (100, 180), ("iron_sword", "chainmail"), 0.15),
            Monster("Bat Swarm", "🦇", 90, 16, 4, 0.15, 60, (80, 150), ("iron_sword", "chainmail"), 0.15),
        ],
    ),
    "crypt": Dungeon(
        "crypt", "Forgotten Crypt", "⚰️", 16,
        [
            Monster("Wraith", "👻", 180, 28, 10, 0.15, 160, (200, 320), ("flame_blade", "plate_armor", "assassins_pendant"), 0.15),
            Monster("Lich Acolyte", "🧙", 160, 32, 8, 0.12, 170, (220, 340), ("flame_blade", "plate_armor"), 0.15),
            Monster("Bone Golem", "🦴", 240, 24, 16, 0.05, 180, (220, 360), ("flame_blade", "plate_armor"), 0.15),
        ],
    ),
    "volcano": Dungeon(
        "volcano", "Molten Depths", "🌋", 25,
        [
            Monster("Fire Elemental", "🔥", 260, 38, 14, 0.12, 300, (400, 600), ("dragon_fang", "dragonscale_armor", "phoenix_feather"), 0.18),
            Monster("Obsidian Golem", "🗿", 340, 30, 22, 0.05, 320, (420, 650), ("dragon_fang", "dragonscale_armor"), 0.18),
            Monster("Ancient Drake", "🐲", 300, 42, 18, 0.18, 380, (500, 800), ("dragon_fang", "dragonscale_armor"), 0.18),
        ],
    ),
    "abyss": Dungeon(
        "abyss", "Endless Abyss", "🕳️", 35,
        [
            Monster("Abyssal Horror", "👁️", 420, 55, 26, 0.14, 520, (700, 1050), ("void_reaver", "void_plate", "void_sigil"), 0.21),
            Monster("Void Serpent", "🐍", 380, 62, 20, 0.20, 540, (720, 1100), ("void_reaver", "void_plate"), 0.21),
            Monster("Nightmare Wraith", "🌑", 460, 50, 30, 0.10, 560, (750, 1150), ("void_reaver", "void_plate"), 0.21),
        ],
    ),
    "celestial": Dungeon(
        "celestial", "Celestial Rift", "🌌", 55,
        [
            Monster("Star Devourer", "⭐", 650, 85, 40, 0.15, 900, (1200, 1800), ("worldbreaker", "worldguard", "crown_of_fate"), 0.24),
            Monster("Astral Guardian", "🌠", 720, 78, 48, 0.10, 940, (1250, 1900), ("worldbreaker", "worldguard"), 0.24),
            Monster("Cosmic Wyrm", "🐉", 680, 92, 36, 0.20, 980, (1300, 2000), ("worldbreaker", "worldguard"), 0.24),
        ],
    ),
    "ruins": Dungeon(
        "ruins", "Sunken Ruins", "🏛️", 75,
        [
            Monster("Drowned Sentinel", "🗿", 990, 128, 58, 0.10, 1180, (1480, 2260), ("dragon_fang", "phoenix_feather"), 0.21),
            Monster("Coral Wraith", "🪸", 950, 135, 54, 0.16, 1220, (1520, 2300), ("dragonscale_armor", "phoenix_feather"), 0.21),
            Monster("Ancient Leviathan", "🐋", 1080, 130, 66, 0.08, 1260, (1560, 2360), ("dragon_fang", "dragonscale_armor"), 0.21),
        ],
    ),
    "frostpeak": Dungeon(
        "frostpeak", "Frostpeak Summit", "🏔️", 100,
        [
            Monster("Frost Giant", "❄️", 1310, 170, 78, 0.08, 1580, (1980, 3020), ("void_reaver", "phoenix_feather"), 0.23),
            Monster("Ice Phoenix", "🧊", 1260, 182, 70, 0.18, 1640, (2020, 3060), ("phoenix_feather", "void_plate"), 0.23),
            Monster("Rime Wyvern", "🐲", 1400, 175, 88, 0.12, 1700, (2060, 3120), ("void_reaver", "void_plate"), 0.23),
        ],
    ),
    "wastes": Dungeon(
        "wastes", "Scorched Wastes", "🏜️", 150,
        [
            Monster("Sand Colossus", "🌪️", 1960, 255, 118, 0.09, 2360, (2980, 4520), ("void_reaver", "void_sigil"), 0.24),
            Monster("Mirage Stalker", "🐆", 1900, 270, 108, 0.22, 2440, (3020, 4560), ("void_plate", "void_sigil"), 0.24),
            Monster("Dust Wyrm", "🌫️", 2100, 260, 130, 0.10, 2500, (3060, 4620), ("void_reaver", "void_plate"), 0.24),
        ],
    ),
    "nightmare_realm": Dungeon(
        "nightmare_realm", "Nightmare Realm", "🌑", 200,
        [
            Monster("Dread Harbinger", "👹", 2600, 340, 158, 0.10, 3160, (3980, 6020), ("void_reaver", "void_sigil"), 0.26),
            Monster("Shrieking Terror", "😱", 2520, 358, 148, 0.20, 3260, (4020, 6060), ("void_plate", "void_sigil"), 0.26),
            Monster("Living Nightmare", "🌚", 2780, 350, 172, 0.14, 3340, (4060, 6120), ("void_reaver", "void_plate"), 0.26),
        ],
    ),
    "sunken_city": Dungeon(
        "sunken_city", "Sunken City", "🌊", 300,
        [
            Monster("Deep One Prophet", "🐙", 3900, 510, 238, 0.11, 4760, (5980, 9020), ("worldbreaker", "crown_of_fate"), 0.27),
            Monster("Drowned King", "👑", 3820, 535, 224, 0.16, 4860, (6020, 9060), ("worldguard", "crown_of_fate"), 0.27),
            Monster("Abyssal Kraken", "🦑", 4180, 520, 262, 0.09, 4960, (6060, 9160), ("worldbreaker", "worldguard"), 0.27),
        ],
    ),
    "voidscar": Dungeon(
        "voidscar", "Voidscar Expanse", "🕳️", 400,
        [
            Monster("Reality Render", "🌀", 5200, 680, 318, 0.12, 6360, (7980, 12020), ("worldbreaker", "crown_of_fate"), 0.29),
            Monster("Null Walker", "⬛", 5080, 715, 300, 0.20, 6460, (8020, 12060), ("worldguard", "crown_of_fate"), 0.29),
            Monster("Entropy Beast", "🕸️", 5560, 695, 350, 0.10, 6560, (8060, 12160), ("worldbreaker", "worldguard"), 0.29),
        ],
    ),
    "titan_forge": Dungeon(
        "titan_forge", "Titan's Forge", "⚒️", 550,
        [
            Monster("Molten Titan", "🗻", 7140, 935, 438, 0.11, 8760, (10980, 16520), ("worldbreaker", "crown_of_fate"), 0.30),
            Monster("Forgebound Colossus", "🔩", 6980, 980, 412, 0.15, 8920, (11020, 16560), ("worldguard", "crown_of_fate"), 0.30),
            Monster("Ember Wyrmlord", "🔥", 7640, 955, 480, 0.18, 9060, (11060, 16660), ("worldbreaker", "worldguard"), 0.30),
        ],
    ),
    "chaos_rift": Dungeon(
        "chaos_rift", "Chaos Rift", "💥", 700,
        [
            Monster("Rift Devourer", "🌪️", 9080, 1190, 558, 0.12, 11160, (13980, 21020), ("worldbreaker", "crown_of_fate"), 0.32),
            Monster("Chaos Incarnate", "🔺", 8880, 1250, 524, 0.19, 11360, (14020, 21060), ("worldguard", "crown_of_fate"), 0.32),
            Monster("Entropic Sovereign", "♾️", 9720, 1215, 610, 0.14, 11520, (14060, 21160), ("worldbreaker", "worldguard"), 0.32),
        ],
    ),
    "eternal_throne": Dungeon(
        "eternal_throne", "Eternal Throne", "🏰", 900,
        [
            Monster("Throneguard Wraith", "⚔️", 11670, 1530, 718, 0.13, 14360, (17980, 27020), ("worldbreaker", "crown_of_fate"), 0.33),
            Monster("Usurper of Ages", "👑", 11400, 1605, 674, 0.20, 14620, (18020, 27060), ("worldguard", "crown_of_fate"), 0.33),
            Monster("The Enthroned", "🪑", 12480, 1560, 784, 0.16, 14820, (18060, 27160), ("worldbreaker", "worldguard"), 0.33),
        ],
    ),
    "world_ender": Dungeon(
        "world_ender", "World Ender's Lair", "☄️", 1200,
        [
            Monster("Herald of Ruin", "🩸", 15560, 2040, 958, 0.14, 19160, (23980, 36020), ("worldbreaker", "crown_of_fate"), 0.38),
            Monster("The Unmaking", "🕳️", 15200, 2140, 898, 0.22, 19520, (24020, 36060), ("worldguard", "crown_of_fate"), 0.38),
            Monster("World Ender", "☄️", 16640, 2080, 1044, 0.18, 19820, (24060, 36160), ("crown_of_fate", "worldbreaker", "worldguard"), 0.38),
        ],
    ),
}

BOSS_NAMES: dict[str, tuple[str, str]] = {
    "forest": ("Elder Treant", "🌳"),
    "cave": ("Troll King", "👑"),
    "crypt": ("Lich Lord", "💀"),
    "volcano": ("Inferno Wyrm", "🌋"),
    "abyss": ("Abyss Devourer", "👁️"),
    "celestial": ("Celestial Sovereign", "🌌"),
    "ruins": ("Leviathan King", "🐋"),
    "frostpeak": ("Frost Monarch", "❄️"),
    "wastes": ("Storm Colossus", "🌪️"),
    "nightmare_realm": ("The Nightmare King", "👹"),
    "sunken_city": ("Kraken Sovereign", "🦑"),
    "voidscar": ("The Unraveler", "🌀"),
    "titan_forge": ("Forge Titan Prime", "⚒️"),
    "chaos_rift": ("Avatar of Chaos", "♾️"),
    "eternal_throne": ("The Eternal Monarch", "🏰"),
    "world_ender": ("The World Ender", "☄️"),
}

BOSS_SKILLS: dict[str, str] = {
    "titan_forge": "double_strike",
    "chaos_rift": "enrage",
    "eternal_throne": "double_strike",
    "world_ender": "enrage",
    "voidscar": "double_strike",
}

BOSS_HP_MULT = 3.5
BOSS_ATK_MULT = 1.6
BOSS_DEF_MULT = 1.6
BOSS_XP_MULT = 4.0
BOSS_GOLD_MULT = 4.0
BOSS_LOOT_CHANCE = 0.75


def _make_boss(dungeon_key: str, monsters: list[Monster]) -> Monster:
    n = len(monsters)
    avg_hp = sum(m.hp for m in monsters) / n
    avg_atk = sum(m.atk for m in monsters) / n
    avg_def = sum(m.defense for m in monsters) / n
    avg_crit = sum(m.crit for m in monsters) / n
    avg_xp = sum(m.xp_reward for m in monsters) / n
    avg_gold_lo = sum(m.gold_reward[0] for m in monsters) / n
    avg_gold_hi = sum(m.gold_reward[1] for m in monsters) / n
    loot_pool = tuple(dict.fromkeys(k for m in monsters for k in m.loot_pool))
    name, emoji = BOSS_NAMES[dungeon_key]
    return Monster(
        name, emoji,
        max(1, int(avg_hp * BOSS_HP_MULT)),
        max(1, int(avg_atk * BOSS_ATK_MULT)),
        max(0, int(avg_def * BOSS_DEF_MULT)),
        min(0.35, avg_crit + 0.05),
        max(1, int(avg_xp * BOSS_XP_MULT)),
        (max(1, int(avg_gold_lo * BOSS_GOLD_MULT)), max(1, int(avg_gold_hi * BOSS_GOLD_MULT))),
        loot_pool,
        BOSS_LOOT_CHANCE,
    )


for _key, _dungeon in list(DUNGEONS.items()):
    DUNGEONS[_key] = dataclasses.replace(_dungeon, boss=_make_boss(_key, _dungeon.monsters))
del _key, _dungeon

SCALE_PER_LEVEL = 0.05
MAX_SCALE_LEVELS = 50

MONSTER_POWER_MULTIPLIER: dict[str, float] = {
    "forest": 3.69,
    "cave": 2.33,
    "crypt": 1.96,
    "volcano": 1.86,
    "abyss": 1.68,
    "celestial": 1.61,
    "ruins": 1.03,
    "frostpeak": 1.03,
    "wastes": 0.98,
    "nightmare_realm": 0.95,
    "sunken_city": 0.99,
    "voidscar": 0.96,
    "titan_forge": 0.95,
    "chaos_rift": 0.94,
    "eternal_throne": 0.94,
    "world_ender": 0.93,
}

BOSS_POWER_MULTIPLIER: dict[str, float] = {
    "forest": 1.75,
    "cave": 1.13,
    "crypt": 0.92,
    "volcano": 0.86,
    "abyss": 0.78,
    "celestial": 0.75,
    "ruins": 0.48,
    "frostpeak": 0.48,
    "wastes": 0.46,
    "nightmare_realm": 0.44,
    "sunken_city": 0.46,
    "voidscar": 0.45,
    "titan_forge": 0.44,
    "chaos_rift": 0.44,
    "eternal_throne": 0.44,
    "world_ender": 0.43,
}

TEAM_HP_MULT_PER_MEMBER = 1.9
TEAM_ATK_MULT_PER_MEMBER = 0.14


def scale_factor(player_level: int, dungeon_min_level: int) -> float:
    diff = min(max(player_level - dungeon_min_level, 0), MAX_SCALE_LEVELS)
    return 1 + diff * SCALE_PER_LEVEL


def team_scale_factor(party_size: int) -> tuple[float, float]:
    size = max(1, party_size)
    hp_mult = 1 + (size - 1) * TEAM_HP_MULT_PER_MEMBER
    atk_mult = 1 + (size - 1) * TEAM_ATK_MULT_PER_MEMBER
    return hp_mult, atk_mult


def scaled_monster(
    monster: Monster,
    player_level: int,
    dungeon_min_level: int,
    dungeon_key: str,
    is_boss: bool = False,
    party_size: int = 1,
) -> dict:
    f = scale_factor(player_level, dungeon_min_level)
    p = (BOSS_POWER_MULTIPLIER if is_boss else MONSTER_POWER_MULTIPLIER)[dungeon_key]
    team_hp_mult, team_atk_mult = team_scale_factor(party_size)
    lo, hi = monster.gold_reward
    return {
        "hp": max(1, int(monster.hp * f * p * team_hp_mult)),
        "atk": max(1, int(monster.atk * f * p * team_atk_mult)),
        "def": max(0, int(monster.defense * f * p)),
        "crit": monster.crit,
        "xp": max(1, int(monster.xp_reward * f)),
        "gold": (max(1, int(lo * f)), max(1, int(hi * f))),
    }

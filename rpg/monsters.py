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
            Monster("Wild Boar", "🐗", 40, 8, 2, 0.05, 25, (30, 60), ("wooden_sword", "leather_armor"), 0.08),
            Monster("Goblin", "👺", 50, 10, 3, 0.08, 30, (40, 70), ("wooden_sword", "leather_armor"), 0.08),
            Monster("Giant Spider", "🕷️", 45, 12, 2, 0.10, 35, (40, 80), ("wooden_sword", "leather_armor"), 0.08),
        ],
    ),
    "cave": Dungeon(
        "cave", "Shadowed Cave", "🕳️", 8,
        [
            Monster("Cave Troll", "🧌", 140, 18, 8, 0.06, 80, (120, 200), ("iron_sword", "chainmail"), 0.10),
            Monster("Skeleton Warrior", "💀", 110, 20, 6, 0.10, 75, (100, 180), ("iron_sword", "chainmail"), 0.10),
            Monster("Bat Swarm", "🦇", 90, 16, 4, 0.15, 60, (80, 150), ("iron_sword", "chainmail"), 0.10),
        ],
    ),
    "crypt": Dungeon(
        "crypt", "Forgotten Crypt", "⚰️", 16,
        [
            Monster("Wraith", "👻", 180, 28, 10, 0.15, 160, (200, 320), ("flame_blade", "plate_armor"), 0.10),
            Monster("Lich Acolyte", "🧙", 160, 32, 8, 0.12, 170, (220, 340), ("flame_blade", "plate_armor"), 0.10),
            Monster("Bone Golem", "🦴", 240, 24, 16, 0.05, 180, (220, 360), ("flame_blade", "plate_armor"), 0.10),
        ],
    ),
    "volcano": Dungeon(
        "volcano", "Molten Depths", "🌋", 25,
        [
            Monster("Fire Elemental", "🔥", 260, 38, 14, 0.12, 300, (400, 600), ("dragon_fang", "dragonscale_armor"), 0.12),
            Monster("Obsidian Golem", "🗿", 340, 30, 22, 0.05, 320, (420, 650), ("dragon_fang", "dragonscale_armor"), 0.12),
            Monster("Ancient Drake", "🐲", 300, 42, 18, 0.18, 380, (500, 800), ("dragon_fang", "dragonscale_armor"), 0.12),
        ],
    ),
    "abyss": Dungeon(
        "abyss", "Endless Abyss", "🕳️", 35,
        [
            Monster("Abyssal Horror", "👁️", 420, 55, 26, 0.14, 520, (700, 1050), ("void_reaver", "void_plate"), 0.14),
            Monster("Void Serpent", "🐍", 380, 62, 20, 0.20, 540, (720, 1100), ("void_reaver", "void_plate"), 0.14),
            Monster("Nightmare Wraith", "🌑", 460, 50, 30, 0.10, 560, (750, 1150), ("void_reaver", "void_plate"), 0.14),
        ],
    ),
    "celestial": Dungeon(
        "celestial", "Celestial Rift", "🌌", 55,
        [
            Monster("Star Devourer", "⭐", 650, 85, 40, 0.15, 900, (1200, 1800), ("worldbreaker", "worldguard"), 0.16),
            Monster("Astral Guardian", "🌠", 720, 78, 48, 0.10, 940, (1250, 1900), ("worldbreaker", "worldguard"), 0.16),
            Monster("Cosmic Wyrm", "🐉", 680, 92, 36, 0.20, 980, (1300, 2000), ("worldbreaker", "worldguard"), 0.16),
        ],
    ),
    "ruins": Dungeon(
        "ruins", "Sunken Ruins", "🏛️", 75,
        [
            Monster("Drowned Sentinel", "🗿", 990, 128, 58, 0.10, 1180, (1480, 2260), ("dragon_fang", "phoenix_feather"), 0.14),
            Monster("Coral Wraith", "🪸", 950, 135, 54, 0.16, 1220, (1520, 2300), ("dragonscale_armor", "phoenix_feather"), 0.14),
            Monster("Ancient Leviathan", "🐋", 1080, 130, 66, 0.08, 1260, (1560, 2360), ("dragon_fang", "dragonscale_armor"), 0.14),
        ],
    ),
    "frostpeak": Dungeon(
        "frostpeak", "Frostpeak Summit", "🏔️", 100,
        [
            Monster("Frost Giant", "❄️", 1310, 170, 78, 0.08, 1580, (1980, 3020), ("void_reaver", "phoenix_feather"), 0.15),
            Monster("Ice Phoenix", "🧊", 1260, 182, 70, 0.18, 1640, (2020, 3060), ("phoenix_feather", "void_plate"), 0.15),
            Monster("Rime Wyvern", "🐲", 1400, 175, 88, 0.12, 1700, (2060, 3120), ("void_reaver", "void_plate"), 0.15),
        ],
    ),
    "wastes": Dungeon(
        "wastes", "Scorched Wastes", "🏜️", 150,
        [
            Monster("Sand Colossus", "🌪️", 1960, 255, 118, 0.09, 2360, (2980, 4520), ("void_reaver", "void_sigil"), 0.16),
            Monster("Mirage Stalker", "🐆", 1900, 270, 108, 0.22, 2440, (3020, 4560), ("void_plate", "void_sigil"), 0.16),
            Monster("Dust Wyrm", "🌫️", 2100, 260, 130, 0.10, 2500, (3060, 4620), ("void_reaver", "void_plate"), 0.16),
        ],
    ),
    "nightmare_realm": Dungeon(
        "nightmare_realm", "Nightmare Realm", "🌑", 200,
        [
            Monster("Dread Harbinger", "👹", 2600, 340, 158, 0.10, 3160, (3980, 6020), ("void_reaver", "void_sigil"), 0.17),
            Monster("Shrieking Terror", "😱", 2520, 358, 148, 0.20, 3260, (4020, 6060), ("void_plate", "void_sigil"), 0.17),
            Monster("Living Nightmare", "🌚", 2780, 350, 172, 0.14, 3340, (4060, 6120), ("void_reaver", "void_plate"), 0.17),
        ],
    ),
    "sunken_city": Dungeon(
        "sunken_city", "Sunken City", "🌊", 300,
        [
            Monster("Deep One Prophet", "🐙", 3900, 510, 238, 0.11, 4760, (5980, 9020), ("worldbreaker", "crown_of_fate"), 0.18),
            Monster("Drowned King", "👑", 3820, 535, 224, 0.16, 4860, (6020, 9060), ("worldguard", "crown_of_fate"), 0.18),
            Monster("Abyssal Kraken", "🦑", 4180, 520, 262, 0.09, 4960, (6060, 9160), ("worldbreaker", "worldguard"), 0.18),
        ],
    ),
    "voidscar": Dungeon(
        "voidscar", "Voidscar Expanse", "🕳️", 400,
        [
            Monster("Reality Render", "🌀", 5200, 680, 318, 0.12, 6360, (7980, 12020), ("worldbreaker", "crown_of_fate"), 0.19),
            Monster("Null Walker", "⬛", 5080, 715, 300, 0.20, 6460, (8020, 12060), ("worldguard", "crown_of_fate"), 0.19),
            Monster("Entropy Beast", "🕸️", 5560, 695, 350, 0.10, 6560, (8060, 12160), ("worldbreaker", "worldguard"), 0.19),
        ],
    ),
    "titan_forge": Dungeon(
        "titan_forge", "Titan's Forge", "⚒️", 550,
        [
            Monster("Molten Titan", "🗻", 7140, 935, 438, 0.11, 8760, (10980, 16520), ("worldbreaker", "crown_of_fate"), 0.20),
            Monster("Forgebound Colossus", "🔩", 6980, 980, 412, 0.15, 8920, (11020, 16560), ("worldguard", "crown_of_fate"), 0.20),
            Monster("Ember Wyrmlord", "🔥", 7640, 955, 480, 0.18, 9060, (11060, 16660), ("worldbreaker", "worldguard"), 0.20),
        ],
    ),
    "chaos_rift": Dungeon(
        "chaos_rift", "Chaos Rift", "💥", 700,
        [
            Monster("Rift Devourer", "🌪️", 9080, 1190, 558, 0.12, 11160, (13980, 21020), ("worldbreaker", "crown_of_fate"), 0.21),
            Monster("Chaos Incarnate", "🔺", 8880, 1250, 524, 0.19, 11360, (14020, 21060), ("worldguard", "crown_of_fate"), 0.21),
            Monster("Entropic Sovereign", "♾️", 9720, 1215, 610, 0.14, 11520, (14060, 21160), ("worldbreaker", "worldguard"), 0.21),
        ],
    ),
    "eternal_throne": Dungeon(
        "eternal_throne", "Eternal Throne", "🏰", 900,
        [
            Monster("Throneguard Wraith", "⚔️", 11670, 1530, 718, 0.13, 14360, (17980, 27020), ("worldbreaker", "crown_of_fate"), 0.22),
            Monster("Usurper of Ages", "👑", 11400, 1605, 674, 0.20, 14620, (18020, 27060), ("worldguard", "crown_of_fate"), 0.22),
            Monster("The Enthroned", "🪑", 12480, 1560, 784, 0.16, 14820, (18060, 27160), ("worldbreaker", "worldguard"), 0.22),
        ],
    ),
    "world_ender": Dungeon(
        "world_ender", "World Ender's Lair", "☄️", 1200,
        [
            Monster("Herald of Ruin", "🩸", 15560, 2040, 958, 0.14, 19160, (23980, 36020), ("worldbreaker", "crown_of_fate"), 0.25),
            Monster("The Unmaking", "🕳️", 15200, 2140, 898, 0.22, 19520, (24020, 36060), ("worldguard", "crown_of_fate"), 0.25),
            Monster("World Ender", "☄️", 16640, 2080, 1044, 0.18, 19820, (24060, 36160), ("crown_of_fate", "worldbreaker", "worldguard"), 0.25),
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

# Bosses are derived from each dungeon's own (already-balanced) regular
# monsters rather than hand-authored, so boss difficulty automatically stays
# consistent with whatever the trash-mob tuning is instead of drifting apart.
BOSS_HP_MULT = 3.5
BOSS_ATK_MULT = 1.6
BOSS_DEF_MULT = 1.6
BOSS_XP_MULT = 4.0
BOSS_GOLD_MULT = 4.0
BOSS_LOOT_CHANCE = 0.6


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

MONSTER_POWER_MULTIPLIER = 2.0


def scale_factor(player_level: int, dungeon_min_level: int) -> float:
    return 1 + max(player_level - dungeon_min_level, 0) * SCALE_PER_LEVEL


def scaled_monster(monster: Monster, player_level: int, dungeon_min_level: int) -> dict:
    f = scale_factor(player_level, dungeon_min_level)
    p = MONSTER_POWER_MULTIPLIER
    lo, hi = monster.gold_reward
    return {
        "hp": max(1, int(monster.hp * f * p)),
        "atk": max(1, int(monster.atk * f * p)),
        "def": max(0, int(monster.defense * f * p)),
        "crit": monster.crit,
        "xp": max(1, int(monster.xp_reward * f)),
        "gold": (max(1, int(lo * f)), max(1, int(hi * f))),
    }

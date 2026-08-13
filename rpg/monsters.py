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
    gold_reward: tuple[int, int]  # (min, max)
    loot_pool: tuple[str, ...] = field(default_factory=tuple)
    loot_chance: float = 0.0


@dataclass(frozen=True)
class Dungeon:
    key: str
    name: str
    emoji: str
    min_level: int
    monsters: list[Monster]


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
}

# Monster stats/rewards scale with how far above a dungeon's min_level the
# player has climbed, so the same six dungeons stay a meaningful challenge
# (and stay worth running) all the way from level 1 to level 1500 instead of
# becoming trivial the moment a player outlevels them.
SCALE_PER_LEVEL = 0.05


def scale_factor(player_level: int, dungeon_min_level: int) -> float:
    return 1 + max(player_level - dungeon_min_level, 0) * SCALE_PER_LEVEL


def scaled_monster(monster: Monster, player_level: int, dungeon_min_level: int) -> dict:
    f = scale_factor(player_level, dungeon_min_level)
    lo, hi = monster.gold_reward
    return {
        "hp": max(1, int(monster.hp * f)),
        "atk": max(1, int(monster.atk * f)),
        "def": max(0, int(monster.defense * f)),
        "crit": monster.crit,
        "xp": max(1, int(monster.xp_reward * f)),
        "gold": (max(1, int(lo * f)), max(1, int(hi * f))),
    }

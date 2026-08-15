LEVELS_PER_PRESTIGE = 50
MAX_PRESTIGE = 29
MAX_LEVEL = (MAX_PRESTIGE + 1) * LEVELS_PER_PRESTIGE


def xp_for_level(level: int) -> int:
    return int(45 * level**1.42)


def apply_xp(level: int, xp: int, gained: int) -> tuple[int, int, int]:
    level = max(level, 1)
    xp += gained
    levels_gained = 0
    while level < MAX_LEVEL and xp >= xp_for_level(level):
        xp -= xp_for_level(level)
        level += 1
        levels_gained += 1
    if level >= MAX_LEVEL:
        level = MAX_LEVEL
        xp = 0
    return level, xp, levels_gained


def prestige_and_level(total_level: int) -> tuple[int, int]:
    prestige = (total_level - 1) // LEVELS_PER_PRESTIGE
    level_in_prestige = ((total_level - 1) % LEVELS_PER_PRESTIGE) + 1
    return prestige, level_in_prestige


PRESTIGE_STAT_BONUS_PER_TIER = 0.005


def prestige_stat_multiplier(total_level: int) -> float:
    prestige, _ = prestige_and_level(total_level)
    return 1 + prestige * PRESTIGE_STAT_BONUS_PER_TIER


TITLES = [
    (1001, "Eternal"),
    (751, "Transcendent"),
    (501, "Godlike"),
    (251, "Immortal"),
    (101, "Mythic"),
    (51, "Ascended"),
    (40, "Legend"),
    (25, "Champion"),
    (15, "Veteran"),
    (5, "Adventurer"),
    (1, "Novice"),
]


def title_for_level(level: int) -> str:
    for threshold, title in TITLES:
        if level >= threshold:
            return title
    return "Novice"

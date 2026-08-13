LEVELS_PER_PRESTIGE = 50
MAX_PRESTIGE = 29
MAX_LEVEL = (MAX_PRESTIGE + 1) * LEVELS_PER_PRESTIGE  # 1500


def xp_for_level(level: int) -> int:
    """XP required to advance from `level` to `level + 1`."""
    return int(50 * level**1.5)


def apply_xp(level: int, xp: int, gained: int) -> tuple[int, int, int]:
    """Applies `gained` XP, rolling over as many level-ups as it earns.

    Returns (new_level, new_xp, levels_gained)."""
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
    """Splits a total level (1-1500) into (prestige, level-within-prestige).

    Prestige 0 covers levels 1-50 and has no badge — level 51 is shown as
    "Prestige 1, Level 1", level 100 as "Prestige 1, Level 50", etc."""
    prestige = (total_level - 1) // LEVELS_PER_PRESTIGE
    level_in_prestige = ((total_level - 1) % LEVELS_PER_PRESTIGE) + 1
    return prestige, level_in_prestige


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

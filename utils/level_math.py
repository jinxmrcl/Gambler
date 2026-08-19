XP_PER_LEVEL_BASE = 20
XP_PER_LEVEL_GROWTH = 14
MAX_LEVEL = 150


def xp_for_level(level: int) -> int:
    if level <= 0:
        return 0
    level = min(level, MAX_LEVEL)
    return XP_PER_LEVEL_GROWTH * level * level + XP_PER_LEVEL_BASE * level


def level_from_total_xp(total_xp: int) -> tuple[int, int, int]:
    level = 0
    while level < MAX_LEVEL and xp_for_level(level + 1) <= total_xp:
        level += 1
    current_floor = xp_for_level(level)
    next_floor = xp_for_level(min(level + 1, MAX_LEVEL))
    return level, total_xp - current_floor, next_floor - current_floor

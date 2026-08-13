import random

# Rolled once per /dungeon run before the fight, so no two runs play out the
# same way even in the same dungeon against the same monster pool.
NORMAL = "normal"
TREASURE = "treasure"
AMBUSH = "ambush"
MERCHANT = "merchant"
CURSED = "cursed"

WEIGHTS = {
    NORMAL: 60,
    TREASURE: 15,
    AMBUSH: 10,
    MERCHANT: 8,
    CURSED: 7,
}


def roll_event() -> str:
    population = list(WEIGHTS.keys())
    weights = list(WEIGHTS.values())
    return random.choices(population, weights=weights, k=1)[0]

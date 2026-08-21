import os


OWNER_IDS = frozenset(
    int(owner_id)
    for owner_id in os.getenv("OWNER_IDS", "1305579806557208657,921005898846064711").split(",")
    if owner_id.strip().isdigit()
)


def is_owner_id(user_id: int) -> bool:
    return user_id in OWNER_IDS

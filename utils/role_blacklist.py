import os

import discord

_raw = os.getenv("BLACKLIST_ROLE_IDS", "1536063348318281748")
BLACKLIST_ROLE_IDS = {int(x) for x in _raw.split(",") if x.strip().isdigit()}


def is_blacklisted(member: discord.Member) -> bool:
    if not BLACKLIST_ROLE_IDS:
        return False
    return any(r.id in BLACKLIST_ROLE_IDS for r in member.roles)

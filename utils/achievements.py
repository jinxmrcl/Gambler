import datetime
from dataclasses import dataclass

import discord
from discord.ext import commands

from utils.economy import StaticView


@dataclass(frozen=True)
class Achievement:
    key: str
    label: str
    description: str
    metric: str
    threshold: int


ACHIEVEMENTS: list[Achievement] = [
    Achievement("net_worth_100k", "🪙 Comfortable", "Reach a net worth of 100,000", "net_worth", 100_000),
    Achievement("net_worth_500k", "💰 Wealthy", "Reach a net worth of 500,000", "net_worth", 500_000),
    Achievement("net_worth_2m", "🐋 Whale", "Reach a net worth of 2,000,000", "net_worth", 2_000_000),
    Achievement("wagered_50k", "🎲 Regular", "Wager a total of 50,000", "total_wagered", 50_000),
    Achievement("wagered_500k", "🎰 High Roller", "Wager a total of 500,000", "total_wagered", 500_000),
    Achievement("wagered_5m", "💎 Legend", "Wager a total of 5,000,000", "total_wagered", 5_000_000),
    Achievement("robs_5", "🦹 Thief", "Successfully rob 5 players", "robs_succeeded", 5),
    Achievement("robs_25", "🥷 Master Thief", "Successfully rob 25 players", "robs_succeeded", 25),
    Achievement("games_100", "🃏 Regular Player", "Play 100 games", "games_played", 100),
    Achievement("games_1000", "🎯 Veteran", "Play 1,000 games", "games_played", 1000),
    Achievement("streak_7", "🔥 On Fire", "Reach a 7-day daily streak", "daily_streak", 7),
    Achievement("streak_30", "⚡ Unstoppable", "Reach a 30-day daily streak", "daily_streak", 30),
]


async def gather_metrics(bot: commands.Bot, user_id: int) -> dict[str, int]:
    wallet = await bot.db.get_balance(user_id)
    bank_balance = await bot.db.get_bank_balance(user_id)
    stats = await bot.db.get_stats(user_id)
    streak = await bot.db.get_daily_streak(user_id)
    return {
        "net_worth": wallet + bank_balance,
        "total_wagered": stats["total_wagered"],
        "robs_succeeded": stats["robs_succeeded"],
        "games_played": stats["games_played"],
        "daily_streak": streak,
    }


async def check_and_announce(
    bot: commands.Bot,
    user: discord.abc.User,
    channel: discord.abc.Messageable | None,
    metrics: dict[str, int] | None = None,
) -> tuple[list[Achievement], list[Achievement]]:
    """Unlocks any newly-earned achievements for `user` and announces them in `channel`.

    Returns (all_unlocked, newly_unlocked).
    """
    if metrics is None:
        metrics = await gather_metrics(bot, user.id)

    unlocked_keys = await bot.db.get_unlocked_achievements(user.id)
    now = datetime.datetime.utcnow()

    newly_unlocked = []
    for achievement in ACHIEVEMENTS:
        if achievement.key in unlocked_keys:
            continue
        if metrics[achievement.metric] >= achievement.threshold:
            if await bot.db.unlock_achievement(user.id, achievement.key, now):
                newly_unlocked.append(achievement)
                unlocked_keys.add(achievement.key)

    if newly_unlocked and channel is not None:
        body = "\n".join(f"{a.label} — {a.description}" for a in newly_unlocked)
        view = StaticView("🏅 Achievement Unlocked!", f"{user.mention}\n{body}", color=discord.Color.gold())
        try:
            await channel.send(view=view)
        except discord.HTTPException:
            pass

    all_unlocked = [a for a in ACHIEVEMENTS if a.key in unlocked_keys]
    return all_unlocked, newly_unlocked

import discord
from discord import app_commands
from discord.ext import commands

from utils.economy import StaticView, fmt

DIVIDER = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"

NET_WORTH_TIERS = [(2_000_000, "🐋 Whale"), (500_000, "💰 Wealthy"), (100_000, "🪙 Comfortable")]
WAGERED_TIERS = [(5_000_000, "💎 Legend"), (500_000, "🎰 High Roller"), (50_000, "🎲 Regular")]
ROBBERY_TIERS = [(25, "🥷 Master Thief"), (5, "🦹 Thief")]
GAMES_TIERS = [(1000, "🎯 Veteran"), (100, "🃏 Regular Player")]
STREAK_TIERS = [(30, "⚡ Unstoppable"), (7, "🔥 On Fire")]


def _tier_badge(value: int, tiers: list[tuple[int, str]]) -> str | None:
    for threshold, label in tiers:
        if value >= threshold:
            return label
    return None


class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="profile", aliases=["stats"], description="Shows a player's statistics.")
    @app_commands.describe(user="Optional: view another user's statistics")
    async def profile(self, ctx: commands.Context, user: discord.User | None = None):
        target = user or ctx.author
        await self.bot.db.ensure_user(target.id, self.bot.starting_balance)

        wallet = await self.bot.db.get_balance(target.id)
        bank_balance = await self.bot.db.get_bank_balance(target.id)
        stats = await self.bot.db.get_stats(target.id)
        streak = await self.bot.db.get_daily_streak(target.id)

        net_worth = wallet + bank_balance
        net_profit = stats["total_won"] - stats["total_wagered"]
        rob_rate = (
            f"{stats['robs_succeeded'] / stats['robs_attempted'] * 100:.0f}%"
            if stats["robs_attempted"]
            else "—"
        )

        badges = [
            b
            for b in (
                _tier_badge(net_worth, NET_WORTH_TIERS),
                _tier_badge(stats["total_wagered"], WAGERED_TIERS),
                _tier_badge(stats["robs_succeeded"], ROBBERY_TIERS),
                _tier_badge(stats["games_played"], GAMES_TIERS),
                _tier_badge(streak, STREAK_TIERS),
            )
            if b
        ]

        lines = [
            f"**Net worth:** {fmt(net_worth)}  (Cash: {fmt(wallet)} • Bank: {fmt(bank_balance)})",
            f"🏅 **Badges:** {' · '.join(badges)}" if badges else "🏅 **Badges:** *none yet*",
            DIVIDER,
            "**🎮 Gaming**",
            f"Games played: {stats['games_played']:,}",
            f"Total wagered: {fmt(stats['total_wagered'])}",
            f"Total won: {fmt(stats['total_won'])}",
            f"Net profit: {'+' if net_profit >= 0 else ''}{fmt(net_profit)}",
            f"Biggest win: {fmt(stats['biggest_win'])}",
            "",
            "**🥷 Robbery**",
            f"Attempts: {stats['robs_attempted']:,}  •  Success rate: {rob_rate}",
            f"Times robbed: {stats['times_robbed']:,}x",
        ]
        if streak:
            lines.append(f"-# 🔥 {streak}-day daily streak")

        color = discord.Color.green() if net_profit > 0 else (discord.Color.red() if net_profit < 0 else None)
        view = StaticView(f"📊 {target.display_name}'s Profile", "\n".join(lines), color=color)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))

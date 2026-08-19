import discord
from discord import app_commands
from discord.ext import commands

from utils.achievements import ACHIEVEMENTS, check_and_announce
from utils.economy import StaticView, fmt

DIVIDER = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"


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

        metrics = {
            "net_worth": net_worth,
            "total_wagered": stats["total_wagered"],
            "robs_succeeded": stats["robs_succeeded"],
            "games_played": stats["games_played"],
            "daily_streak": streak,
        }
        if target == ctx.author:
            all_unlocked, _ = await check_and_announce(self.bot, target, ctx.channel, metrics)
        else:
            unlocked_keys = await self.bot.db.get_unlocked_achievements(target.id)
            all_unlocked = [a for a in ACHIEVEMENTS if a.key in unlocked_keys]
        badges = [a.label for a in all_unlocked]

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

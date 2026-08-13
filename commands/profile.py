import discord
from discord import app_commands
from discord.ext import commands

from utils.economy import StaticView, fmt


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

        net_profit = stats["total_won"] - stats["total_wagered"]
        rob_rate = (
            f"{stats['robs_succeeded'] / stats['robs_attempted'] * 100:.0f}%"
            if stats["robs_attempted"]
            else "—"
        )

        lines = [
            f"**Net worth:** {fmt(wallet + bank_balance)}  (Cash: {fmt(wallet)}, Bank: {fmt(bank_balance)})",
            "",
            f"**Games played:** {stats['games_played']}",
            f"**Total wagered:** {fmt(stats['total_wagered'])}",
            f"**Total won:** {fmt(stats['total_won'])}",
            f"**Net profit:** {'+' if net_profit >= 0 else ''}{fmt(net_profit)}",
            f"**Biggest win:** {fmt(stats['biggest_win'])}",
            "",
            f"**Rob attempts:** {stats['robs_attempted']} (success rate: {rob_rate})",
            f"**Times robbed:** {stats['times_robbed']}x",
        ]

        view = StaticView(f"📊 {target.display_name}'s Profile", "\n".join(lines))
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))

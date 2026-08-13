import datetime
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from database.db import InsufficientFunds
from utils.economy import StaticView, fmt

BOARD_TITLES = {
    "balance": "🏆 Leaderboard — Richest Players",
    "games_played": "🎲 Leaderboard — Most Games Played",
    "total_wagered": "💵 Leaderboard — Biggest Spenders",
    "biggest_win": "🎉 Leaderboard — Biggest Wins",
    "robs_succeeded": "🥷 Leaderboard — Most Successful Robberies",
}
MONEY_BOARDS = {"balance", "total_wagered", "biggest_win"}


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="balance", aliases=["bal"], description="Shows your balance.")
    @app_commands.describe(user="Optional: view another user's balance")
    async def balance(self, ctx: commands.Context, user: discord.User | None = None):
        target = user or ctx.author
        await self.bot.db.ensure_user(target.id, self.bot.starting_balance)
        bal = await self.bot.db.get_balance(target.id)

        view = StaticView("💰 Balance", f"**{target.display_name}** has {fmt(bal)}.")
        await ctx.send(view=view)

    @commands.hybrid_command(name="daily", description="Claim your daily bonus.")
    async def daily(self, ctx: commands.Context):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        last = await self.bot.db.get_last_daily(ctx.author.id)
        now = datetime.datetime.utcnow()

        if last is not None:
            elapsed = now - last
            if elapsed < datetime.timedelta(hours=24):
                remaining = datetime.timedelta(hours=24) - elapsed
                hours, rem = divmod(int(remaining.total_seconds()), 3600)
                minutes = rem // 60
                await ctx.send(
                    f"⏳ You already claimed your bonus. Next one in {hours}h {minutes}m."
                )
                return

        await self.bot.db.set_last_daily(ctx.author.id, now)
        new_balance = await self.bot.db.update_balance(ctx.author.id, self.bot.daily_amount)

        view = StaticView(
            "🎁 Daily Bonus",
            f"You received {fmt(self.bot.daily_amount)}!\nNew balance: {fmt(new_balance)}",
            color=discord.Color.green(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="leaderboard", aliases=["lb"], description="Shows a leaderboard.")
    @app_commands.describe(
        board="Which leaderboard to show (default: balance)",
        limit="Number of players (default: 10)",
    )
    async def leaderboard(
        self,
        ctx: commands.Context,
        board: Literal["balance", "games_played", "total_wagered", "biggest_win", "robs_succeeded"] = "balance",
        limit: app_commands.Range[int, 1, 25] = 10,
    ):
        rows = await self.bot.db.top_balances(limit) if board == "balance" else await self.bot.db.top_stat(board, limit)
        if not rows:
            await ctx.send("There's no data for this leaderboard yet.")
            return

        lines = []
        for i, (user_id, value) in enumerate(rows, start=1):
            member = ctx.guild.get_member(user_id) if ctx.guild else None
            name = member.display_name if member else f"<@{user_id}>"
            value_text = fmt(value) if board in MONEY_BOARDS else str(value)
            lines.append(f"**{i}.** {name} — {value_text}")

        view = StaticView(BOARD_TITLES[board], "\n".join(lines))
        await ctx.send(view=view)

    @commands.hybrid_command(name="pay", description="Transfer balance to another player.")
    @app_commands.describe(user="Recipient", amount="Amount")
    async def pay(self, ctx: commands.Context, user: discord.User, amount: app_commands.Range[int, 1]):
        if user.bot:
            await ctx.send("⚠️ You can't pay bots.")
            return
        if user.id == ctx.author.id:
            await ctx.send("⚠️ You can't send money to yourself.")
            return

        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        await self.bot.db.ensure_user(user.id, self.bot.starting_balance)

        try:
            await self.bot.db.update_balance(ctx.author.id, -amount)
        except InsufficientFunds:
            await ctx.send("⚠️ You don't have enough balance for this transfer.")
            return

        await self.bot.db.update_balance(user.id, amount)

        view = StaticView(
            "💸 Transfer",
            f"{ctx.author.mention} sent {fmt(amount)} to {user.mention}.",
            color=discord.Color.green(),
        )
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))

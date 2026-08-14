import random

import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, StaticView, fmt, resolve_bet

RTP = 1 - HOUSE_EDGE
MIN_TARGET = 1.01
MAX_TARGET = 1_000.0


def roll_crash_point() -> float:
    r = random.random()
    crash_point = RTP / (1 - r)
    return max(1.0, crash_point)


class Limbo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="limbo", description="Set a target multiplier and hope the result reaches it.")
    @app_commands.describe(
        bet="Bet (a number, 'half', 'all', or e.g. '50%')",
        target="Target multiplier (min. 1.01x)",
    )
    @game_enabled("limbo")
    async def limbo(
        self,
        ctx: commands.Context,
        bet: str,
        target: app_commands.Range[float, MIN_TARGET, MAX_TARGET],
    ):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        crash_point = roll_crash_point()
        won = crash_point >= target
        payout = int(amount * target) if won else 0
        if payout:
            await self.bot.db.update_balance(ctx.author.id, payout)
        await self.bot.db.record_game_result(ctx.author.id, amount, payout)

        lines = [
            f"**Bet:** {fmt(amount)}  •  **Target:** {target:g}x  •  **Result:** {crash_point:.2f}x",
        ]
        if won:
            lines.append(f"🎉 **You won!** Payout: {fmt(payout)}")
        else:
            lines.append(f"😢 **You lost.** Didn't reach {crash_point:.2f}x.")

        view = StaticView("🚀 Limbo", "\n".join(lines), color=discord.Color.green() if won else discord.Color.red())
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Limbo(bot))

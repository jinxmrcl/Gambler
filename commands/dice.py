import random
from math import comb

import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, StaticView, fmt, resolve_bet

RTP = 1 - HOUSE_EDGE


def probability_of_sum(total: int) -> float:
    ways = sum(1 for a in range(1, 7) for b in range(1, 7) if a + b == total)
    return ways / 36


def multiplier_for(total: int) -> float:
    return round((RTP / probability_of_sum(total)), 2)


class Dice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="dice", description="Predict the sum of two dice.")
    @app_commands.describe(
        bet="Bet (a number, 'half', 'all', or e.g. '50%')",
        prediction="Predicted sum of the two dice (2-12)",
    )
    @game_enabled("dice")
    async def dice(self, ctx: commands.Context, bet: str, prediction: commands.Range[int, 2, 12]):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        d1, d2 = random.randint(1, 6), random.randint(1, 6)
        total = d1 + d2
        won = total == prediction
        multiplier = multiplier_for(prediction)
        payout = int(amount * multiplier) if won else 0
        if payout:
            await self.bot.db.update_balance(ctx.author.id, payout)
        await self.bot.db.record_game_result(ctx.author.id, amount, payout)

        lines = [
            f"## 🎲 {d1} + 🎲 {d2} = {total}",
            f"**Bet:** {fmt(amount)}  •  **Prediction:** {prediction}  •  **Multiplier:** {multiplier:g}x",
        ]
        if won:
            lines.append(f"🎉 **You won!** Payout: {fmt(payout)}")
        else:
            lines.append("😢 You lost.")

        view = StaticView("🎲 Dice", "\n".join(lines), color=discord.Color.green() if won else discord.Color.red())
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Dice(bot))

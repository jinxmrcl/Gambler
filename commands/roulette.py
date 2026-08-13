import random

import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import StaticView, fmt, resolve_bet

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}


def color_of(number: int) -> str:
    if number == 0:
        return "green"
    return "red" if number in RED_NUMBERS else "black"


class Roulette(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="roulette", description="Bet on a number, color, or even/odd.")
    @app_commands.describe(
        bet="Bet (a number, 'half', 'all', or e.g. '50%')",
        choice="A number (0-36), 'red', 'black', 'even', or 'odd'",
    )
    @game_enabled("roulette")
    async def roulette(self, ctx: commands.Context, bet: str, choice: str):
        choice = choice.strip().lower()
        if choice not in ("red", "black", "even", "odd") and not (choice.isdigit() and 0 <= int(choice) <= 36):
            await ctx.send("⚠️ Invalid choice. Use a number from 0-36, 'red', 'black', 'even', or 'odd'.")
            return

        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        result = random.randint(0, 36)
        color = color_of(result)

        if choice.isdigit():
            won = int(choice) == result
            multiplier = 36.0
        elif choice in ("red", "black"):
            won = choice == color
            multiplier = 2.0
        else:
            won = result != 0 and (result % 2 == 0) == (choice == "even")
            multiplier = 2.0

        payout = int(amount * multiplier) if won else 0
        if payout:
            await self.bot.db.update_balance(ctx.author.id, payout)
        await self.bot.db.record_game_result(ctx.author.id, amount, payout)

        emoji = {"red": "🔴", "black": "⚫", "green": "🟢"}[color]
        lines = [
            f"## {emoji} {result}",
            f"**Bet:** {fmt(amount)}  •  **Choice:** {choice}",
        ]
        if won:
            lines.append(f"🎉 **You won!** {multiplier:g}x → Payout {fmt(payout)}")
        else:
            lines.append("😢 You lost.")

        view = StaticView("🎡 Roulette", "\n".join(lines), color=discord.Color.green() if won else discord.Color.red())
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Roulette(bot))

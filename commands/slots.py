import random

import discord
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, StaticView, fmt, resolve_bet

RTP = 1 - HOUSE_EDGE

SYMBOLS = [
    ("🍒", 30, 3),
    ("🍋", 25, 4),
    ("🍇", 20, 6),
    ("🔔", 15, 10),
    ("💎", 7, 25),
    ("7️⃣", 3, 50),
]

_total_weight = sum(weight for _, weight, _ in SYMBOLS)
_expected_raw = sum(((weight / _total_weight) ** 3) * base_mult for _, weight, base_mult in SYMBOLS)
_scale = RTP / _expected_raw
PAYOUTS = {emoji: round(_scale * base_mult, 2) for emoji, _, base_mult in SYMBOLS}
_POPULATION = [emoji for emoji, _, _ in SYMBOLS]
_WEIGHTS = [weight for _, weight, _ in SYMBOLS]


def spin() -> list[str]:
    return random.choices(_POPULATION, weights=_WEIGHTS, k=3)


class Slots(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="slots", description="Spin the slot machine.")
    @game_enabled("slots")
    async def slots(self, ctx: commands.Context, bet: str):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        reels = spin()
        won = reels[0] == reels[1] == reels[2]
        multiplier = PAYOUTS[reels[0]] if won else 0.0
        payout = int(amount * multiplier)
        if payout:
            await self.bot.db.update_balance(ctx.author.id, payout)
        await self.bot.db.record_game_result(ctx.author.id, amount, payout)

        lines = [
            f"## {' '.join(reels)}",
            f"**Bet:** {fmt(amount)}",
        ]
        if won:
            lines.append(f"🎉 **Jackpot!** {multiplier:g}x → Payout {fmt(payout)}")
        else:
            lines.append("😢 No match — better luck next spin.")

        view = StaticView("🎰 Slots", "\n".join(lines), color=discord.Color.green() if won else discord.Color.red())
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Slots(bot))

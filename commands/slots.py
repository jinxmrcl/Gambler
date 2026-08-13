import random

import discord
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, StaticView, fmt, resolve_bet

RTP = 1 - HOUSE_EDGE
PARTIAL_FRACTION = 0.2  # a 2-of-3 match pays this fraction of the full 3-of-a-kind multiplier

SYMBOLS = [
    ("🍒", 30, 3),
    ("🍋", 25, 4),
    ("🍇", 20, 6),
    ("🔔", 15, 10),
    ("💎", 7, 25),
    ("7️⃣", 3, 50),
]

_total_weight = sum(weight for _, weight, _ in SYMBOLS)
_probs = {emoji: weight / _total_weight for emoji, weight, _ in SYMBOLS}

# A 3-of-a-kind requiring all reels to match is rare (~5% of spins here), which
# makes for a very swingy game even at a fair RTP. Paying out a fraction of the
# multiplier on a 2-of-3 partial match keeps the same overall RTP but spreads it
# across far more frequent, smaller wins (~55% of spins) alongside the rarer jackpot.
_expected_raw = sum(
    (_probs[emoji] ** 3) * base_mult
    + PARTIAL_FRACTION * (3 * _probs[emoji] ** 2 * (1 - _probs[emoji])) * base_mult
    for emoji, _, base_mult in SYMBOLS
)
_scale = RTP / _expected_raw
FULL_PAYOUTS = {emoji: round(_scale * base_mult, 2) for emoji, _, base_mult in SYMBOLS}
PARTIAL_PAYOUTS = {emoji: round(FULL_PAYOUTS[emoji] * PARTIAL_FRACTION, 2) for emoji, _, _ in SYMBOLS}
_POPULATION = [emoji for emoji, _, _ in SYMBOLS]
_WEIGHTS = [weight for _, weight, _ in SYMBOLS]


def spin() -> list[str]:
    return random.choices(_POPULATION, weights=_WEIGHTS, k=3)


def resolve_spin(reels: list[str]) -> tuple[float, str]:
    """Returns (multiplier, result_kind) where result_kind is 'jackpot', 'partial', or 'none'."""
    if reels[0] == reels[1] == reels[2]:
        return FULL_PAYOUTS[reels[0]], "jackpot"

    counts: dict[str, int] = {}
    for symbol in reels:
        counts[symbol] = counts.get(symbol, 0) + 1
    for symbol, count in counts.items():
        if count == 2:
            return PARTIAL_PAYOUTS[symbol], "partial"

    return 0.0, "none"


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
        multiplier, kind = resolve_spin(reels)
        payout = int(amount * multiplier)
        if payout:
            await self.bot.db.update_balance(ctx.author.id, payout)
        await self.bot.db.record_game_result(ctx.author.id, amount, payout)

        lines = [
            f"## {' '.join(reels)}",
            f"**Bet:** {fmt(amount)}",
        ]
        if kind == "jackpot":
            lines.append(f"🎉 **Jackpot!** {multiplier:g}x → Payout {fmt(payout)}")
        elif kind == "partial":
            lines.append(f"✨ **Match!** {multiplier:g}x → Payout {fmt(payout)}")
        else:
            lines.append("😢 No match — better luck next spin.")

        won = kind != "none"
        view = StaticView("🎰 Slots", "\n".join(lines), color=discord.Color.green() if won else discord.Color.red())
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Slots(bot))
